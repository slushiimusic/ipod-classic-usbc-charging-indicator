"""Reproducible experimental patch; exact previous image required. No device I/O."""
from pathlib import Path
import struct,json,hashlib,argparse,subprocess
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description='Build the single preparation paint preview offline; no device access')
p.add_argument('--input',type=Path,required=True)
p.add_argument('--output-dir',type=Path,default=ROOT/'build/single-paint')
p.add_argument('--clang',default='clang')
args=p.parse_args();W=args.output_dir;W.mkdir(parents=True,exist_ok=True)
for source,name in [('compact_blit.S','compact_blit.o'),('single_paint.S','compact_helpers.o')]:
 subprocess.run([args.clang,'--target=armv4t-none-eabi','-marm','-c',str(ROOT/'src'/source),'-o',str(W/name)],check=True)
b=args.input.read_bytes();assert hashlib.sha256(b).hexdigest()=='93a0cc76e089b5edeafed0ea2b0177c912ffbcc0ff3ba9b7d75eb0b47828600e'
def elf(name):
 with (W/name).open('rb') as f:
  e=ELFFile(f);assert not e.get_section_by_name('.rel.text')
  syms={s.name:s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols()};return bytearray(e.get_section_by_name('.text').data()),syms
copy,cs=elf('compact_blit.o');help,hs=elf('compact_helpers.o')
assert len(copy)==188 and len(help)==236,(len(copy),len(help))
def branch(a,z,link=False):
 v=z-a-8;assert v%4==0 and -(1<<25)<=v<(1<<25)
 return (0xeb000000 if link else 0xea000000)|((v>>2)&0xffffff)
start=0x735e54;hstart=start+len(copy);a=bytearray(b)
# Resolve the one deliberately local branch placeholder to the original entry.
assert struct.unpack_from('<I',help,hs['capture_done'])[0]==0xeafffffe
struct.pack_into('<I',help,hs['capture_done'],branch(hstart+hs['capture_done'],0x2023a8))
patches={0x11db68:branch(0x11db68,start+cs['copy_aligned_words']),0x11dc10:branch(0x11dc10,start+cs['copy_halfword_shift']),0x2028c8:branch(0x2028c8,hstart+hs['cadence'],True),0x2023a4:branch(0x2023a4,hstart+hs['capture']),0x202ca8:(branch(0x202ca8,hstart+hs['paint_gate'])&0x0fffffff)|0x10000000}
assert struct.unpack_from('<I',b,0x202ca8)[0]==0x112fff12
for p,v in patches.items():struct.pack_into('<I',a,p,v)
a[start:0x735ffc]=copy+help
a[0x735ffc:]=bytes.fromhex("55aa55aa")
struct.pack_into("<I",a,0xe8,0x736000)
for p in (0x308,0xdec):struct.pack_into("<I",a,p,0x4735ffc)
assert a[0x7358c0:start]==b[0x7358c0:start]
(W/'osos-single-paint.bin').write_bytes(a)
r=dict(input_sha256=hashlib.sha256(b).hexdigest(),output_sha256=hashlib.sha256(a).hexdigest(),copy_start=start,helper_start=hstart,symbols={n:hstart+hs[n] for n in ['cadence','capture','paint_gate']},patches={hex(k):hex(v) for k,v in patches.items()},device_access=False)
(W/'candidate.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
