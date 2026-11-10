OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { RAM (rwx) : ORIGIN = 0, LENGTH = 128K }
SECTIONS {
    .text : { KEEP(*(.text.start)) *(.text*) *(.rodata*) } > RAM
    . = ALIGN(4);
    .data : { *(.data*) *(.sdata*) } > RAM
    PROVIDE(__global_pointer$ = . + 0x800);
    . = ALIGN(4);
    _bss_start = .;
    .bss (NOLOAD) : { *(.bss*) *(.sbss*) *(COMMON) } > RAM
    . = ALIGN(4);
    _bss_end = .;
    _stack_top = ORIGIN(RAM) + LENGTH(RAM);
    ASSERT(_bss_end < _stack_top - 4096, "Firmware leaves less than 4KiB stack")
}
