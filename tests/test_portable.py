"""No hardware access: fake disks, synthetic firmware, and native Windows temp files."""
import copy
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from installer import firmware as f, hosts, main


class MemoryDisk:
    def __init__(self, data, fail=None):
        self.data = bytearray(data)
        self.fail = fail
        self.writes = 0
        self.closed = False

    def read(self, offset, length):
        return bytes(self.data[offset:offset + length])

    def write(self, offset, data):
        self.writes += 1
        if self.fail == self.writes:
            self.data[offset:offset + 100] = data[:100]
            raise OSError('Simulated partial write')
        self.data[offset:offset + len(data)] = data

    def flush(self):
        pass

    def close(self):
        self.closed = True


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.before = bytes(f.BLOCK * 12)
        self.plan = [(i * f.BLOCK, bytes(f.BLOCK), bytes([i + 1]) * f.BLOCK) for i in range(1, 12)]
        self.plan.append((0, bytes(f.BLOCK), bytes([99]) * f.BLOCK))
        self.after = bytearray(self.before)
        for off, _, data in self.plan:
            self.after[off:off + f.BLOCK] = data
        self.after = bytes(self.after)

    def test_success(self):
        disk = MemoryDisk(self.before)
        f.transact(disk, self.plan, self.before, self.after)
        self.assertEqual(bytes(disk.data), self.after)

    def test_rollback_every_write_position(self):
        for index in range(1, len(self.plan) + 1):
            with self.subTest(index=index):
                disk = MemoryDisk(self.before, fail=index)
                with self.assertRaisesRegex(RuntimeError, 'previous firmware restored and verified'):
                    f.transact(disk, self.plan, self.before, self.after)
                self.assertEqual(bytes(disk.data), self.before)

    def test_changed_sector_stops_before_write(self):
        disk = MemoryDisk(self.before)
        disk.data[f.BLOCK] = 7
        with self.assertRaisesRegex(RuntimeError, 'Sector changed'):
            f.transact(disk, self.plan, self.before, self.after)
        self.assertEqual(disk.writes, 0)

    def test_disconnect_reports_unverified_rollback(self):
        disk = MemoryDisk(self.before)
        disk.write = lambda *a: (_ for _ in ()).throw(OSError('Disconnected'))
        with self.assertRaisesRegex(RuntimeError, 'RECOVERY REQUIRED'):
            f.transact(disk, self.plan, self.before, self.after)

    def test_corruption_outside_plan_is_not_hidden(self):
        disk = MemoryDisk(self.before + bytes(f.BLOCK))
        # The full-prefix check must reject an extra, unplanned sector.
        with self.assertRaisesRegex(RuntimeError, 'RECOVERY REQUIRED'):
            f.transact(disk, self.plan, self.before, self.after)


def example_windows():
    return dict(number=4, model='Apple iPod USB Device', pnp=r'USBSTOR\DISK&VEN_APPLE&PROD_IPOD\SERIAL&0',
                unique='synthetic-identity', serial='synthetic', size=f.PREFIX + 1024 * 1024,
                block=f.BLOCK, bus='USB', style='MBR', boot=False, system=False,
                partitions=[dict(offset=63 * f.BLOCK, size=48132 * f.BLOCK), dict(offset=f.PREFIX, size=1024 * 1024)],
                volumes=[dict(path='\\\\?\\Volume{00000000-1111-2222-3333-444444444444}\\', fs='FAT32',
                              offset=f.PREFIX, size=1024 * 1024)])


