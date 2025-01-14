#include <stdio.h>
#include <string.h>
#include <mobile.h>
#include "gbridge.h"
#include "device_config.h"
#include "pico_mobile_adapter.h"
#include "bridge_debug_commands.h"
#include "gbridge_timeout.h"
#include "save_load_config.h"
#include "utils.h"

#define MAX_DEBUG_COMMAND_SIZE 0x3F
#define DEBUG_COMMAND_ID_SIZE 1
#define MAX_NEEDED_DEBUG_SIZE EEPROM_SIZE

enum bridge_debug_command_id {
    SEND_EEPROM_CMD = 1,
    UPDATE_EEPROM_CMD = 2,
    UPDATE_RELAY_CMD = 3,
    UPDATE_RELAY_TOKEN_CMD = 4,
    UPDATE_DNS1_CMD = 5,
    UPDATE_DNS2_CMD = 6,
    UPDATE_P2P_PORT_CMD = 7,
    UPDATE_DEVICE_CMD = 8,
    GET_NUMBER_STATUS_CMD = 9,
    SEND_IMPL_INFO_CMD = 10,
    STOP_CMD = 11,
    START_CMD = 12,
    STATUS_CMD = 13,
    SEND_NUMBER_OWN_CMD = 14,
    SEND_NUMBER_OTHER_CMD = 15,
    SEND_RELAY_TOKEN_CMD = 16,
    SET_SAVE_STYLE_CMD = 17,
    FORCE_SAVE_CMD = 18,
    SEND_GBRIDGE_CFG_CMD = 19,
    UPDATE_GBRIDGE_CFG_CMD = 20,
    ASK_NUMBER_CMD = 21
};

enum bridge_debug_command_info_id {
    CMD_DEBUG_INFO_CFG = 0x01,
    CMD_DEBUG_INFO_NUM_STATUS = 0x02,
    CMD_DEBUG_INFO_IMPL = 0x03,
    CMD_DEBUG_INFO_STATUS = 0x04,
    CMD_DEBUG_INFO_NUMBER = 0x05,
    CMD_DEBUG_INFO_NUMBER_PEER = 0x06,
    CMD_DEBUG_INFO_RELAY_TOKEN = 0x07,
    CMD_DEBUG_INFO_GBRIDGE_CFG = 0x08
};

