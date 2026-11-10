#include <stdint.h>
#include "generated/model.h"
#include "neurotile.h"
#include "quant.h"

static void putch(char c) { *(volatile uint32_t *)0x20000000u = (uint8_t)c; }
static void puts_nt(const char *s) { while (*s) putch(*s++); }
static void print_u32(uint32_t value) {
    static const uint32_t places[] = {1000000000u,100000000u,10000000u,1000000u,
                              100000u,10000u,1000u,100u,10u,1u};
    int started = 0;
    for (unsigned i=0; i<10; ++i) {
        unsigned digit=0;
        while (value >= places[i]) { value-=places[i]; ++digit; }
        if (digit || started || i==9) { putch((char)('0'+digit)); started=1; }
    }
}
static void print_i32(int32_t value) {
    if (value < 0) { putch('-'); print_u32((uint32_t)(-(int64_t)value)); }
    else print_u32((uint32_t)value);
}
static int fail(int error) {
    puts_nt("NT_RESULT {\"passed\":false,\"error\":");
    print_i32(error); puts_nt("}\n");
    *(volatile uint32_t *)0x20000004u=2;
    return 1;
}

int main(void) {
    int32_t ref1[NT_HIDDEN], hw1[NT_HIDDEN]={0}, ref2[NT_OUTPUTS], hw2[NT_OUTPUTS]={0};
    int8_t ref_hidden[NT_HIDDEN], hw_hidden[NT_HIDDEN];
    uint32_t start = nt_clock();
    nt_dense_ref(nt_sample_input, nt_w1, ref1, NT_INPUTS, NT_HIDDEN);
    for (unsigned i=0; i<NT_HIDDEN; ++i)
        ref_hidden[i]=nt_activate(ref1[i]+nt_b1[i], NT_HIDDEN_SHIFT);
    nt_dense_ref(ref_hidden, nt_w2, ref2, NT_HIDDEN, NT_OUTPUTS);
    for (unsigned i=0; i<NT_OUTPUTS; ++i) ref2[i]+=nt_b2[i];
    uint32_t software_cycles = nt_clock()-start;

    start=nt_clock();
    uint32_t kernel_cycles=0;
    int error=nt_dense_hw(nt_sample_input,nt_w1,hw1,NT_INPUTS,NT_HIDDEN,&kernel_cycles);
    if(error) return fail(error);
    for (unsigned i=0; i<NT_HIDDEN; ++i)
        hw_hidden[i]=nt_activate(hw1[i]+nt_b1[i],NT_HIDDEN_SHIFT);
    error=nt_dense_hw(hw_hidden,nt_w2,hw2,NT_HIDDEN,NT_OUTPUTS,&kernel_cycles);
    if(error) return fail(error);
    for (unsigned i=0; i<NT_OUTPUTS; ++i) hw2[i]+=nt_b2[i];
    uint32_t accelerated_cycles=nt_clock()-start;
    unsigned prediction=0;
    for (unsigned i=0; i<NT_HIDDEN; ++i) if (hw1[i]!=ref1[i] || hw_hidden[i]!=ref_hidden[i]) error=3;
    for (unsigned i=0; i<NT_OUTPUTS; ++i) {
        if (hw2[i]!=ref2[i]) error=4;
        if (hw2[i]>hw2[prediction]) prediction=i;
    }
    puts_nt("NT_RESULT {\"passed\":"); puts_nt(error ? "false" : "true");
    puts_nt(",\"prediction\":"); print_u32(prediction);
    puts_nt(",\"label\":"); print_u32(nt_sample_label);
    puts_nt(",\"software_cycles\":"); print_u32(software_cycles);
    puts_nt(",\"accelerated_cycles\":"); print_u32(accelerated_cycles);
    puts_nt(",\"kernel_cycles\":"); print_u32(kernel_cycles);
    puts_nt(",\"logits\":[");
    for (unsigned i=0; i<NT_OUTPUTS; ++i) { if(i) putch(','); print_i32(hw2[i]); }
    puts_nt("]}\n");
    *(volatile uint32_t *)0x20000004u = error ? 2 : 1;
    return error;
}
