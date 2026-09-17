"""Build an duration-preserving cadence on top of optimized pixel copies; no device I/O."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parent.parent


def build(source, output, clang):
    before = source.read_bytes()
    assert hashlib.sha256(before).hexdigest() == 'ab0d616a6b93b6db5dff423b827948a6bc4708384f22adb8d7476ac247a30724'
    output.mkdir(parents=True, exist_ok=True)
    obj = output / 'smooth-drawing.o'
    subprocess.run([clang, '--target=armv4t-none-eabi', '-marm', '-Oz', '-ffreestanding',
                    '-fno-builtin', '-fomit-frame-pointer', '-Wall', '-Wextra', '-Werror', '-c',
                    str(ROOT / 'src/smooth_drawing.c'), '-o', str(obj)], check=True)
    with obj.open('rb') as file:
        elf = ELFFile(file)
        code = elf.get_section_by_name('.text').data()
        assert not elf.get_section_by_name('.rel.text')
        for name in ('.data', '.bss', '.rodata'):
            section = elf.get_section_by_name(name)
            assert section is None or section['sh_size'] == 0
        assert elf.get_section_by_name('.symtab').get_symbol_by_name('smooth_drawing')[0]['st_value'] == 0
    start = struct.unpack_from('<I', before, 0xe8)[0] - 4
    assert before[start:start + 4] == bytes.fromhex('55aa55aa') and not any(before[start + 4:])
    end = start + len(code) + 4
    assert end <= len(before) and len(code) % 4 == 0
    def branch(src, dst):
        delta = dst - src - 8
        assert delta % 4 == 0 and -(1 << 25) <= delta < (1 << 25)
        return 0xeb000000 | ((delta >> 2) & 0xffffff)
    assert struct.unpack_from('<I', before, 0x2028c8)[0] == branch(0x2028c8, 0x151c24)
    after = bytearray(before)
    struct.pack_into('<I', after, 0x2028c8, branch(0x2028c8, start))
    struct.pack_into('<I', after, 0xe8, end)
    for offset in (0x308, 0xdec):
        assert struct.unpack_from('<I', before, offset)[0] == 0x4000000 + start
        struct.pack_into('<I', after, offset, 0x4000000 + end - 4)
    after[start:end] = code + bytes.fromhex('55aa55aa')
    (output / 'osos-smooth-drawing.bin').write_bytes(after)
    manifest = dict(status='LOCAL PROTOTYPE; NOT INSTALLED; PHYSICAL SMOOTHNESS AND BATTERY IMPACT UNMEASURED',
                    input_sha256=hashlib.sha256(before).hexdigest(), output_sha256=hashlib.sha256(after).hexdigest(),
                    image_bytes=len(after), hook_offset=hex(0x2028c8), payload_offset=hex(start),
                    payload_bytes=len(code), original_interval_ms=30, requested_interval_ms=17,
                    transition_duration_ms=300, duration_changed=False, cpu_policy_changed=False,
                    added_idle_timers=False, charging_payload_unchanged=True, physical_device_access=False,
                    changed_sectors=[hex(off) for off in range(0, len(before), 2048)
                                     if before[off:off+2048] != after[off:off+2048]])
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, default=ROOT / 'build/smooth-drawing')
    p.add_argument('--clang', default='clang')
    a = p.parse_args()
    build(a.input, a.output_dir, a.clang)
