/*
 * esp32_servo_controller.ino
 * ---------------------------------------------------------------------------
 * ESP32 edge controller for the Distributed Vision-Control (Face-Locked Servo).
 *
 * Role:   PC Vision Node  --MQTT-->  [ THIS ESP32 ]  -->  Servo
 *
 * Same MQTT topic + JSON payload as the ESP8266 and the Python simulated ESP:
 *     topic   : vision/<TEAM_ID>/movement
 *     payload : {"status":"MOVE_LEFT|MOVE_RIGHT|CENTERED|NO_FACE", ...}
 *
 * ESP32 uses the LEDC peripheral for servo PWM (ESP32Servo library), which is
 * the main difference from the ESP8266 sketch.
 *
 * Libraries (Arduino Library Manager):
 *   - WiFi          (bundled with the ESP32 board package by Espressif)
 *   - PubSubClient  (Nick O'Leary)
 *   - ESP32Servo    (Kevin Harrington / John K. Bennett)
 *   - ArduinoJson   (Benoit Blanchon, v6+)
 *
 * IMPORTANT: Do NOT commit real Wi-Fi credentials. Fill these in locally only.
 * ---------------------------------------------------------------------------
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h>

// ===== USER CONFIG (edit locally; keep secrets out of git) =================
static const char* WIFI_SSID = ".";
static const char* WIFI_PASS = "ntwalivieira";
static const char* MQTT_HOST = "157.173.101.159";
static const uint16_t MQTT_PORT = 1883;
static const char* TEAM_ID   = "Winners";          // MUST match PC + backend
// ===========================================================================

// ===== Servo config ========================================================
static const int  SERVO_PIN      = 18;   // any PWM-capable GPIO
static const int  SERVO_MIN      = 0;
static const int  SERVO_MAX      = 180;
static const int  SERVO_CENTER   = 90;
static const bool INVERT_DIRECTION = false;

static const int TRACK_STEP  = 3;
static const int SMOOTH_STEP = 1;
static const int SEARCH_STEP = 4;
// ===========================================================================

String topicMovement;
WiFiClient espClient;
PubSubClient mqtt(espClient);
Servo servo;

int  currentAngle = SERVO_CENTER;
int  targetAngle  = SERVO_CENTER;
bool searchMode   = false;
int  searchDir    = 1;

void clampTarget() {
  if (targetAngle < SERVO_MIN) targetAngle = SERVO_MIN;
  if (targetAngle > SERVO_MAX) targetAngle = SERVO_MAX;
}

void moveServoSmooth() {
  if (currentAngle < targetAngle) currentAngle += SMOOTH_STEP;
  else if (currentAngle > targetAngle) currentAngle -= SMOOTH_STEP;
  servo.write(currentAngle);
}

void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  StaticJsonDocument<256> doc;
  if (deserializeJson(doc, payload, length)) return;
  String s = String((const char*)(doc["status"] | "NO_FACE"));

  if (s == "MOVE_LEFT" || s == "MOVE_RIGHT" || s == "CENTERED") {
    searchMode = false;
    if (s == "MOVE_LEFT")  targetAngle += (INVERT_DIRECTION ?  TRACK_STEP : -TRACK_STEP);
    if (s == "MOVE_RIGHT") targetAngle += (INVERT_DIRECTION ? -TRACK_STEP :  TRACK_STEP);
  } else if (s == "NO_FACE") {
    searchMode = true;
  }
  clampTarget();
}

void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) delay(500);
}

void ensureMqtt() {
  while (!mqtt.connected()) {
    String clientId = String(TEAM_ID) + "_esp32_" + String((uint32_t)ESP.getEfuseMac(), HEX);
    if (mqtt.connect(clientId.c_str())) {
      mqtt.subscribe(topicMovement.c_str());
    } else {
      delay(1000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  topicMovement = String("vision/") + TEAM_ID + "/movement";

  ESP32PWM::allocateTimer(0);          // reserve a hardware timer for servo PWM
  servo.setPeriodHertz(50);            // standard 50 Hz servo
  servo.attach(SERVO_PIN, 500, 2400);  // typical 0.5ms..2.4ms pulse range
  servo.write(SERVO_CENTER);

  ensureWifi();
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
}

void loop() {
  ensureWifi();
  ensureMqtt();
  mqtt.loop();

  if (searchMode) {
    targetAngle += searchDir * SEARCH_STEP;
    if (targetAngle >= SERVO_MAX) { targetAngle = SERVO_MAX; searchDir = -1; }
    else if (targetAngle <= SERVO_MIN) { targetAngle = SERVO_MIN; searchDir = 1; }
  }
  clampTarget();
  moveServoSmooth();
  delay(15);
}
