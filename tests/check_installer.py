"""Failure-injection and dedicated-file tests; in-memory disks and temp files only."""
from pathlib import Path
from tempfile import TemporaryDirectory
import argparse,importlib.util,json,struct
R=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--config',type=Path,required=True)
args=parser.parse_args()
package=R/'tools'
spec=importlib.util.spec_from_file_location('installer',package/'install.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.configure(args.config)
backup,original,candidate=m.assets()
plan,expected=m.plan_for(backup,backup,original,candidate)
assert len(plan)==8 and plan[-1][0]==m.DIR_BLOCK
allowed={o for o,a,b in plan}
assert all(o+2048<=m.OS_OFFSET+m.OS_LENGTH for o in allowed)
sentinel=b'preserve music partition'*100
class Disk:
    def __init__(self,initial,fail=None):self.data=bytearray(initial+sentinel);self.calls=0;self.fail=fail
    def read(self,fd,o,n):return bytes(self.data[o:o+n])
    def write(self,fd,data,o):
        self.calls+=1
        assert o in allowed and len(data)==2048
        if self.calls==self.fail:raise OSError('Injected failure')
        self.data[o:o+len(data)]=data
        return len(data)
    def sync(self,fd):pass
    def apply(self,p,e):m.transact(None,p,e,self.read,self.write,self.sync)
cases=[]
d=Disk(backup);d.apply(plan,expected)
assert d.data==expected+sentinel
assert m.plan_for(expected,backup,original,candidate)[0]==[]
restore,restored=m.plan_for(expected,backup,original,candidate,True)
assert restored==backup and len(restore)==8
d.apply(restore,restored);assert d.data==backup+sentinel
cases.append('install and exact-stock restore modify only eight reviewed sectors and preserve all other bytes')
for source,p,target,label in ((backup,plan,expected,'install'),(expected,restore,backup,'restore')):
    for n in range(1,9):
        d=Disk(source,n)
        try:d.apply(p,target)
        except RuntimeError as e:assert 'restored and verified' in str(e)
        else:raise AssertionError('Injected failure accepted')
        assert d.data==source+sentinel
        cases.append(f'{label}: failure at sector {n} rolls back and verifies')
d=Disk(backup)
normal=d.write
def short(fd,data,o):
    if d.calls==2:d.calls+=1;d.data[o:o+100]=data[:100];return 100
    return normal(fd,data,o)
try:m.transact(None,plan,expected,d.read,short,d.sync)
except RuntimeError as e:assert 'restored and verified' in str(e)
else:raise AssertionError('Short write accepted')
assert d.data==backup+sentinel;cases.append('short write restores exact prior prefix')
def disconnected(*args):raise OSError('Disconnected')
try:m.transact(None,plan,expected,d.read,disconnected,d.sync)
except RuntimeError as e:assert 'ROLLBACK COULD NOT BE VERIFIED' in str(e)
else:raise AssertionError('Persistent failure accepted')
cases.append('persistent disconnect explicitly reports unverified recovery')
for label,off in [('partition',446),('directory',m.DIRECTORY+12),('resource',0x75b020),('unknown firmware',m.OS_OFFSET+5000)]:
    bad=bytearray(backup);bad[off]^=1
    try:m.plan_for(bad,backup,original,candidate)
    except RuntimeError:pass
    else:raise AssertionError(label)
    cases.append(label+' mismatch rejected')

# Dedicated snapshot checks are defined below.
# Validate identity guards without invoking diskutil or opening device nodes.
real_diskutil,real_info=m.diskutil,m.info
import plistlib
valid_d={'MediaType':'iPod','Internal':False,'WholeDisk':True,'MediaName':'iPod','BusProtocol':'USB','TotalSize':m.SIZE,'DeviceBlockSize':m.BLOCK}
valid_v={'VolumeUUID':m.UUID,'PartitionMapPartitionOffset':m.PREFIX}
m.diskutil=lambda *args:plistlib.dumps({'WholeDisks':['disk42']})
m.info=lambda name:valid_v.copy() if name.endswith('s2') else valid_d.copy()
assert m.identify()[0]=='disk42'
for key,val in [('Internal',True),('BusProtocol','SATA'),('TotalSize',1),('DeviceBlockSize',512)]:
    old=valid_d[key];valid_d[key]=val
    try:m.identify()
    except RuntimeError:pass
    else:raise AssertionError(key)
    valid_d[key]=old;cases.append(key+' identity mismatch rejected')
valid_v['VolumeUUID']='wrong'
try:m.identify()
except RuntimeError:pass
else:raise AssertionError('Wrong UUID')
cases.append('wrong volume UUID rejected')
m.diskutil,m.info=real_diskutil,real_info
saved_identify=m.identify
# Only ordinary ejection is retried, after fresh identity checks. No device use.
import subprocess,time
old_diskutil,old_identify,old_sleep=m.diskutil,m.identify,time.sleep
calls=[];time.sleep=lambda seconds:calls.append(('sleep',seconds))
dev={'DeviceTreePath':'expected'}
m.identify=lambda:('disk42',dev,{})
def eject(*args):
    calls.append(args)
    if len([c for c in calls if c[0]=='eject'])==1:raise subprocess.CalledProcessError(1,args)
    return b'Disk disk42 ejected'
m.diskutil=eject
assert m.safe_eject('disk42',dev)['retried']
assert calls==[('eject','disk42'),('sleep',1),('eject','disk42')]
cases.append('normal eject retry succeeds after identity recheck, without force')
calls=[];m.identify=lambda:('disk43',dev,{})
try:m.safe_eject('disk42',dev)
except RuntimeError:pass
else:raise AssertionError('Eject retried against changed disk')
assert calls==[('eject','disk42'),('sleep',1)]
cases.append('eject retry refuses changed device identity')
calls=[];m.identify=lambda:('disk42',dev,{})
m.diskutil=lambda *a:calls.append(a)
assert not m.safe_eject('disk42',dev)['retried'] and calls==[('eject','disk42')]
cases.append('successful first ejection is not repeated')
m.diskutil=old_diskutil;m.identify=old_identify;time.sleep=old_sleep
report=dict(status='LOCAL INSTALLER AND RECOVERY CHECKS PASS; NOT INSTALLED',firmware_sha256=m.CANDIDATE_SHA,
    installer_script_sha256=m.sha((package/'install.py').read_bytes()),
    restore_sha256=m.ORIGINAL_SHA,case_count=len(cases),cases=cases,device_access=False,
    planned_disk_sectors=[hex(o) for o,a,b in plan],stock_install_bytes=16384,
    limitation='Simulated disks and identities only; no physical install, boot or USB-C timing verification.')
(m.ROOT/'installer-tests.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ('status','case_count','firmware_sha256')}))
