"""Differential ARM replay of Apple clipping, copying and menu frames.

Requires privately retained exact images and saved UI state; never upload them.
No device access. External display notifications and scheduling are simulated.
Instruction counts are not physical frame rate, latency or battery measurements.
"""
from pathlib import Path
import argparse,hashlib,json,random,struct
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm_const import *
EFFICIENT = 'ab0d616a6b93b6db5dff423b827948a6bc4708384f22adb8d7476ac247a30724'
SMOOTH_DRAWING = '53bfd968ba80f83c359faa5d7a1325f9a9744a875ffea0d0ecc12b103d24944d'

def load_images(baseline, candidate, snapshot):
    global BASE, NEW, SNAP
    BASE, NEW = baseline.read_bytes(), candidate.read_bytes()
    assert hashlib.sha256(BASE).hexdigest() == '9122a8bd1c99e2be03c29c52425849a86277ddbb778a817b64fed5cb82985ba8'
    assert hashlib.sha256(NEW).hexdigest() in (EFFICIENT, SMOOTH_DRAWING)
    prefix = snapshot.read_bytes()
    assert hashlib.sha256(prefix).hexdigest() == '6f5012f98469a8c74070876b302ca297b0d001845d6bc554af58b2b2b707f285'
    SNAP = prefix[0xd64000:0x2d64000]

OWNER,OUTGOING,INCOMING=0x11d3071c,0x11ded90c,0x11ddbb2c
STOP,STACK=0x40000000,0x20008000
RECT=(24,0,240,320)

class Machine:
    def __init__(self, image):
        u = self.u = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        for p, n in [(0, 0x740000), (0x10000000, 0x2000000), (0x20000000, 0x10000),
                     (STOP, 0x1000), (0x6000d000, 0x1000)]:
            u.mem_map(p, n)
        u.mem_write(0, image)
        u.mem_write(0x10000000, SNAP)
        self.clock = 1_000_000
        self.blits, self.calls, self.instructions = [], [], 0
        self.scheduled = False
        self.gpio(7)
        self.put(OWNER + 0x20, (self.word(OWNER + 0x20) & ~0x1800) | 0x800)
        # Mock external UI visibility and geometry calls. Transition math,
        # frame dispatch, start/reverse/cancel and cleanup code remain real.
        self.visibility = self.word(self.word(OUTGOING) + 0x9c)
        self.position = self.word(self.word(OUTGOING) + 0x64)
        self.root_method = self.word(self.word(OWNER) + 0x5c)
        self.root = 0x11dfa6e0
        self.paint_method = self.word(self.word(self.root) + 0x74)
        u.hook_add(UC_HOOK_CODE, self.hook)

    def word(self, p): return struct.unpack('<I', self.u.mem_read(p, 4))[0]
    def put(self, p, v): self.u.mem_write(p, struct.pack('<I', v & 0xffffffff))
    def byte(self, p): return self.u.mem_read(p, 1)[0]
    def putbyte(self, p, v): self.u.mem_write(p, bytes([v]))
    def rect(self, p): return struct.unpack('<4i', self.u.mem_read(p, 16))
    def setrect(self, p, values): self.u.mem_write(p, struct.pack('<4i', *values))
    def gpio(self, bits):
        for i, p in enumerate((0x6000d004, 0x6000d014, 0x6000d024)):
            self.put(p, 8 if bits & (1 << i) else 0)

    def hook(self, uc, pc, n, data):
        self.instructions += 1
        r0, r1, r2, r3 = [uc.reg_read(x) for x in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
        result = None
        if pc == 0xccebc:
            self.put(r0, self.clock); result = r0
        elif pc == 0x151c24:
            self.calls.append(('period', r0, r1)); self.put(r0 + 4, r1); result = 0
        elif pc == 0x151694:
            self.scheduled = True; self.calls.append(('schedule', r0)); result = 0
        elif pc == 0x151c98:
            self.scheduled = False; self.calls.append(('stop', r0)); result = 0
        elif pc == 0x210114:
            self.blits.append((r0, r1, self.rect(r2), self.rect(r3))); result = 0
        elif pc in (0xd6a64, 0xd6afc, 0x2115fc, 0x2115f0, 0x211a70,
                    0x21ab98, 0x21ac04, 0x130090, 0x218be4, 0x1300f4, 0x13d524,
                    0xd15cc, 0x2141a0, 0x140384, 0x2141d8):
            self.calls.append((hex(pc), r0)); result = 0
        elif pc == self.visibility:
            flags = self.word(r0 + 0x20)
            self.put(r0 + 0x20, (flags & ~0x1800) | (0x800 if r1 else 0x1000))
            result = 0
        elif pc == self.position:
            self.setrect(r0 + 0x58, self.rect(r1)); result = 0
        elif pc == self.root_method: result = self.root
        elif pc == self.paint_method: result = 0
        if result is not None:
            uc.reg_write(UC_ARM_REG_R0, result)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def call(self, pc, *args, stack=()):
        regs = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)
        for r, v in zip(regs, args): self.u.reg_write(r, v)
        for i, v in enumerate(stack): self.put(STACK + i * 4, v)
        self.u.reg_write(UC_ARM_REG_SP, STACK)
        self.u.reg_write(UC_ARM_REG_LR, STOP)
        try: self.u.emu_start(pc, STOP, count=100000)
        except Exception:
            print('Execution stopped at', hex(self.u.reg_read(UC_ARM_REG_PC)))
            raise
        assert self.u.reg_read(UC_ARM_REG_PC) == STOP, hex(self.u.reg_read(UC_ARM_REG_PC))
        assert self.u.reg_read(UC_ARM_REG_SP) == STACK

    def start(self, direction=0, mode=0, reverse=False):
        a, b = (INCOMING, OUTGOING) if reverse else (OUTGOING, INCOMING)
        self.call(0x2023a4, OWNER, a, b, direction, stack=(mode, 30, 300, 0, 0))
        assert self.word(OWNER + 0xb8) == 300
        assert self.byte(OWNER + 0xb0) == 1
        # Apple's separate draw-completion callback starts the timer after
        # caching screen images. Simulate its graphics completion boundary.
        if self.byte(0x1082320d):
            self.putbyte(0x1082320d, 0)
            self.call(0x202ea8, OWNER)
        return self.word(OWNER + 0xc0)

    def frame(self, elapsed_ms, base=1_000_000):
        self.clock = (base + elapsed_ms * 1000) & 0xffffffff
        before = len(self.blits)
        self.call(0x202fec, OWNER, 0x20001000)
        return self.blits[before:]


