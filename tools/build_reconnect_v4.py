"""Build the charging indicator from hash-pinned Apple firmware; no device I/O."""
from pathlib import Path
from elftools.elf.elffile import ELFFile
import argparse, hashlib, json, shutil, struct, subprocess
ROOT=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--original',type=Path,required=True)
parser.add_argument('--output-dir',type=Path,default=ROOT/'build/reconnect-v4')
parser.add_argument('--clang',default=shutil.which('clang') or 'clang')
args=parser.parse_args()
OUT=args.output_dir.resolve()
OUT.mkdir(parents=True,exist_ok=True)
command=[args.clang,'--target=armv4t-none-eabi','-marm','-Oz',
         '-ffreestanding','-fno-builtin','-fomit-frame-pointer','-Wall','-Wextra',
         '-Werror','-c',str(ROOT/'src/charging_indicator_v4.c'),'-o',str(OUT/'indicator.o')]
subprocess.run(command,check=True)
original=args.original.read_bytes()
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha(original)=='784ae3d5540fd2f89e8c947b93629e97f62a06dc311d9745aab143e4db6bb251'
names=('charging_constructor','charging_timer','charging_display','response_step')
with (OUT/'indicator.o').open('rb') as f:
    elf=ELFFile(f)
    code=bytearray(elf.get_section_by_name('.text').data())
    syms=elf.get_section_by_name('.symtab')
    offsets={n:syms.get_symbol_by_name(n)[0]['st_value'] for n in names}
    for name in ('.data','.bss','.rodata'):
        s=elf.get_section_by_name(name)
        assert s is None or s['sh_size']==0,name
    rel=elf.get_section_by_name('.rel.text')
    if rel:
        for r in rel.iter_relocations():
            symbol=syms.get_symbol(r['r_info_sym'])
            # Resolve only compiler-emitted ARM internal calls. Everything
            # else is rejected rather than guessing relocation semantics.
            assert r['r_info_type'] in (28,29) and symbol.name in offsets
            off=r['r_offset']; w=struct.unpack_from('<I',code,off)[0]
            addend=(w&0xffffff)<<2
            if addend&(1<<25): addend-=1<<26
            delta=offsets[symbol.name]+addend-off
            assert delta%4==0 and -(1<<25)<=delta<(1<<25)
            struct.pack_into('<I',code,off,(w&0xff000000)|((delta>>2)&0xffffff))
start=0x7358c0
end=start+len(code)+4
assert original[start:start+4]==bytes.fromhex('55aa55aa')
assert not any(original[start+4:])
assert len(code)%4==0 and end<=len(original),(len(code),len(original)-start-4)
candidate=bytearray(original); changes=[]
def branch(src,dst,link=True):
    delta=dst-src-8
    assert delta%4==0 and -(1<<25)<=delta<(1<<25)
    return (0xeb000000 if link else 0xea000000)|((delta>>2)&0xffffff)
def word(offset,before,after,reason):
    assert struct.unpack_from('<I',original,offset)[0]==before,hex(offset)
    struct.pack_into('<I',candidate,offset,after)
    changes.append(dict(offset=hex(offset),before=hex(before),after=hex(after),reason=reason))
word(0x18ad4c,0xe3a00024,0xe3a000c0,'Allocate 192 bytes for original object and isolated voltage estimate')
word(0x18ad5c,branch(0x18ad5c,0x1e080c,False),branch(0x18ad5c,start+offsets['charging_constructor'],False),'Initialize isolated edge estimate')
word(0x1d8ebc,branch(0x1d8ebc,0x1d91dc),branch(0x1d8ebc,start+offsets['charging_timer']),'Fresh voltage polling with immediate native notification on state changes')
word(0x1d95a0,30000,250,'Quarter-second estimator polling; full native housekeeping remains 30 seconds or state change')
word(0x1ae664,branch(0x1ae664,0x1ae774),branch(0x1ae664,start+offsets['charging_display']),'Reuse the original Apple charging animation for the fast voltage estimate')
word(0xe8,start+4,end,'Payload logical end')
word(0x308,0x04000000+start,0x04000000+end-4,'Startup boundary')
word(0xdec,0x04000000+start,0x04000000+end-4,'Runtime boundary')
candidate[start:end]=code+bytes.fromhex('55aa55aa')
(OUT/'osos-reconnect-v4.bin').write_bytes(candidate)
report=dict(status='LOCAL BUILD; NOT INSTALLED',input_sha256=sha(original),
    output_sha256=sha(candidate),image_bytes=len(candidate),payload_offset=hex(start),payload_bytes=len(code),
    symbols={n:hex(start+v) for n,v in offsets.items()},changes=changes,
    changed_os_sectors=[hex(i) for i in range(0,len(original),2048) if original[i:i+2048]!=candidate[i:i+2048]],
    additive_checksum=sum(candidate)&0xffffffff,device_access=False,physical_charging_fixed=False,
    allocation_bytes=192,poll_interval_ms=250,confirmation_clock_ticks=400,nominal_step_response_ms=[500,750],startup_settle_ms=3000,
    legacy_gradual_path_preserved=False,stale_after_clock_ticks=2000,rise_counts=32,reconnect_min_rise_counts=12,reconnect_retains_prior_peak=True,reconnect_window_clock_ticks=10000,reconnect_prior_high_tolerance_counts=4,rise_window_ticks=3000,pre_rise_reference_held=True,positive_noise_does_not_raise_reference=True,fall_counts=16,normal_native_update_clock_ticks=30000,
    fresh_native_battery_reads=True,charger_control_changes=False,cpu_clock_changes=False,
    storage_writes_at_runtime=False,direct_usb_presence=False,screen_on_rise_preserved=True,deep_sleep_wake_fixed=False,build_command=command,
    limitations=['Voltage changes can result from load changes as well as charging.',
     'Recent same-load rise/fall pairs allow a 12-count return near the previous high for about ten seconds; this can also match a load recovery.',
     'Fresh backlight-only turn-on no longer erases a large rise. Other load changes, boot, flat voltage and polling gaps can still prevent detection.',
     'An unplug without a sufficient voltage fall cannot be distinguished from continued charging.',
     'Polling adds up to four battery reads per second; battery-runtime cost is unmeasured.',
     'Physical timing and full boot are unverified; this is not a proven Apple-speed fix.'])
(OUT/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
