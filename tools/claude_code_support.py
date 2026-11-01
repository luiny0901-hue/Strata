"""Claude Code helpers shared by the Desktop and terminal entry points."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess

if __package__:
    from .claude_code_guidance import ROOT, managed_guidance, validate_managed_guidance, hook_context
else:
    from claude_code_guidance import ROOT, managed_guidance, validate_managed_guidance, hook_context


def write_changed(path: Path, data: str) -> None:
    encoded = data.encode('utf-8')
    if path.exists() and path.read_bytes() == encoded:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.pending')
    if temporary.exists():
        raise ValueError(f'게시 대기 파일을 먼저 확인하세요: {temporary}')
    temporary.write_bytes(encoded)
    os.replace(temporary, path)


def context_limits(context: int) -> tuple[int, int | str]:
    output = min(32000, context // 4)
    # Claude reserves its own compaction buffer inside this window. Subtracting
    # output here a second time shrinks the model window shown by Desktop Code.
    window = min(context, 1000000) if context >= 100000 else 'auto'
    return output, window


def find_claude() -> Path | None:
    candidates = [Path.home() / '.local/bin' / ('claude.exe' if os.name == 'nt' else 'claude')]
    found = shutil.which('claude')
    if found:
        candidates.append(Path(found))
    return next((path for path in candidates if path.is_file()), None)


def merge_hook(entries, rule, commands):
    result = []
    for entry in entries:
        handlers = [handler for handler in entry.get('hooks', [])
                    if handler.get('command') not in commands]
        if handlers:
            result.append({**entry, 'hooks': handlers})
    if rule is not None:
        result.append(rule)
    return result


def validate_tool_selection(arguments, servers) -> None:
    if 'rea' not in servers:
        return
    for index, argument in enumerate(arguments):
        if argument == '--tools':
            selected = []
            for value in arguments[index + 1:]:
                if value.startswith('-'):
                    break
                selected.extend(re.split(r'[, ]+', value))
        elif argument.startswith('--tools='):
            selected = re.split(r'[, ]+', argument.split('=', 1)[1])
        else:
            continue
        if not {'default', 'ToolSearch'}.intersection(selected):
            raise ValueError('REA 사용 중에는 --tools에 ToolSearch를 포함하거나 --tools를 생략하세요. 전체 REA 정의가 문맥에 한꺼번에 들어가는 것을 막습니다.')


def select_project() -> Path:
    if os.name == 'nt':
        script = ("Add-Type -AssemblyName System.Windows.Forms; $picker=New-Object System.Windows.Forms.FolderBrowserDialog; "
                  "$picker.Description='Claude Code + Strata 프로젝트 폴더'; $picker.ShowNewFolderButton=$true; "
                  "if ($picker.ShowDialog() -eq 'OK') { [Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
                  "[Console]::Write($picker.SelectedPath) }")
        chosen = subprocess.check_output(['powershell.exe', '-NoProfile', '-STA', '-Command', script],
                                         text=True, encoding='utf-8').strip()
    else:
        chosen = input('작업할 프로젝트 폴더: ').strip()
    if not chosen:
        raise ValueError('프로젝트 선택이 취소됐습니다.')
    return Path(chosen).expanduser().resolve()
