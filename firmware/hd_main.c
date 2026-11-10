/* RV32IM benchmark: the real MNIST sample and a synthetic horizontal mirror.
 * The mirror is a second correctness workload, not a labeled accuracy sample. */
#include <stdint.h>
#include "generated/mnist_model.h"
#include "quant.h"
#include "hd_driver.h"
static void putch(char c){*(volatile uint32_t *)0x20000000u=(uint8_t)c;}
static void text(const char *s){while(*s)putch(*s++);}
static void number(int32_t value){
    char digits[11];unsigned count=0;
    uint32_t magnitude;
    if(value<0){putch('-');magnitude=0u-(uint32_t)value;}else magnitude=(uint32_t)value;
    do{digits[count++]=(char)('0'+magnitude%10u);magnitude/=10u;}while(magnitude);
    while(count)putch(digits[--count]);
}
static int failure(int error){
    text("HD_SOC_RESULT {\"passed\":false,\"error\":");number(error);text("}\n");
    *(volatile uint32_t *)0x20000004u=2;return 1;
}
int main(void){
    int8_t inputs[2][HD_INPUTS],ref_hidden[2][HD_HIDDEN],hw_hidden[2][HD_HIDDEN];
    int32_t ref1[2][HD_HIDDEN],hw1[2][HD_HIDDEN];
    int32_t ref2[2][HD_OUTPUTS],hw2[2][HD_OUTPUTS];
    unsigned predictions[2]={0,0};
    for(unsigned i=0;i<HD_INPUTS;++i){
        inputs[0][i]=hd_sample_input[i];
        unsigned row=i/28,col=i%28;
        inputs[1][i]=hd_sample_input[row*28+(27-col)];
    }
    uint32_t start=nt_clock();
    for(unsigned row=0;row<2;++row){
        nt_dense_ref(inputs[row],hd_w1,ref1[row],HD_INPUTS,HD_HIDDEN);
        for(unsigned j=0;j<HD_HIDDEN;++j)ref_hidden[row][j]=nt_activate(ref1[row][j]+hd_b1[j],HD_HIDDEN_SHIFT);
        nt_dense_ref(ref_hidden[row],hd_w2,ref2[row],HD_HIDDEN,HD_OUTPUTS);
        for(unsigned j=0;j<HD_OUTPUTS;++j)ref2[row][j]+=hd_b2[j];
    }
    uint32_t software_cycles=nt_clock()-start;
    uint32_t kernel_cycles=0,macs=0,tiles=0;
    start=nt_clock();
    int error=hd_dense_hw_batch(&inputs[0][0],hd_w1,&hw1[0][0],2,HD_INPUTS,HD_HIDDEN,&kernel_cycles,&macs,&tiles);
    if(error)return failure(error);
    for(unsigned row=0;row<2;++row)for(unsigned j=0;j<HD_HIDDEN;++j)
        hw_hidden[row][j]=nt_activate(hw1[row][j]+hd_b1[j],HD_HIDDEN_SHIFT);
    error=hd_dense_hw_batch(&hw_hidden[0][0],hd_w2,&hw2[0][0],2,HD_HIDDEN,HD_OUTPUTS,&kernel_cycles,&macs,&tiles);
    if(error)return failure(error);
    for(unsigned row=0;row<2;++row)for(unsigned j=0;j<HD_OUTPUTS;++j)hw2[row][j]+=hd_b2[j];
    uint32_t accelerated_cycles=nt_clock()-start;
    for(unsigned row=0;row<2;++row){
        for(unsigned j=0;j<HD_HIDDEN;++j)
            if(hw1[row][j]!=ref1[row][j] || hw_hidden[row][j]!=ref_hidden[row][j])return failure(3);
        for(unsigned j=0;j<HD_OUTPUTS;++j){
            if(hw2[row][j]!=ref2[row][j])return failure(4);
            if(hw2[row][j]>hw2[row][predictions[row]])predictions[row]=j;
        }
    }
    text("HD_SOC_RESULT {\"passed\":true,\"batch_size\":2,\"second_input\":\"synthetic horizontal mirror\",\"predictions\":[");
    number((int32_t)predictions[0]);putch(',');number((int32_t)predictions[1]);
    text("],\"software_cycles\":");number((int32_t)software_cycles);
    text(",\"accelerated_cycles\":");number((int32_t)accelerated_cycles);
    text(",\"kernel_cycles\":");number((int32_t)kernel_cycles);
    text(",\"macs\":");number((int32_t)macs);
    text(",\"tiles\":");number((int32_t)tiles);
    text(",\"logits\":[");
    for(unsigned row=0;row<2;++row){if(row)putch(',');putch('[');
        for(unsigned j=0;j<HD_OUTPUTS;++j){if(j)putch(',');number(hw2[row][j]);}putch(']');}
    text("]}\n");*(volatile uint32_t *)0x20000004u=1;return 0;
}
