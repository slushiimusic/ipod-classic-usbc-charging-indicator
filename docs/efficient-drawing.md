# Drawing optimization preview

This preview targets the pixel-copy work used by Apple's menu slides and image
drawing. It keeps the reconnect-v4 charging patch and restores Apple's original
300 ms menu duration and 30 ms timer interval. CPU policy, display refresh policy,
artwork file reads, image quality and library metadata are unchanged.

This is an offline-validated candidate, not a verified fix for physical menu
stalls, slow artwork loading or battery consumption. It does not provide frame
generation or promise 60 displayed frames per second.

## Download

- [Mac ZIP containing one executable command](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/download/v0.5.0-preview.1/Install-Drawing-Optimization-Preview-Mac.zip)
- [Windows command](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/download/v0.5.0-preview.1/Install-Drawing-Optimization-Preview.cmd)

Use the original 30-pin connection and the normal installation and restart steps
in the README. Exact Video 5G Apple 1.3 and the supported FAT32 layout only.
Sixth- and seventh-generation firmware is unsupported.

To undo just the drawing changes and keep the charging correction, use the
**standard installer from this preview release**:
[Mac ZIP](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/download/v0.5.0-preview.1/Install-iPod-USB-C-Mac.zip) or
[Windows command](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/download/v0.5.0-preview.1/Install-iPod-USB-C.cmd).
Its Apple-restoration launchers can instead restore the exact original OS.
Older releases do not recognize this preview's firmware fingerprint.

## Implementation

Two ARM loop-entry branches inside the original BitBlt routine lead to 196 bytes
of appended code. The firmware image's allocated length stays unchanged.

- Aligned middle spans copy eight words per block. Forward overlap under 32 bytes
  retains the original scalar ordering; edge masks still use Apple's code.
- For a 16-bit alignment difference, middle spans combine adjacent halfwords
  directly. Byte-order conversion happens once at each end of the span instead
  of repeatedly for each word. Other alignment differences use the original loop.

Clipping, format selection, overlap direction, before/after drawing notifications,
edge handling and completion remain in their original callers. No new global
state, heap allocation, background work or CPU-speed request is introduced.

## Validation and limits

353 differential comparisons passed against the original routines: 26 saved-menu
frame/state comparisons and 327 pixel-copy comparisons. The latter include six
pixel depths, edge clipping, small rectangles, different pitches, overlapping
buffers, native thumbnail sizes and full menu-sized copies. Pixel buffers and
outside-rectangle bytes matched. The saved-menu checks compared all simulated
SDRAM after each frame.

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
[efficient-blit-validation.json](efficient-blit-validation.json). Reproduction
requires private exact firmware and the retained UI snapshot; neither is
included in the repository. `tools/build_efficient_blit.py` accepts the exact
reconnect-v4 image, and `tools/check_efficient_blit.py` takes explicit baseline,
candidate and private snapshot paths. The ARM replay also requires `unicorn`.
