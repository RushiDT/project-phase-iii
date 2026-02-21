#include <ArduinoJson.h>
#include <ESP8266WiFi.h>
#include <PubSubClient.h>

// WiFi Configuration
const char *ssid = "thakre_home";
const char *password = "rushi@7728";

// MQTT Configuration
const char *mqtt_server = "192.168.1.161"; // Raspberry Pi Base Station IP
const int mqtt_port = 1883;
const char *device_id_base = "esp8266_env_01";
const char *user_id = "user_789";
const char *topic_data = "iot/devices/esp8266_env_01/data";

char device_id[32]; // Buffer for unique ID

// Constant Sensor Values (Using constants as you don't have HW sensors yet)
const float CONST_TEMP = 24.5;
const float CONST_HUM = 55.0;

WiFiClient espClient;
PubSubClient client(espClient);
unsigned long lastMsg = 0;
int seq_num = 1;

void setup_wifi() {
  delay(10);
  Serial.println("\nConnecting to WiFi...");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected. IP: " + WiFi.localIP().toString());
}

void callback(char *topic, byte *payload, unsigned int length) {
  Serial.print("Message arrived [");
  Serial.print(topic);
  Serial.print("] ");
  for (int i = 0; i < length; i++) {
    Serial.print((char)payload[i]);
  }
  Serial.println();
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    if (client.connect(device_id)) {
      Serial.println("connected");
      // Subscribe to control topic
      char control_topic[64];
      snprintf(control_topic, sizeof(control_topic), "iot/devices/%s/control",
               device_id_base);
      client.subscribe(control_topic);
      Serial.print("Subscribed to: ");
      Serial.println(control_topic);
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);

  // Create a unique client ID to avoid rc=2 (Identifier Rejected)
  snprintf(device_id, sizeof(device_id), "%s_%04x", device_id_base,
           random(0xffff));
  Serial.print("Unique Client ID: ");
  Serial.println(device_id);

  setup_wifi();
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  unsigned long now = millis();
  if (now - lastMsg > 5000) { // Send every 5 seconds
    lastMsg = now;

    StaticJsonDocument<512> doc;
    doc["device_id"] = device_id;
    doc["user_id"] = user_id;
    doc["timestamp"] = 0; // Gateway will overwrite with real time
    doc["sequence_number"] = seq_num++;

    JsonObject sensors = doc.createNestedObject("sensors");
    // Using your constant values here
    sensors["temperature"] =
        CONST_TEMP + (random(-5, 5) / 10.0); // Adding tiny jitter
    sensors["humidity"] = CONST_HUM;
    sensors["vibration"] = 0.05;

    JsonObject system = doc.createNestedObject("system");
    system["battery_level"] = 100;
    system["cpu_usage"] = 20;
    system["wifi_signal"] = WiFi.RSSI();

    char buffer[512];
    serializeJson(doc, buffer);
    client.publish(topic_data, buffer);

    Serial.print("Published to Basestation: ");
    Serial.println(buffer);
  }
}
