#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// WiFi Configuration
const char* ssid = "thakre_home";
const char* password = "rushi@7728";

// MQTT Configuration
const char* mqtt_server = "192.168.1.133";
const int mqtt_port = 1883;
const char* device_id_base = "esp32_sec_01";
const char* user_id = "user_456";
const char* topic_data = "iot/devices/esp32_sec_01/data";

char device_id[32]; // Buffer for unique ID

// Sensor Pins
const int PIR_PIN = 12;
const int LDR_PIN = 34;

WiFiClient espClient;
PubSubClient client(espClient);
unsigned long lastMsg = 0;
int seq_num = 1;

void setup_wifi() {
  delay(10);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected");
}

void reconnect() {
  while (!client.connected()) {
    if (client.connect(device_id)) {
      Serial.println("MQTT connected");
    } else {
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIR_PIN, INPUT);
  
  // Create a unique client ID to avoid rc=2 (Identifier Rejected)
  snprintf(device_id, sizeof(device_id), "%s_%04x", device_id_base, random(0xffff));
  Serial.print("Unique Client ID: ");
  Serial.println(device_id);

  setup_wifi();
  client.setServer(mqtt_server, mqtt_port);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  unsigned long now = millis();
  if (now - lastMsg > 2000) { // Every 2 seconds for security
    lastMsg = now;

    int motion = digitalRead(PIR_PIN);
    int light = analogRead(LDR_PIN);

    StaticJsonDocument<512> doc;
    doc["device_id"] = device_id;
    doc["user_id"] = user_id;
    doc["timestamp"] = time(nullptr);
    doc["sequence_number"] = seq_num++;

    JsonObject sensors = doc.createNestedObject("sensors");
    sensors["motion"] = (motion == HIGH);
    sensors["light_level"] = light;
    sensors["vibration"] = random(0, 10) / 100.0;

    JsonObject system = doc.createNestedObject("system");
    system["battery_level"] = 100;
    system["cpu_usage"] = random(5, 15);
    system["wifi_signal"] = WiFi.RSSI();

    char buffer[512];
    serializeJson(doc, buffer);
    client.publish(topic_data, buffer);
    
    Serial.print("Published Security Data: ");
    Serial.println(buffer);
  }
}
