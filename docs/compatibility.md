# Model compatibility and port requirements

| Target | Current patch | Physical validation | Remaining work |
| --- | --- | --- | --- |
| iPod Video 5th generation, exact Apple 1.3 OS | Implemented, experimental | Repeated icon changes observed, occasional reconnect misses remain | Improve short reconnects and verify full-charge behavior |
| iPod Classic 6th generation | Not supported | None for this patch | Separate firmware and installer port |
| iPod Classic 7th generation | Not supported | None for this patch | Separate firmware and installer port |

These statuses apply to this charging-indicator project. They do not describe
general Rockbox support or the compatibility of a physical USB-C kit.

## Why a separate port is required

The current implementation calls fixed functions in one Apple 1.3 executable,
reads specific hardware registers, and patches known locations in that image.
It also expects a specific firmware-directory and disk-sector layout.

Rockbox's primary hardware definitions identify the Video platform as
**PP5022** and the Classic platform as **S5L8702**, with distinct USB and I2C
interfaces. Its Classic boot-tool documentation covers the 2007, 2008, 2009
and 2012 Classic revisions and lists different stock firmware versions for
them. That is evidence of distinct platform and firmware requirements; it
does not provide working Apple charging-display hook addresses for this
project. Sources: [Video hardware definition](https://github.com/Rockbox/rockbox/blob/master/firmware/export/config/ipodvideo.h),
[Classic hardware definition](https://github.com/Rockbox/rockbox/blob/master/firmware/export/config/ipod6g.h),
[Classic boot-tool documentation](https://github.com/Rockbox/rockbox/blob/master/utils/mks5lboot/README).

Changing the model name, bypassing the firmware hash, or reusing the Video's
addresses cannot establish Classic compatibility. No such bypass is included.

## Port work needed for each Classic revision

1. Obtain and identify its exact original firmware, boot format and recoverable
   device layout. Keep its original firmware and data recoverable.
2. Locate the original battery sampling, cable-status, timer and display paths
   in that firmware. Establish which signal the particular USB-C kit exposes.
3. Adapt the hook and image construction to those verified routines and that
   platform while preserving Apple software and charging controls.
4. Validate installation, rollback, boot, playback, repeated cable transitions
   and full-charge behavior for the specific revision.

No Classic firmware candidate, installation method for this patch, or working
6th/7th-generation charging indicator has been produced yet. A successful
5th-generation result is not validation for these targets.

## Host platforms

The patch runs on the iPod. The current raw-device installer uses macOS disk
identification and I/O; Windows installation requires a separate host-side
implementation. A Windows installer would not, by itself, add support for
additional iPod generations.
