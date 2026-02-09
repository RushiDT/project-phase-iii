#include <cstdlib>
#include <ctime>
#include "../common/packet.h"

static int seq_counter = 0;

IoTPacket generate_packet() {
    IoTPacket pkt;
    pkt.device_id = "ESP32_SIM_01";
    pkt.sequence_no = ++seq_counter;
    pkt.timestamp = std::time(nullptr);

    pkt.temperature = 25 + rand() % 10;
    pkt.humidity = 45 + rand() % 20;
    pkt.packet_rate = 10 + rand() % 10;

    pkt.cpu_usage = 20 + rand() % 60;        // %
    pkt.battery_level = 30 + rand() % 70;    // %

    return pkt;
}
