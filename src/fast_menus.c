/* Shorten the known horizontal menu slide from 300 ms to 150 ms.
 * Ten requested updates at 15 ms preserve the stock ideal update count.
 * Keep Apple's easing, drawing, cleanup, CPU and sleep policies.
 */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

/* The patched entry's original first instruction, then its continuation. */
__attribute__((naked, noinline))
void original_menu_start(u8 *view, void *outgoing, void *incoming, u32 direction,
                         u32 mode, u32 interval, u32 duration, u32 flag_a, u32 flag_b)
{
    __asm__ volatile("push {r4-r11, lr}\n"
                     "ldr pc, [pc, #-4]\n"
                     ".word 0x2023a8\n");
}

void fast_menu_start(u8 *view, void *outgoing, void *incoming, u32 direction,
                     u32 mode, u32 interval, u32 duration, u32 flag_a, u32 flag_b)
{
    if (*(u32 *)view == 0x673004 && *(u16 *)(view + 0x1c) == 0x5e15 &&
        (*(u32 *)(view + 0x20) & 0x1800) == 0x800 &&
        direction <= 1 && mode == 0 && interval == 30 && duration == 300) {
        interval = 15;
        duration = 150;
    }
    original_menu_start(view, outgoing, incoming, direction, mode, interval,
                        duration, flag_a, flag_b);
}
