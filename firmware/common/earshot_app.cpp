#include <Arduino.h>
#include <NimBLEDevice.h>
#include <WiFi.h>
#include "earshot_app.h"
#include "earshot_proto.h"
#include "adpcm.h"
#include "tap_detect.h"

// ---------------- config ----------------
#ifndef ES_WIFI_FALLBACK
#define ES_WIFI_FALLBACK 1          // soft AP + TCP when no BLE central is connected
#endif
#define RESEND_FRAMES 150           // 3 s of audio kept in RAM (PSRAM when present) for resend after a short drop
#define TAP_QUEUE 16
#define TAP_RESEND_MS 500

static EsHal *hal;
static es_sm sm;
static es_tap_detector det;
static es_adpcm_state adpcm;
static uint16_t audio_seq = 0, tap_seq = 0, state_seq = 0;
static uint32_t mute_until = 0;
static int64_t clock_offset_ms = 0;   // iPad epoch - clip ms (kept for reference / logs)

// audio resend ring (encoded packets). Lives in RAM only, never flash.
static uint8_t (*ring)[ES_MAX_PACKET] = nullptr;
static uint32_t ring_clip[RESEND_FRAMES];
static int ring_head = 0, ring_count = 0;
static uint32_t link_lost_at = 0;
static bool resend_pending = false;

struct PendingTap { bool used; uint16_t seq; uint8_t pkt[ES_HDR_SIZE + ES_TAP_PAYLOAD]; uint32_t last_sent; };
static PendingTap taps[TAP_QUEUE];

// ---------------- transport ----------------
static NimBLECharacteristic *chAudio, *chTap, *chState, *chClock, *chAck;
static volatile bool ble_connected = false;
static WiFiServer *tcp = nullptr;
static WiFiClient tcpClient;
static uint8_t rxbuf[64]; static int rxlen = 0;

static void handle_incoming(const uint8_t *p, int len);

static bool link_up() { return ble_connected || (tcpClient && tcpClient.connected()); }

static void send_packet(NimBLECharacteristic *ch, const uint8_t *p, size_t len) {
    if (ble_connected && ch) { ch->setValue(p, len); ch->notify(); }
    if (tcpClient && tcpClient.connected()) {
        uint8_t hdr[2] = {(uint8_t)(len & 0xFF), (uint8_t)(len >> 8)};
        tcpClient.write(hdr, 2); tcpClient.write(p, len);
    }
}

class ServerCB : public NimBLEServerCallbacks {
    void onConnect(NimBLEServer *s, ble_gap_conn_desc *desc) override {
        ble_connected = true;
        // 15 ms interval (iOS minimum), no latency, 4 s supervision timeout
        s->updateConnParams(desc->conn_handle, 12, 12, 0, 400);
        s->setDataLen(desc->conn_handle, 251);
        ble_gap_set_prefered_le_phy(desc->conn_handle, BLE_GAP_LE_PHY_2M_MASK, BLE_GAP_LE_PHY_2M_MASK, BLE_GAP_LE_PHY_CODED_ANY);
        if (link_lost_at) resend_pending = true;
    }
    void onDisconnect(NimBLEServer *s) override {
        ble_connected = false; link_lost_at = millis();
        NimBLEDevice::startAdvertising();
    }
};
class WriteCB : public NimBLECharacteristicCallbacks {
    void onWrite(NimBLECharacteristic *c) override {
        std::string v = c->getValue();
        handle_incoming((const uint8_t *)v.data(), (int)v.size());
    }
};
static WriteCB writeCB;

