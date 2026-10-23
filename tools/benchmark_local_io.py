"""Opt-in isolated local file I/O timings; does not clear OS caches or tune disks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    rows=[]
    def save(): (root/'results.json').write_text(json.dumps({'notes':'OS-cached reads; fsync-backed isolated writes, not raw SSD throughput or power-loss proof','rows':rows},indent=2),encoding='utf-8')
    for size in (8192,1048576,16777216):
        data=(bytes(range(256))*(size//256+1))[:size]
        path=root/f'fixture-{size}.bin';path.write_bytes(data)
        offset=size//2;expected=data[offset:offset+1024]
        for sample in range(5):
            for kind in (('read-all','read-range') if sample%2==0 else ('read-range','read-all')):
                start=time.perf_counter()
                with path.open('rb') as f:
                    if kind=='read-all':actual=f.read()[offset:offset+1024]
                    else:f.seek(offset);actual=f.read(1024)
                rows.append({'size':size,'sample':sample+1,'kind':kind,'seconds':time.perf_counter()-start,'logical_bytes_read':size if kind=='read-all' else 1024,'pass':actual==expected})
                save()
                if actual!=expected:raise RuntimeError('Range content mismatch')
            target=root/f'atomic-{size}.bin';start=time.perf_counter()
            fd,name=tempfile.mkstemp(dir=root,prefix='.io-',suffix='.tmp')
            try:
                with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
                os.replace(name,target)
            finally:
                if os.path.exists(name):os.unlink(name)  # Only this explicitly owned temp file.
            elapsed=time.perf_counter()-start
            correct=hashlib.sha256(target.read_bytes()).digest()==hashlib.sha256(data).digest()
            rows.append({'size':size,'sample':sample+1,'kind':'atomic-write-fsync','seconds':elapsed,'pass':correct});save()
            if not correct:raise RuntimeError('Write content mismatch')
    print('PASS: 45 isolated read/write cases; OS cache retained; no disk settings changed',flush=True)


if __name__=='__main__':main()
