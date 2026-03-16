.section:
L0:
L1:
L2:
mov x9, x0
cbz w3, L12
mov x0, x4
mov w10, 64
sub w10, w10, w3
lsr x11, x2, 2
cbz x11, L4
L3:
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
b.ne L3
L4:
ands x11, x2, 3
cbz x11, L6
L5:
ldr x5, [x1], 8
lsl x7, x5, x3
add x7, x7, x0
str x7, [x9], 8
lsr x0, x5, x10
subs x11, x11, 1
b.ne L5
L6:
ret
L7:
sub w8, w3, 64
lsr x11, x2, 2
L8:
mov x0, 0
ldr x5, [x1], 8
str x0, [x9], 8
lsl x0, x5, x8
ldr x5, [x1], 8
str x0, [x9], 8
lsl x0, x5, x8
ldr x5, [x1], 8
str x0, [x9], 8
lsl x0, x5, x8
ldr x5, [x1], 8
str x0, [x9], 8
lsl x0, x5, x8
subs x11, x11, 1
b.ne L15
L9:
ands x11, x2, 3
cbz x11, L11
L10:
ldr x5, [x1], 8
str x0, [x9], 8
lsl x0, x5, x8
subs x11, x11, 1
b.ne L10
L11:
ret
L12:
mov x0, x4
ldr x5, [x1], 8
add x7, x5, x0
str x7, [x9], 8
subs x2, x2, 1
lsr x11, x2, 2
cbz x11, L14
L13:
ldr x5, [x1], 8
str x5, [x9], 8
ldr x5, [x1], 8
str x5, [x9], 8
ldr x5, [x1], 8
str x5, [x9], 8
ldr x5, [x1], 8
str x5, [x9], 8
subs x11, x11, 1
b.ne L13
L14:
ands x11, x2, 3
cbz x11, L16
L15:
ldr x5, [x1], 8
str x5, [x9], 8
subs x11, x11, 1
b.ne L15
L16:
ret
L17:
mov x0, x4
ret
