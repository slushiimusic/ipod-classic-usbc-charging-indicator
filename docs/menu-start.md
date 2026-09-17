# Faster transition preparation, preview 3

Version **0.5.0-preview.3** targets the work before the first moving frame. It
retains the optimized pixel copies, 17 ms requested updates, Apple's 300 ms slide
duration and original CPU policy from preview 2. One physical report confirmed
faster animation in preview 2, with an approximately half-second pause between a
press and movement. Preview 3's effect on that pause has not been measured.

## Download and return to the previous version

- [Mac installer ZIP](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/download/v0.5.0-preview.3/Install-Drawing-Optimization-Preview-Mac.zip)
- [Windows installer](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/download/v0.5.0-preview.3/Install-Drawing-Optimization-Preview.cmd)
- Return directly to preview 2: [Mac ZIP](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/download/v0.5.0-preview.3/Restore-Previous-Drawing-Preview-Mac.zip) or [Windows command](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/download/v0.5.0-preview.3/Restore-Previous-Drawing-Preview.cmd).

Use the original 30-pin connection with the kit USB-C cable unplugged. After
verification and safe eject complete, disconnect and restart with Menu + Center.
Use this release's standard installer to remove all drawing changes while
keeping charging correction, or its Apple restore launcher for original firmware.
Earlier launchers do not recognize this candidate's hash.

Only the exact supported Video 5G Apple 1.3 image and FAT32 layout are accepted.
Sixth- and seventh-generation firmware remains unsupported.

## What changes before the slide

Apple's normal preparation paints the root screen, constructs the incoming menu
image, then paints the outgoing menu again to construct its transition image.
Apple also has a caller-selectable path that captures the outgoing image from
the existing visible screen. This preview selects that existing path for the
known menu container, an idle transition, horizontal directions and ordinary
slide mode. A transition already in progress uses the original behavior, so
reversals and interruption cleanup are retained.

The new 80-byte entry wrapper preserves the original registers and prologue,
changing only the capture argument when eligible. The equivalent cadence helper
is compacted from 164 to 144 bytes to fit both helpers in the existing firmware
allocation. Charging and optimized pixel-copy code are byte-for-byte unchanged.
No clock boost, background polling, library edit or shorter slide is added.

A captured outgoing image reflects the already visible pixels. Pending content
updates may not appear in that outgoing snapshot. The incoming screen is still
prepared through Apple's renderer. There is no new persistent image cache.

## Offline evidence and limits

In the saved UI replay, both directions retained identical outgoing, incoming
and root pixels. The default preparation path changed from three root-paint calls
to two. In one direction, preparation fell from **1,756,247 to 950,204 executed
ARM instructions**, a **45.9% reduction**. When the caller already selected
capture, the wrapper adds 13 instructions and saves no redraw.

These are instruction counts, not measured milliseconds. The half-second pause
may also include input dispatch, list construction, storage waits or other
rendering work. This change cannot claim a specific physical latency or battery
improvement without a device observation.

The replay runs native visibility, positioning, root painting, cache preparation
and pixel copies. External OS/UI notifications, the clock and scheduling remain
modeled. It covers one saved UI graph, not every menu or input sequence.

The checks cover four native preparation cases, 72 subsequent animation frames,
96 entry-scope cases, 486 cadence-scope cases, three reversals and two
cancellations. All pixel comparisons passed.

See [native preparation checks](menu-start-validation.json) and
[77 saved-image installer and restore paths](installer-v050-preview3-validation.json).
The installer also supports a direct return to preview 2. Mac and Windows tests
use simulated storage or temporary files; they do not establish Windows physical
installation or iPod behavior. USB-C wake from deep sleep remains unresolved.

## Reproduce privately

Build from the exact previous candidate with Clang and `pyelftools`:

```sh
python3 tools/build_menu_start.py --input local/preview-2.bin
```

Replay with `unicorn`, privately retained firmware and the saved UI snapshot:

```sh
python3 tools/check_menu_start.py --base local/reconnect-v4.bin \
  --previous local/preview-2.bin --candidate build/menu-start/osos-menu-start.bin \
  --snapshot local/ui-snapshot.bin --report build/menu-start/replay.json
```

Candidate SHA-256:
`93a0cc76e089b5edeafed0ea2b0177c912ffbcc0ff3ba9b7d75eb0b47828600e`

Complete firmware and private saved UI images are not distributed.
