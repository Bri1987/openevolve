.section .text
.global nn_add_mc

nn_add_mc:
    mov	x7, x0
    mov	x0, x4
    cmp	x3, #0x0
    b.le	L4300
    mov	x6, #0x0
L42d8:
    ldr	x4, [x2, x6, lsl #3]
    ldr	x5, [x1, x6, lsl #3]
    adds	x5, x5, x4
    cset	x4, cs
    adds	x5, x5, x0
    str	x5, [x7, x6, lsl #3]
    add	x6, x6, #0x1
    cinc	x0, x4, cs
    cmp	x3, x6
    b.ne	L42d8
L4300:
    ret