class Blit(Machine):
 def __init__(self,image):
  self.contexts=[];self.pcs={};super().__init__(image)
 def hook(self,uc,pc,n,data):
  self.pcs[pc]=self.pcs.get(pc,0)+1
  if pc==0x210114:
   self.instructions+=1
   r0,r1,r2,r3=[uc.reg_read(x) for x in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
   self.blits.append((r0,r1,self.rect(r2),self.rect(r3)))
   return
  if pc in (0xe442c,0xe944c):
   # External display notifications are simulated. Clipping and pixels execute.
   uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR));return
  if pc==0x11d88c:
   p=uc.reg_read(UC_ARM_REG_R0)
   self.contexts.append([hex(x) for x in struct.unpack('<31I',uc.mem_read(p,124))])
  super().hook(uc,pc,n,data)
 def call(self,pc,*args,stack=()):
  for r,v in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),args):self.u.reg_write(r,v)
  for i,v in enumerate(stack):self.put(STACK+i*4,v)
  self.u.reg_write(UC_ARM_REG_SP,STACK);self.u.reg_write(UC_ARM_REG_LR,STOP)
  self.u.emu_start(pc,STOP,count=5000000)
  assert self.u.reg_read(UC_ARM_REG_PC)==STOP,hex(self.u.reg_read(UC_ARM_REG_PC))
  assert self.u.reg_read(UC_ARM_REG_SP)==STACK

