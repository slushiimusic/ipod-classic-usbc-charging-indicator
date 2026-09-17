# Bulk background-fill preview

Version **0.5.0-preview.5** speeds up the solid background fills used when drawing
menus. The previous preview installed successfully but was reported to feel the
same as preview 3. The earlier overall improvement over stock remains a subjective
physical report; the remaining button-to-motion pause is not established as fixed.

- [Mac installer ZIP](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/download/v0.5.0-preview.5/Install-Drawing-Optimization-Preview-Mac.zip)
- [Windows installer](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/download/v0.5.0-preview.5/Install-Drawing-Optimization-Preview.cmd)
- Restore preview 4: [Mac ZIP](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/download/v0.5.0-preview.5/Restore-Previous-Drawing-Preview-Mac.zip) or [Windows command](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/download/v0.5.0-preview.5/Restore-Previous-Drawing-Preview.cmd).

Connect through original 30-pin with USB-C unplugged. Wait for verification and
safe eject, disconnect, then restart with Menu + Center until the Apple logo.
Use this release's restore launchers: earlier installers reject the new image.
Only exact iPod Video 5G Apple 1.3 and recognized project images are accepted.

## Change

The solid-fill inner loop at `0x12123c` was prominent in the native saved-state
menu-action and first-paint trace. It stored one 32-bit word per iteration. This
patch writes two at a time, with a scalar remainder. Apple's masked first/last
words, row pitch, zero-width path, other drawing operations and clipping remain.

The small masked-edge helper occupies 16 bytes made unreachable by the existing
aligned-copy replacement. The copy helper retains its original continuation;
shifted-copy fallback code is untouched. Firmware size and allocation stay fixed.
Only 48 bytes differ from preview 4. The installer permits one additional exact
firmware sector for the fill routine; the maximum transaction is now 12 sectors,
including the directory written last. Backups and full read-back checks remain.

All preview 4 animation, charging and CPU-policy bytes remain identical. There is
no overclock, new polling, shorter slide duration or change to button-release and
long-press behavior. Fewer instructions are not a measurement of energy use.
USB-C deep-sleep wake and artwork file loading remain outside this change.

## Evidence and limits

- 1,080 full native fill comparisons matched pixels, surrounding buffer bytes,
  registers and condition flags across dimensions, edge masks and all eight modes.
- Saved menu preparation, 72 frame comparisons, three reversals, two cancellations
  and six pending-redraw cases matched the previous preview.
- 353 copy comparisons include the reused bytes and preserve overlap behavior.
- One fuller trace executed native selection, the menu-action interpreter,
  allocation, layout and the first paint. The complete saved RAM result matched.
  It used **1,792,266 versus 1,976,586 emulated instructions**, about 9.3% less work.
- 91 exact saved-prefix install/restore plans cover thirteen recognized images
  and seven destinations. Every possible write-failure position is rollback-tested.

The full trace still models locks, current task context, clock, timer scheduling
and message posting. It is not physical input-latency profiling, and covers only
one saved menu selection. This is an incremental experimental optimization, not a
claim to eliminate the reported half-second pause. Physical latency, frame rate
and battery impact remain unmeasured for this preview.

Reports: [fill](bulk-fill-validation.json), [menu](bulk-fill-menus.json),
[copy](bulk-fill-copies.json), [input path](bulk-fill-input-path.json),
[installer](installer-v050-preview5-validation.json).

## Reproduce offline

The private firmware and saved memory are required locally and are not distributed.
Build with Clang for ARMv4T and pyelftools; checks additionally need Unicorn.

```sh
python tools/build_bulk_fill.py --input local/preview-4.bin
python tools/check_bulk_fill.py --base local/charging-v4.bin \
  --previous local/preview-4.bin --candidate build/bulk-fill/osos-bulk-fill.bin \
  --snapshot local/ui-snapshot.bin --report build/bulk-fill/fill.json
python tools/check_bulk_fill_menus.py --base local/charging-v4.bin \
  --previous local/preview-4.bin --candidate build/bulk-fill/osos-bulk-fill.bin \
  --snapshot local/ui-snapshot.bin --report build/bulk-fill/menu.json
python tools/check_bulk_fill_input.py --previous local/preview-4.bin \
  --candidate build/bulk-fill/osos-bulk-fill.bin --snapshot local/ui-snapshot.bin \
  --report build/bulk-fill/input.json
python tools/check_bulk_fill_copies.py --base local/charging-v4.bin \
  --candidate build/bulk-fill/osos-bulk-fill.bin \
  --snapshot local/ui-snapshot.bin --report build/bulk-fill/copies.json
```
