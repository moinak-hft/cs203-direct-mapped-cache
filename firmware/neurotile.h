#ifndef NEUROTILE_H
#define NEUROTILE_H
#include <stdint.h>
#define NT_BASE 0x10000000u
#define NT_REG(offset) (*(volatile uint32_t *)(NT_BASE + (offset)))
#define NT_ID 0x00u
#define NT_CONTROL 0x04u
#define NT_STATUS 0x08u
#define NT_M 0x0cu
#define NT_N 0x10u
#define NT_K 0x14u
#define NT_CYCLES 0x18u
#define NT_MACS 0x1cu
#define NT_TILES 0x20u
#define NT_A 0x1000u
#define NT_B 0x2000u
#define NT_C 0x6000u
#define NT_BUSY 1u
#define NT_DONE 2u
#define NT_ERROR 4u
static inline uint32_t nt_clock(void) {
    return *(volatile uint32_t *)0x20000008u;
}
static inline int nt_dense_hw(const int8_t *input, const int8_t *weights,
                             int32_t *out, unsigned k, unsigned n,
                             uint32_t *kernel_cycles) {
    if (NT_REG(NT_ID) != 0x4e543031u) return -1;
    NT_REG(NT_CONTROL) = 2;
    NT_REG(NT_M) = 1;
    NT_REG(NT_N) = n;
    NT_REG(NT_K) = k;
    for (unsigned i = 0; i < k; ++i) NT_REG(NT_A+4*i) = (uint8_t)input[i];
    for (unsigned i = 0; i < k*n; ++i) NT_REG(NT_B+4*i) = (uint8_t)weights[i];
    NT_REG(NT_CONTROL) = 1;
    unsigned timeout = 100000;
    while ((NT_REG(NT_STATUS) & NT_DONE) == 0) {
        if ((NT_REG(NT_STATUS) & NT_ERROR) || --timeout == 0) return -2;
    }
    if (NT_REG(NT_STATUS) & NT_ERROR) return -2;
    *kernel_cycles += NT_REG(NT_CYCLES);
    for (unsigned j = 0; j < n; ++j) out[j] = (int32_t)NT_REG(NT_C+4*j);
    return 0;
}
#endif
