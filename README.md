# iPod Classic USB-C Charging Indicator

An experimental charging-icon patch for **iPod Video 5G, Apple firmware 1.3**,
developed with a Moonlit Classic Connect 2 setup. It keeps Apple's interface
and displays Apple's charging animation when a recent battery-voltage change
looks like USB-C charging.

This repository contains the **current working reconnect-v2 version**. In
physical use, repeated connections worked roughly twenty times with two
reported misses. Waiting about three seconds before reconnecting improved
reliability. Detection at full charge remains unverified.

The patch estimates connection state from voltage. It does not create a
direct USB-C presence signal or change the charger, charging current, battery
protection, CPU clock, or battery-level gauge. Load changes can still imitate
charging, and unchanged voltage can prevent detection.

## Contents

- `src/charging_indicator.c` — firmware hook source.
- `tools/build_firmware.py` — constructs the patch from an exact original OS
  image, with input-hash and patch-location checks.
- `tools/install.py` — guarded macOS installer and original-firmware restore.
- `config/device.example.json` — template for a private local device profile.
- `tests/check_installer.py` — in-memory installation and rollback checks.
- `docs/validation.json` — recorded validation scope and physical observations.

Apple firmware, device backups, device identifiers, and generated binaries are
not distributed here. Supply your own verified original firmware and backup.
Other iPod models, firmware versions, and disk layouts are not supported.

## Build

Python 3, `pyelftools`, and Clang with ARMv4T support are required.

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 tools/build_firmware.py --original local/apple-original.bin
```

The original OS image must be 7,561,216 bytes with SHA-256:

```text
784ae3d5540fd2f89e8c947b93629e97f62a06dc311d9745aab143e4db6bb251
```

The reference build, produced with Apple Clang 21.0.0, has SHA-256:

```text
f8b28791b84c5a36ff240a59636208fe7edbf652eb87967d81564c6e37f2622a
```

The installer accepts only that candidate hash. A different compiler may
produce different bytes; such builds require separate validation and are
rejected by this installer.

## Local device profile

Copy `config/device.example.json` to `local/device.json`. Fill in the exact
volume UUID and whole-disk size of your iPod, the SHA-256 of its verified
original firmware-prefix backup, and the paths to the backup, original OS
and built candidate. Paths resolve relative to the profile file. The
`local/` and `build/` directories are ignored by Git.

The supported layout uses 2048-byte sectors, a firmware prefix of 98,703,360
bytes, and a music partition beginning at that offset. Device identity,
layout, OS bytes, resource bytes, directory, and checksums must match before
any firmware write is attempted. The example profile intentionally cannot
run until completed with actual verified values.

Run the file-only installer checks first:

```sh
python3 tests/check_installer.py --config local/device.json
```

These tests simulate storage and identity checks. They do not access an iPod.

## Install or restore on macOS

Connect the iPod through its **original 30-pin port**, leaving USB-C unplugged.
The installer writes raw firmware sectors, so retain the verified original
backup and use only the exact supported device and firmware layout.

```sh
sudo python3 tools/install.py inspect --config local/device.json
sudo python3 tools/install.py install --config local/device.json
```

Wait for successful verification and safe ejection in the result. If ejection
reports an error, keep the device connected until that is resolved. Disconnect
30-pin and restart with **Menu + Center** until the Apple logo appears.

To restore the exact original OS:

```sh
sudo python3 tools/install.py restore --config local/device.json
```

The public installer accepts exact original firmware or this exact candidate.
It does not migrate older experimental builds. It creates a fresh recovery
copy before writes, changes only differing OS sectors and the checksum block
last, verifies the full prefix, and attempts verified rollback after a failed
write. Music, settings, resources, and hibernation are outside its write plan.
Safe ejection is never forced. Receipts and fresh backups stay in the local
profile's output directory.

## Detection behavior

The patch polls battery voltage every 250 ms. Initial detection needs a
sustained 32-count rise; a sustained 16-count fall clears the estimate. After
a confirmed fall, a recent same-load return near the previous high can
recognize a reconnect. Small positive increments no longer move the baseline
upward and erase a gradual rise. Native 30-pin charging retains priority.

The old slow fallback is absent. Startup settling, sample freshness, load
changes and failed readings limit stale indications. A qualifying abrupt
sensor change responds in about 500–750 ms in local replay; this is not a
guaranteed physical cable latency. The extra polling's battery-runtime cost
has not been measured.

Recorded firmware checks used simulated sensor inputs and event transport.
They do not replace physical validation. Full-charge behavior, every playback
mode, and universal reliability are not established.
