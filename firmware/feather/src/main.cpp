// Feather ESP32-S3 fallback. No button: knocks drive everything
// (triple = start / no / stop, double = yes / mark). Vibration replaces tones.
// Silkscreen -> GPIO (Adafruit Feather ESP32-S3 pinout; verify on your board):
//   D10 = GPIO10 (I2S SCK), D11 = GPIO11 (I2S WS), D12 = GPIO12 (I2S SD), D9 = GPIO9 (motor),
//   I2C power = GPIO7 (must be HIGH for the STEMMA/OLED pull-ups).
#include <Arduino.h>
#include <Wire.h>
#include <driver/i2s.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "earshot_app.h"
#include "earshot_proto.h"

#define PIN_SCK 10
#define PIN_WS 11
#define PIN_SD 12
#define PIN_MOTOR 9
#define PIN_I2C_POWER 7

static Adafruit_SSD1306 oled(128, 32, &Wire, -1);
static bool oled_ok = false;

class FeatherHal : public EsHal {
public:
    bool begin() override {
        pinMode(PIN_MOTOR, OUTPUT); digitalWrite(PIN_MOTOR, LOW);
        pinMode(PIN_I2C_POWER, OUTPUT); digitalWrite(PIN_I2C_POWER, HIGH); delay(10);
        Wire.begin();
        oled_ok = oled.begin(SSD1306_SWITCHCAPVCC, 0x3C);
        i2s_config_t cfg = {};
        cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
        cfg.sample_rate = ES_SAMPLE_RATE;
        cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;           // INMP441 sends 24-bit in 32-bit slots
        cfg.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;             // L/R tied to GND
        cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
        cfg.dma_buf_count = 8; cfg.dma_buf_len = ES_FRAME_SAMPLES;
        i2s_driver_install(I2S_NUM_0, &cfg, 0, nullptr);
        i2s_pin_config_t pins = {};
        pins.mck_io_num = I2S_PIN_NO_CHANGE; pins.bck_io_num = PIN_SCK; pins.ws_io_num = PIN_WS;
        pins.data_out_num = I2S_PIN_NO_CHANGE; pins.data_in_num = PIN_SD;
        i2s_set_pin(I2S_NUM_0, &pins);
        return true;
    }
    int readMic(int16_t *buf, int n) override {
        static int32_t raw[ES_FRAME_SAMPLES];
        size_t got = 0;
        i2s_read(I2S_NUM_0, raw, n * sizeof(int32_t), &got, portMAX_DELAY);
        int m = (int)(got / sizeof(int32_t));
        for (int i = 0; i < m; i++) buf[i] = (int16_t)(raw[i] >> 14);   // 24-bit -> 16-bit with ~6 dB gain
        return m;
    }
    uint32_t feedback(es_tone t) override {
        // vibration patterns: number of pulses
        int pulses = t == ES_TONE_RISING ? 2 : t == ES_TONE_HIGH ? 1 : t == ES_TONE_LOW ? 3 : t == ES_TONE_CLICK ? 1 : t == ES_TONE_FALLING ? 2 : 0;
        int on = t == ES_TONE_CLICK ? 40 : 120;
        for (int i = 0; i < pulses; i++) { digitalWrite(PIN_MOTOR, HIGH); delay(on); digitalWrite(PIN_MOTOR, LOW); delay(80); }
        return pulses * (on + 80);
    }
    bool hasButton() override { return false; }
    bool buttonPressed() override { return false; }
    void showState(uint8_t st) override {
        if (!oled_ok) return;
        static const char *names[] = {"OFF", "ASKING", "LISTENING", "REFUSED"};
        oled.clearDisplay(); oled.setTextColor(SSD1306_WHITE);
        oled.setTextSize(2); oled.setCursor(0, 0); oled.print(names[st & 3]);
        oled.setTextSize(1); oled.setCursor(0, 22);
        oled.print(st == ES_STATE_OFF ? "knock x3 to start" : st == ES_STATE_ASKING ? "x2 yes / x3 no" : st == ES_STATE_LISTENING ? "x2 mark / x3 stop" : "");
        oled.display();
    }
    uint8_t powerFlags() override { return 0; }   // LiPo; add a battery monitor to set ES_FLAG_BATT_LOW
    const char *name() override { return "Feather ESP32-S3"; }
};

static FeatherHal board;
void setup() { earshot_setup(&board, true); }
void loop() { earshot_loop(); }
