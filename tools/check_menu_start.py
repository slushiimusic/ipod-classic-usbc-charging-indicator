"""Replay native transition preparation against a private saved UI image.

External OS/UI notifications, clock and scheduling are modeled. Native root
painting, visibility, positioning, cache preparation and pixel copies execute.
This does not measure physical input latency, LCD delivery or battery use.
"""
import argparse, hashlib, itertools, json, struct
from pathlib import Path
import check_efficient_blit as replay
from check_efficient_blit import Machine, Blit, OWNER, OUTGOING, INCOMING, RECT, STACK
from unicorn.arm_const import *
CANDIDATE='93a0cc76e089b5edeafed0ea2b0177c912ffbcc0ff3ba9b7d75eb0b47828600e'

class Render(Blit):
    def __init__(self,image):
        super().__init__(image)
        self.paints=0
    def hook(self,u,pc,n,data):
        if pc in (self.visibility,self.position,0x2115fc,0x2115f0,0x211a70,0x21ab98,0x21ac04):
            self.instructions+=1
            return
        if pc==self.paint_method:
            self.instructions+=1
            self.paints+=1
            return
        super().hook(u,pc,n,data)
    def visible(self):
        self.put(0x20001008,0x20001100)
        self.put(0x2000111c,self.root)
        self.put(0x20001004,9)
        self.call(self.visibility,INCOMING,0)
        self.call(self.visibility,OUTGOING,1)
        self.call(0x21ab98,OWNER,OWNER+0x58)
        self.call(self.paint_method,self.root,1)
    def prepare(self,direction=0,capture=0):
        self.call(0x2023a4,OWNER,OUTGOING,INCOMING,direction,stack=(0,30,300,capture,0))
        self.call(0x202c88,0x20001000)
    def pixels(self):
        return [bytes(self.u.mem_read(p,n)) for p,n in
                ((0x11d5b618,138240),(0x11d35e14,138240),(0x10885db0,153600))]

