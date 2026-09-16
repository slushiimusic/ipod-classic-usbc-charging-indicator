"""Firmware validation and reversible sector transactions. No device discovery."""
import hashlib
import json
import struct
from pathlib import Path

BLOCK = 2048
PREFIX = 98703360
OS_OFFSET = 0x24800
OS_LENGTH = 0x736000
DIR_BLOCK = 0x23800
CHECKSUM = 0x21c
STOCK = '784ae3d5540fd2f89e8c947b93629e97f62a06dc311d9745aab143e4db6bb251'
V2 = 'f8b28791b84c5a36ff240a59636208fe7edbf652eb87967d81564c6e37f2622a'
V3 = '4322aba038229466ebf6c25116327d38ca76ce7bb98216fc7d6e91753b13a270'
RESPONSIVE = '253fe5b2df1ace5d3c871ef96dcc29d0cb86401a4e107a29c7e9f957be4c38ec'
DIRECTORY_SHA = '2f81b47602a6d172ddfff3a706461d13f87da8f62eac72b85fb484625098b392'
RESOURCE_SHA = '080d43f7cf87fb4b4a3f079ce7f35731a217031bf59f1fc80cb87fa49821af11'
OS_SECTORS = {0, 0x800, 0xfe000, 0x18a800, 0x1ae000, 0x1d8800, 0x1d9000, 0x735800}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def manifests(root=None):
    root = root or Path(__file__).resolve().parent.parent / 'patches'
    result = {}
    for name, expected in [('v2', V2), ('v3', V3), ('responsive', RESPONSIVE)]:
        m = json.loads((root / (name + '.json')).read_text())
        require(m['original_sha256'] == STOCK and m['target_sha256'] == expected,
                'Patch manifest identity mismatch')
        result[expected] = m
    return result


def transform(data, manifest, reverse=False):
    source = manifest['target_sha256'] if reverse else STOCK
    target = STOCK if reverse else manifest['target_sha256']
    require(len(data) == OS_LENGTH and sha(data) == source, 'Unsupported firmware image')
    result = bytearray(data)
    end = 0
    for change in manifest['changes']:
        off = change['offset']
        before, after = bytes.fromhex(change['before']), bytes.fromhex(change['after'])
        if reverse:
            before, after = after, before
        require(off >= end and len(before) == len(after) > 0 and off + len(before) <= OS_LENGTH,
                'Invalid or overlapping patch extent')
        require(all(s in OS_SECTORS for s in range(off // BLOCK * BLOCK,
                    (off + len(before) - 1) // BLOCK * BLOCK + BLOCK, BLOCK)), 'Unexpected patch sector')
        require(result[off:off + len(before)] == before, 'Patch bytes mismatch')
        result[off:off + len(after)] = after
        end = off + len(before)
    require(sha(result) == target, 'Resulting firmware hash mismatch')
    return bytes(result)


def plan_for(prefix, mode='install', patch_set=None):
    require(mode in ('install', 'responsive', 'restore', 'inspect'), 'Invalid operation')
    require(len(prefix) == PREFIX, 'Unexpected firmware prefix length')
    require(prefix[510:512] == b'\x55\xaa', 'Unsupported partition map')
    first, second = prefix[446:462], prefix[462:478]
    require(first[4] == 0 and struct.unpack_from('<II', first, 8) == (63, 48132),
            'Unsupported firmware partition')
    require(second[4] == 0x0b and struct.unpack_from('<I', second, 8)[0] * BLOCK == PREFIX,
            'Only the supported FAT32 iPod layout is accepted')
    require(not any(prefix[478:510]), 'Unexpected additional partitions')
    require(sha(prefix[0x75b000:0xc5b800]) == RESOURCE_SHA, 'Apple resource image mismatch')
    current = prefix[OS_OFFSET:OS_OFFSET + OS_LENGTH]
    observed = sha(current)
    require(observed in (STOCK, V2, V3, RESPONSIVE),
            'Unsupported firmware. Requires exact iPod Video 5G Apple 1.3 or a recognized project patch.')
    directory = bytearray(prefix[DIR_BLOCK:DIR_BLOCK + BLOCK])
    require(struct.unpack_from('<I', directory, CHECKSUM)[0] == sum(current) & 0xffffffff,
            'Firmware directory checksum mismatch')
    struct.pack_into('<I', directory, CHECKSUM, 0)
    require(sha(directory) == DIRECTORY_SHA, 'Unsupported firmware directory layout')
    patch_set = patch_set or manifests()
    original = current if observed == STOCK else transform(current, patch_set[observed], reverse=True)
    target = RESPONSIVE if mode == 'responsive' else V3
    wanted = original if mode == 'restore' else transform(original, patch_set[target])
    struct.pack_into('<I', directory, CHECKSUM, sum(wanted) & 0xffffffff)
    plan = []
    for off in range(0, OS_LENGTH, BLOCK):
        before, after = current[off:off + BLOCK], wanted[off:off + BLOCK]
        if before != after:
            require(off in OS_SECTORS, 'Unexpected changed firmware sector')
            plan.append((OS_OFFSET + off, before, after))
    old_dir = prefix[DIR_BLOCK:DIR_BLOCK + BLOCK]
    if directory != old_dir:
        plan.append((DIR_BLOCK, old_dir, bytes(directory)))
    require(len(plan) <= 9, 'Too many firmware sectors')
    expected = bytearray(prefix)
    for off, _, after in plan:
        expected[off:off + BLOCK] = after
    return plan, bytes(expected), original


def transact(device, plan, before, expected):
    """Directory last; failed writes restore and verify the entire original prefix."""
    touched = False
    try:
        for off, old, new in plan:
            require(device.read(off, BLOCK) == old, 'Sector changed before writing')
            touched = True
            device.write(off, new)
            device.flush()
            require(device.read(off, BLOCK) == new, 'Sector verification failed')
        require(device.read(0, PREFIX) == expected, 'Full-prefix verification failed')
    except BaseException as error:
        if not touched:
            raise
        try:
            for off, old, _ in plan:
                device.write(off, old)
            device.flush()
            require(device.read(0, PREFIX) == before, 'Full rollback verification failed')
        except BaseException as rollback:
            raise RuntimeError(f'RECOVERY REQUIRED. Keep the device connected. {error}; rollback: {rollback}') from error
        raise RuntimeError(f'Installation stopped; previous firmware restored and verified. {error}') from error
