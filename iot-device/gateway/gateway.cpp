#include <iostream>
#include <vector>
#include "../common/packet.h"

#define BATCH_SIZE 5

std::vector<IoTPacket> batch_buffer;

/* -------- VALIDATION -------- */
bool validate_packet(const IoTPacket& pkt) {

    if (pkt.sequence_no <= 0) return false;
    if (pkt.temperature < -20 || pkt.temperature > 100) return false;
    if (pkt.cpu_usage < 0 || pkt.cpu_usage > 100) return false;
    if (pkt.battery_level < 0 || pkt.battery_level > 100) return false;
    if (pkt.timestamp > std::time(nullptr) + 5) return false;

    return true;
}

/* -------- BATCH SEND -------- */
void send_batch_to_server() {
    std::cout << "\n[SENDING BATCH TO SERVER]\n";

    for (const auto& pkt : batch_buffer) {
        std::cout
            << pkt.device_id << ", "
            << pkt.sequence_no << ", "
            << pkt.temperature << ", "
            << pkt.humidity << ", "
            << pkt.packet_rate << ", "
            << pkt.cpu_usage << ", "
            << pkt.battery_level << ", "
            << pkt.timestamp << std::endl;
    }

    batch_buffer.clear();
}

/* -------- GATEWAY ENTRY -------- */
void process_packet(const IoTPacket& pkt) {

    if (!validate_packet(pkt)) {
        std::cout << "[INVALID PACKET DROPPED] Seq: "
                  << pkt.sequence_no << std::endl;
        return;
    }

    batch_buffer.push_back(pkt);

    if (batch_buffer.size() >= BATCH_SIZE) {
        send_batch_to_server();
    }
}
