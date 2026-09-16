# Optional smooth menu slides, v0.3.0

The optional profile keeps Apple's **300 ms transition and easing curve**.
It requests cached-image positions on a 60 Hz deadline grid: 17, 34, 50, 67,
84, 100 ms, continuing through 300 ms. An ideal scheduler produces **18 timed
updates**, versus 15 in [the previous profile](smooth-menus-v1.md) and 10 in
stock firmware. This is not measured LCD fps or optical-flow frame generation.

Late callbacks select the next future slot. They do not build up a queue of
missed frames. Apple's existing start, elapsed-time position calculation,
image copies, completion and cancellation remain in use.

## Battery and scope

CPU policy, transition duration, display transfer code and sleep policy stay
unchanged. No background timer is added. More image copies and deadline
calculations add work during each slide. **Battery impact, visual smoothness,
audio behavior, tearing and physical frame rate are unmeasured.** The earlier
profile felt snappier to its user, but that was not a measured result.

This profile includes the [v4 screen-on charging correction](screen-on-correction.md)
and removes the legacy screen-lit CPU boost. Drawing load can affect a
voltage-based charging estimate; the combined build still needs physical
validation. It does not fix USB-C wake from deep sleep.

## Firmware implementation

Only the exact supported Video 5G Apple 1.3 image is accepted. A 416-byte helper
is appended to the v4 charging payload. It changes the timer setup call at
`0x2028c8` and rearm calls at `0x2028dc`, `0x202ebc` and `0x20300c`.

Eligibility requires the known visible horizontal menu container (`0x673004`,
view `0x5e15`), ordinary mode, direction 0 or 1, a 300 ms duration, and an enabled
backlight output. Setup changes only an original 30 ms interval. Rearm adjusts
intervals of 1–30 ms only while that eligible transition is active. Other cases
pass through to Apple's existing timer calls. If eligibility changes during a
slide, the last interval can persist until Apple's normal completion stops it.

The helper has no independent state or allocations. Native unsigned division
and clock routines calculate future deadlines. No clock, charger or wake-source
register is changed. The charging payload is byte-identical to v4.

## Validation

Saved-firmware ARM execution passed:

- Both directions: 18 requested updates ending at 300 ms.
- 244 equal-time geometry comparisons, including clock wraparound.
- Five delayed-callback scenarios, with missed slots skipped.
- Six reversals and eight cancellations through original routines.
- 485 scope checks, including screen-off and non-menu cases.

Clock, scheduling, external UI and image copies were simulated. This is isolated
routine validation, not a full iPod emulator or proof of physical performance.
See [results](smooth-v2-validation.json).

Build privately with Clang supporting ARMv4T and the dependencies in
`requirements.txt`:

```sh
python3 tools/build_reconnect_v4.py --original local/apple-original.bin
python3 tools/build_smooth_v2.py --input build/reconnect-v4/osos-reconnect-v4.bin
```

The replay also needs the exact privately retained UI snapshot and v3 baseline;
these Apple images are not included in public downloads:

```sh
python3 tools/check_smooth_v2.py --baseline build/osos-reconnect-v3.bin \
  --candidate build/smooth-v2/osos-smooth-v2.bin --snapshot-prefix local/ui-snapshot.bin \
  --report build/smooth-v2/replay.json
```

Candidate OS SHA-256:
`c2d63d4b441956fc336fd9f84806f862773c4c1370fa847a0d3d82366853c849`

Use a **v0.3.0 or newer** standard installer to remove menu pacing while keeping
the v4 charging correction, or its restore launcher to return to original Apple
firmware. Older launchers refuse the new hashes.
