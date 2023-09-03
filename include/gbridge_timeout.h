#ifndef GBRIDGE_TIMEOUT_H_
#define GBRIDGE_TIMEOUT_H_

#include "time_defs.h"

typedef user_time_t timeout_time_t;
typedef uint8_t num_retries_t;

enum timeout_resolution {
    RESOLUTION_SECONDS = 0,
    RESOLUTION_MILLI_SECONDS = 1,
    RESOLUTION_MICRO_SECONDS = 2,
    RESOLUTION_NANO_SECONDS = 3,
    RESOLUTION_PICO_SECONDS = 4,
    RESOLUTION_MINUTES = 5,
    RESOLUTION_HOURS = 6
};

num_retries_t get_num_retries(void);
void set_num_retries(num_retries_t new_num_retries);

// Get the timeout's resolution
enum timeout_resolution get_timeout_resolution(void);
// Gets/Sets the timeout with the unit specified by get_timeout_resolution
timeout_time_t get_timeout_time(void);
void set_timeout_time(timeout_time_t new_timeout_time, enum timeout_resolution new_timeout_resolution);

// Preparation functions for the rest of the code.
// Called before an attempt is made.
void prepare_timeout(void);
void prepare_failure(void);

// If this returns true, try again.
// Otherwise, fail.
bool timeout_can_try_again(void);
bool failed_can_try_again(void);

#endif /* GBRIDGE_TIMEOUT_H_ */