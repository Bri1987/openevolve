.section .text
.global __rshift_D2A

__rshift_D2A:
add x8, x0, #0x18
ldrsw x13, [x0, #20]
asr w10, w1, #5
mov x11, x8
cmp w10, w13
b.ge .Ltmp8  // b.tcont
add x9, x8, x13, lsl #2
sxtw x14, w10
add x10, x8, w10, sxtw #2
ands w11, w1, #0x1f
b.eq .Ltmp1  // b.none
ldr w12, [x10], #4
cmp x10, x9
lsr w12, w12, w11
b.cs .Ltmp2  // b.hs, b.nlast
mov w10, #0x20 // #32
lsl x13, x14, #2
sub w10, w10, w11
add x14, x0, #0x1c
.Ltmp0:
ldr w15, [x14, x13]
lsl w15, w15, w10
orr w12, w15, w12
stur w12, [x14, #-4]
ldr w12, [x14, x13]
add x14, x14, #0x4
add x15, x14, x13
cmp x15, x9
lsr w12, w12, w11
b.cc .Ltmp0  // b.lo, b.ul, b.last
sub x9, x14, #0x4
b .Ltmp3
.Ltmp1:
lsl x12, x14, #2
add x13, x0, x13, lsl #2
add x11, x12, x0
add x15, x13, #0x18
add x14, x11, #0x1c
cmp x14, x15
csel x13, x14, x15, hi // hi = pmore
sub x13, x13, x11
sub x13, x13, #0x19
cmp x13, #0x1c
b.cs .Ltmp4  // b.hs, b.nlast
mov x11, x8
b .Ltmp7
.Ltmp2:
mov x9, x8
.Ltmp3:
cmp w12, #0x0
str w12, [x9]
cset w10, ne // ne = any
add x11, x9, w10, uxtw #2
b .Ltmp8
.Ltmp4:
cmp x14, x15
add x16, x0, #0x18
csel x14, x14, x15, hi // hi = pmore
sub x14, x14, x11
sub x14, x14, #0x19
and x14, x14, #0xfffffffffffffffc
add x15, x14, x12
add x15, x15, x0
add x15, x15, #0x1c
cmp x15, x16
b.ls .Ltmp5  // b.plast
add x14, x14, x0
add x15, x11, #0x18
mov x11, x8
add x14, x14, #0x1c
cmp x15, x14
b.cc .Ltmp7  // b.lo, b.ul, b.last
.Ltmp5:
lsr x11, x13, #2
mov x16, x0
add x13, x11, #0x1
and x14, x13, #0x7ffffffffffffff8
lsl x11, x14, #2
add x15, x0, x11
add x10, x10, x11
add x11, x15, #0x18
mov x15, x14
.Ltmp6:
add x17, x16, x12
subs x15, x15, #0x8
ldur q0, [x17, #24]
ldur q1, [x17, #40]
add x17, x16, #0x20
stur q0, [x16, #24]
stur q1, [x16, #40]
mov x16, x17
b.ne .Ltmp6  // b.any
cmp x13, x14
b.eq .Ltmp8  // b.none
.Ltmp7:
ldr w12, [x10], #4
cmp x10, x9
str w12, [x11], #4
b.cc .Ltmp7  // b.lo, b.ul, b.last
.Ltmp8:
sub x9, x11, x8
lsr x9, x9, #2
str w9, [x0, #20]
cbz w9, .Ltmp9
ret
.Ltmp9:
str wzr, [x8]
ret