static void ble_begin() {
    NimBLEDevice::init("Earshot");
    NimBLEDevice::setMTU(247);
    NimBLEDevice::setPower(ESP_PWR_LVL_P9);
    // encrypted pairing (Just Works, LE Secure Connections, bonded)
    NimBLEDevice::setSecurityAuth(true, false, true);
    NimBLEDevice::setSecurityIOCap(BLE_HS_IO_NO_INPUT_OUTPUT);
    NimBLEServer *srv = NimBLEDevice::createServer();
    srv->setCallbacks(new ServerCB());
    NimBLEService *svc = srv->createService(ES_GATT_SERVICE);
    chAudio = svc->createCharacteristic(ES_GATT_AUDIO, NIMBLE_PROPERTY::NOTIFY | NIMBLE_PROPERTY::READ_ENC);
    chTap   = svc->createCharacteristic(ES_GATT_TAP,   NIMBLE_PROPERTY::NOTIFY | NIMBLE_PROPERTY::READ_ENC);
    chState = svc->createCharacteristic(ES_GATT_STATE, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::READ_ENC | NIMBLE_PROPERTY::NOTIFY |
                                                       NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_ENC);
    chClock = svc->createCharacteristic(ES_GATT_CLOCK, NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_ENC);
    chAck   = svc->createCharacteristic(ES_GATT_ACK,   NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_NR | NIMBLE_PROPERTY::WRITE_ENC);
    chState->setCallbacks(&writeCB); chClock->setCallbacks(&writeCB); chAck->setCallbacks(&writeCB);
    svc->start();
    NimBLEAdvertising *adv = NimBLEDevice::getAdvertising();
    adv->addServiceUUID(ES_GATT_SERVICE);
    adv->setScanResponse(true);
    adv->start();
}

static void wifi_begin() {
#if ES_WIFI_FALLBACK
    char ssid[24];
    uint64_t mac = ESP.getEfuseMac();
    snprintf(ssid, sizeof ssid, "Earshot-%04X", (unsigned)(mac & 0xFFFF));
    WiFi.mode(WIFI_AP);
    WiFi.softAP(ssid, "earshot-demo");   // WPA2; change before real use
    tcp = new WiFiServer(ES_WIFI_PORT);
    tcp->begin();
    tcp->setNoDelay(true);
#endif
}

static void wifi_poll() {
    if (!tcp) return;
    if (!tcpClient || !tcpClient.connected()) {
        WiFiClient c = tcp->available();
        if (c) { tcpClient = c; tcpClient.setNoDelay(true); rxlen = 0; if (link_lost_at) resend_pending = true; }
        return;
    }
    while (tcpClient.available()) {
        if (rxlen < (int)sizeof rxbuf) rxbuf[rxlen++] = tcpClient.read(); else { rxlen = 0; break; }
        if (rxlen >= 2) {
            int need = rxbuf[0] | (rxbuf[1] << 8);
            if (need > (int)sizeof rxbuf - 2) { rxlen = 0; continue; }
            if (rxlen == need + 2) { handle_incoming(rxbuf + 2, need); rxlen = 0; }
        }
    }
}

// ---------------- state + taps ----------------
static void send_state() {
    uint8_t p[ES_HDR_SIZE + 2];
    uint8_t flags = hal->powerFlags() | (millis() < mute_until ? ES_FLAG_TONE : 0);
    es_state_packet(p, state_seq++, millis(), sm.state, flags);
    if (chState) chState->setValue(p, sizeof p);
    send_packet(chState, p, sizeof p);
}

static void queue_tap(uint8_t gesture, uint8_t source, uint32_t press_ms) {
    for (auto &t : taps) if (!t.used) {
        t.used = true; t.seq = tap_seq++;
        es_tap_packet(t.pkt, t.seq, millis(), gesture, source, press_ms);
        t.last_sent = 0;
        return;
    }
}

static void resend_taps() {
    uint32_t now = millis();
    if (!link_up()) return;
    for (auto &t : taps) if (t.used && (t.last_sent == 0 || now - t.last_sent > TAP_RESEND_MS)) {
        send_packet(chTap, t.pkt, sizeof t.pkt); t.last_sent = now;
    }
}

static void clear_audio() {
    ring_head = ring_count = 0;
    if (ring) memset(ring, 0, (size_t)RESEND_FRAMES * ES_MAX_PACKET);
    adpcm.predictor = 0; adpcm.index = 0;
}

static void apply(const es_action &a) {
    if (a.tone != ES_TONE_NONE) {
        uint32_t dur = hal->feedback(a.tone);
        mute_until = millis() + dur + 200;
        es_tap_mute(&det, millis() + dur);
    }
    if (a.clear_buffers) clear_audio();
    if (a.emit_tap) queue_tap(a.tap_gesture, a.tap_source, a.tap_press_ms);
    if (a.state_changed) { hal->showState(sm.state); send_state(); }
    if (a.log_refusal) Serial.printf("[earshot] consent refused (total %u) — nothing captured\n", (unsigned)sm.refusals);
}

