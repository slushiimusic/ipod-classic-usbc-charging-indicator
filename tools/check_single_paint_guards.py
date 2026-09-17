"""Offline paint-gate and dirty-screen comparisons; no device I/O."""
from pathlib import Path
import argparse,json,itertools,hashlib
import check_efficient_blit as r
from check_single_paint import Render,CANDIDATE
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *
p=argparse.ArgumentParser(description=__doc__)
for name in ('previous','candidate','snapshot','report'):p.add_argument('--'+name,type=Path,required=True)
args=p.parse_args();old=args.previous.read_bytes();new=args.candidate.read_bytes()
assert hashlib.sha256(old).hexdigest()=='93a0cc76e089b5edeafed0ea2b0177c912ffbcc0ff3ba9b7d75eb0b47828600e'
assert hashlib.sha256(new).hexdigest()==CANDIDATE
prefix=args.snapshot.read_bytes()
assert hashlib.sha256(prefix).hexdigest()=='6f5012f98469a8c74070876b302ca297b0d001845d6bc554af58b2b2b707f285'
r.SNAP=prefix[0xd64000:0x2d64000]
m=r.Machine(new);u=m.u;paint=0x40000100;ret=0x40000200
u.hook_add(UC_HOOK_CODE,lambda u,pc,n,data:u.emu_stop() if pc in (paint,ret) else None)
checks=0
for pending,pointer,cls,direction,mode,capture,active in itertools.product((0,1),(0,r.OWNER),(0x673004,0x66b298),(0,1,2),(0,1,2),(0,1,2),(0,1)):
 m.putbyte(0x1082320d,pending);m.put(0x10823210,pointer)
 m.put(r.OWNER,cls);m.putbyte(r.OWNER+0xa4,direction);m.putbyte(r.OWNER+0xa5,mode);m.putbyte(r.OWNER+0x131,capture);m.putbyte(r.OWNER+0xb0,active)
 u.reg_write(UC_ARM_REG_R0,0x11dfa6e0);u.reg_write(UC_ARM_REG_R1,1);u.reg_write(UC_ARM_REG_R2,paint);u.reg_write(UC_ARM_REG_SP,r.STACK);u.reg_write(UC_ARM_REG_LR,ret)
 u.emu_start(0x735fb0,0,count=100)
 expected=ret if pending and pointer and cls==0x673004 and direction<=1 and mode==0 and capture==1 and active==1 else paint
 assert u.reg_read(UC_ARM_REG_PC)==expected,(pending,pointer,cls,direction,mode,capture,hex(u.reg_read(UC_ARM_REG_PC)))
 assert [u.reg_read(x) for x in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_SP,UC_ARM_REG_LR)]==[0x11dfa6e0,1,paint,r.STACK,ret]
 checks+=1
print('Gate guards passed',checks,flush=True)
cases=[]
for direction,dirty in itertools.product((0,1),((0,0,240,320),(0,0,24,320),(24,0,60,320))):
 a,b=Render(old),Render(new)
 for x in (a,b):
  x.visible();x.setrect(0x20001200,dirty);x.call(0x141e30,x.root,0x20001200);x.prepare(direction)
 assert a.pixels()==b.pixels(),('dirty prep',direction,dirty)
 for t in (17,85,170,255,306):
  a.frame(t);b.frame(t);assert a.pixels()==b.pixels(),('dirty frame',direction,dirty,t)
 # Compare native UI object and region state, not only the final picture.
 for p,n in [(r.OWNER,0x228),(r.OUTGOING,0xa4),(r.INCOMING,0xa4),(a.root,0xc0)]:
  assert bytes(a.u.mem_read(p,n))==bytes(b.u.mem_read(p,n)),('object state',hex(p),direction,dirty)
 cases.append(dict(direction=direction,dirty_rect=dirty,pixels_and_state_match=True));print(cases[-1],flush=True)
# Ordinary paint callback must still draw with no transition, including a null root.
for root in (0,0x11dfa6e0):
 a,b=Render(old),Render(new)
 for x in (a,b):
  x.visible();x.put(0x2000111c,root);x.putbyte(0x1082320d,0);x.put(0x10823210,0);x.paints=0;x.call(0x202c88,0x20001000)
 assert a.pixels()==b.pixels() and a.paints==b.paints
print('Normal and null-root callbacks passed',flush=True)
args.report.write_text(json.dumps(dict(candidate_sha256=hashlib.sha256(new).hexdigest(),guards=checks,dirty_cases=cases,normal_callbacks=2,device_access=False),indent=2)+'\n')
