#ifndef NEUROTILE_HD_DRIVER_H
#define NEUROTILE_HD_DRIVER_H
#include <stdint.h>
#include "neurotile.h"

/* Host-scheduled K blocking with actual accelerator counters. Operands/output
 * are compact row-major matrices; M=1/2 reuses each B block across digit rows. */
static inline int hd_dense_hw_batch(const int8_t *input,const int8_t *weights,
    int32_t *out,unsigned m,unsigned k,unsigned n,uint32_t *kernel_cycles,
    uint32_t *macs,uint32_t *tiles) {
    if(m<1 || m>2 || k<1 || k>784 || n<1 || n>64)return -3;
    if(NT_REG(NT_ID)!=0x4e543031u)return -1;
    for(unsigned i=0;i<m*n;++i)out[i]=0;
    for(unsigned base=0;base<k;base+=64) {
        unsigned block=k-base<64 ? k-base : 64;
        NT_REG(NT_CONTROL)=2;
        NT_REG(NT_M)=m;NT_REG(NT_N)=n;NT_REG(NT_K)=block;
        for(unsigned row=0;row<m;++row)for(unsigned q=0;q<block;++q)
            NT_REG(NT_A+4*(row*block+q))=(uint8_t)input[row*k+base+q];
        for(unsigned q=0;q<block;++q)for(unsigned j=0;j<n;++j)
            NT_REG(NT_B+4*(q*n+j))=(uint8_t)weights[(base+q)*n+j];
        NT_REG(NT_CONTROL)=1;
        unsigned timeout=100000;
        while(!(NT_REG(NT_STATUS)&NT_DONE)) {
            if((NT_REG(NT_STATUS)&NT_ERROR) || --timeout==0)return -2;
        }
        if(NT_REG(NT_STATUS)&NT_ERROR)return -2;
        *kernel_cycles+=NT_REG(NT_CYCLES);
        *macs+=NT_REG(NT_MACS);*tiles+=NT_REG(NT_TILES);
        for(unsigned i=0;i<m*n;++i)out[i]+=(int32_t)NT_REG(NT_C+4*i);
    }
    return 0;
}
#endif
