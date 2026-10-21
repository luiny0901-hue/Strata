"""Opt-in real cached REA CLI smoke test. Creates its own target, never runs it."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cli',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    root=args.output.resolve()
    root.mkdir(parents=True,exist_ok=False)
    target=root/'한글 앱 with spaces'
    target.mkdir()
    fixtures={
        'package.json':json.dumps({'name':'rea-reconstruction-fixture','version':'1.0.0','main':'main.js'}),
        'main.js':"const {app,BrowserWindow,ipcMain}=require('electron'); const {normalizeName}=require('./model'); app.whenReady().then(()=>{const win=new BrowserWindow();win.loadFile('index.html');}); ipcMain.handle('normalize',(_,name)=>normalizeName(name));",
        'model.js':"exports.normalizeName = name => String(name).trim().toUpperCase();",
        'index.html':"<!doctype html><html><body><h1>Fixture</h1><input id='name'><button id='save'>Save</button></body></html>",
    }
    for name,text in fixtures.items():
        (target/name).write_text(text,encoding='utf-8')
    hashes={name:hashlib.sha256((target/name).read_bytes()).hexdigest() for name in fixtures}
    summary=[]
    for label,path in [('valid',target),('missing',root/'missing-target')]:
        result=subprocess.run(['node',str(args.cli),'analyze-javascript-application',str(path),'--format','json'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
        (root/f'{label}.stdout.json').write_text(result.stdout,encoding='utf-8')
        (root/f'{label}.stderr.log').write_text(result.stderr,encoding='utf-8')
        data=json.loads(result.stdout)
        if label=='valid':
            assert result.returncode==0, result.stderr
            assert 'normalizeName' in json.dumps(data), 'Expected fixture symbol not found in real evidence'
        else:
            assert result.returncode!=0 or data.get('success') is False or data.get('error'), 'Missing target reported as success'
        summary.append({'case':label,'exit':result.returncode,'top_level_keys':list(data) if isinstance(data,dict) else []})
    for name,digest in hashes.items():
        assert hashlib.sha256((target/name).read_bytes()).hexdigest()==digest,'Source target changed'
    summary.append({'target_preserved':True,'ui_rendering':'NOT_RUN','new_program_implementation':'NOT_RUN'})
    (root/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    main()
