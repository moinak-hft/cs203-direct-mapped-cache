/* Native C 28x28 reference. stdin: batch count1/2 followed by784 pixels/image. */
#include <stdio.h>
#include <stdint.h>
#include "generated/mnist_model.h"
#include "quant.h"
int main(void) {
    unsigned batch;
    int8_t input[2][HD_INPUTS],hidden[2][HD_HIDDEN];
    int32_t first[HD_HIDDEN],logits[2][HD_OUTPUTS];
    unsigned predictions[2]={0,0};
    if(scanf("%u",&batch)!=1 || batch<1 || batch>2)return 2;
    for(unsigned row=0;row<batch;++row)for(unsigned i=0;i<HD_INPUTS;++i) {
        int value;
        if(scanf("%d",&value)!=1 || value<0 || value>16)return 2;
        input[row][i]=(int8_t)value;
    }
    for(unsigned row=0;row<batch;++row) {
        nt_dense_ref(input[row],hd_w1,first,HD_INPUTS,HD_HIDDEN);
        for(unsigned j=0;j<HD_HIDDEN;++j)hidden[row][j]=nt_activate(first[j]+hd_b1[j],HD_HIDDEN_SHIFT);
        nt_dense_ref(hidden[row],hd_w2,logits[row],HD_HIDDEN,HD_OUTPUTS);
        for(unsigned j=0;j<HD_OUTPUTS;++j) {
            logits[row][j]+=hd_b2[j];
            if(logits[row][j]>logits[row][predictions[row]])predictions[row]=j;
        }
    }
    printf("{\"batch_size\":%u,\"predictions\":[",batch);
    for(unsigned row=0;row<batch;++row)printf("%s%u",row?",":"",predictions[row]);
    printf("],\"hidden\":[");
    for(unsigned row=0;row<batch;++row) {
        printf("%s[",row?",":"");
        for(unsigned j=0;j<HD_HIDDEN;++j)printf("%s%d",j?",":"",(int)hidden[row][j]);
        putchar(']');
    }
    printf("],\"logits\":[");
    for(unsigned row=0;row<batch;++row) {
        printf("%s[",row?",":"");
        for(unsigned j=0;j<HD_OUTPUTS;++j)printf("%s%ld",j?",":"",(long)logits[row][j]);
        putchar(']');
    }
    puts("]}");return 0;
}
