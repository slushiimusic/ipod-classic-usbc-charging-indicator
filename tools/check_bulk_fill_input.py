"""Replay one native saved menu selection and first paint, not physical timing.

Locks, clock, timers, task context, message posting and memcpy are modeled.
Native allocation, menu action/interpreter, layout and drawing execute. No device
access. The private exact images and saved memory are supplied by the operator.
"""
from pathlib import Path
import argparse,json,collections,hashlib
import check_efficient_blit as r
from unicorn import UC_HOOK_BLOCK,UC_HOOK_MEM_INVALID
from unicorn.arm_const import *
class Trace(r.Machine):
 def __init__(self,image):
  self.clock=1000000;self.events=[];self.recent=collections.deque(maxlen=90);self.counts=collections.Counter();super().__init__(image)
  self.u.hook_add(UC_HOOK_BLOCK,self.block);self.u.hook_add(UC_HOOK_MEM_INVALID,self.invalid)
 def invalid(self,u,access,addr,size,value,data):
  self.events.append(dict(unmapped=hex(addr),size=size,access=access,registers=[hex(u.reg_read(x)) for x in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_LR)]));return False
 def block(self,u,pc,n,data):self.recent.append(hex(pc));self.counts[pc]+=1
 def hook(self,u,pc,n,data):
  self.instructions+=1
  if pc in (0x23cf84,0x23ca4c,0x239f7c,0x23cbd4,0x19db8c,0x19cec8,0x2023a4,0x141cf0,0x2248b4,0x151c10,0x1516b8,0x151694,0x151c24,0x2021d4,0x202c88,0x202ea8,0x141e8c):
   self.events.append(dict(pc=hex(pc),instructions=self.instructions,args=[hex(u.reg_read(x)) for x in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)],stack=[hex(self.word(u.reg_read(UC_ARM_REG_SP)+4*i)) for i in range(5)]))
  if pc in (0xc9a84,0xc9b58,0xd6a64,0xd6afc,0xd15cc):
   pass
   u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR));return
  if pc in (0x151c10,0x1516b8):
   self.events[-1]['message']=bytes(u.mem_read(u.reg_read(UC_ARM_REG_R2),24)).hex()
   u.reg_write(UC_ARM_REG_R0,1);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR));return
  if pc==0x282860:
   u.reg_write(UC_ARM_REG_R0,self.clock);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR));return
  if pc in (0x151694,0x151c98):
   u.reg_write(UC_ARM_REG_R0,1);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR));return
  if pc==0x7cae0:
   dst,src,size=[u.reg_read(x) for x in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2)]
   assert size<0x200000
   u.mem_write(dst,bytes(u.mem_read(src,size)));u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR));return
  if pc in (0x101800,0xd6aac):
   u.reg_write(UC_ARM_REG_R0,0x11e5cd7c if pc==0x101800 else 0x11e5cde8);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR));return
  if pc in (0x11c9fc,0xd6b18,0x120e7c):
   self.events.append(dict(kernel_boundary=hex(pc),lr=hex(u.reg_read(UC_ARM_REG_LR)),instructions=self.instructions,args=[hex(u.reg_read(x)) for x in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]));u.emu_stop()
def execute(image):
 m=Trace(image)
 m.put(0x11dea13c+0xa4,0);m.put(0x20001004,7);m.put(0x20001010,0x6f0000)
 m.u.reg_write(UC_ARM_REG_R0,0x11dea3fc);m.u.reg_write(UC_ARM_REG_R1,0x20001000)
 m.u.reg_write(UC_ARM_REG_SP,r.STACK);m.u.reg_write(UC_ARM_REG_LR,r.STOP)
 m.u.emu_start(0x23cd9c,r.STOP,count=3000000)
 assert m.u.reg_read(UC_ARM_REG_PC)==r.STOP,'Menu action did not return'
 m.put(0x20001008,0x11dfa5d4)
 m.u.reg_write(UC_ARM_REG_R0,0x20001000);m.u.reg_write(UC_ARM_REG_SP,r.STACK);m.u.reg_write(UC_ARM_REG_LR,r.STOP)
 m.u.emu_start(0x202c88,r.STOP,count=10000000)
 assert m.u.reg_read(UC_ARM_REG_PC)==r.STOP,'First paint did not return'
 assert any(e.get('pc')=='0x202ea8' for e in m.events),'Transition timer not reached'
 return m.instructions,bytes(m.u.mem_read(0x10000000,0x2000000))

parser=argparse.ArgumentParser(description=__doc__)
for name in ('previous','candidate','snapshot','report'):parser.add_argument('--'+name,type=Path,required=True)
a=parser.parse_args();old=a.previous.read_bytes();new=a.candidate.read_bytes();snapshot=a.snapshot.read_bytes()
assert hashlib.sha256(old).hexdigest()=='d95c3ded58467b7778575d33d8e3f2065b257534ca6909134e8c08d72c932dd6'
assert hashlib.sha256(new).hexdigest()=='20b25c2436ebb1df79a2e5150a816c17c1c7482d59850316565007a8e0df1470'
assert hashlib.sha256(snapshot).hexdigest()=='6f5012f98469a8c74070876b302ca297b0d001845d6bc554af58b2b2b707f285'
r.SNAP=snapshot[0xd64000:0x2d64000]
p,pr=execute(old);n,nr=execute(new);assert pr==nr,'Saved RAM differs'
report=dict(candidate_sha256=hashlib.sha256(new).hexdigest(),previous_instructions=p,candidate_instructions=n,complete_saved_ram_equal=True,device_access=False,limits=['One saved menu selection starting at its release handler. Locks, clock, timers, task context, message posting and memcpy are modeled.','Native menu action, interpreter, allocator, layout and first paint execute.','No physical input latency or battery measurement.'])
a.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
