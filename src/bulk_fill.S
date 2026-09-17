/* Pixel-exact bulk background fill for Apple Video 5G 1.3.
 * Keep masked edge words and native row stride. No clock or timer changes.
 */
.syntax unified
.arch armv4t
.arm
.text
.balign 4
fill_row:
 ldr r1,[r4]
 and r2,r0,r6
 bic r1,r1,r6
 orr r1,r1,r2
 str r1,[r4]
 add r1,r4,#4
 subs r2,r8,#1
 ble fill_edge
 mov r3,r0
fill_pairs:
 subs r2,r2,#2
 stmiage r1!,{r0,r3}
 bgt fill_pairs
 strmi r0,[r1],#4
fill_edge:
 ldr r2,[r1]
edge_branch:
 b edge_branch
fill_resume:
 add r4,r1,r10
 sub r5,r5,#1
 str r2,[r1]
fill_test:
 cmp r5,#0
 bne fill_row
 pop {r3-r11,pc}
.section .edge,"ax",%progbits
edge:
 and r3,r0,r7
 bic r2,r2,r7
 orr r2,r2,r3
resume_branch:
 b resume_branch
