/* Native C reference: stdin is exactly 64 pixel integers in 0..16. */
#include <stdio.h>
#include <stdint.h>
#include "generated/model.h"
#include "quant.h"
int main(void) {
    int8_t input[NT_INPUTS], hidden[NT_HIDDEN];
    int32_t h[NT_HIDDEN], logits[NT_OUTPUTS];
    for(unsigned i=0;i<NT_INPUTS;++i) {
        int value;
        if(scanf("%d",&value)!=1 || value<0 || value>16) return 2;
        input[i]=(int8_t)value;
    }
    nt_dense_ref(input,nt_w1,h,NT_INPUTS,NT_HIDDEN);
    for(unsigned i=0;i<NT_HIDDEN;++i) hidden[i]=nt_activate(h[i]+nt_b1[i],NT_HIDDEN_SHIFT);
    nt_dense_ref(hidden,nt_w2,logits,NT_HIDDEN,NT_OUTPUTS);
    unsigned prediction=0;
    for(unsigned i=0;i<NT_OUTPUTS;++i) {
        logits[i]+=nt_b2[i];
        if(logits[i]>logits[prediction]) prediction=i;
    }
    printf("{\"prediction\":%u,\"hidden\":[",prediction);
    for(unsigned i=0;i<NT_HIDDEN;++i)printf("%s%d",i?",":"",(int)hidden[i]);
    printf("],\"logits\":[");
    for(unsigned i=0;i<NT_OUTPUTS;++i) printf("%s%ld",i?",":"",(long)logits[i]);
    puts("]}");
    return 0;
}
