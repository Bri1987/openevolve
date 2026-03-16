.section:
L0:
L1:
cmp x2, 0
b.le L12
mov x9, x0
cbz w3, L8
mov x0, x4
cmp w3, 64
b.ge L4
mov w10, 64
sub w10, w10, w3
lsr x11, x2, 1
cbz x11, L3
L2:
ldr x5, [x1], 8
lsl x7, x5, x3
add x7, x7, x0
str x7, [x9], 8
lsr x0, x5, x10
ldr x5, [x1], 8
lsl x7, x5, x3
add x7, x7, x0
str x7, [x9], 8
lsr x0, x5, x10
subs x11, x11, 1
b.ne L2
tst x2, 1
b.eq L7
L3:
ldr x5, [x1]
lsl x7, x5, x3
add x7, x7, x0
str x7, [x9]
lsr x0, x5, x10
ret
L4:
sub w8, w3, 64
lsr x11, x2, 1
cbz x11, L6
L5:
ldr x5, [x1], 8
str x0, [x9], 8
lsl x0, x5, x8
ldr x5, [x1], 8
str x0, [x9], 8
lsl x0, x5, x8
subs x11, x11, 1
b.ne L5
tst x2, 1
b.eq L7
L6:
ldr x5, [x1]
str x0, [x9]
lsl x0, x5, x8
L7:
ret
L8:
mov x0, x4
ldr x5, [x1], 8
add x7, x5, x0
str x7, [x9], 8
mov x0, 0
subs x2, x2, 1
b.le L11
lsr x11, x2, 1
cbz x11, L10
L9:
ldr x5, [x1], 8
str x5, [x9], 8
ldr x5, [x1], 8
str x5, [x9], 8
subs x11, x11, 1
b.ne L9
tst x2, 1
b.eq L11
L10:
ldr x5, [x1], 8
str x5, [x9], 8
L11:
ret
L12:
mov x0, x4
ret
