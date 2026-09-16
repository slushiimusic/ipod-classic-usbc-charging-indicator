/* Optional screen-lit response profile for exact Apple Video 5G firmware 1.3.
 * Uses the existing policy ceiling and original clock driver. No PLL writes,
 * persistent preference edits, extra timer, or screen-off frequency floor.
 * Battery impact and physical menu/track latency have not been measured.
 */
typedef unsigned int u32;
u32 responsive_policy(u32 *demand) {
    u32 enabled=*(volatile u32 *)0x6000d004;
    u32 output=*(volatile u32 *)0x6000d014;
    u32 value=*(volatile u32 *)0x6000d024;
    u32 ceiling=*(volatile u32 *)0x10874764;
    if ((enabled & output & value & 8) && ceiling>=26000 && ceiling<=80000)
        *demand=ceiling;
    /* Preserve Apple's final overrides, rounding and return value. */
    return ((u32 (*)(u32 *))0x99c)(demand);
}
