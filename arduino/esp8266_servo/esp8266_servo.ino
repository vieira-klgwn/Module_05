#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <Servo.h>
#include <ArduinoJson.h>

// =========================
// WiFi
// =========================
static const char* WIFI_SSID = "God-Only-s";
static const char* WIFI_PASS = "Arlene+250";

// =========================
// MQTT
// =========================
static const char* MQTT_HOST = "157.173.101.159";
static const uint16_t MQTT_PORT = 1883;
static const char* TEAM_ID = "Winners";

String topicMovement;

WiFiClient espClient;
PubSubClient mqtt(espClient);
Servo servo;

// =========================
// Servo config
// =========================
static const uint8_t SERVO_PIN = D4;
static const int SERVO_MIN = 10;
static const int SERVO_MAX = 170;
static const int SERVO_CENTER = 90;

static const bool INVERT_DIRECTION = true;

// Tracking tuning
static const int TRACK_STEP = 2;
static const int SMOOTH_STEP = 1;

// Search tuning (BIG SWEEPS)
static const int SEARCH_STEP = 4;   // bigger = faster rotation

// =========================

int currentAngle = SERVO_CENTER;
int targetAngle = SERVO_CENTER;

bool searchMode = false;
int searchDirection = 1;  // 1 = right, -1 = left

// =========================

void clampTarget() {
  if (targetAngle < SERVO_MIN) targetAngle = SERVO_MIN;
  if (targetAngle > SERVO_MAX) targetAngle = SERVO_MAX;
}

void moveServoSmooth() {
  if (currentAngle < targetAngle) currentAngle += SMOOTH_STEP;
  else if (currentAngle > targetAngle) currentAngle -= SMOOTH_STEP;

  servo.write(currentAngle);
}

// =========================
// MQTT CALLBACK
// =========================

void onMqttMessage(char* topic, byte* payload, unsigned int length) {

  StaticJsonDocument<256> doc;
  if (deserializeJson(doc, payload, length)) return;

  const char* status = doc["status"] | "NO_FACE";
  String s = String(status);

  // ======================
  // FACE DETECTED → TRACK MODE
  // ======================
  if (s == "MOVE_LEFT" || s == "MOVE_RIGHT" || s == "CENTERED") {

    searchMode = false;   // stop searching immediately

    if (s == "MOVE_LEFT") {
      targetAngle += (INVERT_DIRECTION ? TRACK_STEP : -TRACK_STEP);
    }
    else if (s == "MOVE_RIGHT") {
      targetAngle += (INVERT_DIRECTION ? -TRACK_STEP : TRACK_STEP);
    }
    // CENTERED → hold position
  }

  // ======================
  // NO FACE → SEARCH MODE
  // ======================
  else if (s == "NO_FACE") {

    searchMode = true;
  }

  clampTarget();
}

// =========================

void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) return;

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
  }
}

void ensureMqtt() {

  while (!mqtt.connected()) {

    String clientId = String(TEAM_ID) + "_esp_" + String(ESP.getChipId(), HEX);

    if (mqtt.connect(clientId.c_str())) {
      mqtt.subscribe(topicMovement.c_str());
    } else {
      delay(1000);
    }
  }
}

// =========================

void setup() {

  Serial.begin(115200);

  topicMovement = String("vision/") + TEAM_ID + "/movement";

  servo.attach(SERVO_PIN);
  servo.write(SERVO_CENTER);

  ensureWifi();

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
}

// =========================

void loop() {

  ensureWifi();
  ensureMqtt();

  mqtt.loop();

  // ======================
  // SEARCH MODE SWEEP
  // ======================
  if (searchMode) {

    targetAngle += searchDirection * SEARCH_STEP;

    if (targetAngle >= SERVO_MAX) {
      targetAngle = SERVO_MAX;
      searchDirection = -1;
    }
    else if (targetAngle <= SERVO_MIN) {
      targetAngle = SERVO_MIN;
      searchDirection = 1;
    }
  }

  clampTarget();
  moveServoSmooth();

  delay(15);
}