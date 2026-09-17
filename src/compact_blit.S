/* Exact Apple Video 5G 1.3 pixel-copy loops. No timers or clock changes.
 * Keep Apple's clipping, edge masks, overlap direction, and notifications.
 */
.syntax unified
.arch armv4t
.arm
.text
.balign 4
.global copy_aligned_words
.type copy_aligned_words,%function
copy_aligned_words:
    /* The scalar guard also handles an empty span after saving registers. */
    push {r2-r4,r7-r9,r12,lr}
    /* Forward overlap under one block must retain scalar read/write order. */
    sub r2, r5, r6
    cmp r2, #32
    blo scalar_words
block_words:
    sub r2, r10, r0
    cmp r2, #8
    blt scalar_words
    ldmia r6!, {r1-r4,r7-r9,r12}
    stmia r5!, {r1-r4,r7-r9,r12}
    mov r1, r12
    add r0, r0, #8
    b block_words
scalar_words:
    cmp r0, r10
    ldrlt r1, [r6], #4
    addlt r0, r0, #1
    strlt r1, [r5], #4
    blt scalar_words
    pop {r2-r4,r7-r9,r12,lr}
aligned_done:
    ldr pc, =0x0011db7c
.size copy_aligned_words, .-copy_aligned_words

.global copy_halfword_shift
.type copy_halfword_shift,%function
copy_halfword_shift:
    cmp r5, #16
    bne shifted_fallback
    cmp r0, r10
    bge shifted_empty
    ldr r3, [sp, #8]
    /* Convert Apple's saved big-endian word once at each end of the row. */
    eor r2, r3, r3, ror #16
    bic r2, r2, #0x00ff0000
    mov r3, r3, ror #8
    eor r3, r3, r2, lsr #8
halfword_words:
    ldr r1, [r11], #4
    mov r2, r3, lsr #16
    orr r2, r2, r1, lsl #16
    str r2, [r9], #4
    mov r3, r1
    add r0, r0, #1
    cmp r0, r10
    blt halfword_words
    eor r2, r3, r3, ror #16
    bic r2, r2, #0x00ff0000
    mov r3, r3, ror #8
    eor r3, r3, r2, lsr #8
    str r3, [sp, #8]
shifted_empty:
    str r0, [sp, #4]
    ldr pc, =0x0011dc54
shifted_fallback:
    ldr pc, =0x0011dc48
.size copy_halfword_shift, .-copy_halfword_shift
.ltorg
