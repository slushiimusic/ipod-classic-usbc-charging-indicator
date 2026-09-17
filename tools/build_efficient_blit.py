from pathlib import Path
import argparse,subprocess,struct,hashlib,json
ROOT=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description='Build exact Apple 1.3 drawing optimization without accessing a device')
p.add_argument('--input',type=Path,required=True)
p.add_argument('--clang',default='clang')
p.add_argument('--output-dir',type=Path,default=ROOT/'build/efficient')
args=p.parse_args()
P=args.output_dir
P.mkdir(parents=True,exist_ok=True)
from elftools.elf.elffile import ELFFile
base=args.input
before=base.read_bytes()
assert hashlib.sha256(before).hexdigest()=='9122a8bd1c99e2be03c29c52425849a86277ddbb778a817b64fed5cb82985ba8'
subprocess.run([args.clang,'--target=armv4t-none-eabi','-marm','-c',str(ROOT/'src/efficient_blit.S'),'-o',str(P/'efficient_blit.o')],check=True)
with (P/'efficient_blit.o').open('rb') as f:
 e=ELFFile(f);code=e.get_section_by_name('.text').data()
 assert e.get_section_by_name('.rel.text') is None
 syms={s.name:s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols() if s.name in ('copy_aligned_words','copy_halfword_shift')}
start=struct.unpack_from('<I',before,0xe8)[0]-4;end=start+len(code)+4
assert before[start:start+4]==bytes.fromhex('55aa55aa') and not any(before[start+4:])
assert end<=len(before) and len(code)%4==0
out=bytearray(before)
def branch(src,dst):
 delta=dst-src-8;assert delta%4==0 and -(1<<25)<=delta<(1<<25)
 return 0xea000000|((delta>>2)&0xffffff)
hooks={0x11db68:(0xe150000a,'copy_aligned_words'),0x11dc10:(0xea00000c,'copy_halfword_shift')}
for p,(original,name) in hooks.items():
 assert struct.unpack_from('<I',before,p)[0]==original,hex(struct.unpack_from('<I',before,p)[0])
 struct.pack_into('<I',out,p,branch(p,start+syms[name]))
struct.pack_into('<I',out,0xe8,end)
for p in (0x308,0xdec):
 assert struct.unpack_from('<I',before,p)[0]==0x4000000+start
 struct.pack_into('<I',out,p,0x4000000+end-4)
out[start:end]=code+bytes.fromhex('55aa55aa')
(P/'osos-efficient-blit.bin').write_bytes(out)
m={'status':'OFFLINE CANDIDATE; NOT INSTALLED','input_sha256':hashlib.sha256(before).hexdigest(),'output_sha256':hashlib.sha256(out).hexdigest(),'payload_offset':hex(start),'payload_bytes':len(code),'hooks':[hex(p) for p in hooks],'symbols':{k:hex(start+v) for k,v in syms.items()},'cpu_policy_changed':False,'timers_changed':False,'menu_duration_ms':300,'menu_interval_ms':30,'artwork_file_io_changed':False,'physical_device_access':False}
(P/'efficient-blit-manifest.json').write_text(json.dumps(m,indent=2)+'\n');print(json.dumps(m,indent=2))
