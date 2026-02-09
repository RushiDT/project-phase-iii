#pragma once
#include <string>
#include <ctime>

struct IoTPacket {
    std::string device_id;
    int sequence_no;
    float temperature;
    float humidity;
    int packet_rate;
    float cpu_usage;
    float battery_level;
    std::time_t timestamp;
};
