#include <stdint.h>

#include "hardware/pio.h"
#include "hardware/irq.h"

#include "linkcable.h"

#ifdef STACKSMASHING
    #include "linkcable_sm.pio.h"
#else
    #include "linkcable.pio.h"
#endif

#define DEFAULT_SAVED_BITS 8

static irq_handler_t linkcable_irq_handler = NULL;
static uint32_t linkcable_pio_initial_pc = 0;
static uint saved_bits = DEFAULT_SAVED_BITS;

static void linkcable_isr(void) {
    if (linkcable_irq_handler) linkcable_irq_handler();
    if (pio_interrupt_get(LINKCABLE_PIO, 0)) pio_interrupt_clear(LINKCABLE_PIO, 0);
}

uint32_t linkcable_receive(void) {
    uint32_t retval = (pio_sm_get(LINKCABLE_PIO, LINKCABLE_SM) & ((1 << saved_bits) - 1));
    //if(saved_bits > 16)
    //    retval = (retval << 16) | (retval >> 16);
    return retval;
}

void linkcable_send(uint32_t data) {
    uint32_t sendval = (data << (32 - saved_bits));
    //if(saved_bits > 16)
    //    sendval = (sendval << 16) | (sendval >> 16);
    pio_sm_put(LINKCABLE_PIO, LINKCABLE_SM, sendval);
}

void clean_linkcable_fifos(void) {
    pio_sm_clear_fifos(LINKCABLE_PIO, LINKCABLE_SM);
}

void linkcable_reset(void) {
    pio_sm_set_enabled(LINKCABLE_PIO, LINKCABLE_SM, false);
    pio_sm_clear_fifos(LINKCABLE_PIO, LINKCABLE_SM);
    pio_sm_restart(LINKCABLE_PIO, LINKCABLE_SM);
    pio_sm_clkdiv_restart(LINKCABLE_PIO, LINKCABLE_SM);
    pio_sm_exec(LINKCABLE_PIO, LINKCABLE_SM, pio_encode_jmp(linkcable_pio_initial_pc));
    pio_sm_set_enabled(LINKCABLE_PIO, LINKCABLE_SM, true);
}

void linkcable_set_is_32(uint32_t is_32) {
    if(is_32)
        saved_bits = 32;
    else
        saved_bits = 8;
#ifdef STACKSMASHING
    linkcable_select_mode(LINKCABLE_PIO, LINKCABLE_SM, saved_bits);
#endif
}

void linkcable_init(irq_handler_t onDataReceive) {
    saved_bits = DEFAULT_SAVED_BITS;
#ifdef STACKSMASHING
    linkcable_sm_program_init(LINKCABLE_PIO, LINKCABLE_SM, linkcable_pio_initial_pc = pio_add_program(LINKCABLE_PIO, &linkcable_sm_program), DEFAULT_SAVED_BITS);
#else
    linkcable_program_init(LINKCABLE_PIO, LINKCABLE_SM, linkcable_pio_initial_pc = pio_add_program(LINKCABLE_PIO, &linkcable_program), CABLE_PINS_START);
#endif
//    pio_sm_put_blocking(LINKCABLE_PIO, LINKCABLE_SM, LINKCABLE_BITS - 1);
    pio_enable_sm_mask_in_sync(LINKCABLE_PIO, (1u << LINKCABLE_SM));

    if (onDataReceive) {
        linkcable_irq_handler = onDataReceive;
        pio_set_irq0_source_enabled(LINKCABLE_PIO, pis_interrupt0, true);
        irq_set_exclusive_handler(PIO0_IRQ_0, linkcable_isr);
        irq_set_enabled(PIO0_IRQ_0, true);
    }
}
