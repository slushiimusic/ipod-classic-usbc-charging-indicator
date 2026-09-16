# Optional screen-lit responsiveness profile

The optional profile requests Apple's existing maximum clock while the
backlight circuit is enabled. It returns to Apple's ordinary policy when the
circuit is disabled. This may reduce CPU-limited menu latency; it does not
remove storage waits, resize the music database, or change rendering cadence.

The exact saved Apple 1.3 configuration requests a 26,000 kHz floor and an
80,000 kHz ceiling. The native policy already raises demand for storage
activity and several application states. Increasing the ceiling is not needed
to try a more responsive screen-lit policy. These are software clock requests,
not physical frequency measurements.

## Implementation

The original clamp at OS offset `0xfe240` ends in a branch at `0xfe264` to the
final policy at `0x99c`. The optional profile redirects that branch to a 96-byte
helper after the unchanged reconnect-v3 payload. The helper checks GPIOB3's
enable, output-enable and output state. If active and the saved maximum is
between 26,000 and 80,000 kHz, it sets the current demand to that maximum and
calls the original final policy, preserving its overrides and return value.
The original clock driver, configuration defaults and persistent preferences
are unchanged. No new timers or direct clock-register writes are introduced.

The backlight signal is corroborated by the primary
[Rockbox Video backlight driver](https://github.com/Rockbox/rockbox/blob/master/firmware/target/arm/ipod/backlight-nano_video.c),
and GPIO addresses by its
[PortalPlayer register definitions](https://github.com/Rockbox/rockbox/blob/master/firmware/export/pp5020.h).
The Apple policy was traced in the exact, hash-verified original image.

## Validation and limits

Saved-image ARM execution passed 384 combinations of demand, GPIO states and
simulated external activity flags, four saved-ceiling guard cases and four
original clock-driver cases. Screen-dark results match the original policy;
screen-lit results use the saved maximum within the guard range. The existing
charging payload and clock-driver bytes remain identical to reconnect-v3.

These are isolated software checks with simulated hardware and synchronization,
not a full-device emulator, physical boot, frame-rate measurement or battery
test. The new profile has not been installed or physically validated by this
project. Keeping the maximum speed while the screen is lit may use more energy,
and the changed load may affect the voltage-based charging estimate.

A 60 Hz panel does not establish that Apple renders menus at 60 frames per
second. This profile does not alter LCD timing or claim 60 fps. No zero-cost
performance improvement or guaranteed faster song changes is claimed.

Profile OS SHA-256:
`253fe5b2df1ace5d3c871ef96dcc29d0cb86401a4e107a29c7e9f957be4c38ec`

The standard installer returns to reconnect-v3 with original CPU policy.
The restore launcher returns to exact original Apple 1.3. Both accept this
profile, save fresh recovery copies, and verify their planned writes.

Build privately after building reconnect-v3:

```sh
python3 tools/build_responsive.py --input build/osos-reconnect-v3.bin
```
