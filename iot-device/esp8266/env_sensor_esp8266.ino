#include <ArduinoJson.h>
#include <DHT.h>
#include <ESP8266WiFi.h>
#include <PubSubClient.h>

// WiFi Configuration
const char *ssid = "thakre_home";    // <-- CHANGE THIS
const char *password = "rushi@7728"; // <-- CHANGE THIS

// MQTT Configuration
const char *mqtt_server = "192.168.1.133"; // Gateway PC LAN IP
const int mqtt_port = 1883;
const char *device_id = "esp8266_env_01";
const char *user_id = "user_789";
const char *topic_data = "iot/devices/esp8266_env_01/data";

// Sensor Configuration
#define DHTPIN D4     // Digital pin connected to the DHT sensor
#define DHTTYPE DHT11 // DHT 11
DHT dht(DHTPIN, DHTTYPE);

// BEST PRACTICES:
// 1. Use a stable 5V power supply for the DHT11 to ensure accuracy.
// 2. Place the sensor away from heat sources (like the ESP8266 itself) and
// direct sunlight.
// 3. Ensure good airflow around the sensor.

// CALIBRATION OFFSETS (Adjust these based on a reference thermometer)
const float TEMP_OFFSET = -2.0; // Subtract 2.0 degrees C
const float HUM_OFFSET = 0.0;   // No humidity offset currently

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
  client.setBufferSize(512); // Increase buffer for large JSON payloads
  dht.begin();
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  unsigned long now = millis();
  if (now - lastMsg > 2000) { // Read every 2 seconds (Prevents self-heating)
    lastMsg = now;

    float h = dht.readHumidity();
    float t = dht.readTemperature();

    // Check if any reads failed and exit early (to try again).
    if (isnan(h) || isnan(t)) {
      Serial.println("Failed to read from DHT sensor!");
      return;
    }

    // Apply Calibration Offsets
    t += TEMP_OFFSET;
    h += HUM_OFFSET;

    StaticJsonDocument<512> doc;
    doc["device_id"] = device_id;
    doc["user_id"] = user_id;
    doc["timestamp"] = 0; // Gateway will timestamp if NTP not set
    doc["sequence_number"] = seq_num++;

    JsonObject sensors = doc.createNestedObject("sensors");
    sensors["temperature"] = t;
    sensors["humidity"] = h;
    sensors["vibration"] = 0.0;

    JsonObject system = doc.createNestedObject("system");
    system["battery_level"] = 100;
    system["cpu_usage"] = random(10, 30);
    system["wifi_signal"] = WiFi.RSSI();

    char buffer[512];
    serializeJson(doc, buffer);
    client.publish(topic_data, buffer);

    Serial.print("Published (ESP8266): ");
    Serial.println(buffer);
  }
}
