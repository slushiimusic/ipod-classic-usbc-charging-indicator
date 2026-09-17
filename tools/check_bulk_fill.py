"""Offline saved-image comparison. Never opens a device; no physical timing claim."""
from pathlib import Path
import argparse,sys,json,random,struct,hashlib
import check_efficient_blit as r
from unicorn.arm_const import *
ROOT=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
for name in ('base','previous','candidate','snapshot','report'):parser.add_argument('--'+name,type=Path,required=True)
args=parser.parse_args()
r.BASE=args.base.read_bytes()
assert hashlib.sha256(r.BASE).hexdigest()=='9122a8bd1c99e2be03c29c52425849a86277ddbb778a817b64fed5cb82985ba8'
snapshot=args.snapshot.read_bytes()
assert hashlib.sha256(snapshot).hexdigest()=='6f5012f98469a8c74070876b302ca297b0d001845d6bc554af58b2b2b707f285'
r.SNAP=snapshot[0xd64000:0x2d64000]
old=args.previous.read_bytes();new=args.candidate.read_bytes()
assert hashlib.sha256(old).hexdigest()=='d95c3ded58467b7778575d33d8e3f2065b257534ca6909134e8c08d72c932dd6'
assert hashlib.sha256(new).hexdigest()=='20b25c2436ebb1df79a2e5150a816c17c1c7482d59850316565007a8e0df1470'

a,b=r.Machine(old),r.Machine(new);rng=random.Random(0xf111);cases=[]
REGS=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_CPSR]
for n in [0,1,2,3,4,5,7,8,9,15,16,31,79,159,319]:
 for mode in range(8):
  for height in [0,1,3]:
   for pattern in range(3):
    pitch=(n+2)*4+pattern*4;size=max(height,1)*pitch+128;buf=rng.randbytes(size)
    left,right=[rng.getrandbits(32) for _ in range(2)] if pattern else (0xffffffff,0xffffffff)
    color=rng.getrandbits(32);results=[]
    for m in (a,b):
     m.u.mem_write(0x11000000,buf);m.u.mem_write(0x20002000,bytes(64));m.put(0x20002004,color);m.putbyte(0x20002008,mode);m.put(0x2000200c,0);m.put(0x20002014,height);m.put(0x20002020,0x11000040);m.put(0x20002024,pitch);m.put(0x20002028,n);m.put(0x20002034,left);m.put(0x20002038,right)
     for k,v in enumerate(REGS[:-3]):m.u.reg_write(v,0x12340000+k)
     m.u.reg_write(UC_ARM_REG_CPSR,0x10)
     count=m.instructions;m.call(0x1210a0,0x20002000)
     results.append((bytes(m.u.mem_read(0x11000000,size)),[m.u.reg_read(k) for k in REGS],m.instructions-count))
    assert results[0][:2]==results[1][:2],(n,mode,height,pattern)
    cases.append(dict(words=n,mode=mode,height=height,pattern=pattern,old=results[0][2],new=results[1][2]))
 print('Passed width',n,flush=True)
rpt=dict(status='Exact pixels, buffer canaries, registers and flags matched',cases=len(cases),candidate_sha256=hashlib.sha256(new).hexdigest(),results=cases,device_access=False,limits=['Offline execution; no physical latency or battery measurement.'])
args.report.write_text(json.dumps(rpt,indent=2)+'\n');print('PASS',len(cases))
