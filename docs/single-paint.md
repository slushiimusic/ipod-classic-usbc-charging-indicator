# Single preparation paint preview

Version **0.5.0-preview.4** tries to reduce the pause before a menu slide. Preview
3 was reported to feel only marginally faster; the remaining physical delay has
not been established as fixed.

- [Mac installer ZIP](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/download/v0.5.0-preview.4/Install-Drawing-Optimization-Preview-Mac.zip)
- [Windows installer](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/download/v0.5.0-preview.4/Install-Drawing-Optimization-Preview.cmd)
- Return to preview 3: [Mac ZIP](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/download/v0.5.0-preview.4/Restore-Previous-Drawing-Preview-Mac.zip) or [Windows command](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/download/v0.5.0-preview.4/Restore-Previous-Drawing-Preview.cmd).

Use the original 30-pin connection with USB-C unplugged. Wait for verified
installation and safe eject, then disconnect and restart with Menu + Center.
Use the restore files included in this version: older launchers do not recognize
the new image. The standard installer restores original drawing while retaining
the charging correction; Restore Apple Firmware restores the original OS.

## Change and limits

Apple's update callback paints the root before preparing cached slide images,
then paints it again during preparation. With the outgoing screen already
captured, the first paint was redundant in the saved UI replay.

The new gate skips it only when a transition is pending, its pointer is nonzero,
the exact known class matches, the transition is active, its mode is ordinary
and horizontal, and its outgoing image is captured. All other paths retain the
original paint call, including canceled transitions and ordinary screen updates.
The original null-root condition is preserved.

The capture wrapper, cadence helper and aligned copy entry were compacted to fit
the existing firmware allocation. The cadence helper uses explicit ARMv4T
interworking. Firmware size and allowed write sectors are unchanged. Charging
payload bytes remain identical to preview 3. This retains 17 ms requested updates,
300 ms slide duration, original CPU policy and the existing charging estimate.
It adds no polling or background task.

This is experimental. One saved UI graph is not every menu or physical input
sequence. External OS notifications, clock, scheduling and display delivery are
modeled. There is no physical latency, FPS or battery measurement for this build.
It does not promise to remove input-release timing, list construction or storage
waits, and does not fix USB-C deep-sleep wake.

## Offline checks

- Four preparation cases and 72 animation-frame comparisons matched preview 3.
- Three reversals and two cancellations matched.
- 96 entry guards, 486 cadence guards and 432 paint-gate cases passed.
- Six pending-redraw cases matched pixels and native menu object state; ordinary
  and null-root update callbacks retained their behavior.
- 353 saved/synthetic comparisons checked the exact compact copy routines
  independently against native copying.
- 84 exact-prefix install/restore paths covered twelve recognized images and
  seven destinations. Backups, read-back verification and rollback remain.

In the saved forward menu, preparation fell from 950,204 to 603,030 emulated ARM
instructions, approximately **36.5% less preparation work**. This is not a measured
36.5% reduction in the complete button-to-animation delay.

Reports: [preparation](single-paint-validation.json),
[guards and pending redraws](single-paint-guards.json),
[copy routines](single-paint-copies.json),
[installer plans](installer-v050-preview4-validation.json).

## Reproduction

The build accepts only the exact preview 3 image. Complete Apple firmware,
private saved RAM and disk images are not distributed.

```sh
python tools/build_single_paint.py --input local/preview-3.bin
python tools/check_single_paint.py --base local/charging-v4.bin \
  --previous local/preview-3.bin --candidate build/single-paint/osos-single-paint.bin \
  --snapshot local/ui-snapshot.bin --report build/single-paint/preparation.json
python tools/check_single_paint_guards.py --previous local/preview-3.bin \
  --candidate build/single-paint/osos-single-paint.bin \
  --snapshot local/ui-snapshot.bin --report build/single-paint/guards.json
python tools/check_single_paint_copies.py --base local/charging-v4.bin \
  --candidate build/single-paint/osos-single-paint.bin \
  --snapshot local/ui-snapshot.bin --report build/single-paint/copies.json
```

Building requires Clang targeting ARMv4T and pyelftools. Replay additionally
requires Unicorn. These commands do not open a device.
