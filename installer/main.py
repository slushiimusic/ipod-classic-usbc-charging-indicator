"""Interactive entry point. Importing this module never accesses hardware."""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid
from .firmware import PREFIX, OS_OFFSET, OS_LENGTH, STOCK, V4, RESPONSIVE, SMOOTH_V2, FAST, EFFICIENT, plan_for, require, sha, transact
from .hosts import MacHost, WindowsHost

VERSION = '0.5.0-preview.1'


def save(path, data):
    with path.open('xb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    if os.name != 'nt' and 'SUDO_UID' in os.environ:
        os.chown(path, int(os.environ['SUDO_UID']), int(os.environ['SUDO_GID']))


def document(path, data):
    save(path, (json.dumps(data, indent=2) + '\n').encode())


def run(host, mode, output):
    """Back up before any write handle is opened; receipts stay on the computer."""
    token = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    receipt = {'release_version': VERSION, 'mode': mode, 'started': token, 'writes_attempted': False, 'verified': False,
               'ejected': False, 'original_sha256': STOCK,
               'candidate_sha256': {'responsive': RESPONSIVE, 'smooth': SMOOTH_V2, 'fast': FAST, 'efficient': EFFICIENT, 'restore': STOCK}.get(mode, V4)}
    device = None
    output.mkdir(parents=True, exist_ok=True)
    # Ensure the recovery destination is writable before dismounting the iPod.
    with tempfile.TemporaryFile(dir=output) as probe:
        probe.write(b'recovery storage check')
        probe.flush()
        os.fsync(probe.fileno())
    d = host.discover()
    host.check_output(d, output.resolve())
    host.check_output(d, Path(__file__).resolve().parent)
    receipt['device'] = d
    try:
        print('Checking the connected iPod and reading firmware...', flush=True)
        host.lock(d)
        device = host.open(d)
        before = device.read(0, PREFIX)
        plan, expected, original = plan_for(before, mode)
        require(device.read(0, PREFIX) == before, 'Firmware changed between verification reads')
        receipt.update(before_prefix_sha256=sha(before), expected_prefix_sha256=sha(expected),
                       before_firmware_sha256=sha(before[OS_OFFSET:OS_OFFSET + OS_LENGTH]),
                       sectors=[off for off, _, _ in plan])
        if mode == 'inspect':
            receipt['status'] = 'Supported firmware and installation plan verified; no writes'
        elif not plan:
            receipt['verified'] = True
            receipt['status'] = 'Requested firmware already installed and verified'
        else:
            recovery = output / ('before-' + token + '.bin')
            save(recovery, before)
            require(sha(recovery.read_bytes()) == sha(before), 'Saved recovery copy verification failed')
            stock_path = output / ('apple-original-' + token + '.bin')
            save(stock_path, original)
            require(sha(stock_path.read_bytes()) == STOCK, 'Saved original OS verification failed')
            receipt['backup'] = str(recovery)
            receipt['original_os'] = str(stock_path)
            document(output / ('preflight-' + token + '.json'), receipt)
            device.close()
            device = None
            host.same(d)
            device = host.open(d, writable=True)
            require(device.read(0, PREFIX) == before, 'Device changed before writing')
            print(f'Recovery backup verified. Writing {len(plan)} firmware sectors...', flush=True)
            receipt['writes_attempted'] = True
            transact(device, plan, before, expected)
            receipt['verified'] = True
            receipt['status'] = {'restore': 'Original Apple OS restored',
                                 'efficient': 'Drawing optimization preview installed; original menu timing and CPU policy active',
                                 'responsive': 'Quick reconnect correction and experimental screen-lit boost installed',
                                 'fast': '150 ms menu slides and screen-on charging correction installed; original CPU policy active',
                                 'smooth': 'Screen-on edge correction and experimental menu pacing installed; original CPU policy active',
                                 'install': 'Reconnect and screen-on edge corrections installed; original CPU policy active'}[mode]
        device.close()
        device = None
        host.unlock()
        host.eject(d)
        receipt['ejected'] = True
        print(receipt['status'] + '. Safe eject completed.', flush=True)
        if mode != 'inspect':
            print('Disconnect 30-pin. Restart with Menu + Center until the Apple logo appears.')
            print('USB-C behavior must be checked on the iPod; this is an experimental display estimate.')
        return receipt
    except BaseException as error:
        receipt['error'] = str(error)
        raise
    finally:
        try:
            if device is not None:
                device.close()
        finally:
            try:
                host.unlock()
            finally:
                document(output / ('result-' + token + '.json'), receipt)


def elevated():
    if os.name == 'nt':
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    return os.geteuid() == 0


def main():
    p = argparse.ArgumentParser(description='iPod Video 5G Apple 1.3 USB-C indicator installer')
    p.add_argument('mode', nargs='?', choices=['install', 'responsive', 'smooth', 'fast', 'efficient', 'restore', 'inspect'], default='install')
    p.add_argument('--output', type=Path, default=Path.home() / 'iPod-USB-C-Recovery')
    p.add_argument('--elevated', action='store_true', help=argparse.SUPPRESS)
    p.add_argument('--self-test', action='store_true', help='Validate bundled patch data without opening any device')
    args = p.parse_args()
    if args.self_test:
        from .firmware import manifests
        require(len(manifests()) == 8, 'Missing patch data')
        print(f'Installer {VERSION}: bundled patch data loaded. No device access.')
        return 0
    require(sys.platform in ('darwin', 'win32'), 'Installation requires macOS or Windows')
    if not elevated():
        require(not args.elevated, 'Administrator authorization was not granted')
        entry = str(Path(__file__).resolve().parent.parent / 'run_installer.py')
        command = [sys.executable, entry, args.mode, '--output', str(args.output.resolve()), '--elevated']
        if sys.platform == 'darwin':
            return subprocess.call(['/usr/bin/sudo', *command])
        import base64
        quote = lambda value: "'" + value.replace("'", "''") + "'"
        script = "$ErrorActionPreference='Stop'; $p=Start-Process -FilePath " + quote(command[0])
        script += ' -ArgumentList ' + quote(subprocess.list2cmdline(command[1:]))
        script += ' -Verb RunAs -Wait -PassThru; exit $p.ExitCode'
        return subprocess.call(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand',
                                base64.b64encode(script.encode('utf-16-le')).decode('ascii')])
    try:
        print(f'iPod USB-C indicator {VERSION} — reconnect and screen-on edge correction')
        if args.mode == 'responsive':
            print('Optional screen-lit boost: battery cost and physical speed gains are unmeasured.')
            print('This legacy profile retains reconnect-v3 and does not include the screen-on edge correction.')
            print('No 60-fps guarantee. Run the standard installer to remove only this boost.')
        if args.mode == 'smooth':
            print('Optional smooth menus: same 300 ms slide, a 60 Hz target for cached-image update deadlines.')
            print('Original CPU policy. Actual display rate and battery impact are unmeasured.')
            print('Run this release\'s standard installer to restore original menu timing.')
        if args.mode == 'fast':
            print('Faster menus: 150 ms slides instead of 300 ms, with the original CPU policy.')
            print('Same ten ideal timed updates as stock; physical latency and battery impact are unmeasured.')
            print('Run this release\'s standard installer to restore original menu timing.')
        if args.mode == 'efficient':
            print('Drawing preview: optimized pixel copies with original Apple menu timing and CPU policy.')
            print('Physical smoothness, artwork loading time and battery impact remain unverified.')
            print('Use THIS release\'s standard installer to undo the drawing changes, or its Apple restore launcher.')
        if args.mode in ('install', 'smooth', 'fast', 'efficient'):
            print('USB-C wake from deep sleep remains unresolved; the icon is a voltage-based estimate.')
        print('Use the original 30-pin connection; leave the kit USB-C cable unplugged.')
        print('Recovery files: ' + str(args.output.resolve()), flush=True)
        run(WindowsHost() if os.name == 'nt' else MacHost(), args.mode, args.output.resolve())
        return 0
    except Exception as error:
        print('STOPPED: ' + str(error), file=sys.stderr, flush=True)
        print('If safe eject did not complete, keep the iPod connected until it can be safely ejected.', file=sys.stderr)
        return 1
    finally:
        if os.name == 'nt' and args.elevated and sys.stdin.isatty():
            input('Press Enter to close this window...')
