/* UART request: 'N','T',64 pixels, XOR of pixels. Reply: one JSON line.
 * One outstanding request. Pixels are integers0..16. Firmware owns buffers. */
#include <stdint.h>
#include "generated/model.h"
#include "neurotile.h"
#include "quant.h"
static void putch(char c) { *(volatile uint32_t *)0x20000000u=(uint8_t)c; }
static void text(const char *s) { while(*s) putch(*s++); }
static int getch(void) {
    uint32_t byte;
    do { byte=*(volatile uint32_t *)0x2000000cu; } while(!(byte&0x80000000u));
    return (int)(byte&255u);
}
static void number(int32_t value) {
    char digits[11];unsigned count=0;
    uint32_t magnitude;
    if(value<0) { putch('-');magnitude=0u-(uint32_t)value; }
    else magnitude=(uint32_t)value;
    do { digits[count++]=(char)('0'+magnitude%10u);magnitude/=10u; } while(magnitude);
    while(count)putch(digits[--count]);
}
int main(void) {
    text("NEUROTILE READY\n");
    for(;;) {
        if(getch()!='N')continue;
        int marker;
        do { marker=getch(); } while(marker=='N');
        if(marker!='T')continue;
        int8_t pixels[NT_INPUTS],hidden[NT_HIDDEN];
        int32_t first[NT_HIDDEN],logits[NT_OUTPUTS];
        unsigned checksum=0,invalid=0;
        for(unsigned i=0;i<NT_INPUTS;++i) {
            unsigned value=(unsigned)getch();checksum^=value;
            if(value>16)invalid=1;
            pixels[i]=(int8_t)value;
        }
        if((unsigned)getch()!=checksum)invalid=1;
        if(invalid) { text("UART_RESULT {\"error\":\"invalid frame\"}\n");continue; }
        *(volatile uint32_t *)0x20000004u=0;
        uint32_t start=nt_clock(),kernel_cycles=0;
        int error=nt_dense_hw(pixels,nt_w1,first,NT_INPUTS,NT_HIDDEN,&kernel_cycles);
        if(error) { text("UART_RESULT {\"error\":\"first layer failed\"}\n");continue; }
        for(unsigned i=0;i<NT_HIDDEN;++i)hidden[i]=nt_activate(first[i]+nt_b1[i],NT_HIDDEN_SHIFT);
        error=nt_dense_hw(hidden,nt_w2,logits,NT_HIDDEN,NT_OUTPUTS,&kernel_cycles);
        if(error) { text("UART_RESULT {\"error\":\"second layer failed\"}\n");continue; }
        unsigned prediction=0;
        for(unsigned i=0;i<NT_OUTPUTS;++i) {
            logits[i]+=nt_b2[i];
            if(logits[i]>logits[prediction])prediction=i;
        }
        uint32_t cycles=nt_clock()-start;
        text("UART_RESULT {\"prediction\":");number((int32_t)prediction);
        text(",\"kernel_cycles\":");number((int32_t)kernel_cycles);
        text(",\"firmware_cycles\":");number((int32_t)cycles);
        text(",\"logits\":[");
        for(unsigned i=0;i<NT_OUTPUTS;++i) { if(i)putch(',');number(logits[i]); }
        text("]}\n");
        *(volatile uint32_t *)0x20000004u=1;
    }
}
