/*
 * esp8266_servo_controller.ino
 * ---------------------------------------------------------------------------
 * Edge controller for the Distributed Vision-Control (Face-Locked Servo) system.
 *
 * Role in the architecture:
 *     PC Vision Node  --MQTT-->  [ THIS ESP8266 ]  -->  Servo
 *
 * Behaviour:
 *   - Connects to Wi-Fi and the MQTT broker.
 *   - Subscribes to:  vision/<TEAM_ID>/movement
 *   - Parses the shared JSON payload:  {"status": "...", "confidence": .., "timestamp": ..}
 *   - Moves the servo smoothly:
 *         MOVE_LEFT  -> angle decreases
 *         MOVE_RIGHT -> angle increases
 *         CENTERED   -> hold
 *         NO_FACE    -> slow search sweep
 *
 * Libraries (install via Arduino Library Manager):
 *   - ESP8266WiFi      (board package: esp8266 by ESP8266 Community)
 *   - PubSubClient     (by Nick O'Leary)
 *   - Servo            (bundled with the ESP8266 core)
 *   - ArduinoJson      (by Benoit Blanchon, v6+)
 *
 * IMPORTANT: Do NOT commit real Wi-Fi credentials. Fill these in locally only.
 * ---------------------------------------------------------------------------
 */

#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <Servo.h>
#include <ArduinoJson.h>

// ===== USER CONFIG (edit locally; keep secrets out of git) =================
static const char* WIFI_SSID = "YOUR_WIFI_SSID";
static const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
static const char* MQTT_HOST = "192.168.1.100";   // broker IP / VPS host
static const uint16_t MQTT_PORT = 1883;
static const char* TEAM_ID   = "Winners";          // MUST match the PC + backend
// ===========================================================================

// ===== Servo config ========================================================
static const uint8_t SERVO_PIN     = D4;   // GPIO2
static const int     SERVO_MIN     = 0;
static const int     SERVO_MAX     = 180;
static const int     SERVO_CENTER  = 90;
static const bool    INVERT_DIRECTION = false;

static const int TRACK_STEP  = 3;   // step per movement command
static const int SMOOTH_STEP = 1;   // per-loop step toward target (smoothing)
static const int SEARCH_STEP = 4;   // sweep speed when no face
// ===========================================================================

String topicMovement;
WiFiClient espClient;
PubSubClient mqtt(espClient);
Servo servo;

int  currentAngle  = SERVO_CENTER;
int  targetAngle   = SERVO_CENTER;
bool searchMode    = false;
int  searchDir     = 1;

void clampTarget() {
  if (targetAngle < SERVO_MIN) targetAngle = SERVO_MIN;
  if (targetAngle > SERVO_MAX) targetAngle = SERVO_MAX;
}

void moveServoSmooth() {
  if (currentAngle < targetAngle) currentAngle += SMOOTH_STEP;
  else if (currentAngle > targetAngle) currentAngle -= SMOOTH_STEP;
  servo.write(currentAngle);
}

// Shared JSON payload handler (identical structure across PC / sim-ESP / ESP32).
void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  StaticJsonDocument<256> doc;
  if (deserializeJson(doc, payload, length)) return;        // ignore malformed
  String s = String((const char*)(doc["status"] | "NO_FACE"));

  if (s == "MOVE_LEFT" || s == "MOVE_RIGHT" || s == "CENTERED") {
    searchMode = false;
    if (s == "MOVE_LEFT")  targetAngle += (INVERT_DIRECTION ?  TRACK_STEP : -TRACK_STEP);
    if (s == "MOVE_RIGHT") targetAngle += (INVERT_DIRECTION ? -TRACK_STEP :  TRACK_STEP);
    // CENTERED -> hold
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
    String clientId = String(TEAM_ID) + "_esp8266_" + String(ESP.getChipId(), HEX);
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
  servo.attach(SERVO_PIN);
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