void interpret_debug_command(const uint8_t* src, uint8_t size, uint8_t real_size, bool is_in_mobile_loop) {
    if(real_size <= GBRIDGE_CHECKSUM_SIZE)
        return;
    if(size > (real_size - GBRIDGE_CHECKSUM_SIZE))
        size = real_size - GBRIDGE_CHECKSUM_SIZE;
    if(!size)
        return;
    if(size > (MAX_DEBUG_COMMAND_SIZE - GBRIDGE_CHECKSUM_SIZE))
        size = MAX_DEBUG_COMMAND_SIZE - GBRIDGE_CHECKSUM_SIZE;
    if(!src)
        return;
    
    if(is_in_mobile_loop)
        return;

    struct mobile_user* mobile = get_mobile_user();
    struct mobile_addr target_addr;
    uint8_t data_out[MAX_NEEDED_DEBUG_SIZE + 1];
    size_t data_out_len;
    unsigned addrsize;
    uint8_t flag;
    bool unmetered;
    enum mobile_adapter_device device;

    uint8_t cmd = src[0];
    const uint8_t* data = src + DEBUG_COMMAND_ID_SIZE;
    const uint8_t* end_of_data = src + size;

    if(!check_checksum(src, size, end_of_data))
        return;

    memset(data_out, 0, MAX_NEEDED_DEBUG_SIZE + 1);
    size -= DEBUG_COMMAND_ID_SIZE;    

    switch(cmd) {
        case SEND_EEPROM_CMD:
            data_out[0] = CMD_DEBUG_INFO_CFG;
#ifdef CAN_SAVE
            ReadEeprom(data_out + 1);
            debug_send(data_out, EEPROM_SIZE + 1, GBRIDGE_CMD_DEBUG_INFO);
#else
            if(mobile->started)
                return;
            memcpy(data_out + 1, mobile->config_eeprom, EEPROM_SIZE);
            debug_send(data_out, EEPROM_SIZE + 1, GBRIDGE_CMD_DEBUG_INFO);
#endif
            break;
        case STATUS_CMD:
            data_out[0] = CMD_DEBUG_INFO_STATUS;
            flag = 0;
            if(mobile->started)
                flag |= 1;
#ifdef CAN_SAVE
            flag |= 2;
            if(mobile->automatic_save)
                flag |= 4;
#endif
            data_out[1] = flag;
            
            unmetered = false;
            device = MOBILE_ADAPTER_BLUE;            
            mobile_config_get_device(mobile->adapter, &device, &unmetered);
            data_out[2] = (device & 0x7F) | (unmetered ? 0x80 : 0);

            debug_send(data_out, 3, GBRIDGE_CMD_DEBUG_INFO);
            break;
        case SEND_IMPL_INFO_CMD:
            data_out[0] = CMD_DEBUG_INFO_IMPL;
            data_out_len = 1;

            write_big_endian(data_out + data_out_len, mobile_version, sizeof(mobile_version));
            data_out_len += sizeof(mobile_version);
            write_big_endian(data_out + data_out_len, IMPLEMENTATION_VERSION, IMPLEMENTATION_VERSION_SIZE);
            data_out_len += IMPLEMENTATION_VERSION_SIZE;
            data_out_len += snprintf(data_out + data_out_len, MAX_NEEDED_DEBUG_SIZE - data_out_len, IMPLEMENTATION_NAME);

            debug_send(data_out, data_out_len, GBRIDGE_CMD_DEBUG_INFO);
            break;
        case SEND_NUMBER_OWN_CMD:
            data_out[0] = CMD_DEBUG_INFO_NUMBER;
            memcpy(data_out + 1, mobile->number_user, MOBILE_MAX_NUMBER_SIZE + 1);
            debug_send(data_out, MOBILE_MAX_NUMBER_SIZE + 2, GBRIDGE_CMD_DEBUG_INFO);
            break;
        case SEND_NUMBER_OTHER_CMD:
            data_out[0] = CMD_DEBUG_INFO_NUMBER_PEER;
            memcpy(data_out + 1, mobile->number_peer, MOBILE_MAX_NUMBER_SIZE + 1);
            debug_send(data_out, MOBILE_MAX_NUMBER_SIZE + 2, GBRIDGE_CMD_DEBUG_INFO);
            break;
        case SEND_RELAY_TOKEN_CMD:
            data_out[0] = CMD_DEBUG_INFO_RELAY_TOKEN;
            data_out[1] = 0;
            unsigned send_size = 1;
            if(mobile_config_get_relay_token(mobile->adapter, data_out + 2)) {
                data_out[1] = 1;
                send_size += MOBILE_RELAY_TOKEN_SIZE;
            }
            debug_send(data_out, send_size + 1, GBRIDGE_CMD_DEBUG_INFO);
            break;
        case UPDATE_EEPROM_CMD:
            if(size < 3)
                return;

            if(mobile->started)
                return;

            unsigned offset = (data[0] << 8) | data[1];
            uint8_t is_done = data[2];
            size -= 3;
            
            if(offset > EEPROM_SIZE)
                offset = EEPROM_SIZE;
            
            if((size + offset) > EEPROM_SIZE)
                size = EEPROM_SIZE - offset;
            
            impl_config_write(mobile, data + 3, offset, size);

            if(is_done)
                mobile_config_load(mobile->adapter);

            debug_send_ack(cmd);

            break;
        case ASK_NUMBER_CMD:
            // Put the future libmobile call here

            debug_send_ack(cmd);

            break;
        case GET_NUMBER_STATUS_CMD:
            data_out[0] = CMD_DEBUG_INFO_NUM_STATUS;
            // Put the future libmobile call here

            debug_send(data_out, 2, GBRIDGE_CMD_DEBUG_INFO);

            break;
        case STOP_CMD:
            mobile_stop(mobile->adapter);
            mobile->started = false;
            debug_send_ack(cmd);

            break;
        case START_CMD:
            mobile_start(mobile->adapter);
            mobile->started = true;
            debug_send_ack(cmd);

            break;
        case SET_SAVE_STYLE_CMD:
            if(size < 1)
                return;
#ifdef CAN_SAVE
            mobile->automatic_save = data[0];
            debug_send_ack(cmd);
#endif

            break;
        case FORCE_SAVE_CMD:
#ifdef CAN_SAVE
            mobile->force_save = true;
            debug_send_ack(cmd);
#endif

            break;
        case UPDATE_DEVICE_CMD:
            if(size < 1)
                return;

            unmetered = data[0] & 0x80 ? true : false;
            device = data[0] & 0x7F;
            
            // Allow any value for device
            //if((device != MOBILE_ADAPTER_BLUE) && (device != MOBILE_ADAPTER_RED) && (device != MOBILE_ADAPTER_YELLOW) && (device != MOBILE_ADAPTER_GREEN))
            //    return;
            
            mobile_config_set_device(mobile->adapter, device, unmetered);
            mobile_config_save(mobile->adapter);
            debug_send_ack(cmd);

            break;
        case UPDATE_P2P_PORT_CMD:
            if(size < 2)
                return;

            uint16_t port = (data[0] << 8) | data[1];

            mobile_config_set_p2p_port(mobile->adapter, port);
            mobile_config_save(mobile->adapter);
            debug_send_ack(cmd);

            break;
        case UPDATE_RELAY_CMD:
            if(size < 1)
                return;

            addrsize = address_read(&target_addr, data, size);
            if(!addrsize)
                return;

            mobile_config_set_relay(mobile->adapter, &target_addr);
            mobile_config_save(mobile->adapter);
            debug_send_ack(cmd);

            break;
        case UPDATE_DNS1_CMD:
            if(size < 1)
                return;

            addrsize = address_read(&target_addr, data, size);
            if(!addrsize)
                return;

            mobile_config_set_dns(mobile->adapter, &target_addr, MOBILE_DNS1);
            mobile_config_save(mobile->adapter);
            debug_send_ack(cmd);

            break;
        case UPDATE_DNS2_CMD:
            if(size < 1)
                return;

            addrsize = address_read(&target_addr, data, size);
            if(!addrsize)
                return;

            mobile_config_set_dns(mobile->adapter, &target_addr, MOBILE_DNS2);
            mobile_config_save(mobile->adapter);
            debug_send_ack(cmd);

            break;
        case UPDATE_RELAY_TOKEN_CMD:
            if(size < 1)
                return;

            bool initialized = data[0] ? true : false;
            size -= 1;
            if((initialized) && (size < MOBILE_RELAY_TOKEN_SIZE))
                return;

            if(initialized)
                mobile_config_set_relay_token(mobile->adapter, data + 1);
            else
                mobile_config_set_relay_token(mobile->adapter, NULL);

            mobile_config_save(mobile->adapter);
            debug_send_ack(cmd);

            break;
        case SEND_GBRIDGE_CFG_CMD:
            data_out[0] = CMD_DEBUG_INFO_GBRIDGE_CFG;
            data_out[1] = get_timeout_resolution();
            write_big_endian(data_out + 1 + 1, get_timeout_time(), sizeof(timeout_time_t));
            write_big_endian(data_out + 1 + 1 + sizeof(timeout_time_t), get_num_retries(), sizeof(num_retries_t));

            debug_send(data_out, 1 + 1 + sizeof(timeout_time_t) + sizeof(num_retries_t), GBRIDGE_CMD_DEBUG_INFO);
            break;
        case UPDATE_GBRIDGE_CFG_CMD:
            if(size < 1)
                return;

            uint8_t kind = data[0] & 3;
            size -= 1;
            uint8_t data_offset = 1;
            
            if(kind & 1) {
                if(size < 1 + sizeof(timeout_time_t))
                    return;
                set_timeout_time(read_big_endian(data + data_offset + 1, sizeof(timeout_time_t)), data[data_offset]);
                
                data_offset += 1 + sizeof(timeout_time_t);
                size -= 1 + sizeof(timeout_time_t);
            }
            
            if(kind & 2) {
                if(size < sizeof(num_retries_t))
                    return;
                set_num_retries(read_big_endian(data + data_offset, sizeof(num_retries_t)));
                
                data_offset += sizeof(num_retries_t);
                size -= sizeof(num_retries_t);
            }

            debug_send_ack(cmd);

            break;
        default:
            break;
    }
}
