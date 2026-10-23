"""Serial, opt-in reasoning-level comparison using the existing scoped fixture.

Does not launch/reconfigure a server. Each level receives the same history and
three coding requests; logs and partial/failing results remain in separate dirs.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--levels',nargs='+',choices=['none','low','medium','high'],default=['none','low','medium','high'])
    parser.add_argument('--target',type=int,default=252000)
    parser.add_argument('--max-output',type=int,default=1536)
    args=parser.parse_args()
    if len(set(args.levels))!=len(args.levels):parser.error('Levels must be unique')
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    results=[]
    for level in args.levels:
        command=[sys.executable,'-m','tools.benchmark_long_context_edits','--output',str(root/level),
                 '--effort',level,'--target',str(args.target),'--max-output',str(args.max_output)]
        print('BEGIN '+level,flush=True)
        row={'effort':level,'state':'running'};results.append(row)
        def save(): (root/'suite.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        save()
        try:
            with (root/(level+'.log')).open('w',encoding='utf-8') as log:
                result=subprocess.run(command,cwd=Path(__file__).resolve().parents[1],stdout=log,stderr=subprocess.STDOUT,timeout=900)
            row.update(state='passed' if result.returncode==0 else 'failed',exit_code=result.returncode)
        except Exception as error:
            row.update(state='failed',error=type(error).__name__+': '+str(error));save();raise
        save();print('END '+level+' '+str(result.returncode),flush=True)
        if result.returncode:return result.returncode
    return 0


if __name__=='__main__':raise SystemExit(main())
