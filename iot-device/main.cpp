#include <iostream>
#include <cstdlib>
#include <ctime>

#include "device/esp32_simulator.cpp"
#include "gateway/gateway.cpp"

int main() {
    srand(time(nullptr));

    for (int i = 0; i < 12; i++) {
        IoTPacket pkt = generate_packet();

        std::cout << "[DEVICE LOG] "
                  << pkt.device_id
                  << " Seq:" << pkt.sequence_no
                  << " Temp:" << pkt.temperature
                  << " CPU:" << pkt.cpu_usage
                  << " Battery:" << pkt.battery_level
                  << std::endl;

        process_packet(pkt);
    }

    return 0;
}
