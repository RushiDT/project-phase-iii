#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <DHT.h>

// WiFi Configuration
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";

// MQTT Configuration
const char* mqtt_server = "YOUR_GATEWAY_IP"; // The IP of the machine running the gateway
const int mqtt_port = 1883;
const char* device_id = "esp32_env_01";
const char* user_id = "user_789";
const char* topic_data = "iot/devices/esp32_env_01/data";

// Sensor Configuration
#define DHTPIN 4
#define DHTTYPE DHT11 // or DHT22
DHT dht(DHTPIN, DHTTYPE);

WiFiClient espClient;
PubSubClient client(espClient);
unsigned long lastMsg = 0;
int seq_num = 1;

void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Connecting to ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("");
  Serial.println("WiFi connected");
  Serial.println("IP address: ");
  Serial.println(WiFi.localIP());
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    if (client.connect(device_id)) {
      Serial.println("connected");
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
  setup_wifi();
  client.setServer(mqtt_server, mqtt_port);
  dht.begin();
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  unsigned long now = millis();
  if (now - lastMsg > 5000) { // Every 5 seconds
    lastMsg = now;

    float h = dht.readHumidity();
    float t = dht.readTemperature();

    if (isnan(h) || isnan(t)) {
      Serial.println("Failed to read from DHT sensor!");
      return;
    }

    StaticJsonDocument<512> doc;
    doc["device_id"] = device_id;
    doc["user_id"] = user_id;
    doc["timestamp"] = time(nullptr); // Requires NTP setup for accuracy, or use gateway time
    doc["sequence_number"] = seq_num++;

    JsonObject sensors = doc.createNestedObject("sensors");
    sensors["temperature"] = t;
    sensors["humidity"] = h;
    sensors["vibration"] = 0.0;

    JsonObject system = doc.createNestedObject("system");
    system["battery_level"] = 100; // Simulated or measured
    system["cpu_usage"] = random(10, 30);
    system["wifi_signal"] = WiFi.RSSI();

    char buffer[512];
    serializeJson(doc, buffer);
    client.publish(topic_data, buffer);
    
    Serial.print("Published: ");
    Serial.println(buffer);
  }
}
