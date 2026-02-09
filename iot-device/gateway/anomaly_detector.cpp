#include "../common/packet.h"

bool is_anomalous(const IoTPacket& pkt) {
    if (pkt.temperature > 60) return true;
    if (pkt.packet_rate > 100) return true;
    return false;
}
