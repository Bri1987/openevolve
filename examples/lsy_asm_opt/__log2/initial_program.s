.section .text
.global __log2

__log2:
cmp w0, #0x2
b.cc .Ltmp1  // b.lo, b.ul, b.last
mov w1, w0
mov w0, wzr
mov w2, #0x1 // #1
.Ltmp0:
lsl w2, w2, #1
add w0, w0, #0x1
cmp w2, w1
b.cc .Ltmp0  // b.lo, b.ul, b.last
ret
.Ltmp1:
mov w0, wzr
ret