static void handle_incoming(const uint8_t *p, int len) {
    if (len < ES_HDR_SIZE) return;
    switch (p[0]) {
    case ES_PKT_ACK:
        if (len >= ES_HDR_SIZE + 2) { uint16_t s = es_get16(p + 7); for (auto &t : taps) if (t.used && t.seq == s) t.used = false; }
        break;
    case ES_PKT_CLOCK:
        if (len >= ES_HDR_SIZE + 8) clock_offset_ms = (int64_t)es_get64(p + 7) - (int64_t)millis();
        break;
    case ES_PKT_STATE:
        if (len >= ES_HDR_SIZE + 1 && p[7] == ES_STATE_OFF) apply(es_sm_input(&sm, ES_IN_FORCE_OFF, 0, millis()));
        if (len >= ES_HDR_SIZE + 10) {   // acoustic tap tuning
            det.cfg.knock_threshold = es_get16(p + 9); det.cfg.min_gap_ms = es_get16(p + 11);
            det.cfg.window_ms = es_get16(p + 13); det.cfg.snap_threshold = es_get16(p + 15);
        }
        break;
    }
}

// ---------------- main ----------------
void earshot_setup(EsHal *h, bool acoustic_consent) {
    hal = h;
    Serial.begin(115200);
    hal->begin();
    es_sm_init(&sm, acoustic_consent);
    es_tap_cfg cfg; es_tap_default_cfg(&cfg); es_tap_init(&det, &cfg, ES_SAMPLE_RATE);
    size_t bytes = (size_t)RESEND_FRAMES * ES_MAX_PACKET;
    ring = (uint8_t (*)[ES_MAX_PACKET])(psramFound() ? ps_malloc(bytes) : malloc(bytes));
    clear_audio();
    ble_begin();
    wifi_begin();
    hal->showState(sm.state);
    Serial.printf("[earshot] %s ready, PSRAM %s\n", hal->name(), psramFound() ? "yes" : "no");
}

void earshot_loop() {
    static int16_t pcm[ES_FRAME_SAMPLES];
    int n = hal->readMic(pcm, ES_FRAME_SAMPLES);     // paces the loop at 20 ms
    uint32_t now = millis();
    es_action a;
    if (hal->hasButton()) {
        if (es_sm_button(&sm, hal->buttonPressed(), now, &a)) apply(a);
        if (es_sm_tick(&sm, now, &a)) apply(a);
    }
    if (n == ES_FRAME_SAMPLES) {
        bool muted = now < mute_until;
        if (muted) memset(pcm, 0, sizeof pcm);   // tones never reach the audio stream
        // acoustic taps from the raw signal, before encoding
        es_tap_event e = es_tap_process(&det, pcm, n, now - 20);
        if (e.kind == ES_TAPEV_DOUBLE) apply(es_sm_input(&sm, ES_IN_DOUBLE, e.source, e.first_ms));
        if (e.kind == ES_TAPEV_TRIPLE) apply(es_sm_input(&sm, ES_IN_TRIPLE, e.source, e.first_ms));
        // consent gate: audio leaves the clip only while LISTENING
        if (es_sm_audio_allowed(&sm)) {
            uint8_t *pkt = ring[ring_head];
            es_header(pkt, ES_PKT_AUDIO, audio_seq++, now);
            es_adpcm_encode_block(pcm, n, &adpcm, pkt + ES_HDR_SIZE);
            ring_clip[ring_head] = now;
            ring_head = (ring_head + 1) % RESEND_FRAMES;
            if (ring_count < RESEND_FRAMES) ring_count++;
            if (resend_pending && link_up()) {
                // resend frames captured since shortly before the drop; the iPad dedupes by seq
                for (int i = ring_count - 1; i >= 1; i--) {
                    int k = (ring_head - 1 - i + RESEND_FRAMES) % RESEND_FRAMES;
                    if (ring_clip[k] + 500 >= link_lost_at) send_packet(chAudio, ring[k], ES_HDR_SIZE + ES_AUDIO_PAYLOAD);
                }
                resend_pending = false; link_lost_at = 0;
            }
            send_packet(chAudio, pkt, ES_HDR_SIZE + ES_AUDIO_PAYLOAD);
        }
    }
    resend_taps();
    wifi_poll();
    static uint32_t last_state = 0;
    if (now - last_state > 2000) { last_state = now; send_state(); }
}
