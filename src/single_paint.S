/* Experimental Apple Video 5G 1.3 menu preparation. Keep the native capture,
 * cadence eligibility, duration and power policy. The paint gate skips only a
 * pending, active, captured horizontal slide of the exact known class.
 * Mixed ARM/Thumb code uses BX explicitly for ARMv4T interworking.
 */
.syntax unified
.arch armv4t
.text
.arm
.balign 4
.global cadence
cadence:
 add ip,pc,#1
 bx ip
.thumb
.thumb_func
cadence_thumb:
 push {r4,lr}
 movs r4,r0
 subs r4,#0xbc
 cmp r1,#30
 bne cadence_done
 ldr r2,[r4]
 ldr r3,cls_t
 cmp r2,r3
 bne cadence_done
 ldrh r2,[r4,#0x1c]
 ldr r3,id_t
 cmp r2,r3
 bne cadence_done
 ldr r2,[r4,#0x20]
 lsls r2,r2,#19
 lsrs r2,r2,#30
 cmp r2,#1
 bne cadence_done
 adds r4,#0xa4
 ldrh r2,[r4]
 cmp r2,#1
 bhi cadence_done
 ldr r2,[r4,#20]
 subs r2,#255
 subs r2,#45
 bne cadence_done
 ldr r4,gpio_t
 ldr r2,[r4]
 ldr r3,[r4,#16]
 ands r2,r3
 ldr r3,[r4,#32]
 ands r2,r3
 lsls r2,r2,#28
 bpl cadence_done
 movs r1,#17
cadence_done:
 pop {r4}
 pop {r3}
 mov lr,r3
 ldr r3,timer_t
 bx r3
.balign 4
cls_t: .word 0x673004
id_t: .word 0x5e15
gpio_t: .word 0x6000d004
timer_t: .word 0x151c24
.arm
.balign 4
.global capture
capture:
 push {r4-r11,lr}
 ldr r4,[r0]
 ldr r5,cls_a
 cmp r4,r5
 ldrbeq r4,[r0,#0xb0]
 cmpeq r4,#0
 bne capture_done
 cmp r3,#1
 ldrls r4,[sp,#36]
 cmpls r4,#0
 moveq r4,#1
 streq r4,[sp,#48]
capture_done:
 /* Builder resolves this branch to native 0x2023a8. */
 b capture_done
cls_a: .word 0x673004
.global paint_gate
paint_gate:
 ldr r4,transition_state
 ldrb r5,[r4,#1]
 cmp r5,#0
 ldrne r4,[r4,#4]
 cmpne r4,#0
 bxeq r2
 ldr r5,[r4]
 ldr r6,cls_a
 cmp r5,r6
 bxne r2
 ldrh r5,[r4,#0xa4]
 cmp r5,#1
 ldrbls r5,[r4,#0xb0]
 cmpls r5,#1
 ldrbeq r5,[r4,#0x131]
 cmpeq r5,#1
 bxeq lr
 bx r2
transition_state: .word 0x1082320c
