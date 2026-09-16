"""Offline ARM replay: real transition math, simulated clock/display/scheduler.

Uses the saved UI graph, never a connected device. It cannot measure LCD FPS,
physical boot, scheduler latency, audio underruns, or battery consumption.
"""
from pathlib import Path
import argparse, hashlib, itertools, json, struct
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import *

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline', type=Path, required=True)
parser.add_argument('--candidate', type=Path, required=True)
parser.add_argument('--snapshot-prefix', type=Path, required=True,
                    help='The exact privately retained UI snapshot; never upload it')
parser.add_argument('--report', type=Path, required=True)
args = parser.parse_args()
OLD = args.baseline.read_bytes()
NEW = args.candidate.read_bytes()
assert hashlib.sha256(OLD).hexdigest() == '9122a8bd1c99e2be03c29c52425849a86277ddbb778a817b64fed5cb82985ba8'
assert hashlib.sha256(NEW).hexdigest() == '13532f5f4312e630384eac74e9a7d17c64d42cf69093f4fe0321d64b7fb8681b'
prefix = args.snapshot_prefix.read_bytes()
assert hashlib.sha256(prefix).hexdigest() == '6f5012f98469a8c74070876b302ca297b0d001845d6bc554af58b2b2b707f285'
SNAP = prefix[0xd64000:0x2d64000]
OWNER, OUTGOING, INCOMING = 0x11d3071c, 0x11ded90c, 0x11ddbb2c
STOP, STACK = 0x40000000, 0x20008000
RECT = (24, 0, 240, 320)


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

    def start(self, direction=0, mode=0, reverse=False, interval=30, duration=300):
        a, b = (INCOMING, OUTGOING) if reverse else (OUTGOING, INCOMING)
        self.call(0x2023a4, OWNER, a, b, direction, stack=(mode, interval, duration, 0, 0))
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



def ready(image=NEW, direction=0, interval=30, duration=300):
    m=Machine(image);m.put(0x20001004,9)
    m.start(direction, interval=interval, duration=duration)
    assert m.byte(OWNER+0xb0)==1
    return m

def finish(m, lag=0):
    at=0;rows=[]
    while m.byte(OWNER+0xb0):
        at+=m.word(OWNER+0xc0)+lag
        assert len(rows)<25
        assert len(m.frame(at))==2
        rows.append(at)
    assert not m.scheduled
    assert m.rect(OWNER+0x218)==RECT
    assert m.word(OWNER+0x108)==m.word(OWNER+0xe4)==0
    return rows

# Native slide completion is actually earlier, without increasing ideal updates.
transitions=[]
for direction in (0,1):
    a,b=ready(OLD,direction),ready(NEW,direction)
    assert a.word(OWNER+0xb8)==300 and b.word(OWNER+0xb8)==150
    stock,fast=finish(a),finish(b)
    assert stock==list(range(30,301,30))
    assert fast==list(range(15,151,15))
    transitions.append(dict(direction=direction,stock_completion_ms=stock[-1],
                            fast_completion_ms=fast[-1],stock_updates=len(stock),fast_updates=len(fast)))

# Same easing positions at corresponding progress, including timer wraparound.
geometry=0
for direction,base in itertools.product((0,1),(1000000,0xfffff000)):
    a,b=ready(OLD,direction),ready(NEW,direction)
    for m in (a,b):m.put(OWNER+0xb4,base)
    for t in range(0,151,3):
        a.frame(t*2,base);b.frame(t,base)
        for off in (0x1c4,0x218):assert a.rect(OWNER+off)==b.rect(OWNER+off)
        assert a.byte(OWNER+0xb0)==b.byte(OWNER+0xb0)
        geometry+=1

# The wrapper must behave like the original entry with 150/15 arguments,
# including the original reversal implementation and cleanup.
reversals=[]
for direction,at in itertools.product((0,1),(0,15,60,135)):
    a,b=ready(OLD,direction,15,150),ready(NEW,direction)
    for m in (a,b):m.frame(at)
    a.start(1-direction,reverse=True,interval=15,duration=150)
    b.start(1-direction,reverse=True)
    for t in range(at,at+181,3):
        assert a.byte(OWNER+0xb0)==b.byte(OWNER+0xb0)
        if not a.byte(OWNER+0xb0):break
        a.frame(t);b.frame(t)
        for off in (0x1c4,0x218):assert a.rect(OWNER+off)==b.rect(OWNER+off)
        assert a.byte(OWNER+0xb0)==b.byte(OWNER+0xb0)
        if not a.byte(OWNER+0xb0):break
    assert not a.scheduled and not b.scheduled, (direction,at,t,a.byte(OWNER+0xb0),b.byte(OWNER+0xb0),a.calls[-12:],b.calls[-12:])
    reversals.append(dict(direction=direction,reversed_at_ms=at,completion_ms=t))

