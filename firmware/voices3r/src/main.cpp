// Atom VoiceS3R: ES8311 codec (mic + DAC) over I2S/I2C, NS4150B amp, button G41.
// Pins from the M5Stack C126 pin map. Audio is never written to flash.
#include <Arduino.h>
#include <Wire.h>
#include <driver/i2s.h>
#include "earshot_app.h"
#include "earshot_proto.h"
#if CONSENT_LIGHT
#include <Adafruit_NeoPixel.h>
static Adafruit_NeoPixel px(1, 2, NEO_GRB + NEO_KHZ800);   // Grove G2
#endif

#define PIN_I2C_SDA 45
#define PIN_I2C_SCL 0
#define PIN_I2S_MCLK 11
#define PIN_I2S_BCLK 17
#define PIN_I2S_WS 3
#define PIN_I2S_DIN 48     // ES8311 DOUT -> ESP32 data in (mic)
#define PIN_I2S_DOUT 4     // ESP32 data out -> ES8311 DIN (speaker)
#define PIN_AMP_EN 18
#define PIN_BUTTON 41
#define ES8311_ADDR 0x18

static void es_w(uint8_t reg, uint8_t v) {
    Wire.beginTransmission(ES8311_ADDR); Wire.write(reg); Wire.write(v); Wire.endTransmission();
}

// ES8311 init for MCLK = 256 * 16 kHz = 4.096 MHz, codec as I2S slave,
// 16-bit Philips I2S, analog mic. Sequence follows Espressif's es8311 driver.
static bool es8311_init() {
    Wire.beginTransmission(ES8311_ADDR);
    if (Wire.endTransmission() != 0) return false;
    es_w(0x01, 0x30); es_w(0x02, 0x00); es_w(0x03, 0x10); es_w(0x16, 0x24); es_w(0x04, 0x10); es_w(0x05, 0x00);
    es_w(0x0B, 0x00); es_w(0x0C, 0x00); es_w(0x10, 0x1F); es_w(0x11, 0x7F);
    es_w(0x00, 0x80);                    // power on, slave mode
    es_w(0x01, 0x3F);                    // clocks on, MCLK from pin
    // clock coefficients for 4.096 MHz / 16 kHz
    es_w(0x02, 0x00); es_w(0x05, 0x00); es_w(0x03, 0x10); es_w(0x04, 0x10);
    es_w(0x07, 0x00); es_w(0x08, 0xFF); es_w(0x06, 0x03);
    es_w(0x13, 0x10); es_w(0x1B, 0x0A); es_w(0x1C, 0x6A);
    es_w(0x09, 0x0C); es_w(0x0A, 0x0C);  // SDP in/out: I2S, 16-bit
    es_w(0x17, 0xBF);                    // ADC volume
    es_w(0x0E, 0x02); es_w(0x12, 0x00);
    es_w(0x14, 0x1A);                    // analog mic, PGA
    es_w(0x0D, 0x01); es_w(0x15, 0x40); es_w(0x37, 0x08); es_w(0x45, 0x00);
    es_w(0x16, 0x04);                    // mic gain (0..7 -> 0..42 dB)
    es_w(0x32, 0xBF);                    // DAC volume (~0 dB)
    return true;
}

class VoiceS3RHal : public EsHal {
public:
    bool begin() override {
        pinMode(PIN_BUTTON, INPUT_PULLUP);
        pinMode(PIN_AMP_EN, OUTPUT); digitalWrite(PIN_AMP_EN, LOW);
        Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 400000);
        i2s_config_t cfg = {};
        cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX | I2S_MODE_RX);
        cfg.sample_rate = ES_SAMPLE_RATE;
        cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
        cfg.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;
        cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
        cfg.dma_buf_count = 8; cfg.dma_buf_len = ES_FRAME_SAMPLES;
        cfg.use_apll = false; cfg.tx_desc_auto_clear = true;
        cfg.mclk_multiple = I2S_MCLK_MULTIPLE_256;
        i2s_driver_install(I2S_NUM_0, &cfg, 0, nullptr);
        i2s_pin_config_t pins = {};
        pins.mck_io_num = PIN_I2S_MCLK; pins.bck_io_num = PIN_I2S_BCLK; pins.ws_io_num = PIN_I2S_WS;
        pins.data_out_num = PIN_I2S_DOUT; pins.data_in_num = PIN_I2S_DIN;
        i2s_set_pin(I2S_NUM_0, &pins);
        delay(20);
        bool ok = es8311_init();
        if (!ok) Serial.println("[earshot] ES8311 not found on I2C 0x18");
#if CONSENT_LIGHT
        px.begin(); px.setBrightness(30);
#endif
        return ok;
    }

    int readMic(int16_t *buf, int n) override {
        size_t got = 0;
        i2s_read(I2S_NUM_0, buf, n * sizeof(int16_t), &got, portMAX_DELAY);
        return (int)(got / sizeof(int16_t));
    }

    // Short distinct tones through the 1 W speaker. The app layer mutes the
    // mic for the tone's duration + 200 ms.
    uint32_t feedback(es_tone t) override {
        struct Seg { int hz; int ms; };
        Seg s[2] = {{0, 0}, {0, 0}};
        switch (t) {
        case ES_TONE_RISING:  s[0] = {660, 120}; s[1] = {990, 120}; break;
        case ES_TONE_HIGH:    s[0] = {1320, 150}; break;
        case ES_TONE_LOW:     s[0] = {330, 300}; break;
        case ES_TONE_CLICK:   s[0] = {2000, 25}; break;
        case ES_TONE_FALLING: s[0] = {990, 120}; s[1] = {660, 120}; break;
        default: return 0;
        }
        digitalWrite(PIN_AMP_EN, HIGH);
        uint32_t total = 0;
        static int16_t buf[ES_FRAME_SAMPLES];
        for (auto &seg : s) {
            if (!seg.ms) continue;
            int n = ES_SAMPLE_RATE * seg.ms / 1000;
            for (int i = 0; i < n; i += ES_FRAME_SAMPLES) {
                int m = min(ES_FRAME_SAMPLES, n - i);
                for (int k = 0; k < m; k++) {
                    float env = min(1.0f, min((i + k) / 160.0f, (n - i - k) / 160.0f));   // 10 ms fade
                    buf[k] = (int16_t)(9000 * env * sinf(2 * PI * seg.hz * (i + k) / ES_SAMPLE_RATE));
                }
                size_t w; i2s_write(I2S_NUM_0, buf, m * sizeof(int16_t), &w, portMAX_DELAY);
            }
            total += seg.ms;
        }
        digitalWrite(PIN_AMP_EN, LOW);
        return total;
    }

    bool hasButton() override { return true; }
    bool buttonPressed() override { return digitalRead(PIN_BUTTON) == LOW; }

    void showState(uint8_t st) override {
#if CONSENT_LIGHT
        uint32_t c = st == ES_STATE_LISTENING ? px.Color(255, 0, 0) : st == ES_STATE_ASKING ? px.Color(255, 120, 0) : 0;
        px.setPixelColor(0, c); px.show();
#else
        (void)st;
#endif
    }
    uint8_t powerFlags() override { return ES_FLAG_USB; }   // no battery: USB power bank
    const char *name() override { return "Atom VoiceS3R"; }
};

static VoiceS3RHal board;
void setup() { earshot_setup(&board, false); }
void loop() { earshot_loop(); }
