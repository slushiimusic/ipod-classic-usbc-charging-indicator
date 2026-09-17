"""Replay cadence, lifecycle and complete pixel work without physical hardware.

The scheduler, clock and display notifications are simulated. Requested update
counts and ARM instruction counts cannot establish physical FPS or energy use.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import check_efficient_blit as replay
from check_efficient_blit import Machine, Blit, OWNER, OUTGOING, INCOMING, RECT


def validate(baseline, previous, candidate, snapshot, report):
    replay.load_images(baseline, candidate, snapshot)
    old = previous.read_bytes()
    assert hashlib.sha256(old).hexdigest() == replay.EFFICIENT
    assert hashlib.sha256(replay.NEW).hexdigest() == replay.SMOOTH_DRAWING
    # Preserve the previous rendering helper and all charging code exactly.
    assert replay.NEW[0x7358c0:0x735f18] == old[0x7358c0:0x735f18]
    transitions = []
    for name, image, period in (('original_drawing', replay.BASE, 30),
                                ('drawing_preview_1', old, 30),
                                ('smooth_drawing_preview_2', replay.NEW, 17)):
        for direction in (0, 1):
            m = Blit(image)
            m.put(0x20001004, 9)
            assert m.start(direction) == period
            started = m.instructions
            frames = []
            for t in range(period, 301 + period, period):
                before = m.instructions
                blits = m.frame(t)
                assert len(blits) == 2
                frames.append(dict(elapsed_ms=t, incoming=m.rect(OWNER+0x218),
                                   instructions=m.instructions-before))
                if not m.byte(OWNER+0xb0):
                    break
            assert not m.scheduled and not m.byte(OWNER+0xb0)
            assert m.word(OWNER+0xe4) == m.word(OWNER+0x108) == 0
            assert frames[-1]['incoming'] == RECT
            assert len(frames) == (18 if period == 17 else 10)
            assert m.word(INCOMING+0x20)&0x1800 == 0x800
            assert m.word(OUTGOING+0x20)&0x1800 == 0x1000
            transitions.append(dict(profile=name, direction=direction, period_ms=period,
                                    timed_updates=len(frames), completion_ms=frames[-1]['elapsed_ms'],
                                    instructions=m.instructions-started, frames=frames))
            print(name, direction, len(frames), m.instructions-started, flush=True)
    # Matching elapsed times preserve Apple's easing and transition geometry.
    matching = 0
    for direction in (0, 1):
        a, b = Machine(replay.BASE), Machine(replay.NEW)
        for m in (a, b):
            m.put(0x20001004, 9); m.start(direction)
        for t in range(0, 301, 5):
            a.frame(t); b.frame(t)
            for off in (0x1c4,0x218):
                assert a.rect(OWNER+off) == b.rect(OWNER+off)
            assert a.byte(OWNER+0xb0) == b.byte(OWNER+0xb0)
            matching += 1
    reversals = []
    for direction, at in itertools.product(range(2), (40, 140, 260)):
        a, b = Machine(replay.BASE), Machine(replay.NEW)
        for m in (a, b):
            m.put(0x20001004, 9); m.start(direction); m.frame(at)
            m.start(1-direction, reverse=True)
        for t in range(at, at+301, 10):
            a.frame(t); b.frame(t)
            for off in (0x1c4,0x218):
                assert a.rect(OWNER+off) == b.rect(OWNER+off)
            assert a.byte(OWNER+0xb0) == b.byte(OWNER+0xb0)
            if not a.byte(OWNER+0xb0): break
        assert not a.scheduled and not b.scheduled
        reversals.append(dict(direction=direction, reversed_at_ms=at))
    cancellations = 0
    for image, direction, at in itertools.product((replay.BASE,replay.NEW), range(2), (0,20,150,280)):
        m=Machine(image);m.put(0x20001004,9);m.start(direction);m.frame(at)
        m.call(0x202fb4,OWNER,0)
        assert not m.scheduled and not m.byte(OWNER+0xb0)
        before=len(m.blits);m.call(0x2028fc,OWNER,0)
        assert len(m.blits)==before
        cancellations+=1
    helper = 0x735f18
    guards = 0
    m = Machine(replay.NEW)
    for interval, mode, direction, gpio in itertools.product((15,17,20,30,40),range(3),range(4),range(8)):
        m.putbyte(OWNER+0xa4,direction);m.putbyte(OWNER+0xa5,mode)
        m.put(OWNER+0xb8,300);m.gpio(gpio)
        m.call(helper,OWNER+0xbc,interval)
        expected=17 if interval==30 and mode==0 and direction<2 and gpio==7 else interval
        assert m.word(OWNER+0xc0)==expected and m.word(OWNER+0xb8)==300
        guards+=1
    for offset,value,size in ((0,0x66b298,4),(0x1c,0xfeec,2),(0x20,0x1000,4),
                              (0xb8,0,4),(0xb8,150,4),(0xb8,600,4)):
        m=Machine(replay.NEW);m.putbyte(OWNER+0xa4,0);m.putbyte(OWNER+0xa5,0);m.put(OWNER+0xb8,300)
        m.u.mem_write(OWNER+offset,value.to_bytes(size,'little'))
        m.call(helper,OWNER+0xbc,30)
        assert m.word(OWNER+0xc0)==30
        guards+=1
    # A delayed callback uses elapsed time, and completion stops the native timer.
    delayed=[]
    for step in (25,50,100):
        m=Machine(replay.NEW);m.put(0x20001004,9);m.start()
        n=0
        for t in range(step,301+step,step):
            m.frame(t);n+=1
            if not m.byte(OWNER+0xb0):break
        assert not m.scheduled and not m.byte(OWNER+0xb0)
        delayed.append(dict(callback_gap_ms=step,timed_updates=n))
    result=dict(status='Offline animation checks passed',candidate_sha256=replay.SMOOTH_DRAWING,
                transitions=transitions,matching_time_geometry_cases=matching,
                reversal_cases=reversals,cancellation_cases=cancellations,
                guard_cases=guards,delayed_callbacks=delayed,device_access=False,
                limits=['Clock, scheduler, display notifications and external UI calls simulated.',
                        'Instruction totals exclude display transfer and storage wait costs.',
                        'Physical frame rate, boot, audio playback and battery use are unmeasured.'])
    report.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS',matching,'geometry,',guards,'guards,',cancellations,'cancellations',flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline','previous','candidate','snapshot-prefix','report'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    validate(a.baseline,a.previous,a.candidate,a.snapshot_prefix,a.report)
