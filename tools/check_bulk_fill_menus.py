"""Offline saved-image comparison. Never opens a device; no physical timing claim."""
from pathlib import Path
import argparse,sys,json,itertools,hashlib
import check_efficient_blit as r
from check_menu_start import Render
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

frames=0;preps=[]
for direction,capture in itertools.product((0,1),(0,1)):
 a,b=Render(old),Render(new);counts=[]
 for m in (a,b):
  m.visible();before=m.instructions;m.prepare(direction,capture);counts.append(m.instructions-before)
 assert a.pixels()==b.pixels()
 for t in range(17,307,17):
  a.frame(t);b.frame(t);assert a.pixels()==b.pixels();frames+=1
 for p,n in [(r.OWNER,0x228),(r.OUTGOING,0xa4),(r.INCOMING,0xa4),(a.root,0xc0)]:assert a.u.mem_read(p,n)==b.u.mem_read(p,n)
 preps.append(dict(direction=direction,capture=capture,previous_instructions=counts[0],candidate_instructions=counts[1]))
 print('menu',preps[-1],flush=True)
for at in (40,140,260):
 a,b=Render(old),Render(new)
 for m in (a,b):m.visible();m.prepare();m.frame(at);m.call(0x2023a4,r.OWNER,r.INCOMING,r.OUTGOING,1,stack=(0,30,300,0,0))
 for t in range(at,at+307,17):
  a.frame(t);b.frame(t);assert a.pixels()==b.pixels()
  if not a.byte(r.OWNER+0xb0):break
 assert not a.scheduled and not b.scheduled
for at in (0,153):
 a,b=Render(old),Render(new)
 for m in (a,b):
  m.visible();m.prepare();m.frame(at);m.call(0x202fb4,r.OWNER,0);assert not m.scheduled and not m.byte(r.OWNER+0xb0)
 assert a.pixels()==b.pixels()
for direction,dirty in itertools.product((0,1),((0,0,240,320),(0,0,24,320),(24,0,60,320))):
 a,b=Render(old),Render(new)
 for m in (a,b):m.visible();m.setrect(0x20001200,dirty);m.call(0x141e30,m.root,0x20001200);m.prepare(direction)
 assert a.pixels()==b.pixels()
 for t in (17,85,170,255,306):a.frame(t);b.frame(t);assert a.pixels()==b.pixels()
 for p,n in [(r.OWNER,0x228),(r.OUTGOING,0xa4),(r.INCOMING,0xa4),(a.root,0xc0)]:assert a.u.mem_read(p,n)==b.u.mem_read(p,n)
rpt=dict(candidate_sha256=hashlib.sha256(new).hexdigest(),preparations=preps,frames=frames,reversals=3,cancellations=2,pending_redraws=6,device_access=False,limits=['One saved UI graph with modeled clock, scheduler and display delivery; no physical latency or battery measurement.'])
args.report.write_text(json.dumps(rpt,indent=2)+'\n');print('PASS menus')
