.section .text
.global nn_shl_c

nn_shl_c:
    // x0 = dest pointer, x1 = src pointer, x2 = count, x3 = shift amount, x4 = carry-in
    // Save dest pointer and initialize carry
    mov     x9, x0
    mov     x0, x4
    
    // Early exit if count <= 0
    cmp     x2, #0
    b.le    L_exit
    
    // Handle shift == 0 separately for better performance
    cbz     x3, L_zero_shift
    
    // Precompute shift values using 64-bit registers
    mov     x10, #64
    sub     x10, x10, x3         // 64 - shift
    sub     x8, x3, #64          // shift - 64
    
    // Check if shift >= 64
    cmp     x8, #0
    b.ge    L_large_shift
    
    // For 0 < shift < 64, proceed to normal loop
    
    // Main loop for normal shifts (0 < shift < 64)
    // Unroll 2x for better performance
    lsr     x11, x2, #1          // count/2 iterations
    cbz     x11, L_normal_single
    
L_normal_loop:
    // First element
    ldr     x5, [x1], #8
    lsl     x7, x5, x3           // src[i] << shift
    add     x0, x0, x7           // dest[i] = (src[i] << shift) + carry
    str     x0, [x9], #8
    lsr     x0, x5, x10          // carry = src[i] >> (64 - shift)
    
    // Second element
    ldr     x5, [x1], #8
    lsl     x7, x5, x3
    add     x0, x0, x7
    str     x0, [x9], #8
    lsr     x0, x5, x10
    
    subs    x11, x11, #1
    b.ne    L_normal_loop
    
    // Handle odd count
    tbz     x2, #0, L_exit
    
L_normal_single:
    ldr     x5, [x1], #8
    lsl     x7, x5, x3
    add     x0, x0, x7
    str     x0, [x9], #8
    lsr     x0, x5, x10
    ret

// Zero shift case
L_zero_shift:
    // When shift == 0, dest[i] = src[i] + carry
    // The carry propagates through additions
    // Unroll 2x for better performance
    lsr     x11, x2, #1          // count/2 iterations
    cbz     x11, L_zero_single

L_zero_loop:
    // First element
    ldr     x5, [x1], #8
    add     x0, x0, x5
    str     x0, [x9], #8
    // Carry for next is 0 because shift == 0
    mov     x0, xzr
    
    // Second element
    ldr     x5, [x1], #8
    add     x0, x0, x5
    str     x0, [x9], #8
    mov     x0, xzr
    
    subs    x11, x11, #1
    b.ne    L_zero_loop
    
    // Handle odd count
    tbz     x2, #0, L_exit
    
L_zero_single:
    ldr     x5, [x1], #8
    add     x0, x0, x5
    str     x0, [x9], #8
    mov     x0, xzr
    ret

L_large_shift:
    // shift >= 64: all bits shift out, carry propagates
    // x8 = shift - 64
    lsr     x11, x2, #1          // count/2 iterations
    cbz     x11, L_large_single
    
L_large_loop:
    // First element
    ldr     x5, [x1], #8
    str     x0, [x9], #8         // Store current carry as dest[i]
    lsl     x0, x5, x8           // New carry = src[i] << (shift - 64)
    
    // Second element
    ldr     x5, [x1], #8
    str     x0, [x9], #8
    lsl     x0, x5, x8
    
    subs    x11, x11, #1
    b.ne    L_large_loop
    
    // Handle odd count
    tbz     x2, #0, L_exit
    
L_large_single:
    ldr     x5, [x1], #8
    str     x0, [x9], #8
    lsl     x0, x5, x8
    ret



L_exit:
    ret