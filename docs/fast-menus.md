# Faster menu slides

The Faster Menus profile changes the identified horizontal menu slide from
**300 ms to 150 ms**. It retains Apple's easing curve and cached-image drawing.
It requests a position update every 15 ms, giving ten timed updates under an
ideal scheduler—the same count as stock's 30 ms cadence over 300 ms.

This profile replaces the previous same-duration menu-pacing experiment. It
also includes the unchanged v4 USB-C charging-display correction. It does not
change CPU clocks or policy, add a background timer, alter sleep behavior, or
speed up storage and song loading. USB-C wake from deep sleep remains unresolved.

The previous 300 ms pacing build produced no noticeable slide improvement for
its user. This new profile deliberately shortens the transition. **Actual
visible completion time, smoothness and battery use remain unmeasured.** Drawing
and event delays can make completion later than 150 ms. Equal ideal update
counts do not prove equal energy use.

## Firmware scope

The installer accepts only the exact supported Video 5G Apple 1.3 image or a
recognized project patch. The 168-byte helper redirects the original slide
entry at OS offset `0x2023a4`. For the known visible menu container (vtable
`0x673004`, view `0x5e15`), horizontal direction 0/1, ordinary mode 0, original
interval 30 ms and duration 300 ms, it substitutes 15 ms and 150 ms. Other
arguments pass through unchanged. There is no backlight-dependent timing
switch during a slide.

A trampoline executes the replaced original instruction and continues at
`0x2023a8`. All nine arguments, original reversal logic, easing, drawing and
cleanup stay with Apple's original function. The helper preserves the calling
convention. There are no new allocations or global state.

The charging payload is byte-identical to v4. The previous 60 Hz deadline
helper and any legacy CPU boost are removed when selecting this profile.

## Offline checks

Saved-firmware ARM execution passed:

- Both directions: native completion at 150 ms, versus stock at 300 ms, with
  ten ideal timed updates in either case.
- 204 matching-progress geometry comparisons, including clock wraparound.
- Eight reversals and eight cancellations through Apple's original routines.
- Four delayed-callback scenarios and 386 entry-scope/calling-convention cases.
- Charging-payload identity and a complete changed-byte boundary check.

Scheduling, image copies, clock and external UI calls are simulated. These are
isolated routine checks, not a full iPod emulator or a physical performance
measurement. See [results](fast-menus-validation.json). The installer separately
passes [40 exact-image install/restore paths](installer-v040-validation.json).

## Build and restore

Build privately from your own verified original firmware with the dependencies
in `requirements.txt` and Clang supporting ARMv4T:

```sh
python3 tools/build_reconnect_v4.py --original local/apple-original.bin
python3 tools/build_fast_menus.py --input build/reconnect-v4/osos-reconnect-v4.bin
python3 tools/check_fast_menus.py --baseline build/reconnect-v4/osos-reconnect-v4.bin \
  --candidate build/fast-menus/osos-fast-menus.bin --snapshot-prefix local/ui-snapshot.bin \
  --report build/fast-menus/replay.json
```

The replay requires the exact privately retained UI snapshot. Apple images and
personal recovery files are not distributed.

Candidate SHA-256:
`13532f5f4312e630384eac74e9a7d17c64d42cf69093f4fe0321d64b7fb8681b`

Use the standard installer **from v0.4.0 or newer** to restore original menu
timing while retaining v4 charging, or its restore launcher for original Apple
firmware. The same release's Smooth Menus launcher returns to the previous
300 ms pacing experiment. Older launchers do not recognize the new hash.
