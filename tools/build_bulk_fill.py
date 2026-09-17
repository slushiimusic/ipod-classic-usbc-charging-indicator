"""Rebuild the bulk background-fill preview offline from exact preview 4."""
from pathlib import Path
import hashlib,struct,subprocess,json,sys,argparse
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--input',type=Path,required=True)
parser.add_argument('--output-dir',type=Path,default=ROOT/'build/bulk-fill')
args=parser.parse_args();w=args.output_dir;w.mkdir(parents=True,exist_ok=True);b=args.input.read_bytes()
assert hashlib.sha256(b).hexdigest()=='d95c3ded58467b7778575d33d8e3f2065b257534ca6909134e8c08d72c932dd6'
subprocess.run(['clang','--target=armv4t-none-eabi','-marm','-c',str(ROOT/'src/bulk_fill.S'),'-o',str(w/'fill.o')],check=True)
with (w/'fill.o').open('rb') as f:
 e=ELFFile(f);assert not e.get_section_by_name('.rel.text') and not e.get_section_by_name('.rel.edge')
 code=bytearray(e.get_section_by_name('.text').data());tail=bytearray(e.get_section_by_name('.edge').data());s={v.name:v['st_value'] for v in e.get_section_by_name('.symtab').iter_symbols()}
assert len(code)==84 and len(tail)==16,(len(code),len(tail))
def branch(p,t):
 n=t-p-8;assert n%4==0 and -(1<<25)<=n<(1<<25)
 return 0xea000000|((n>>2)&0xffffff)
start=0x121220;cave=0x11db6c
struct.pack_into('<I',code,s['edge_branch'],branch(start+s['edge_branch'],cave))
struct.pack_into('<I',tail,s['resume_branch'],branch(cave+s['resume_branch'],start+s['fill_resume']))
a=bytearray(b);a[start:start+len(code)]=code;a[cave:cave+len(tail)]=tail
for p in (0x121200,0x121210):
 assert struct.unpack_from('<I',b,p)[0]==branch(p,0x121268)
 struct.pack_into('<I',a,p,branch(p,start+s['fill_test']))
# The aligned-copy hook has replaced this entire original loop, with a fixed
# continuation at 0x11db7c. The cave is never entered by the copy helper.
assert b[0x11db6c:0x11db7c].hex()=='041096b4010080b2041085b4faffffba'
assert struct.unpack_from('<I',b,0x11db68)[0]==branch(0x11db68,0x735e54)
assert a[0x7358c0:]==b[0x7358c0:]
(w/'osos-bulk-fill.bin').write_bytes(a)
r=dict(sha256=hashlib.sha256(a).hexdigest(),base_sha256=hashlib.sha256(b).hexdigest(),fill_start=hex(start),fill_test=hex(start+s['fill_test']),cave=hex(cave),size=len(a),changed_bytes=sum(x!=y for x,y in zip(a,b)),device_access=False)
(w/'fill-candidate.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
