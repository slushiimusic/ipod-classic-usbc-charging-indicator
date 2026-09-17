"""Compare the candidate copy routines with native stock copies, offline.

Only the two copy hooks and their exact emitted helpers are applied to a local
charging-v4 image. This isolates pixel-copy equivalence from intentional changes
to cadence and preparation. Neither the fixture nor private firmware is output.
"""
from pathlib import Path
import argparse,hashlib,json
import check_efficient_blit as r
CANDIDATE='20b25c2436ebb1df79a2e5150a816c17c1c7482d59850316565007a8e0df1470'
p=argparse.ArgumentParser(description=__doc__)
for name in ('base','candidate','snapshot','report'):p.add_argument('--'+name,type=Path,required=True)
args=p.parse_args();r.BASE=args.base.read_bytes();candidate=args.candidate.read_bytes()
assert hashlib.sha256(r.BASE).hexdigest()=='9122a8bd1c99e2be03c29c52425849a86277ddbb778a817b64fed5cb82985ba8'
assert hashlib.sha256(candidate).hexdigest()==CANDIDATE
prefix=args.snapshot.read_bytes()
assert hashlib.sha256(prefix).hexdigest()=='6f5012f98469a8c74070876b302ca297b0d001845d6bc554af58b2b2b707f285'
r.SNAP=prefix[0xd64000:0x2d64000]
copy_only=bytearray(r.BASE)
for start,end in [(0x11db68,0x11db7c),(0x11dc10,0x11dc14),(0x735e54,0x735f10)]:copy_only[start:end]=candidate[start:end]
r.NEW=bytes(copy_only)
r.validate(args.report)
report=json.loads(args.report.read_text())
report['full_candidate_sha256']=CANDIDATE
report['scope']='Only candidate copy hooks and helpers transplanted into a charging-v4 fixture; complete candidate menu behavior is tested separately.'
args.report.write_text(json.dumps(report,indent=2)+'\n')
