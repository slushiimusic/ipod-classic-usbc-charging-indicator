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
assert hashlib.sha256(OLD).hexdigest() == '4322aba038229466ebf6c25116327d38ca76ce7bb98216fc7d6e91753b13a270'
assert hashlib.sha256(NEW).hexdigest() == '7b882c8985ce5e13f99e47085631d05b888f9086df97bf73a6d6bae364416cf1'
MANIFEST = {'payload_offset': '0x735e38'}
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


def main():
    assert NEW[0x7358c0:0x735e38] == OLD[0x7358c0:0x735e38]
    assert NEW[0xfe000:0xfe800] == OLD[0xfe000:0xfe800]
    assert NEW[0x202100:0x2028c8] == OLD[0x202100:0x2028c8]
    assert NEW[0x2028cc:0x203134] == OLD[0x2028cc:0x203134]
    cases = []
    for image, label in ((OLD, 'original'), (NEW, 'smooth')):
        for direction, mode in itertools.product(range(2), (0,)):
            m = Machine(image)
            m.put(0x20001004, 9)
            period = m.start(direction, mode)
            assert period == (30 if label == 'original' else 20)
            frames = []
            for t in range(period, 301, period):
                blits = m.frame(t)
                assert len(blits) == 2, (label, direction, mode, t, blits)
                frames.append(dict(t=t, outgoing=m.rect(OWNER + 0x1c4), incoming=m.rect(OWNER + 0x218)))
            assert m.byte(OWNER + 0xb0) == 0 and not m.scheduled
            assert m.word(OWNER + 0xe4) == m.word(OWNER + 0x108) == 0
            assert frames[-1]['incoming'] == RECT
            assert m.word(INCOMING + 0x20) & 0x1800 == 0x800
            assert m.word(OUTGOING + 0x20) & 0x1800 == 0x1000
            before = len(m.blits)
            m.call(0x2028fc, OWNER, 0)
            assert len(m.blits) == before
            cases.append(dict(profile=label, direction=direction, mode=mode, period_ms=period,
                              duration_ms=300, timed_frames=len(frames), frames=frames))
    # At matching wall-clock times the complete native easing and geometry
    # must be identical. The cadence change cannot accelerate the motion.
    for direction in range(2):
        a, b = Machine(OLD), Machine(NEW)
        for m in (a, b): m.put(0x20001004, 9); m.start(direction)
        for t in range(0, 301, 5):
            a.frame(t); b.frame(t)
            for off in (0x1c4, 0x218): assert a.rect(OWNER+off) == b.rect(OWNER+off)
            assert a.byte(OWNER+0xb0) == b.byte(OWNER+0xb0)
    # Full start path reversals and explicit cancellation, including late
    # callbacks after cancellation. No mocked transition or cleanup routine.
    reversal_cases = []
    for direction, at in itertools.product(range(2), (40, 140, 260)):
        a, b = Machine(OLD), Machine(NEW)
        for m in (a, b):
            m.put(0x20001004, 9); m.start(direction); m.frame(at)
            m.start(1-direction, reverse=True)
        for t in range(at, at+301, 10):
            a.frame(t); b.frame(t)
            for off in (0x1c4, 0x218): assert a.rect(OWNER+off) == b.rect(OWNER+off)
            assert a.byte(OWNER+0xb0) == b.byte(OWNER+0xb0)
            if not a.byte(OWNER+0xb0): break
        assert not a.scheduled and not b.scheduled
        assert not a.byte(OWNER+0xb0) and not b.byte(OWNER+0xb0)
        reversal_cases.append(dict(direction=direction, reversed_at_ms=at))
    cancellation_cases = 0
    for image, direction, at in itertools.product((OLD, NEW), range(2), (0, 20, 150, 280)):
        m = Machine(image); m.put(0x20001004, 9); m.start(direction); m.frame(at)
        m.call(0x202fb4, OWNER, 0)
        assert not m.scheduled and not m.byte(OWNER+0xb0)
        before = len(m.blits)
        m.call(0x2028fc, OWNER, 0)
        assert len(m.blits) == before
        cancellation_cases += 1
    # Scope guards exercise the emitted ARM helper with simulated GPIOs.
    guards = 0
    m = Machine(NEW)
    helper = int(MANIFEST['payload_offset'], 16)
    for interval, mode, direction, gpio in itertools.product((15,20,30,40), range(3), range(4), range(8)):
        m.putbyte(OWNER+0xa4, direction); m.putbyte(OWNER+0xa5, mode)
        m.put(OWNER+0xb8, 300); m.gpio(gpio)
        m.call(helper, OWNER+0xbc, interval)
        expected = 20 if interval == 30 and mode == 0 and direction < 2 and gpio == 7 else interval
        assert m.word(OWNER+0xc0) == expected
        assert m.word(OWNER+0xb8) == 300
        guards += 1
    for offset, value, size in [(0,0x66b298,4),(0x1c,0xfeec,2),(0x20,0x1000,4),
                               (0xb8,0,4),(0xb8,150,4),(0xb8,600,4)]:
        m = Machine(NEW); m.putbyte(OWNER+0xa4,0); m.putbyte(OWNER+0xa5,0); m.put(OWNER+0xb8,300)
        m.u.mem_write(OWNER+offset, value.to_bytes(size,'little'))
        m.call(helper, OWNER+0xbc,30)
        assert m.word(OWNER+0xc0) == 30
        guards += 1
    report = dict(status='OFFLINE MENU TRANSITION REPLAY PASSED', physical_device_access=False,
                  candidate_sha256=hashlib.sha256(NEW).hexdigest(), transition_cases=len(cases),
                  scope_guard_cases=guards, matching_time_geometry_cases=122,
                  reversal_cases=reversal_cases, cancellation_cases=cancellation_cases,
                  cases=cases, limitations=['Clock, scheduler, synchronization, image copies and external UI calls simulated',
                                           'No physical boot, LCD frame rate or battery measurement'])
    path = args.report
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k:v for k,v in report.items() if k != 'cases'}, indent=2))


if __name__ == '__main__': main()
