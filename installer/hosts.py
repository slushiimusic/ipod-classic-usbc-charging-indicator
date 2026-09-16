"""macOS and Windows storage access, with explicit identity and volume locks."""
import base64
import ctypes
import json
import os
import plistlib
import re
import stat
import struct
import subprocess
from .firmware import BLOCK, PREFIX, require


def bounds(offset, length):
    require(offset >= 0 and length > 0 and offset % BLOCK == length % BLOCK == 0
            and offset + length <= PREFIX, 'Unaligned or out-of-prefix device access')


def select_windows(items):
    candidates = [x for x in items if re.search(r'\bipod\b', x.get('model', ''), re.I)]
    require(len(candidates) == 1, 'Connect exactly one iPod using its original 30-pin port')
    d = candidates[0]
    require(type(d['number']) is int and d['number'] >= 0, 'Invalid disk number')
    require(d['bus'] == 'USB' and d['boot'] is False and d['system'] is False,
            'Refusing an internal, system or boot disk')
    require(d['style'] == 'MBR' and d['block'] == BLOCK and d['size'] > PREFIX,
            'Unsupported disk layout or sector size')
    require(d['pnp'].upper().startswith('USBSTOR\\') and bool(d['unique']),
            'Missing stable USB disk identity')
    parts = sorted(d['partitions'], key=lambda x: x['offset'])
    require(len(parts) == 2 and parts[0]['offset'] == 63 * BLOCK and
            parts[0]['size'] == 48132 * BLOCK and parts[1]['offset'] == PREFIX and
            parts[1]['size'] > 0 and PREFIX + parts[1]['size'] <= d['size'],
            'Unsupported partition extents')
    require(len(d['volumes']) == 1 and d['volumes'][0]['fs'] == 'FAT32',
            'Requires a Windows-readable FAT32 iPod music volume')
    v = d['volumes'][0]
    require(re.fullmatch(r'\\\\\?\\Volume\{[0-9a-fA-F-]{36}\}\\', v['path']) is not None,
            'Invalid volume identity')
    require(v['offset'] == PREFIX and v['size'] == parts[1]['size'], 'Volume extent mismatch')
    return d


class MacDisk:
    def __init__(self, path, writable=False):
        self.fd = os.open(path, os.O_RDWR if writable else os.O_RDONLY)
        try:
            require(stat.S_ISCHR(os.fstat(self.fd).st_mode), 'Expected raw character device')
            require(os.fstat(self.fd).st_rdev == os.stat(path).st_rdev, 'Device identity changed')
        except BaseException:
            self.close()
            raise

    def read(self, offset, length):
        bounds(offset, length)
        result = []
        while length:
            n = min(length, 1024 * 1024)
            data = os.pread(self.fd, n, offset)
            require(len(data) == n, 'Short device read')
            result.append(data)
            offset += n
            length -= n
        return b''.join(result)

    def write(self, offset, data):
        bounds(offset, len(data))
        require(len(data) == BLOCK, 'Only individual firmware sectors may be written')
        require(os.pwrite(self.fd, data, offset) == len(data), 'Short device write')

    def flush(self):
        os.fsync(self.fd)

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


class MacHost:
    @staticmethod
    def command(*args):
        return subprocess.check_output(['/usr/sbin/diskutil', *args], stderr=subprocess.STDOUT)

    def info(self, name):
        return plistlib.loads(self.command('info', '-plist', name))

    def discover(self):
        names = plistlib.loads(self.command('list', '-plist', 'external', 'physical'))['WholeDisks']
        found = []
        for name in names:
            require(re.fullmatch(r'disk[0-9]+', name), 'Invalid disk identifier')
            d = self.info(name)
            if d.get('MediaType') != 'iPod':
                continue
            require(d.get('Internal') is False and d.get('WholeDisk') is True and
                    d.get('MediaName') == 'iPod' and d.get('BusProtocol') == 'USB', 'Unexpected iPod transport')
            require(d.get('DeviceBlockSize') == BLOCK and d.get('TotalSize', 0) > PREFIX,
                    'Unsupported iPod sector layout')
            v = self.info(name + 's2')
            require(v.get('PartitionMapPartitionOffset') == PREFIX and bool(v.get('VolumeUUID')),
                    'Unsupported iPod music partition')
            require(bool(d.get('DeviceTreePath')), 'Missing device identity')
            found.append(dict(name=name, size=d['TotalSize'], tree=d['DeviceTreePath'],
                              uuid=v['VolumeUUID'], mount=v.get('MountPoint')))
        require(len(found) == 1, 'Connect exactly one iPod using its original 30-pin port')
        return found[0]

    def same(self, d):
        fresh = self.discover()
        require(all(fresh[k] == d[k] for k in ('name', 'size', 'tree', 'uuid')), 'iPod identity changed')
        require(not fresh['mount'], 'iPod is still mounted')

    def check_output(self, d, path):
        if d['mount']:
            require(os.path.commonpath([str(path), d['mount']]) != d['mount'],
                    'Save the installer and backups on the computer, not the iPod')

    def lock(self, d):
        self.command('unmountDisk', d['name'])
        self.same(d)

    def open(self, d, writable=False):
        self.same(d)
        return MacDisk('/dev/r' + d['name'], writable)

    def unlock(self):
        pass

    def eject(self, d):
        self.same(d)
        self.command('eject', d['name'])


