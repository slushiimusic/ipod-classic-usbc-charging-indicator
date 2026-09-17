"""Combine existing optimized drawing with Apple's visible-screen capture path.

Offline only. Accepts the exact second drawing preview; never opens a device.
"""
from pathlib import Path
import argparse, hashlib, json, struct, subprocess
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--input',type=Path,required=True)
p.add_argument('--output-dir',type=Path,default=ROOT/'build/menu-start')
p.add_argument('--clang',default='clang')
a=p.parse_args();out=a.output_dir;out.mkdir(parents=True,exist_ok=True)
before=a.input.read_bytes()
assert hashlib.sha256(before).hexdigest()=='53bfd968ba80f83c359faa5d7a1325f9a9744a875ffea0d0ecc12b103d24944d'
def compile(name):
 obj=out/(name+'.o')
 source=ROOT/'src'/name
 subprocess.run([a.clang,'--target=armv4t-none-eabi','-marm','-Oz','-ffreestanding',
                 '-fno-builtin','-fomit-frame-pointer','-Wall','-Wextra','-Werror',
                 '-c',str(source),'-o',str(obj)],check=True)
 with obj.open('rb') as f:
  elf=ELFFile(f);code=elf.get_section_by_name('.text').data()
  assert not elf.get_section_by_name('.rel.text')
  for section in ('.data','.bss','.rodata'):
   s=elf.get_section_by_name(section);assert s is None or s['sh_size']==0
  return code
cadence=compile('smooth_drawing_v3.c');capture=compile('menu_start.S')
assert len(cadence)==144 and len(capture)==80
start=0x735f18;end=start+len(cadence)+len(capture)+4
assert end<=len(before) and before[0x735fbc:0x735fc0]==bytes.fromhex('55aa55aa') and not any(before[0x735fc0:])
after=bytearray(before)
def branch(src,dst):
 delta=dst-src-8;assert delta%4==0 and -(1<<25)<=delta<(1<<25)
 return 0xea000000|((delta>>2)&0xffffff)
assert struct.unpack_from('<I',before,0x2023a4)[0]==0xe92d4ff0
struct.pack_into('<I',after,0x2023a4,branch(0x2023a4,start+len(cadence)))
struct.pack_into('<I',after,0xe8,end)
for off in (0x308,0xdec):
 assert struct.unpack_from('<I',before,off)[0]==0x4000000+0x735fbc
 struct.pack_into('<I',after,off,0x4000000+end-4)
after[start:]=cadence+capture+bytes.fromhex('55aa55aa')+bytes(len(before)-end)
# Drawing and charging machine code remain exactly the same.
assert after[0x7358c0:start]==before[0x7358c0:start]
(out/'osos-menu-start.bin').write_bytes(after)
m=dict(status='OFFLINE CANDIDATE; NOT INSTALLED',input_sha256=hashlib.sha256(before).hexdigest(),
       output_sha256=hashlib.sha256(after).hexdigest(),payload_offset=hex(start),
       cadence_bytes=len(cadence),capture_offset=hex(start+len(cadence)),capture_bytes=len(capture),
       logical_end=hex(end),requested_interval_ms=17,duration_ms=300,
       cpu_policy_changed=False,physical_device_access=False)
(out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps(m,indent=2))
