.section .text
.global nn_shl_c

nn_shl_c:
    mov	x9, x0
    mov	x0, x4
    cmp	x2, #0x0
    b.le	L462c
    mov	w10, #0x3f
    sub	w8, w3, #0x40
    sub	w10, w10, w3
    mov	x6, #0x0
    nop
L45f8:
    ldr	x5, [x1, x6, lsl #3]
    cmp	w8, #0x0
    lsr	x4, x5, #1
    lsl	x7, x5, x3
    csel	x7, xzr, x7, ge
    lsl	x5, x5, x8
    add	x0, x0, x7
    str	x0, [x9, x6, lsl #3]
    add	x6, x6, #0x1
    lsr	x4, x4, x10
    csel	x0, x5, x4, ge
    cmp	x2, x6
    b.ne	L45f8
L462c:
    ret