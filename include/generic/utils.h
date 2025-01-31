#ifndef UTILS_H_
#define UTILS_H_

#include <mobile.h>

uint64_t read_big_endian(const uint8_t* buffer, size_t size);
void write_big_endian(uint8_t* buffer, uint64_t data, size_t size);

uint16_t calc_checksum(const uint8_t* buffer, uint32_t size);
void set_checksum(const uint8_t* buffer, uint32_t size, uint8_t* checksum_buffer);
bool check_checksum(const uint8_t* buffer, uint32_t size, const uint8_t* checksum_buffer);

unsigned address_write(const struct mobile_addr *addr, unsigned char *buffer);
unsigned address_read(struct mobile_addr *addr, const unsigned char *buffer, unsigned size);

#endif /* UTILS_H_ */
