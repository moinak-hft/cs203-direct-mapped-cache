#ifndef NEUROTILE_QUANT_H
#define NEUROTILE_QUANT_H
#include <stdint.h>

/* Explicit floor division, so host C and RTL agree for negative values.
 * Network sums are bounded far from INT32_MIN; shift is constrained to 0..24. */
static inline int32_t nt_floor_shift(int32_t value, unsigned shift) {
    int32_t divisor = (int32_t)(1u << shift);
    int32_t quotient=value/divisor;
    if (value<0 && value%divisor) --quotient;
    return quotient;
}
static inline int8_t nt_activate(int32_t value, unsigned shift) {
    int32_t q = nt_floor_shift(value, shift);
    return (int8_t)(q < 0 ? 0 : q > 127 ? 127 : q);
}
static inline void nt_dense_ref(const int8_t *input, const int8_t *weights,
                               int32_t *out, unsigned k, unsigned n) {
    for (unsigned j = 0; j < n; ++j) {
        int32_t acc = 0;
        for (unsigned i = 0; i < k; ++i)
            acc += (int32_t)input[i] * (int32_t)weights[i*n+j];
        out[j] = acc;
    }
}
#endif