def check(base,previous,candidate,snapshot,report):
    replay.load_images(base,previous,snapshot)
    old=replay.NEW;new=candidate.read_bytes()
    assert hashlib.sha256(old).hexdigest()==replay.SMOOTH_DRAWING
    assert hashlib.sha256(new).hexdigest()==CANDIDATE
    assert old[0x7358c0:0x735f18]==new[0x7358c0:0x735f18]
    assert old[0x11d88c:0x11e000]==new[0x11d88c:0x11e000]
    cases=[];frame_checks=0
    for direction,capture in itertools.product((0,1),(0,1)):
        a,b=Render(old),Render(new)
        counts=[];paints=[]
        for m in (a,b):
            m.visible();i=m.instructions;p=m.paints
            m.prepare(direction,capture)
            counts.append(m.instructions-i);paints.append(m.paints-p)
            assert m.byte(OWNER+0xb0)==1 and m.word(OWNER+0xc0)==17
        assert a.pixels()==b.pixels()
        for t in range(17,307,17):
            a.frame(t);b.frame(t)
            assert a.pixels()==b.pixels(),('frame pixels',direction,capture,t)
            assert a.rect(OWNER+0x1c4)==b.rect(OWNER+0x1c4)
            assert a.rect(OWNER+0x218)==b.rect(OWNER+0x218)
            assert a.byte(OWNER+0xb0)==b.byte(OWNER+0xb0)
            frame_checks+=1
        for m in (a,b):
            assert not m.scheduled and not m.byte(OWNER+0xb0)
            assert m.word(OWNER+0xe4)==m.word(OWNER+0x108)==0
            assert m.rect(OWNER+0x218)==RECT
        cases.append(dict(direction=direction,caller_requested_capture=capture,
                          previous_preparation_instructions=counts[0],candidate_preparation_instructions=counts[1],
                          previous_root_paints=paints[0],candidate_root_paints=paints[1],pixel_match=True))
        print(cases[-1],flush=True)
    # Directly execute the emitted entry wrapper up to the original continuation.
    # Confirm exact register/prologue behavior and only the intended stack argument.
    m=Machine(new);entry=0x735fa8;guards=0
    regs=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)
    for cls,active,direction,mode,capture in itertools.product((0x673004,0x66b298),(0,1),(0,1,2,3),(0,1,2),(0,1)):
        m.put(OWNER,cls);m.putbyte(OWNER+0xb0,active)
        values=(OWNER,OUTGOING,INCOMING,direction)
        for reg,value in zip(regs,values):m.u.reg_write(reg,value)
        for i,value in enumerate((mode,30,300,capture,0)):m.put(STACK+4*i,value)
        m.u.reg_write(UC_ARM_REG_SP,STACK);m.u.reg_write(UC_ARM_REG_LR,0x40000000)
        m.u.emu_start(entry,0x2023a8,count=100)
        assert m.u.reg_read(UC_ARM_REG_PC)==0x2023a8
        assert m.u.reg_read(UC_ARM_REG_SP)==STACK-36
        assert tuple(m.u.reg_read(reg) for reg in regs)==values
        expected=1 if cls==0x673004 and active==0 and direction<=1 and mode==0 else capture
        assert [m.word(STACK+4*i) for i in range(5)]==[mode,30,300,expected,0]
        guards+=1
    # The smaller cadence helper has exactly the same eligibility and period.
    m=Machine(new);cadence_guards=0
    for interval,mode,direction,gpio in itertools.product((15,17,20,30,40),range(3),range(4),range(8)):
        m.putbyte(OWNER+0xa4,direction);m.putbyte(OWNER+0xa5,mode);m.put(OWNER+0xb8,300);m.gpio(gpio)
        m.call(0x735f18,OWNER+0xbc,interval)
        expected=17 if interval==30 and mode==0 and direction<2 and gpio==7 else interval
        assert m.word(OWNER+0xc0)==expected
        cadence_guards+=1
    for offset,value,size in ((0,0x66b298,4),(0x1c,0xfeec,2),(0x20,0x1000,4),(0xb8,0,4),(0xb8,150,4),(0xb8,600,4)):
        m=Machine(new);m.putbyte(OWNER+0xa4,0);m.putbyte(OWNER+0xa5,0);m.put(OWNER+0xb8,300)
        m.u.mem_write(OWNER+offset,value.to_bytes(size,'little'));m.call(0x735f18,OWNER+0xbc,30)
        assert m.word(OWNER+0xc0)==30;cadence_guards+=1
    reversals=0;cancellations=0
    for at in (40,140,260):
        a,b=Render(old),Render(new)
        for m in (a,b):m.visible();m.prepare();m.frame(at)
        assert a.pixels()==b.pixels()
        for m in (a,b):
            m.call(0x2023a4,OWNER,INCOMING,OUTGOING,1,stack=(0,30,300,0,0))
        for t in range(at,at+307,17):
            a.frame(t);b.frame(t)
            assert a.pixels()==b.pixels()
            if not a.byte(OWNER+0xb0):break
        assert not a.scheduled and not b.scheduled
        reversals+=1
    for at in (0,153):
        a,b=Render(old),Render(new)
        for m in (a,b):
            m.visible();m.prepare();m.frame(at);m.call(0x202fb4,OWNER,0)
            assert not m.scheduled and not m.byte(OWNER+0xb0)
            n=len(m.blits);m.call(0x2028fc,OWNER,0);assert len(m.blits)==n
        assert a.pixels()==b.pixels()
        cancellations+=1
    result=dict(status='Offline native preparation and pixel comparisons passed',candidate_sha256=CANDIDATE,
                preparation_cases=cases,animation_frame_comparisons=frame_checks,
                entry_guard_cases=guards,cadence_guard_cases=cadence_guards,
                reversal_cases=reversals,cancellation_cases=cancellations,device_access=False,
                limits=['One saved UI graph; not every menu or physical input sequence is covered.',
                        'External OS/UI notifications, clock and scheduling are modeled.',
                        'Current visible pixels may precede a pending content update; the outgoing image intentionally captures what is already displayed.',
                        'No physical input latency, display FPS, boot, music playback or battery measurement.'])
    report.write_text(json.dumps(result,indent=2)+'\n');print('PASS',guards,'entry guards,',cadence_guards,'cadence guards',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base','previous','candidate','snapshot','report'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();check(a.base,a.previous,a.candidate,a.snapshot,a.report)
