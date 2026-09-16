/* Apple 5G 1.3 edge-based charging-display reconnect tolerance prototype.
 * No charger controls, persistent files, CPU-clock changes or gauge changes.
 * A sustained voltage step is an estimate, not proof of USB-C presence.
 */
typedef unsigned int u32;
typedef unsigned char u8;
#define INLINE static __attribute__((always_inline)) inline
#define CALL(a,t) ((t)(a))
enum { MAGIC=0x4653433b, ALLOCATION=0xc0, RISE=32, FALL=16, NOISE=4,
       PERIOD=250, FRESH=2000, STARTUP=3000, CONFIRM=400, RECONNECT=10000 };
struct observer {
    u32 initialized, first, last, base, stable, pending, since, peak, active, load;
    u32 rearm, released;
};
struct extension { u32 magic, fast, last_native, native; struct observer s; };
typedef char bounded[(sizeof(struct extension)+36<=ALLOCATION)?1:-1];
INLINE u32 now(void) { return CALL(0x11dc,u32 (*)(void))(); }
INLINE void lock(void) { CALL(0xa6540,void (*)(u32))(0x125); }
INLINE void unlock(void) { CALL(0xa687c,void (*)(u32))(0x125); }
INLINE struct extension *state(void) {
    u32 *p=*(u32 *volatile *)0x10822eb4;
    if (!p || *p!=0x670720) return (void *)0;
    struct extension *e=(void *)((u8 *)p+36);
    return e->magic==MAGIC ? e : (void *)0;
}
void *charging_constructor(void *p,u32 owner) {
    void *r=CALL(0x1e080c,void *(*)(void *,u32))(p,owner);
    if (r) {
        struct extension *e=(void *)((u8 *)r+36);
        for (u32 i=0;i<sizeof(*e)/4;i++) ((u32 *)e)[i]=0;
        e->magic=MAGIC;
    }
    return r;
}
/* Explicit time confirmation, not a number of display calls. */
u32 response_step(struct observer *s,u32 raw,u32 t,u32 valid,u32 load) {
    if (!valid || raw>1023) { s->initialized=s->active=s->rearm=0; return 0; }
    if (!s->initialized || t-s->last>FRESH) {
        s->initialized=1;s->first=t;s->last=t;s->base=raw;
        s->active=s->pending=s->rearm=0;s->load=load;return 0;
    }
    s->last=t;
    u32 changed=load!=s->load;s->load=load;
    /* A changing observed load invalidates the remembered voltage pair. */
    if (changed) s->rearm=0;
    if (t-s->first<STARTUP) {
        s->base=raw;s->pending=s->active=s->rearm=0;return 0;
    }
    if (s->active) {
        /* Rebase only sub-threshold load changes. A larger sustained fall
         * invalidates the estimate even if the backlight changes with it. */
        if (changed && raw+FALL>s->peak) { s->peak=raw;s->pending=0; }
        if (raw+FALL<=s->peak) {
            if (!s->pending) { s->pending=1;s->since=t; }
            if (t-s->since>=CONFIRM) {
                s->active=s->pending=0;s->base=raw;s->released=t;
            }
        } else { s->pending=0;if (raw>s->peak) s->peak=raw; }
        return s->active;
    }
    if (t-s->released>RECONNECT) s->rearm=0;
    if (changed) { s->base=raw;s->pending=0;return 0; }
    /* Hold the pre-rise reference across a short ramp. Updating it on each
     * increasing sample would erase a real 1-2 second charging-voltage rise.
     * pending: 0 baseline, 1 rise window, 2 threshold confirmation. */
    if (raw<=s->base || (s->pending && t-s->since>3000)) {
        s->base=raw;s->pending=0;
    } else if (raw>s->base+NOISE || s->pending) {
        /* Ignore tiny positive changes without moving the reference upward.
         * Tracking every +1..4 count increment erased small distributed
         * reconnect rises. The existing three-second rise window still
         * prevents small long-term drift from accumulating without limit. */
        if (!s->pending) { s->pending=1;s->since=t; }
        /* The first edge still needs RISE. Following a confirmed FALL, a
         * short reconnect may return FALL-NOISE counts from a partly relaxed
         * baseline. Require return near the prior high, the same load and
         * the same confirmation time. A timeout/gap/error erases the pair. */
        u32 paired=s->rearm && raw>=s->base+FALL-NOISE && raw+NOISE>=s->peak;
        if (raw>=s->base+RISE || paired) {
            if (s->pending!=2) { s->pending=2;s->stable=t; }
            if (t-s->stable>=CONFIRM) {
                s->active=s->rearm=1;s->pending=0;
                /* Keep the remembered high within its noise allowance.
                 * Otherwise a lower accepted return would lower the fall
                 * reference and prevent the next identical unplug clearing. */
                if (!paired || raw>s->peak) s->peak=raw;
            }
        } else s->pending=1;
    }
    return s->active;
}
void charging_timer(void *owner) {
    struct extension *e=state();
    if (!e) goto native_tick;
    u32 t=now();
    if (!e->fast) {
        CALL(0x151c24,void (*)(void *,u32))((u8 *)owner+0xa0,PERIOD);
        e->fast=1;e->last_native=t-30000;
    }
    u32 l=*(volatile u8 *)0x6000d13c;
    u32 native=!!((l&0x10) || !(l&8));
    u32 load=(l&128)|(*(volatile u8 *)0x6000d034&8);
    u32 raw=0,status=1;
    /* Fresh reads have no dependence on the gauge's activity/sample gate. */
    if (!native) status=CALL(0x265fd8,u32 (*)(u32 *))(&raw);
    lock();
    u32 old=e->s.active;
    response_step(&e->s,raw,t,!status && !native,load);
    /* No gradual-rise fallback: a small long-term recovery cannot be
     * promoted into an indefinitely latched cable-presence estimate. */
    u32 publish=old!=e->s.active || native!=e->native || t-e->last_native>=30000;
    e->native=native;
    if (publish) e->last_native=t;
    unlock();
    if (publish) goto native_tick;
    CALL(0x151694,void (*)(void *))((u8 *)owner+0xa0);
    return;
native_tick:
    CALL(0x1d91dc,void (*)(void *))(owner);
}
u32 charging_display(void *ui) {
    u32 original=CALL(0x1ae774,u32 (*)(void *))(ui);
    struct extension *e=state();
    if (!e) return original;
    lock();
    if (original<4) e->s.initialized=e->s.active=e->s.rearm=0;
    u32 active=e->s.initialized && e->s.active && now()-e->s.last<=FRESH;
    unlock();
    return original>=6 && original<=24 && active ? 0 : original;
}