def validate(report_path):
 rng=random.Random(0xE771C1E7)
 results=[]
 # Replay real start/frame/reverse and clipping against the private saved UI.
 for direction in (0,1):
  a,b=Blit(BASE),Blit(NEW)
  for m in (a,b):m.put(0x20001004,9);m.start(direction)
  for t in (15,30,45,50,75,90,110,150,190,220,260,299,300):
   counts=[]
   for m in (a,b):
    old=m.instructions;m.frame(t);counts.append(m.instructions-old)
   left=bytearray(a.u.mem_read(0x10000000,0x2000000));right=bytearray(b.u.mem_read(0x10000000,0x2000000))
   # The only intended UI-state difference is the requested timer period.
   period=OWNER+0xc0-0x10000000
   expected=17 if hashlib.sha256(NEW).hexdigest()==SMOOTH_DRAWING else 30
   assert b.word(OWNER+0xc0)==expected and a.word(OWNER+0xc0)==30
   right[period:period+4]=left[period:period+4]
   assert left==right,('saved UI mismatch',direction,t)
   results.append({'kind':'saved_menu','direction':direction,'elapsed_ms':t,'original_instructions':counts[0],'candidate_instructions':counts[1]})
 print('Saved menu pixel/state equality passed',len(results),flush=True)
 # Execute the original complete clipping + BitBlt entry, replacing only external
 # before/after display notifications; compare whole pixel buffers and canaries.
 a,b=Blit(BASE),Blit(NEW)
 def draw(m,c,seed):
  depth,w,h,dx,dy,pad,overlap=c
  pitch=((w*depth+7)//8+3)&~3;pitch+=pad
  size=pitch*h
  assert 0<size<0x100000
  src=0x11000000;dst=src+overlap if overlap is not None else 0x11200000
  # One encompassing region also checks outside-rectangle bytes and overlaps.
  lo=min(src,dst)-64;hi=max(src,dst)+size+64
  rand=random.Random(seed);data=rand.randbytes(hi-lo)
  m.u.mem_write(lo,data)
  fmt={1:1,2:2,4:4,8:8,16:0x565,32:0x888}[depth]
  desc=lambda p:struct.pack('<9I',p,pitch,depth,{1:0,2:1,4:2,8:3,16:4,32:5}[depth],fmt,0,0,h,w)
  m.u.mem_write(0x20002000,desc(src));m.u.mem_write(0x20002040,desc(dst))
  # Different source/destination rectangles trigger clipping, edges, and shifts.
  s=(0,0,h,w);d=(dy,dx,h+dy,w+dx)
  m.setrect(0x20002100,s);m.setrect(0x20002110,d)
  m.setrect(0x20002120,(0,0,h,w))
  m.u.mem_write(0x20002200,bytes.fromhex('ffffffff00000000'))
  n=m.instructions
  m.call(0x1216a0,0x20002000,0x20002040,0x20002100,0x20002110,stack=(0x20002200,0x20002204,0,0x20002120))
  return bytes(m.u.mem_read(lo,hi-lo)),m.instructions-n
 cases=[]
 # Pixel formats, pitches, source/destination overlaps and both edge directions.
 for depth in (1,2,4,8,16,32):
  for dx in (-17,-3,-2,-1,0,1,2,3,17):
   cases.append((depth,43,7,dx,1,0,None))
 for depth in (8,16,32):
  for overlap in (-64,-32,-28,-8,-4,-2,0,2,4,8,28,32,64):
   for dx in (0,1):cases.append((depth,43,6,dx,-1,0,overlap))
 for _ in range(180):
  depth=rng.choice((1,2,4,8,16,32));w=rng.randint(1,80);h=rng.randint(1,18)
  cases.append((depth,w,h,rng.randint(-w,w),rng.randint(-h,h),rng.choice((0,2,4)),rng.choice((None,None,None,-8,0,2,8,64))))
 # Exact native thumbnail dimensions, full menu size, both alignments.
 for w,h in ((100,100),(200,200),(320,216)):
  for dx in (0,1,2,-1,-2):cases.append((16,w,h,dx,0,0,None))
 for idx,c in enumerate(cases):
  x,n=draw(a,c,idx);y,k=draw(b,c,idx)
  assert x==y,('pixel mismatch',idx,c,next(i for i,(j,l) in enumerate(zip(x,y)) if j!=l))
  results.append({'kind':'copy','case':list(c),'original_instructions':n,'candidate_instructions':k})
  if idx%80==79:print('Pixel comparisons passed',idx+1,flush=True)
 report={'status':'Offline differential checks passed; not installed','candidate_sha256':hashlib.sha256(NEW).hexdigest(),'cases':len(results),'results':results,'limits':['The clock, timer scheduler and external display notifications are simulated.','Instruction counts are not physical latency, FPS or energy measurements.','Art-file reads and storage wait times are unchanged.','Full boot, actual music playback and battery runtime are not validated.'],'device_access':False}
 report_path.write_text(json.dumps(report,indent=2)+'\n')
 print('PASS',len(results),'cases')
 for r in results:
  if r['kind']=='copy' and r['case'][0]==16 and r['case'][1] in (100,200,320):print(r)

if __name__ == '__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--baseline',type=Path,required=True)
 p.add_argument('--candidate',type=Path,required=True)
 p.add_argument('--snapshot-prefix',type=Path,required=True)
 p.add_argument('--report',type=Path,required=True)
 args=p.parse_args()
 load_images(args.baseline,args.candidate,args.snapshot_prefix)
 validate(args.report)
