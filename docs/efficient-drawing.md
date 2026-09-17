# Drawing optimization preview

Version **0.5.0-preview.2** combines faster pixel copies with more frequent
animation updates. Eligible, screen-lit horizontal menu slides request an update
every **17 ms**, about **58.8 updates per second**, instead of every 30 ms. Apple's
300 ms duration and easing curve are retained: 18 ideal timed steps instead of
10, with completion at 306 ms under an ideal fixed-period scheduler.

The reconnect-v4 charging patch, original CPU policy, display refresh policy,
artwork file reads, image quality and library metadata are unchanged. The timer
request is not synchronized to the panel's refresh. This does not generate frames
or guarantee 60 displayed frames per second. Callback delays can still drop steps.

The preceding drawing-only preview received a subjective report of improvement,
with remaining animation and artwork delays. This new cadence has passed offline
checks; physical smoothness, frame delivery and battery consumption remain
unmeasured.

## Download

- [Mac ZIP containing one executable command](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/download/v0.5.0-preview.2/Install-Drawing-Optimization-Preview-Mac.zip)
- [Windows command](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/download/v0.5.0-preview.2/Install-Drawing-Optimization-Preview.cmd)

Use the original 30-pin connection and the normal installation and restart steps
in the README. Exact Video 5G Apple 1.3 and the supported FAT32 layout only.
Sixth- and seventh-generation firmware is unsupported.

To undo just the drawing changes and keep the charging correction, use the
**standard installer from this preview release**:
[Mac ZIP](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/download/v0.5.0-preview.2/Install-iPod-USB-C-Mac.zip) or
[Windows command](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/download/v0.5.0-preview.2/Install-iPod-USB-C.cmd).
Its Apple-restoration launchers can instead restore the exact original OS.
Use version 0.5.0-preview.2 or newer to remove this preview; earlier launchers
do not recognize its fingerprint. Both preview firmware versions are recognized.

## Implementation

Two ARM loop-entry branches inside the original BitBlt routine lead to 196 bytes
of appended code. A separate 164-byte cadence helper wraps the menu's timer
configuration. The firmware image's allocated length stays unchanged.

- Aligned middle spans copy eight words per block. Forward overlap under 32 bytes
  retains the original scalar ordering; edge masks still use Apple's code.
- For a 16-bit alignment difference, middle spans combine adjacent halfwords
  directly. Byte-order conversion happens once at each end of the span instead
  of repeatedly for each word. Other alignment differences use the original loop.

Clipping, format selection, overlap direction, before/after drawing notifications,
edge handling and completion remain in their original callers. No new global
state, heap allocation, idle timer or CPU-speed request is introduced. The cadence
helper checks the exact view class, view identity, visibility flags, slide mode,
direction, 300 ms duration and enabled backlight circuit. Other transitions keep
their original requested period. More updates occur only during eligible slides.

## Validation and limits

353 differential comparisons passed against the original routines: 26 saved-menu
frame/state comparisons and 327 pixel-copy comparisons. The latter include six
pixel depths, edge clipping, small rectangles, different pitches, overlapping
buffers, native thumbnail sizes and full menu-sized copies. Pixel buffers and
outside-rectangle bytes matched. The saved-menu checks compared all simulated
SDRAM after each frame, allowing only the intentionally different timer period.

The cadence replay additionally passed 122 matching-time geometry checks, six
reversals, 16 cancellations and 486 eligibility checks. Delayed callbacks use
Apple's elapsed-time movement rather than accumulating a backlog. Three delayed
callback scenarios also reached completion and stopped the native timer.

For the saved complete transition in one direction:

| Profile | Timed steps | ARM instructions |
| --- | ---: | ---: |
| Apple drawing and cadence | 10 | 2,029,186 |
| Drawing-only preview 1 | 10 | 813,538 |
| Smooth drawing preview 2 | 18 | 1,398,702 |

Preview 2 uses about 31% fewer instructions than original drawing in this saved
case, but about 72% more than preview 1. Display-transfer costs, memory behavior
and energy consumption are not included. The unchanged clock policy and absence
of idle work do not establish zero battery cost.

Examples from the complete clipping-and-copy call, with external display
notifications simulated:

| Copy | Original instructions | Preview instructions | Reduction |
| --- | ---: | ---: | ---: |
| 200 × 200, aligned | 114,507 | 40,107 | 65.0% |
| 200 × 200, shifted one pixel | 647,713 | 179,913 | 72.2% |
| 320 × 216, aligned | 188,443 | 59,707 | 68.3% |
| 320 × 216, shifted one pixel | 1,114,225 | 297,961 | 73.3% |

These are executed ARM instruction counts, **not measured milliseconds, frame
rates or energy savings**. Memory-bus behavior and hardware callbacks are not
validated by this replay. Fewer copy instructions may reduce rendering cost;
it does not establish that storage waits or artist-list construction are fixed.
Small or ineligible spans incur dispatch overhead: 79 of the 327 synthetic copy
cases used more instructions, with a maximum increase of about 10.1%. All 26
saved-menu frame comparisons used fewer instructions (58.3–68.1% fewer). The
aligned block path temporarily uses 32 extra stack bytes. Full boot, playback
and physical battery runtime remain unverified.

The detailed anonymous test cases are in
[smooth-drawing-pixels-validation.json](smooth-drawing-pixels-validation.json) and
[smooth-drawing-validation.json](smooth-drawing-validation.json). The installer
also verifies all 60 install/restore plans across ten recognized saved images;
see [installer checks](installer-v050-preview2-validation.json). Reproduction
requires private exact firmware and the retained UI snapshot; neither is
included in the repository. `tools/build_efficient_blit.py` accepts the exact
reconnect-v4 image, and `tools/check_efficient_blit.py` takes explicit baseline,
candidate and private snapshot paths. `tools/build_smooth_drawing.py` appends
the cadence helper to the exact first drawing preview.
`tools/check_smooth_drawing.py` checks cadence and transition lifecycle.
The ARM replay also requires `unicorn`.