class WindowsDisk:
    """Synchronous Win32 handle; also exercised against ordinary files in CI."""
    def __init__(self, path, writable=False):
        from ctypes import wintypes as w
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        self.k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID, w.DWORD, w.DWORD, w.HANDLE]
        self.k.CreateFileW.restype = w.HANDLE
        self.k.SetFilePointerEx.argtypes = [w.HANDLE, ctypes.c_longlong, ctypes.POINTER(ctypes.c_longlong), w.DWORD]
        self.k.SetFilePointerEx.restype = w.BOOL
        for name in ('ReadFile', 'WriteFile'):
            fn = getattr(self.k, name)
            fn.argtypes = [w.HANDLE, w.LPVOID, w.DWORD, ctypes.POINTER(w.DWORD), w.LPVOID]
            fn.restype = w.BOOL
        self.k.DeviceIoControl.argtypes = [w.HANDLE, w.DWORD, w.LPVOID, w.DWORD,
                                          w.LPVOID, w.DWORD, ctypes.POINTER(w.DWORD), w.LPVOID]
        self.k.DeviceIoControl.restype = w.BOOL
        for name in ('FlushFileBuffers', 'CloseHandle'):
            getattr(self.k, name).argtypes = [w.HANDLE]
            getattr(self.k, name).restype = w.BOOL
        self.handle = self.k.CreateFileW(str(path), 0x80000000 | (0x40000000 if writable else 0),
                                         3, None, 3, 0x80000080 if writable else 0x80, None)
        if self.handle == ctypes.c_void_p(-1).value:
            self.handle = None
            raise ctypes.WinError(ctypes.get_last_error())

    def check(self, result):
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())

    def seek(self, offset):
        actual = ctypes.c_longlong()
        self.check(self.k.SetFilePointerEx(self.handle, offset, ctypes.byref(actual), 0))
        require(actual.value == offset, 'Device seek mismatch')

    def ioctl(self, code, size=0):
        out = ctypes.create_string_buffer(size) if size else None
        count = ctypes.c_uint32()
        self.check(self.k.DeviceIoControl(self.handle, code, None, 0, out, size, ctypes.byref(count), None))
        return out.raw[:count.value] if out else b''

    def read(self, offset, length):
        bounds(offset, length)
        self.seek(offset)
        result = []
        while length:
            n = min(length, 1024 * 1024)
            buf, count = ctypes.create_string_buffer(n), ctypes.c_uint32()
            self.check(self.k.ReadFile(self.handle, buf, n, ctypes.byref(count), None))
            require(count.value == n, 'Short device read')
            result.append(buf.raw)
            length -= n
        return b''.join(result)

    def write(self, offset, data):
        bounds(offset, len(data))
        require(len(data) == BLOCK, 'Only individual firmware sectors may be written')
        self.seek(offset)
        buf, count = ctypes.create_string_buffer(data), ctypes.c_uint32()
        self.check(self.k.WriteFile(self.handle, buf, len(data), ctypes.byref(count), None))
        require(count.value == len(data), 'Short device write')

    def flush(self):
        self.check(self.k.FlushFileBuffers(self.handle))

    def close(self):
        if self.handle is not None:
            handle, self.handle = self.handle, None
            self.check(self.k.CloseHandle(handle))


