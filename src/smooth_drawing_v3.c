/* Exact Apple 1.3 menu slide: retain duration and cached image composition.
 * Request a frame every 17 ms only for the known, visible horizontal menu
 * transition that normally requests 30 ms for 300 ms. No idle timer or CPU
 * policy changes. 17 ms is about 58.8 requested updates per second.
 * This is a requested cadence, not a measured display rate.
 */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

void smooth_drawing(void *timer, u32 interval)
{
    u8 *view = (u8 *)timer - 0xbc;
    if (interval == 30 && *(u32 *)view == 0x673004 &&
        *(u16 *)(view + 0x1c) == 0x5e15 &&
        (*(u32 *)(view + 0x20) & 0x1800) == 0x800 &&
        *(u16 *)(view + 0xa4) <= 1 && *(u32 *)(view + 0xb8) == 300 &&
        ((*(volatile u32 *)0x6000d004 &
          *(volatile u32 *)0x6000d014 &
          *(volatile u32 *)0x6000d024) & 8))
        interval = 17;
    ((void (*)(void *, u32))0x151c24)(timer, interval);
}
