/* Target a 60 Hz deadline grid for the known 300 ms horizontal menu slide.
 * Apple's elapsed-time easing, image copies, completion and CPU policy stay
 * unchanged. Late callbacks skip elapsed slots, rather than queueing work.
 */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
#define CALL(a,t) ((t)(a))
static __attribute__((noinline)) u32 eligible(u8 *v)
{
    return *(u32 *)v==0x673004 && *(u16 *)(v+0x1c)==0x5e15 &&
        (*(u32 *)(v+0x20)&0x1800)==0x800 && *(u16 *)(v+0xa4)<=1 &&
        *(u32 *)(v+0xb8)==300 &&
        ((*(volatile u32 *)0x6000d004 & *(volatile u32 *)0x6000d014 &
          *(volatile u32 *)0x6000d024)&8);
}
void smooth_prepare(void *timer,u32 interval)
{
    if (interval==30 && eligible((u8 *)timer-0xbc)) interval=17;
    CALL(0x151c24,void (*)(void *,u32))(timer,interval);
}
void smooth_rearm(void *timer)
{
    u8 *v=(u8 *)timer-0xbc;
    u32 interval=*((u32 *)timer+1);
    if (v[0xb0] && interval && interval<=30 && eligible(v)) {
        u32 now;
        CALL(0xccebc,void (*)(u32 *))(&now);
        u32 elapsed=CALL(0x82694,u32 (*)(u32,u32))(now-*(u32 *)(v+0xb4),1000);
        u32 delay=1;
        if (elapsed<300) {
            u32 slot=CALL(0x82694,u32 (*)(u32,u32))(elapsed*3,50)+1;
            u32 next=CALL(0x82694,u32 (*)(u32,u32))(slot*50+2,3);
            delay=next-elapsed;
        }
        if (interval!=delay) CALL(0x151c24,void (*)(void *,u32))(timer,delay);
    }
    CALL(0x151694,void (*)(void *))(timer);
}
