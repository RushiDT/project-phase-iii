#include <ArduinoJson.h>
#include <HTTPUpdate.h>
#include <PubSubClient.h>
#include <WiFi.h>


// WiFi Configuration
const char *ssid = "thakre_home";    // <-- CHANGE THIS
const char *password = "rushi@7728"; // <-- CHANGE THIS

// MQTT Configuration
const char *mqtt_server = "192.168.1.161"; // Raspberry Pi Base Station IP
const int mqtt_port = 1883;
const char *device_id_base = "esp32_sec_01";
const char *user_id = "user_456";
const char *mqtt_user = "admin";
const char *mqtt_pass = "password123";
const char *topic_data = "iot/devices/esp32_sec_01/data";

char device_id[32]; // Buffer for unique ID

// Sensor Pins
const int PIR_PIN = 12; // Labeled as G12 on ESP32
const int LED_PIN = 13; // LED Indicator for Motion

WiFiClient espClient;
PubSubClient client(espClient);
unsigned long lastMsg = 0;
unsigned long motionOffTime = 0;
bool ledManualMode = false;
int seq_num = 1;

void setup_wifi() {
  delay(10);
  Serial.print("Connecting to ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected");
}

void callback(char *topic, byte *payload, unsigned int length) {
  Serial.print("Message arrived [");
  Serial.print(topic);
  Serial.print("] ");

  StaticJsonDocument<256> doc;
  deserializeJson(doc, payload, length);
  const char *command = doc["command"];

  Serial.println(command);

  if (strcmp(command, "LIGHT_ON") == 0) {
    digitalWrite(LED_PIN, HIGH);
    ledManualMode = true;
    Serial.println("→ Remote Command: LED ON (Manual Mode)");
  } else if (strcmp(command, "LIGHT_OFF") == 0) {
    digitalWrite(LED_PIN, LOW);
    ledManualMode = false;
    Serial.println("→ Remote Command: LED OFF (Manual Off)");
  } else if (strncmp(command, "OTA_UPDATE|", 11) == 0) {
    // Expected format: OTA_UPDATE|v2.0.0
    String version = String(command).substring(11);
    Serial.print(
        "→ Remote Command: OTA Firmware Update Initiated! Target Version: ");
    Serial.println(version);

    // Construct the firmware download URL
    String otaUrl = "http://192.168.1.121:5002/api/ota/firmware/" + version;
    Serial.print("Downloading from: ");
    Serial.println(otaUrl);

    WiFiClient otaClient;
    t_httpUpdate_return ret = httpUpdate.update(otaClient, otaUrl);

    switch (ret) {
    case HTTP_UPDATE_FAILED:
      Serial.printf("HTTP_UPDATE_FAILED Error (%d): %s\n",
                    httpUpdate.getLastError(),
                    httpUpdate.getLastErrorString().c_str());
      break;
    case HTTP_UPDATE_NO_UPDATES:
      Serial.println("HTTP_UPDATE_NO_UPDATES");
      break;
    case HTTP_UPDATE_OK:
      Serial.println("HTTP_UPDATE_OK - Rebooting...");
      break;
    }
  }
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    if (client.connect(device_id, mqtt_user, mqtt_pass)) {
      Serial.println("connected");
      // Subscribe to control topic
      char control_topic[64];
      snprintf(control_topic, sizeof(control_topic), "iot/devices/%s/control",
               device_id);
      client.subscribe(control_topic);
      Serial.print("Subscribed to: ");
      Serial.println(control_topic);
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIR_PIN, INPUT);
  pinMode(LED_PIN, OUTPUT); // Set LED pin as output

  // Create a unique client ID
  snprintf(device_id, sizeof(device_id), "%s", device_id_base);
  Serial.print("Fixed Client ID: ");
  Serial.println(device_id);

  setup_wifi();
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
  client.setBufferSize(512); // Increase buffer for large JSON payloads
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  unsigned long now = millis();
  if (now - lastMsg > 800) { // High-speed telemetry (0.8s)
    lastMsg = now;

    int motion = digitalRead(PIR_PIN);

    // Visual Indicator: LED is now strictly manual (Dashboard controlled)
    // Motion is only logged for telemetry, no hardware trigger here.
    if (motion == HIGH) {
      Serial.println("Motion Detected! (Logging only)");
    }

    StaticJsonDocument<512> doc;
    doc["device_id"] = device_id;
    doc["user_id"] = user_id;
    doc["timestamp"] = 0;
    doc["sequence_number"] = seq_num++;

    JsonObject sensors = doc.createNestedObject("sensors");
    sensors["motion"] = (motion == HIGH);
    sensors["light_state"] = (digitalRead(LED_PIN) == HIGH);
    sensors["vibration"] = random(0, 10) / 100.0;

    JsonObject system = doc.createNestedObject("system");
    system["battery_level"] = 100;
    system["cpu_usage"] = random(5, 15);
    system["wifi_signal"] = WiFi.RSSI();

    char buffer[512];
    serializeJson(doc, buffer);

    if (client.publish(topic_data, buffer)) {
      Serial.print("Published Security Data (ESP32): ");
      Serial.println(buffer);
    } else {
      Serial.print("ERROR: Publish FAILED! State: ");
      Serial.println(client.state());
    }
  }
}