class HostTests(unittest.TestCase):
    def test_valid_windows_identity(self):
        d = example_windows()
        self.assertEqual(hosts.select_windows([d]), d)

    def test_reject_unsafe_windows_identities(self):
        changes = [('boot', True), ('system', True), ('bus', 'SATA'), ('style', 'RAW'),
                   ('block', 512), ('unique', ''), ('pnp', 'SCSI\\device'), ('volumes', []),
                   ('partitions', []), ('number', -1)]
        for key, value in changes:
            with self.subTest(field=key):
                d = example_windows()
                d[key] = value
                with self.assertRaises(RuntimeError):
                    hosts.select_windows([d])
        for items in ([], [example_windows(), example_windows()]):
            with self.assertRaises(RuntimeError):
                hosts.select_windows(items)

    def test_refuse_unknown_volume(self):
        for key, value in [('fs', 'NTFS'), ('path', 'C:\\'), ('offset', 0), ('size', 1)]:
            d = example_windows()
            d['volumes'][0][key] = value
            with self.assertRaises(RuntimeError):
                hosts.select_windows([d])

    def test_no_dismount_when_volume_lock_fails(self):
        calls = []
        class Handle:
            def __init__(self, *args): pass
            def ioctl(self, code, size=0):
                calls.append(code)
                if code == 0x560000:
                    return struct.pack('<I4xI4xqq', 1, 4, f.PREFIX, 1024 * 1024)
                raise OSError('Volume busy')
            def close(self): calls.append('close')
        host = hosts.WindowsHost()
        host.same = lambda d: None
        with patch.object(hosts, 'WindowsDisk', Handle):
            with self.assertRaisesRegex(OSError, 'busy'):
                host.lock(example_windows())
            host.unlock()
        self.assertEqual(calls, [0x560000, 0x90018, 'close'])

    def test_refuse_multi_disk_or_wrong_extent_before_lock(self):
        for count, number, start in [(2, 4, f.PREFIX), (1, 0, f.PREFIX), (1, 4, 0)]:
            calls = []
            class Handle:
                def __init__(self, *args): pass
                def ioctl(self, code, size=0):
                    calls.append(code)
                    return struct.pack('<I4xI4xqq', count, number, start, 1024 * 1024)
                def close(self): pass
            host = hosts.WindowsHost()
            host.same = lambda d: None
            with patch.object(hosts, 'WindowsDisk', Handle):
                with self.assertRaises(RuntimeError):
                    host.lock(example_windows())
                host.unlock()
            self.assertEqual(calls, [0x560000])

    def test_prefix_bounds(self):
        for offset, length in [(1, f.BLOCK), (0, 1), (-f.BLOCK, f.BLOCK), (f.PREFIX, f.BLOCK), (0, 0)]:
            with self.assertRaises(RuntimeError): hosts.bounds(offset, length)

    @unittest.skipUnless(os.name == 'nt', 'Windows native API')
    def test_windows_native_file_io_and_short_reads(self):
        with tempfile.TemporaryDirectory(prefix='iPod file checks ') as folder:
            path = Path(folder) / 'unicode-é-音.bin'
            path.write_bytes(bytes(f.BLOCK * 2))
            disk = hosts.WindowsDisk(path, True)
            try:
                self.assertEqual(disk.read(0, f.BLOCK), bytes(f.BLOCK))
                data = bytes(range(256)) * 8
                disk.write(f.BLOCK, data)
                disk.flush()
                self.assertEqual(disk.read(f.BLOCK, f.BLOCK), data)
                with self.assertRaisesRegex(RuntimeError, 'Short device read'):
                    disk.read(2 * f.BLOCK, f.BLOCK)
            finally:
                disk.close()
            self.assertEqual(path.read_bytes()[f.BLOCK:], data)


class FirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Generated fixtures, not Apple firmware. Production fingerprints are
        # replaced only inside these tests; real-image checks run privately.
        a = bytes(f.OS_LENGTH)
        b, c, d = bytearray(a), bytearray(a), bytearray(a)
        b[0x18ad4c:0x18ad50] = b'old!'
        c[0x18ad4c:0x18ad50] = b'new!'
        d[0x18ad4c:0x18ad50] = b'fast'
        e = bytearray(c)
        e[0x2028c8:0x2028cc] = b'menu'
        v4 = bytearray(c)
        v4[0x18ad4c:0x18ad50] = b'edg4'
        smooth2 = bytearray(v4)
        smooth2[0x2028c8:0x2028cc] = b'60Hz'
        smooth2[0x20300c:0x203010] = b'time'
        fast = bytearray(v4)
        fast[0x2023a4:0x2023a8] = b'150m'
        efficient = bytearray(v4)
        efficient[0x11db68:0x11db6c] = b'copy'
        efficient[0x11dc10:0x11dc14] = b'half'
        efficient2 = bytearray(efficient)
        efficient2[0x2028c8:0x2028cc] = b'17ms'
        efficient3 = bytearray(efficient2)
        efficient3[0x2023a4:0x2023a8] = b'cap!'
        efficient4 = bytearray(efficient3)
        efficient4[0x202ca8:0x202cac] = b'gate'
        efficient5 = bytearray(efficient4)
        efficient5[0x12123c:0x121240] = b'fill'
        cls.images = [a, bytes(b), bytes(c), bytes(d), bytes(e), bytes(v4), bytes(smooth2), bytes(fast), bytes(efficient), bytes(efficient2), bytes(efficient3), bytes(efficient4), bytes(efficient5)]
        cls.hashes = [f.sha(x) for x in cls.images]
        cls.patches = {h: dict(original_sha256=cls.hashes[0], target_sha256=h,
                              changes=[dict(offset=0x18ad4c, before='00000000', after=image[0x18ad4c:0x18ad50].hex())])
                       for h, image in zip(cls.hashes[1:], cls.images[1:])}
        cls.patches[cls.hashes[4]]['changes'].append(dict(offset=0x2028c8, before='00000000', after='6d656e75'))
        cls.patches[cls.hashes[6]]['changes'].extend([
            dict(offset=0x2028c8, before='00000000', after='3630487a'),
            dict(offset=0x20300c, before='00000000', after='74696d65')])
        cls.patches[cls.hashes[7]]['changes'].append(dict(offset=0x2023a4, before='00000000', after='3135306d'))
        cls.patches[cls.hashes[8]]['changes'][0:0] = [
            dict(offset=0x11db68, before='00000000', after=b'copy'.hex()),
            dict(offset=0x11dc10, before='00000000', after=b'half'.hex())]
        cls.patches[cls.hashes[9]]['changes'] = copy.deepcopy(cls.patches[cls.hashes[8]]['changes'])
        cls.patches[cls.hashes[9]]['changes'].append(dict(offset=0x2028c8, before='00000000', after=b'17ms'.hex()))
        cls.patches[cls.hashes[10]]['changes'] = copy.deepcopy(cls.patches[cls.hashes[9]]['changes'])
        cls.patches[cls.hashes[10]]['changes'].insert(-1, dict(offset=0x2023a4, before='00000000', after=b'cap!'.hex()))
        cls.patches[cls.hashes[11]]['changes'] = copy.deepcopy(cls.patches[cls.hashes[10]]['changes'])
        cls.patches[cls.hashes[11]]['changes'].append(dict(offset=0x202ca8, before='00000000', after=b'gate'.hex()))
        cls.patches[cls.hashes[12]]['changes'] = copy.deepcopy(cls.patches[cls.hashes[11]]['changes'])
        cls.patches[cls.hashes[12]]['changes'].insert(2, dict(offset=0x12123c, before='00000000', after=b'fill'.hex()))
        prefix = bytearray(f.PREFIX)
        prefix[510:512] = b'\x55\xaa'
        struct.pack_into('<II', prefix, 454, 63, 48132)
        prefix[466] = 0x0b
        struct.pack_into('<II', prefix, 470, f.PREFIX // f.BLOCK, 100000)
        cls.prefix = bytes(prefix)

    def constants(self):
        return patch.multiple(f, STOCK=self.hashes[0], V2=self.hashes[1], V3=self.hashes[2], RESPONSIVE=self.hashes[3],
                              SMOOTH=self.hashes[4],
                              V4=self.hashes[5], SMOOTH_V2=self.hashes[6], FAST=self.hashes[7], EFFICIENT=self.hashes[8], EFFICIENT_V2=self.hashes[9], EFFICIENT_V3=self.hashes[10], EFFICIENT_V4=self.hashes[11], EFFICIENT_V5=self.hashes[12],
                              RESOURCE_SHA=f.sha(self.prefix[0x75b000:0xc5b800]),
                              DIRECTORY_SHA=f.sha(bytes(f.BLOCK)))

    def image_prefix(self, index):
        p = bytearray(self.prefix)
        p[f.OS_OFFSET:f.OS_OFFSET + f.OS_LENGTH] = self.images[index]
        struct.pack_into('<I', p, f.DIR_BLOCK + f.CHECKSUM, sum(self.images[index]) & 0xffffffff)
        return bytes(p)

    def test_all_supported_install_and_restore_paths(self):
        with self.constants():
            for index in range(13):
                for mode, target in [('install', 5), ('restore', 0), ('responsive', 3), ('smooth', 6), ('fast', 7), ('efficient', 12), ('drawing_previous', 11)]:
                    with self.subTest(source=index, mode=mode):
                        plan, expected, original = f.plan_for(self.image_prefix(index), mode, self.patches)
                        self.assertEqual(expected, self.image_prefix(target))
                        self.assertEqual(original, self.images[0])
                        if plan:
                            self.assertEqual(plan[-1][0], f.DIR_BLOCK)
                        else:
                            self.assertEqual(index, target)

    def test_corrupt_layout_resource_firmware_and_checksum_rejected(self):
        with self.constants():
            for offset in (510, 454, 466, 470, 478, 0x75b000, f.OS_OFFSET + 50, f.DIR_BLOCK + f.CHECKSUM, f.DIR_BLOCK + 9):
                with self.subTest(offset=offset):
                    data = bytearray(self.prefix)
                    data[offset] ^= 1
                    with self.assertRaises(RuntimeError):
                        f.plan_for(bytes(data), 'install', self.patches)

    def test_tampered_patch_rejected(self):
        with self.constants():
            bad = copy.deepcopy(self.patches)
            bad[self.hashes[5]]['changes'][0]['after'] = '01020304'
            with self.assertRaisesRegex(RuntimeError, 'hash mismatch'):
                f.plan_for(self.prefix, 'install', bad)


class WorkflowTests(unittest.TestCase):
    def test_backup_before_write_and_eject_error_not_success(self):
        before = bytes(f.BLOCK * 2)
        after = b'x' * f.BLOCK + bytes(f.BLOCK)
        plan = [(0, before[:f.BLOCK], after[:f.BLOCK])]
        events = []
        class Host:
            def discover(self): return {'synthetic': True}
            def check_output(self, *a): pass
            def lock(self, d): events.append('lock')
            def same(self, d): pass
            def open(self, d, writable=False):
                if writable:
                    self_test.assertEqual(len(list(Path(folder).glob('before-*.bin'))), 1)
                    events.append('write-open')
                return MemoryDisk(before)
            def unlock(self): events.append('unlock')
            def eject(self, d): raise RuntimeError('Eject busy')
        self_test = self
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(main, 'PREFIX', len(before)), patch.object(f, 'PREFIX', len(before)), \
                 patch.object(main, 'STOCK', f.sha(b'original')), \
                 patch.object(main, 'plan_for', return_value=(plan, after, b'original')), \
                 patch('sys.stdout', new=io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, 'Eject busy'):
                    main.run(Host(), 'install', Path(folder))
            receipt = json.loads(next(Path(folder).glob('result-*.json')).read_text())
            self.assertTrue(receipt['verified'])
            self.assertFalse(receipt['ejected'])
            self.assertEqual(receipt['error'], 'Eject busy')
            self.assertIn('write-open', events)


if __name__ == '__main__':
    unittest.main()
