#!/usr/bin/env python3
"""Install a fast voltage-based charging display on exact original Apple 1.3, or restore exact original firmware.

Only changes differing 2048-byte OS sectors and the OS directory checksum.
Firmware writes never touch the partition table, resources, hibernation or music partition. No mounted-file preparation or recording.
"""
import argparse,datetime,hashlib,json,os,plistlib,re,stat,struct,subprocess,sys
from pathlib import Path

ROOT=BACKUP=ORIGINAL=CANDIDATE=RECOVERY=None
BACKUP_SHA=None
ORIGINAL_SHA='784ae3d5540fd2f89e8c947b93629e97f62a06dc311d9745aab143e4db6bb251'
CANDIDATE_SHA='f8b28791b84c5a36ff240a59636208fe7edbf652eb87967d81564c6e37f2622a'
BLOCK=2048
PREFIX=98703360
OS_OFFSET=0x24800
OS_LENGTH=0x736000
DIRECTORY=0x23a00
DIR_BLOCK=DIRECTORY//BLOCK*BLOCK
CHECKSUM=DIRECTORY-DIR_BLOCK+28
SIZE=UUID=None

def require(test,message):
    if not test:raise RuntimeError(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def diskutil(*args):
    return subprocess.check_output(['/usr/sbin/diskutil',*args],stderr=subprocess.STDOUT)
def info(name):return plistlib.loads(diskutil('info','-plist',name))
def stamp():return datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
def own(path):
    if 'SUDO_UID' in os.environ:
        os.chown(path,int(os.environ['SUDO_UID']),int(os.environ['SUDO_GID']))
    elif os.geteuid()==0:
        s=ROOT.stat();os.chown(path,s.st_uid,s.st_gid)
def save(path,data):
    with path.open('xb') as f:
        f.write(data);f.flush();os.fsync(f.fileno())
    own(path)
def document(path,value):save(path,(json.dumps(value,indent=2)+'\n').encode())

def configure(profile_path):
    """Load local device identity and asset paths before any device access."""
    global ROOT,BACKUP,ORIGINAL,CANDIDATE,RECOVERY,BACKUP_SHA,SIZE,UUID
    profile_path=Path(profile_path).expanduser().resolve()
    profile=json.loads(profile_path.read_text())
    require(profile.get('schema_version')==1,'Unsupported local profile')
    UUID=profile.get('volume_uuid')
    SIZE=profile.get('total_size_bytes')
    BACKUP_SHA=profile.get('backup_sha256')
    require(isinstance(UUID,str) and re.fullmatch(r'[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}',UUID),'Set your exact iPod volume UUID in the local profile')
    require(type(SIZE) is int and SIZE>PREFIX and SIZE%BLOCK==0,'Set your exact disk size in bytes')
    require(isinstance(BACKUP_SHA,str) and re.fullmatch(r'[0-9a-f]{64}',BACKUP_SHA),'Set the SHA-256 of your verified original prefix backup')
    def local_path(key):
        value=profile.get(key)
        require(isinstance(value,str) and bool(value),'Missing local path: '+key)
        path=Path(value).expanduser()
        return (path if path.is_absolute() else profile_path.parent/path).resolve()
    BACKUP=local_path('backup_path')
    ORIGINAL=local_path('original_firmware_path')
    CANDIDATE=local_path('candidate_firmware_path')
    ROOT=local_path('output_directory')
    ROOT.mkdir(parents=True,exist_ok=True)
    RECOVERY=ROOT/'backups';RECOVERY.mkdir(exist_ok=True)

def assets():
    backup=BACKUP.read_bytes();original=ORIGINAL.read_bytes();candidate=CANDIDATE.read_bytes()
    require(sha(backup)==BACKUP_SHA,'Recovery backup hash mismatch')
    require(sha(original)==ORIGINAL_SHA and sha(candidate)==CANDIDATE_SHA,'Firmware asset hash mismatch')
    require(len(original)==len(candidate)==OS_LENGTH,'Unexpected firmware length')
    require(sha(backup[OS_OFFSET:OS_OFFSET+OS_LENGTH])=='784ae3d5540fd2f89e8c947b93629e97f62a06dc311d9745aab143e4db6bb251','Recovery backup does not contain stock Apple firmware')
    require(backup[OS_OFFSET:OS_OFFSET+OS_LENGTH]==original,'Restore target is not byte-identical to the original backup')
    changed={i//BLOCK for i,(a,b) in enumerate(zip(original,candidate)) if a!=b}
    require(changed=={0,1,0x18a800//BLOCK,0x1ae000//BLOCK,0x1d8800//BLOCK,0x1d9000//BLOCK,0x735800//BLOCK},'Unexpected fast-indicator firmware sectors')
    return backup,original,candidate

def identify():
    disks=plistlib.loads(diskutil('list','-plist','external','physical')).get('WholeDisks',[])
    matches=[]
    for name in disks:
        if not re.fullmatch(r'disk[0-9]+',name):continue
        d=info(name)
        if d.get('MediaType')!='iPod':continue
        require(d.get('Internal') is False and d.get('WholeDisk') is True,'Refusing a non-external whole disk')
        require(d.get('MediaName')=='iPod' and d.get('BusProtocol')=='USB','Unexpected iPod transport')
        require(d.get('TotalSize')==SIZE and d.get('DeviceBlockSize')==BLOCK,'iPod size or sector layout changed')
        v=info(name+'s2')
        require(v.get('VolumeUUID')==UUID,'iPod volume identity changed')
        require(v.get('PartitionMapPartitionOffset')==PREFIX,'iPod music partition offset changed')
        matches.append((name,d,v))
    require(len(matches)==1,'Exactly one matching iPod must be connected through the 30-pin cable')
    return matches[0]

def read_exact(fd,offset,length):
    require(offset%BLOCK==0 and length%BLOCK==0,'Unaligned device read')
    parts=[]
    while length:
        n=min(length,1024*1024)
        data=os.pread(fd,n,offset)
        require(len(data)==n,'Short device read')
        parts.append(data);offset+=n;length-=n
    return b''.join(parts)

def plan_for(prefix,backup,original,candidate,restore=False):
    require(len(prefix)==PREFIX,'Unexpected captured prefix size')
    require(prefix[:BLOCK]==backup[:BLOCK],'Partition table differs from recovery backup')
    require(prefix[510:512]==b'\x55\xaa','Invalid partition table')
    require(prefix[0x75b000:0xc5b800]==backup[0x75b000:0xc5b800],'Apple resource image differs from the original backup')
    current=prefix[OS_OFFSET:OS_OFFSET+OS_LENGTH]
    wanted=original if restore else candidate
    other=candidate if restore else original
    require(current in (wanted,other),'Connected firmware is not an exact verified source or original Apple firmware')
    directory=prefix[DIR_BLOCK:DIR_BLOCK+BLOCK]
    expected_dir=bytearray(backup[DIR_BLOCK:DIR_BLOCK+BLOCK])
    struct.pack_into('<I',expected_dir,CHECKSUM,sum(current)&0xffffffff)
    require(directory==expected_dir,'Firmware directory differs from the expected layout or checksum')
    target_dir=bytearray(directory)
    struct.pack_into('<I',target_dir,CHECKSUM,sum(wanted)&0xffffffff)
    plan=[]
    for off in range(0,OS_LENGTH,BLOCK):
        before=current[off:off+BLOCK];after=wanted[off:off+BLOCK]
        if before!=after:plan.append((OS_OFFSET+off,before,after))
    if bytes(target_dir)!=directory:plan.append((DIR_BLOCK,directory,bytes(target_dir)))
    require(all(off%BLOCK==0 and len(before)==len(after)==BLOCK and off+BLOCK<=PREFIX for off,before,after in plan),'Invalid write extent')
    require(len(plan) in (0,8),'Unexpected number of installation sectors')
    result=bytearray(prefix)
    for off,_,after in plan:result[off:off+BLOCK]=after
    return plan,bytes(result)

def transact(fd,plan,expected,read=read_exact,write=os.pwrite,sync=os.fsync):
    """Restore all reviewed sectors if a write or verification fails."""
    touched=False
    try:
        for off,before,after in plan:
            require(read(fd,off,BLOCK)==before,'Device sector changed before writing')
            touched=True
            require(write(fd,after,off)==BLOCK,'Short device write')
            sync(fd)
            require(read(fd,off,BLOCK)==after,'Sector read-back did not match')
        require(read(fd,0,PREFIX)==expected,'Final firmware-prefix verification failed')
    except BaseException as error:
        if not touched:raise
        try:
            # Keep the directory last, including during rollback.
            for off,before,_ in plan:
                require(write(fd,before,off)==BLOCK,'Short rollback write')
            sync(fd)
            for off,before,_ in plan:require(read(fd,off,BLOCK)==before,'Rollback verification failed')
        except BaseException as rollback:
            raise RuntimeError(f'INSTALLATION FAILED AND ROLLBACK COULD NOT BE VERIFIED: {error}; {rollback}') from error
        raise RuntimeError(f'Installation stopped; original target sectors restored and verified: {error}') from error

def safe_eject(name,device):
    try:
        diskutil('eject',name)
        return {'retried':False}
    except subprocess.CalledProcessError as first:
        # The manual installations repeatedly needed one ordinary retry after
        # closing the raw handle. Never force a busy volume or reuse a stale id.
        import time
        time.sleep(1)
        n,d,v=identify()
        require(n==name and d.get('DeviceTreePath')==device.get('DeviceTreePath'),'iPod identity changed before eject retry')
        diskutil('eject',name)
        return {'retried':True,'first_error':str(first)}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['install','restore','inspect'])
    p.add_argument('--config',type=Path,required=True)
    args=p.parse_args();mode=args.mode
    configure(args.config)
    backup,original,candidate=assets()
    name,d,v=identify()
    raw='/dev/r'+name
    require(os.geteuid()==0,'macOS administrator authorization is required')
    receipt={'started_utc':stamp(),'mode':mode,'device':name,'volume_uuid':UUID,'device_tree':d.get('DeviceTreePath'),
             'candidate_sha256':CANDIDATE_SHA,'original_sha256':ORIGINAL_SHA,'target_osos_sha256':ORIGINAL_SHA if mode=='restore' else CANDIDATE_SHA,'music_partition_offset':PREFIX,
             'status':'preflight','writes_completed':False}
    # Refuse a busy disk rather than forcing another application off it.
    diskutil('unmountDisk',name)
    result_path=ROOT/f'{mode}-{receipt["started_utc"]}.json'
    fd=None
    try:
        name2,d2,v2=identify()
        require(name2==name and d2.get('DeviceTreePath')==d.get('DeviceTreePath'),'Device identity changed after unmount')
        require(not v2.get('MountPoint'),'iPod is still mounted')
        fd=os.open(raw,os.O_RDONLY)
        require(stat.S_ISCHR(os.fstat(fd).st_mode),'Expected a raw disk character device')
        before=read_exact(fd,0,PREFIX)
        require(sha(read_exact(fd,0,PREFIX))==sha(before),'Device changed between pre-install reads')
        receipt['observed_before_osos_sha256']=sha(before[OS_OFFSET:OS_OFFSET+OS_LENGTH])
        plan,expected=plan_for(before,backup,original,candidate,mode=='restore')
        receipt['before_prefix_sha256']=sha(before)
        receipt['expected_after_prefix_sha256']=sha(expected)
        receipt['sectors']=[{'offset':off,'bytes':BLOCK,'before_sha256':sha(a),'after_sha256':sha(b)} for off,a,b in plan]
        if mode=='inspect' or not plan:
            receipt['status']='inspection passed' if mode=='inspect' else 'target already installed and verified'
            receipt['target_verified']=mode!='inspect'
            return
        recovery=RECOVERY/f'pre-{mode}-{receipt["started_utc"]}-prefix.bin'
        save(recovery,before)
        require(sha(recovery.read_bytes())==sha(before),'Saved fresh recovery copy failed verification')
        receipt['fresh_recovery_copy']=str(recovery)
        receipt['status']='preflight passed; recovery copy verified'
        document(ROOT/f'preflight-{receipt["started_utc"]}.json',receipt)
        os.close(fd);fd=None
        # Recheck both identity and bytes immediately before opening for writes.
        name3,d3,v3=identify()
        require(name3==name and d3.get('DeviceTreePath')==d.get('DeviceTreePath') and not v3.get('MountPoint'),'Device changed before writing')
        fd=os.open(raw,os.O_RDWR)
        require(stat.S_ISCHR(os.fstat(fd).st_mode) and os.fstat(fd).st_rdev==os.stat(raw).st_rdev,'Raw device identity changed')
        require(read_exact(fd,0,PREFIX)==before,'Device contents changed before writing')
        receipt['writes_attempted']=True
        transact(fd,plan,expected)
        receipt['status']=('Original Apple 1.3 firmware restored and read-back verified; physical boot pending' if mode=='restore' else 'Reconnect ramp correction installed and read-back verified; physical boot, repeated USB-C detection and full-charge behavior unverified')
        receipt['writes_completed']=True
        receipt['after_osos_sha256']=sha(read_exact(fd,OS_OFFSET,OS_LENGTH))
        receipt['verified_only_planned_prefix_changes']=True
    except BaseException as e:
        receipt['status']='stopped';receipt['error']=str(e)
        receipt['rollback_verified']=str(e).startswith('Installation stopped; original target sectors restored and verified:')
        raise
    finally:
        if fd is not None:os.close(fd)
        receipt['finished_utc']=stamp()
        try:
            if receipt['writes_completed'] or receipt.get('target_verified'):receipt['eject_result']=safe_eject(name,d);receipt['ejected']=True
            elif not receipt.get('writes_attempted') or receipt.get('rollback_verified'):diskutil('mountDisk',name)
            else:receipt['requires_recovery']=True
        except Exception as e:
            receipt['mount_or_eject_error']=str(e)
            print('Device mount/eject needs attention:',e,file=sys.stderr)
        try:document(result_path,receipt)
        except Exception as e:print('Could not save final receipt:',e,file=sys.stderr)
        print(json.dumps(receipt,indent=2))

def run_cli():
    try:main()
    except Exception as e:
        # main() can fail during asset or device identification before it
        # creates an installation receipt. Preserve that error as well.
        record={'finished_utc':stamp(),'status':'command stopped',
                'mode':sys.argv[1] if len(sys.argv)>1 else None,
                'candidate_sha256':CANDIDATE_SHA,'error':str(e),
                'writes_completed':'not established by this error record',
                'note':'Use any installation receipt for write and rollback status.'}
        try:document(ROOT/f'error-{record["finished_utc"]}.json',record)
        except Exception as log_error:
            print('Could not save command error:',log_error,file=sys.stderr)
        raise SystemExit(str(e))

if __name__=='__main__':run_cli()