cancellations=0
for direction,at in itertools.product((0,1),(0,15,75,135)):
    m=ready(direction=direction);m.frame(at);m.call(0x202fb4,OWNER,0)
    assert not m.scheduled and not m.byte(OWNER+0xb0)
    count=len(m.blits);m.call(0x2028fc,OWNER,0);assert len(m.blits)==count
    cancellations+=1
lag_cases=[]
for lag in (1,5,20,75):
    rows=finish(ready(),lag)
    assert len(rows)<=10 and 150<=rows[-1]<=150+15+lag
    lag_cases.append(dict(callback_delay_ms=lag,updates=len(rows),completion_ms=rows[-1]))

# Intercept only the original-entry trampoline to inspect all nine forwarded
# arguments across guards. Execute the compiled wrapper; do not emulate its C.
class EntryMachine(Machine):
    def hook(self,uc,pc,n,data):
        if pc==0x735e54:
            sp=uc.reg_read(UC_ARM_REG_SP)
            self.forwarded=[uc.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
            self.forwarded += [self.word(sp+4*i) for i in range(5)]
            uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
        else:super().hook(uc,pc,n,data)
m=EntryMachine(NEW);guards=0
saved_regs=(UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)
def guard(direction,mode,period,duration,visible,klass=0x673004,view=0x5e15):
    global guards
    m.put(OWNER,klass);m.u.mem_write(OWNER+0x1c,struct.pack('<H',view))
    m.put(OWNER+0x20,0x800 if visible else 0x1000)
    for i,r in enumerate(saved_regs):m.u.reg_write(r,0xabc000+i)
    m.call(0x2023a4,OWNER,OUTGOING,INCOMING,direction,stack=(mode,period,duration,0x12345678,0x87654321))
    yes=klass==0x673004 and view==0x5e15 and visible and direction<=1 and mode==0 and period==30 and duration==300
    assert m.forwarded==[OWNER,OUTGOING,INCOMING,direction,mode,15 if yes else period,150 if yes else duration,0x12345678,0x87654321]
    assert [m.u.reg_read(r) for r in saved_regs]==[0xabc000+i for i in range(8)]
    guards+=1
for values in itertools.product(range(4),range(3),(0,15,30,40),(0,150,300,600),(False,True)):
    guard(*values)
for klass,view in ((0x66b298,0x5e15),(0x673004,0xfeec)):
    guard(0,0,30,300,True,klass,view)
# No runtime clock, charging, LCD or timer-driver code was changed.
assert OLD[0x7358c0:0x735e54]==NEW[0x7358c0:0x735e54]
changed=set(i for i,(a,b) in enumerate(zip(OLD,NEW)) if a!=b)
allowed=set(range(0x735e54,0x735f00))
for p in (0xe8,0x308,0xdec,0x2023a4):allowed.update(range(p,p+4))
assert changed<=allowed
report=dict(status='OFFLINE SHORTER MENU CHECKS PASSED',candidate_sha256=hashlib.sha256(NEW).hexdigest(),
 transition_cases=transitions,matching_progress_geometry_cases=geometry,reversal_cases=reversals,
 cancellation_cases=cancellations,lag_cases=lag_cases,entry_guard_cases=guards,
 charging_payload_unchanged=True,cpu_policy_unchanged=True,physical_device_access=False,
 physical_slide_latency_measured=False,battery_impact_measured=False,
 limitations=['Clock, scheduling and image copies are simulated; original easing and completion execute.',
 'The requested 150 ms slide can finish later if real drawing or event delivery is delayed.',
 'Ideal update count equals stock, but physical battery use is not measured.'])
args.report.parent.mkdir(parents=True,exist_ok=True)
args.report.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
