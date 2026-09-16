# Optional smooth menu slides

The smooth-menu prototype keeps Apple's **300 ms transition duration** and
original easing curve. It requests a cached-image position update every
**20 ms**, replacing the normal **30 ms** request for the identified menu
slide. Under an ideal scheduler that gives 15 timed updates instead of 10.
These numbers describe requested updates, not measured LCD frames per second.

Apple already caches the outgoing and incoming menu images, calculates their
intermediate positions from elapsed time, and copies the two images into the
display context. The patch reuses that mechanism. It does not analyze rendered
frames or synthesize text with optical-flow interpolation.

## Battery and performance limits

The patch keeps the original CPU policy, animation duration, drawing code,
display timing and sleep behavior. It adds no background timer. The existing
transition timer stops through Apple's original completion and cancellation
paths. The faster cadence is selected only if the backlight circuit is enabled.

More image copies still cost processing and memory bandwidth: a nominal slide
has five additional timed updates. The cost is confined to those short menu
slides, but **a negligible or zero battery hit has not been demonstrated**.
Audio behavior, visual smoothness, scheduler delays, tearing and physical
battery runtime remain unmeasured. A 20 ms request is not a promise of 50 fps,
and this is not a 60-fps patch. The display transfer path has its own limits;
the [Rockbox Video display driver](https://github.com/Rockbox/rockbox/blob/master/firmware/target/arm/ipod/video/lcd-video.c)
also distinguishes submitted updates from the display controller's completion.

This profile includes reconnect-v3 and replaces the separate optional screen
boost if present. It uses Apple's ordinary CPU policy. A different draw load
could affect the voltage-based USB-C charging estimate; physical coexistence
has not been validated.

## Narrow firmware scope

Only the exact supported iPod Video 5G Apple 1.3 image is accepted. The call to
the timer setter at OS offset `0x2028c8` is redirected to a 164-byte helper.
It changes the requested period only when all these conditions hold:

- Original period: 30 ms; duration: 300 ms.
- Container vtable: `0x673004`; view identifier: `0x5e15`.
- View visible; horizontal direction 0 or 1; ordinary slide mode 0.
- GPIOB3 enabled, configured as output, and active.

Other periods, durations, containers, directions and transition modes pass
through unchanged. The helper calls Apple's original timer setter. It has no
state, allocation or hardware writes. The reconnect-v3 payload remains byte
identical. Neither the easing function nor transition cleanup is patched.

## Validation

Saved-firmware ARM execution, using a privately retained UI graph, passed:

- Four complete slide replays: both directions, original and modified cadence.
- 122 comparisons at matching elapsed times: identical positions and completion
  state, confirming that the easing curve and duration are unchanged in replay.
- Six reversals and sixteen cancellations through the original routines.
- 390 helper scope checks, including screen-off and non-menu cases.

Clock, scheduler, drawing/image copies, synchronization and external UI calls
were simulated. This is isolated routine validation, not a full iPod emulator
or a physical installation. See [machine-readable results](smooth-menu-validation.json).

The installer also validates transformations and restoration using exact saved
images, fresh backups, sector bounds and full-prefix comparisons. These checks
do not establish the physical results above.

Build privately after building reconnect-v3:

```sh
python3 tools/build_smooth.py --input build/osos-reconnect-v3.bin
```

The offline replay requires the exact private snapshot and the `unicorn`
Python package. It is not included in the public download:

```sh
python3 tools/check_smooth_runtime.py --baseline build/osos-reconnect-v3.bin \
  --candidate build/smooth/osos-smooth.bin --snapshot-prefix local/ui-snapshot.bin \
  --report build/smooth/replay.json
```

Candidate OS SHA-256:
`7b882c8985ce5e13f99e47085631d05b888f9086df97bf73a6d6bae364416cf1`

Use the standard installer **from the same release or newer** to remove the
smooth-menu change while retaining reconnect-v3, or that release's restore
launcher to return to original Apple firmware. Older launchers do not recognize
the new profile and will refuse it.
