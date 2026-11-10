/* Small freestanding runtime: compiler-generated aggregate copies/initializers. */
#include <stddef.h>
void *memcpy(void *destination, const void *source, size_t length) {
    unsigned char *d=destination;
    const unsigned char *s=source;
    for(size_t i=0;i<length;++i) d[i]=s[i];
    return destination;
}
void *memset(void *destination, int value, size_t length) {
    unsigned char *d=destination;
    for(size_t i=0;i<length;++i) d[i]=(unsigned char)value;
    return destination;
}
