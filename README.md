# iPod Classic USB-C Charging Indicator

An experimental charging-icon patch for **iPod Video 5G, exact Apple firmware 1.3**,
developed with a Moonlit Classic Connect 2 setup. Keeps Apple's interface.

## Download and run

**[Download for Mac — one command file in a ZIP](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/latest/download/Install-iPod-USB-C-Mac.zip)** ·
**[Download the Windows command file](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/latest/download/Install-iPod-USB-C.cmd)** ·
**[Download both launchers as a ZIP](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/latest/download/iPod-USB-C-Launchers.zip)**

Downloads are in **Releases → Assets**. GitHub's **Packages** section is a separate
package registry and is not used by this project.

Connect the iPod through its **original 30-pin port** and leave the kit USB-C
cable unplugged. Close applications using the iPod. Run the downloaded file
from your computer, not from the iPod.

- **Mac:** unzip the Mac download and open `Install-iPod-USB-C.command`.
  The ZIP preserves its execute permission. You can also drag the extracted
  command into Terminal and press Return.
- **Windows 10/11:** install [Python 3](https://www.python.org/downloads/windows/)
  with its launcher if needed, then double-click `Install-iPod-USB-C.cmd`.
  Accept the administrator prompt. FAT32-formatted supported iPods only.

Python 3 is required on both platforms. The launcher contains the installer
and patch data: no repository checkout, compiler, manual device profile, or
separate firmware download is needed. It reads and verifies your own firmware.
**Full Apple firmware and personal device backups are not distributed.**

The [direct command file](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/latest/download/Install-iPod-USB-C.command)
is also available. Browsers can strip execute permission from a direct download;
if macOS says it cannot execute the file because of access privileges, open
Terminal, type `bash ` (with a space), drag that file in, and press Return.
Do not change permissions on a whole folder or disable macOS security checks.

Wait for **verification and safe eject completed**. If an error appears, do
not treat installation as complete. After safe eject, disconnect 30-pin and
restart with **Menu + Center** until the Apple logo appears.

Recovery backups and receipts are saved in `iPod-USB-C-Recovery` in your user
home folder. Keep them. To restore original Apple firmware, use
[Restore-Apple-Firmware.command](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/latest/download/Restore-Apple-Firmware.command)
or [Restore-Apple-Firmware.cmd](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/latest/download/Restore-Apple-Firmware.cmd)
with the same connection and restart steps.

## What changed

Version **0.4.0** adds the optional [150 ms Faster Menus profile](#faster-menu-slides--new-in-v040).
The standard charging profile is unchanged from v0.3.0.

Version **0.3.0** adds a narrow screen-on correction to reconnect-v3. A fresh,
large voltage rise is no longer discarded solely because the backlight turns
on at the same time. Other observed load changes still reset that reference.
The thresholds, reconnect qualification and confirmation time are unchanged.

The timer samples every 250 ms and uses a 400-tick confirmation. Qualified
abrupt changes respond in roughly 500–750 ms in simulated replay. That is
**not a guaranteed physical cable latency**. Native 30-pin charging keeps
priority. The old slow, long-term fallback remains absent.

The previous smooth-menu build was reported to detect 15 of 18 physical USB-C
connections. One miss occurred with the screen off, and USB-C did not wake the
iPod. The new correction addresses a reproduced software edge-loss case;
**installation is now verified on one iPod, but those three physical misses
have not been shown to be fixed**.
See [charging scope and checks](docs/screen-on-correction.md). Windows device
installation also remains physically unverified; automated installer tests
use temporary files and simulated storage.

## Compatibility

| Model | Status |
| --- | --- |
| iPod Video 5G, exact Apple 1.3 image and supported FAT32 layout | Experimental |
| iPod Classic 6th generation | Unsupported; separate firmware port required |
| iPod Classic 7th generation | Unsupported; separate firmware port required |

The 6th/7th-generation models are requested port targets, not compatible with
this download. The installer rejects other images and layouts. See
[compatibility and port requirements](docs/compatibility.md).

## Limits

This is a voltage-based **display estimate**. It does not control USB-C charging,
change charging current, add a cable-presence signal, or prove the battery is
charging. Load changes can imitate a connection; flat voltage, including near
full charge, can prevent detection. Full-charge behavior remains unverified.

**USB-C wake from sleep is not fixed.** When the processor is asleep, this
polling hook cannot observe a new voltage edge. No separate kit USB-C wake
signal has been established. Keeping the iPod awake just to poll would use
more power and is not part of this patch. An unlit display by itself does not
establish whether the external charging board is charging the battery.

The standard installer preserves Apple's original CPU policy. There is no
underclock or overclock in it. The additional polling's battery cost is unmeasured. No
60-fps, menu-speed, song-change, or battery-runtime improvement is claimed.

## Optional responsiveness profiles

### Faster menu slides — new in v0.4.0

[Mac faster menus](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/latest/download/Install-Faster-Menus-Mac.zip) ·
[Windows faster menus](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/latest/download/Install-Faster-Menus.cmd)

This profile shortens the horizontal slide from **300 ms to 150 ms**, retaining
Apple's easing curve and original CPU policy. It requests ten timed updates
per slide, the same ideal count as stock, using a 15 ms interval. It includes
v4 charging and replaces the previous smooth-menu helper or CPU boost.

Offline checks show the original slide completing in half the time in both
directions. **Physical latency, smoothness and battery impact are unmeasured.**
No background timer or CPU boost is added. It does not fix USB-C wake from
sleep. See [implementation and checks](docs/fast-menus.md).

Use standard/restore launchers **from v0.4.0 or newer** to remove it. The
standard download restores original menu timing and retains v4 charging.

### Smooth menu movement, original transition length

[Mac optional smooth menus](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/latest/download/Install-Optional-Smooth-Menus-Mac.zip) ·
[Windows optional smooth menus](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/latest/download/Install-Optional-Smooth-Menus.cmd)

This experimental profile keeps the same **300 ms menu slide** and original
CPU policy. It requests cached-image positions on a **60 Hz deadline grid**:
18 timed updates per slide, compared with 15 in the previous smooth profile
and 10 in stock firmware. Late callbacks skip missed slots rather than queueing
extra work. It adds no background timer.

**This is not measured 60 fps.** After a verified v0.3.0 installation, the user
reported no noticeable improvement in the slide animation itself. Display
frame rate and battery impact remain unmeasured. Additional image copies cost work during menu slides; unchanged CPU
policy and sleep behavior do not establish zero battery cost. This profile
includes the new screen-on charging correction and replaces the CPU boost if
installed. See [scope and validation](docs/smooth-menus.md).

To remove this profile, use the standard or restore launcher **from v0.3.0 or
newer**. Older launchers do not recognize the new firmware hashes.

### Screen-lit CPU boost

[Mac optional screen boost](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/latest/download/Install-Optional-Screen-Boost-Mac.zip) ·
[Windows optional screen boost](https://github.com/slushiimusic/ipod-classic-usbc-charging-indicator/releases/latest/download/Install-Optional-Screen-Boost.cmd)

This legacy profile retains reconnect-v3; it **does not include the new
screen-on charging correction**. It requests Apple's existing maximum speed while the backlight circuit is enabled. With
the saved stock settings, that request is 80 MHz. When the circuit is disabled,
Apple's normal policy is preserved. It does not change the clock driver,
write clock registers directly, add a timer, or raise the stock ceiling.

**Experimental: no physical speed or battery improvement has been established.**
It may help CPU-limited menu work; storage, database and audio-buffering delays
can remain. Apple's policy already requests maximum speed during storage
activity. This is not a 60-fps patch and cannot promise zero battery cost.
It can use more power while the screen is lit and may affect the voltage-based
charging estimate. Use the standard installer to remove only the boost while
keeping the reconnect correction, or the restore launcher to remove both.
See [implementation and validation](docs/responsiveness.md).

## Installation safeguards

The launcher requires one external iPod, an exact supported firmware hash,
2048-byte sectors, the known firmware directory/resource hashes, and a music
partition starting at 98,703,360 bytes. It locks or unmounts the music volume,
verifies repeated reads and a fresh recovery backup, rechecks identity, writes
only changed OS sectors plus the directory checksum last, and verifies the
entire prefix. Failure triggers restoration and full-prefix verification;
unverifiable recovery and failed safe eject are errors. Music, resources,
partition tables and hibernation data are outside the write plan.

## Source and validation

- `src/charging_indicator_v4.c`: current charging source; v3 source is retained.
- `src/smooth_menus_v2.c`: optional deadline-based menu timing helper.
- `src/fast_menus.c`: optional 150 ms menu slide wrapper.
- `installer/`: shared planner, transaction/recovery code and macOS/Windows backends.
- `patches/`: small reversible byte patches and exact firmware hashes.
- `tools/package_release.py`: reproducible standalone launcher packaging.
- `tests/test_portable.py`: storage guards, failed-write recovery, synthetic firmware,
  and native Windows temporary-file I/O; never opens a physical device.
- `docs/screen-on-validation.json` and `docs/smooth-v2-validation.json`: current offline checks.
- `docs/fast-menus-validation.json`: shorter-slide firmware checks.
- `docs/installer-v040-validation.json`: 40 install/restore paths using exact saved images.
- `docs/validation.json`: historical reconnect-v3 checks.
- `tools/install.py` and `config/device.example.json`: legacy v0.1.0 macOS workflow.

Run portable checks and build the launchers:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 tools/package_release.py
bash build/release/Install-iPod-USB-C.command --self-test
```

The self-test checks extraction and bundled manifests; it does not access hardware.

To rebuild the full candidate privately from your own verified original OS,
install `requirements.txt` and use Clang with ARMv4T support:

```sh
python3 tools/build_reconnect_v4.py --original local/apple-original.bin
python3 tools/build_fast_menus.py --input build/reconnect-v4/osos-reconnect-v4.bin
```

Original OS SHA-256:
`784ae3d5540fd2f89e8c947b93629e97f62a06dc311d9745aab143e4db6bb251`

Reference v4 OS SHA-256 (Apple Clang 21.0.0):
`9122a8bd1c99e2be03c29c52425849a86277ddbb778a817b64fed5cb82985ba8`

Optional Faster Menus OS SHA-256:
`13532f5f4312e630384eac74e9a7d17c64d42cf69093f4fe0321d64b7fb8681b`

Other compiler output requires separate validation. No complete firmware
image or private device profile belongs in a public commit or release.
