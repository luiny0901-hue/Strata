"""검증한 OpenCodex 2.95.0에 재부팅 후 재사용된 PID의 스테일 판정을 추가한다.

재부팅으로 기록 PID가 다른 프로세스에 재사용되고 그 명령줄이 읽히지 않으면 소유권 검증이
"확신 불가"로 기동을 영구 거부한다(2026-11-06 NgcIso.exe 사례). 생성 시각과 PID 기록
파일의 mtime을 비교해 재사용을 확증하면 같은 상태를 스테일로 판정하고 기존 absent 복구로
이어간다. 읽을 수 없으면 지금까지와 똑같이 거부한다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.claude_opencodex_client import publish_files

VERSION = '2.95.0'
MARKER = 'STRATA_OPENCODEX_PID_REUSE_V1'
FENCE = 'src/cli/start-owner-fence.ts'
STATE = 'src/config/process-state.ts'

HELPER = r'''const PID_REUSE_GRACE_MS = 5_000; // STRATA_OPENCODEX_PID_REUSE_V1

/** Converts WMIC's `20261106130507.123456+540` datetime into epoch milliseconds. */
function parseWmicCreationDate(raw: string): number | undefined {
  const match = /CreationDate=(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})\.\d+([+-]\d+)/
    .exec(raw.replace(/\r/g, ""));
  if (!match) return undefined;
  const utc = Date.UTC(+match[1], +match[2] - 1, +match[3], +match[4], +match[5], +match[6]);
  return Number.isNaN(utc) ? undefined : utc - Number(match[7]) * 60_000;
}

/** Creation epoch milliseconds via WMIC, falling back to the fixed trusted PowerShell; undefined when unreadable. */
export function readProcessCreationEpochMs(pid: number): number | undefined {
  if (!Number.isSafeInteger(pid) || pid <= 0) return undefined;
  if (process.platform !== "win32") return undefined;
  try {
    const wmic = join(resolveTrustedWindowsSystemDirectory(), "wbem", "WMIC.exe");
    const created = parseWmicCreationDate(processCommandLineExec(wmic, [
      "process", "where", `ProcessId=${pid}`, "get", "CreationDate", "/VALUE",
    ], { encoding: "utf-8", stdio: ["ignore", "pipe", "ignore"], timeout: 3000, windowsHide: true }));
    if (created !== undefined) return created;
  } catch {
    /* WMIC missing or failed — use the trusted PowerShell fallback below */
  }
  try {
    const output = processCommandLineExec(resolveTrustedWindowsPowerShellExe(), [
      "-NoProfile", "-NoLogo", "-NonInteractive", "-Command",
      `(Get-CimInstance Win32_Process -Filter "ProcessId = ${pid}").CreationDate.ToString("o")`,
    ], { encoding: "utf-8", stdio: ["ignore", "pipe", "ignore"], timeout: 3000, windowsHide: true });
    const created = new Date(output.trim()).getTime();
    return Number.isNaN(created) ? undefined : created;
  } catch {
    return undefined;
  }
}

/**
 * A recorded pid whose process was created strictly after the pid record cannot be the
 * recorded owner: the owner writes the record while already running, so a later creation
 * time proves Windows reused the number (typically after a reboot) — the case where the
 * new owner's command line is unreadable and identity stays unknown. Unreadable evidence
 * keeps every caller's conservative behaviour. STRATA_OPENCODEX_PID_REUSE_V1
 */
export function pidReusedSincePidRecord(candidatePid: number, nowMs: () => number = Date.now): boolean {
  let mtimeMs: number;
  try {
    mtimeMs = statSync(getPidPath()).mtimeMs;
  } catch {
    return false;
  }
  if (nowMs() < mtimeMs) return false; // clock moved backwards; stay conservative
  const created = readProcessCreationEpochMs(candidatePid);
  return created !== undefined && created > mtimeMs + PID_REUSE_GRACE_MS;
}
'''

CHANGES = {
    Path(FENCE): {
        'marker': 1,
        'pairs': (
            ('import { removePidIfValueIs } from "../config/process-state";',
             'import { pidReusedSincePidRecord, removePidIfValueIs } from "../config/process-state";'),
            ('  if (observation.kind !== "absent") {',
             '  // STRATA_OPENCODEX_PID_REUSE_V1: a recorded pid reused after the record proves the owner exited; recover like an absent owner.\n'
             '  if (observation.kind !== "absent"\n'
             '      && !(owner.pidSnapshot !== null && pidReusedSincePidRecord(owner.pidSnapshot))) {'),
        ),
    },
    Path(STATE): {
        'marker': 2,
        'pairs': (
            ('import { existsSync, mkdirSync, readFileSync, unlinkSync } from "node:fs";',
             'import { statSync, existsSync, mkdirSync, readFileSync, unlinkSync } from "node:fs";'),
            (r'''export function readAlivePid(): number | null {
  const pid = readPidFileValue();
  if (pid === null) return null;
  try {
    process.kill(pid, 0);
    return pid;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "EPERM") return pid;
    return null;
  }
}
''',
             None),  # replaced by itself + HELPER
        ),
    },
}


def patch_file(relative, source):
    spec = CHANGES.get(relative)
    if spec is None:
        raise ValueError('패치 대상이 아닌 파일입니다.')
    pairs = [(old, new if new is not None else old + '\n' + HELPER) for old, new in spec['pairs']]
    applied = [new in source for old, new in pairs]
    if all(applied):
        if source.count(MARKER) != spec['marker']:
            raise ValueError('스테일 판정 마커 개수가 예상과 다릅니다. 기존 소스를 보존합니다.')
        return source
    if any(applied):
        raise ValueError('스테일 판정 수정이 일부만 존재합니다. 기존 소스를 보존합니다.')
    text = source
    for old, new in pairs:
        if text.count(old) != 1:
            raise ValueError('알 수 없거나 중복된 앵커입니다. 기존 소스를 보존합니다.')
        text = text.replace(old, new, 1)
    if text.count(MARKER) != spec['marker']:
        raise ValueError('스테일 판정 마커 개수가 예상과 다릅니다. 기존 소스를 보존합니다.')
    return text


def install(package_root):
    package_root = Path(package_root).resolve()
    package = json.loads((package_root/'package.json').read_text(encoding='utf-8-sig'))
    if package.get('name') != '@bitkyc08/opencodex' or package.get('version') != VERSION:
        raise ValueError('검증한 OpenCodex 2.95.0 설치에만 적용할 수 있습니다.')
    files, before = {}, {}
    for relative in CHANGES:
        path = package_root/relative
        raw = path.read_bytes()
        text = raw.decode('utf-8-sig')
        newline = '\r\n' if '\r\n' in text else '\n'
        updated = patch_file(relative, text.replace('\r\n', '\n')).replace('\n', newline)
        if raw.startswith(b'\xef\xbb\xbf'):
            updated = chr(0xfeff)+updated
        files[path], before[path] = updated, raw
    backup, changed = publish_files(files, package_root/'.strata-pid-reuse', before)
    return {'changed_files': changed, 'backup': str(backup) if backup else None,
            'version': VERSION,
            'runtime_reflection': 'next_startup' if changed else 'not_verified'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package_root', type=Path)
    args = parser.parse_args()
    try:
        result = install(args.package_root)
    except (OSError, UnicodeError, ValueError) as exc:
        print('PID 재사용 스테일 판정 적용 실패: '+str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
