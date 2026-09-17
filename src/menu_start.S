/* Use Apple's existing visible-screen capture for idle horizontal menus.
 * The original input arguments, register values and prologue are preserved.
 * A running transition, another view class or another mode uses stock behavior.
 */
.syntax unified
.arm
.text
.global capture_menu_start
.type capture_menu_start,%function
capture_menu_start:
    push {r1,r2}
    ldr r1,[r0]
    ldr r2,menu_class
    cmp r1,r2
    bne original_start
    ldrb r1,[r0,#0xb0]
    cmp r1,#0
    bne original_start
    cmp r3,#1
    bhi original_start
    ldr r1,[sp,#8]
    cmp r1,#0
    bne original_start
    mov r1,#1
    str r1,[sp,#20]
original_start:
    pop {r1,r2}
    push {r4,r5,r6,r7,r8,r9,r10,r11,lr}
    ldr pc,original_continuation
menu_class: .word 0x673004
original_continuation: .word 0x2023a8
.size capture_menu_start,.-capture_menu_start
