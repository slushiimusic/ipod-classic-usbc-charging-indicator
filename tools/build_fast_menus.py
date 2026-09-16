"""Append the shorter-slide menu helper to exact reconnect-v4, offline only."""
from pathlib import Path
import argparse,hashlib,json,struct,subprocess
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--input',type=Path,required=True)
p.add_argument('--output-dir',type=Path,default=ROOT/'build/fast-menus')
p.add_argument('--clang',default='clang')
args=p.parse_args()
OUT=args.output_dir
OUT.mkdir(parents=True,exist_ok=True)
before=args.input.read_bytes()
assert hashlib.sha256(before).hexdigest()=='9122a8bd1c99e2be03c29c52425849a86277ddbb778a817b64fed5cb82985ba8'
obj=OUT/'fast-menus.o'
subprocess.run([args.clang,'--target=armv4t-none-eabi','-marm','-Oz','-ffreestanding',
 '-fno-builtin','-fomit-frame-pointer','-Wall','-Wextra','-Werror','-c',str(ROOT/'src/fast_menus.c'),'-o',str(obj)],check=True)
with obj.open('rb') as f:
 e=ELFFile(f);code=bytearray(e.get_section_by_name('.text').data());sym=e.get_section_by_name('.symtab')
 offsets={s.name:s['st_value'] for s in sym.iter_symbols() if s.name in ('original_menu_start','fast_menu_start')}
 for name in ('.data','.bss','.rodata'):
  section=e.get_section_by_name(name);assert section is None or section['sh_size']==0
 for r in e.get_section_by_name('.rel.text').iter_relocations():
  s=sym.get_symbol(r['r_info_sym']);assert r['r_info_type'] in (28,29) and s.name in offsets
  off=r['r_offset'];w=struct.unpack_from('<I',code,off)[0];addend=(w&0xffffff)<<2
  if addend&(1<<25):addend-=1<<26
  delta=offsets[s.name]+addend-off
  assert delta%4==0 and -(1<<25)<=delta<(1<<25)
  struct.pack_into('<I',code,off,(w&0xff000000)|((delta>>2)&0xffffff))
def branch(src,dst):
 delta=dst-src-8;assert delta%4==0 and -(1<<25)<=delta<(1<<25)
 return 0xea000000|((delta>>2)&0xffffff)
start=struct.unpack_from('<I',before,0xe8)[0]-4
assert before[start:start+4]==bytes.fromhex('55aa55aa') and not any(before[start+4:])
end=start+len(code)+4
assert len(code)%4==0 and end<=len(before)
after=bytearray(before)
hooks=[0x2023a4]
assert struct.unpack_from('<I',before,0x2023a4)[0]==0xe92d4ff0
assert code[offsets['original_menu_start']:offsets['original_menu_start']+12]==bytes.fromhex('f04f2de904f01fe5a8232000')
struct.pack_into('<I',after,0x2023a4,branch(0x2023a4,start+offsets['fast_menu_start']))
struct.pack_into('<I',after,0xe8,end)
for p in (0x308,0xdec):
 assert struct.unpack_from('<I',before,p)[0]==0x4000000+start
 struct.pack_into('<I',after,p,0x4000000+end-4)
after[start:end]=code+bytes.fromhex('55aa55aa')
(OUT/'osos-fast-menus.bin').write_bytes(after)
m=dict(status='OFFLINE CANDIDATE; NOT INSTALLED',input_sha256=hashlib.sha256(before).hexdigest(),
 output_sha256=hashlib.sha256(after).hexdigest(),payload_offset=hex(start),payload_bytes=len(code),
 symbols={n:hex(start+v) for n,v in offsets.items()},hooks=[hex(p) for p in hooks],
 requested_interval_ms=15,duration_ms=150,ideal_timed_updates=10,cpu_policy_changed=False,
 deep_sleep_wake_fixed=False,physical_device_access=False)
(OUT/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
print(json.dumps(m,indent=2))
