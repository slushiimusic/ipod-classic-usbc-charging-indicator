"""Build standalone launchers. Includes our patches, never complete Apple images."""
import argparse
import base64
import hashlib
import io
from pathlib import Path
import textwrap
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def package(output):
    output.mkdir(parents=True, exist_ok=True)
    runtime = io.BytesIO()
    files = [ROOT / 'run_installer.py', *sorted((ROOT / 'installer').glob('*.py')),
             *sorted((ROOT / 'patches').glob('*.json'))]
    with zipfile.ZipFile(runtime, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(ROOT).as_posix(), (2026, 9, 16, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, path.read_bytes())
    data = runtime.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    payload = '\n'.join(textwrap.wrap(base64.b64encode(data).decode(), 76)) + '\n'
    bootstrap = '''import base64,hashlib,io,pathlib,subprocess,sys,tempfile,zipfile
blob=pathlib.Path(sys.argv[1]).read_text().rsplit("\\n# PAYLOAD\\n",1)[1]
data=base64.b64decode(blob)
if hashlib.sha256(data).hexdigest() != "DIGEST": raise SystemExit("Launcher payload verification failed")
with tempfile.TemporaryDirectory(prefix="ipod-indicator-") as folder:
    zipfile.ZipFile(io.BytesIO(data)).extractall(folder)
    status=subprocess.call([sys.executable,str(pathlib.Path(folder)/"run_installer.py"),"MODE",*sys.argv[2:]])
raise SystemExit(status)
'''.replace('DIGEST', digest)
    # No firmware I/O occurs until the extracted Python program runs and validates the iPod.
    for mode, name in [('install', 'Install-iPod-USB-C'), ('restore', 'Restore-Apple-Firmware'),
                       ('responsive', 'Install-Optional-Screen-Boost'), ('smooth', 'Install-Optional-Smooth-Menus'), ('fast', 'Install-Faster-Menus')]:
        shell = '''#!/bin/bash
set -eu
py="$(command -v python3 || true)"
if [ -z "$py" ]; then
  echo "Python 3 is required. Install Python 3 from python.org, then run this file again."
  exit 1
fi
exec "$py" - "$0" "$@" <<'IPOD_PYTHON'
''' + bootstrap.replace('MODE', mode) + 'IPOD_PYTHON\n# PAYLOAD\n' + payload
        path = output / (name + '.command')
        path.write_text(shell)
        path.chmod(0o755)
        ps = r'''
$ErrorActionPreference='Stop'
$tmp=Join-Path ([IO.Path]::GetTempPath()) ('ipod-indicator-'+[Guid]::NewGuid().ToString('N'))
try {
 $text=[IO.File]::ReadAllText($env:IPOD_LAUNCHER)
 $data=[Convert]::FromBase64String(($text -split '# PAYLOAD\r?\n')[-1])
 $h=[Security.Cryptography.SHA256]::Create()
 $hash=([BitConverter]::ToString($h.ComputeHash($data))).Replace('-','').ToLowerInvariant()
 if ($hash -ne 'DIGEST') { throw 'Launcher payload verification failed' }
 [IO.Directory]::CreateDirectory($tmp) | Out-Null
 $zip=Join-Path $tmp 'runtime.zip'; [IO.File]::WriteAllBytes($zip,$data)
 Add-Type -AssemblyName System.IO.Compression.FileSystem
 [IO.Compression.ZipFile]::ExtractToDirectory($zip,$tmp)
 $entry=Join-Path $tmp 'run_installer.py'
 $params=@($entry,'MODE')
 if ($env:IPOD_OPTION -eq '--self-test') { $params+='--self-test' }
 if (Get-Command py.exe -ErrorAction SilentlyContinue) { & py.exe -3 @params }
 elseif (Get-Command python.exe -ErrorAction SilentlyContinue) { & python.exe @params }
 else { throw 'Python 3 is required. Install Python 3 from python.org and enable its launcher, then run this file again.' }
 $result=$LASTEXITCODE
} catch { Write-Host ('STOPPED: '+$_); $result=1 }
finally { if (Test-Path $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force } }
exit $result
'''.replace('DIGEST', digest).replace('MODE', mode)
        encoded = base64.b64encode(ps.encode('utf-16-le')).decode()
        cmd = ('@echo off\r\nsetlocal\r\nset "IPOD_LAUNCHER=%~f0"\r\nset "IPOD_OPTION=%~1"\r\n'
               + 'powershell.exe -NoProfile -NonInteractive -EncodedCommand ' + encoded + '\r\n'
               + 'set "IPOD_RESULT=%ERRORLEVEL%"\r\n'
               + 'if not "%IPOD_OPTION%"=="--self-test" pause\r\n'
               + 'exit /b %IPOD_RESULT%\r\n# PAYLOAD\r\n' + payload.replace('\n', '\r\n'))
        (output / (name + '.cmd')).write_bytes(cmd.encode('ascii'))
    archives = []
    groups = [('iPod-USB-C-Launchers.zip', sorted(output.glob('*.command')) + sorted(output.glob('*.cmd'))),
              ('Install-iPod-USB-C-Mac.zip', [output / 'Install-iPod-USB-C.command']),
              ('Install-Optional-Screen-Boost-Mac.zip', [output / 'Install-Optional-Screen-Boost.command']),
              ('Install-Optional-Smooth-Menus-Mac.zip', [output / 'Install-Optional-Smooth-Menus.command']),
              ('Install-Faster-Menus-Mac.zip', [output / 'Install-Faster-Menus.command'])]
    for name, members in groups:
        archive = output / name
        archives.append(archive)
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
          for path in members:
            info = zipfile.ZipInfo(path.name, (2026, 9, 16, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100755 if path.suffix == '.command' else 0o100644) << 16
            z.writestr(info, path.read_bytes())
    paths = sorted(output.glob('*.command')) + sorted(output.glob('*.cmd')) + archives
    (output / 'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in paths))
    return paths


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/release')
    args = parser.parse_args()
    for item in package(args.output):
        print(item)