INVENTORY = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$items = @(Get-CimInstance Win32_DiskDrive | Where-Object { $_.Model -match '\bipod\b' } | ForEach-Object {
    $w = $_; $d = Get-Disk -Number $w.Index
    $parts = @(Get-Partition -DiskNumber $d.Number)
    $volumes = @($parts | Where-Object { $_.PartitionNumber -eq 2 } | ForEach-Object {
        $p = $_; $v = $p | Get-Volume
        if ($v) { @{path=[string]$v.Path; fs=[string]$v.FileSystemType; offset=[long]$p.Offset; size=[long]$p.Size} }
    })
    @{number=[int]$d.Number; model=[string]$w.Model; pnp=[string]$w.PNPDeviceID;
      unique=[string]$d.UniqueId; serial=[string]$w.SerialNumber; size=[long]$d.Size;
      block=[int]$d.LogicalSectorSize; bus=[string]$d.BusType; style=[string]$d.PartitionStyle;
      boot=[bool]$d.IsBoot; system=[bool]$d.IsSystem; volumes=$volumes;
      partitions=@($parts | ForEach-Object { @{offset=[long]$_.Offset; size=[long]$_.Size} })}
})
ConvertTo-Json -InputObject $items -Depth 6 -Compress
'''


class WindowsHost:
    def __init__(self):
        self.locks = []

    def discover(self):
        script = base64.b64encode(INVENTORY.encode('utf-16-le')).decode('ascii')
        output = subprocess.check_output(['powershell.exe', '-NoProfile', '-NonInteractive',
                                          '-EncodedCommand', script])
        return select_windows(json.loads(output.decode('utf-8-sig')))

    def same(self, d):
        fresh = self.discover()
        require(fresh == d, 'iPod disk identity or partition layout changed')

    def check_output(self, d, path):
        from ctypes import wintypes as w
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        for name in ('GetVolumePathNameW', 'GetVolumeNameForVolumeMountPointW'):
            getattr(k, name).argtypes = [w.LPCWSTR, w.LPWSTR, w.DWORD]
            getattr(k, name).restype = w.BOOL
        mount, guid = ctypes.create_unicode_buffer(32768), ctypes.create_unicode_buffer(128)
        require(k.GetVolumePathNameW(str(path), mount, len(mount)), 'Cannot identify backup filesystem')
        require(k.GetVolumeNameForVolumeMountPointW(mount.value, guid, len(guid)), 'Cannot identify backup volume')
        require(guid.value.lower() != d['volumes'][0]['path'].lower(),
                'Save the installer and backups on the computer, not the iPod')

    def lock(self, d):
        self.same(d)
        for v in d['volumes']:
            handle = WindowsDisk(v['path'].rstrip('\\'), True)
            self.locks.append(handle)
            ext = handle.ioctl(0x00560000, 1024)  # IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS
            require(len(ext) >= 32 and struct.unpack_from('<I', ext)[0] == 1,
                    'Refusing a missing or multi-disk volume extent')
            disk, start, size = struct.unpack_from('<I4xqq', ext, 8)
            require((disk, start, size) == (d['number'], v['offset'], v['size']), 'Volume belongs to another disk')
            handle.ioctl(0x00090018)  # FSCTL_LOCK_VOLUME; failure must stop before dismount.
            handle.ioctl(0x00090020)  # FSCTL_DISMOUNT_VOLUME; keep the successful lock open.

    def open(self, d, writable=False):
        self.same(d)
        handle = WindowsDisk(r'\\.\PhysicalDrive' + str(d['number']), writable)
        try:
            number = handle.ioctl(0x002d1080, 12)
            require(len(number) == 12 and struct.unpack('<III', number)[:2] == (7, d['number']),
                    'Opened physical disk number mismatch')
            return handle
        except BaseException:
            handle.close()
            raise

    def unlock(self):
        # Closing releases the locks, including after a failed dismount.
        while self.locks:
            self.locks.pop().close()

    def eject(self, d):
        self.same(d)
        from ctypes import wintypes as w
        cfg = ctypes.WinDLL('cfgmgr32', use_last_error=True)
        cfg.CM_Locate_DevNodeW.argtypes = [ctypes.POINTER(w.DWORD), w.LPWSTR, w.ULONG]
        cfg.CM_Locate_DevNodeW.restype = w.ULONG
        cfg.CM_Request_Device_EjectW.argtypes = [w.DWORD, ctypes.POINTER(w.DWORD), w.LPWSTR, w.ULONG, w.ULONG]
        cfg.CM_Request_Device_EjectW.restype = w.ULONG
        node, veto = w.DWORD(), w.DWORD()
        name = ctypes.create_unicode_buffer(1024)
        require(cfg.CM_Locate_DevNodeW(ctypes.byref(node), d['pnp'], 0) == 0, 'Cannot locate iPod for safe eject')
        rc = cfg.CM_Request_Device_EjectW(node, ctypes.byref(veto), name, len(name), 0)
        require(rc == 0, f'Safe eject refused ({rc}, veto {veto.value}, {name.value}). Keep the iPod connected.')
