"""검증한 OpenCodex 버전에만 빈 추론 서명의 원문 보존 수정을 적용한다."""
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
RELATIVE_SOURCE = Path('src/adapters/anthropic-replay.ts')
ORIGINAL = 'if (typeof value.signature !== "string" || value.signature.length === 0) throw new Error("incomplete thinking signature");'
PATCHED = 'if (typeof value.signature !== "string") throw new Error("incomplete thinking signature");'
SERVICE_MARKER = '// STRATA_OPENCODEX_SEARCH_REPLAY_V2'
SERVICE_CHANGES = {
    Path('src/service/repair.ts'): (
        ('  stopScheduler?: () => void;\n',
         '  stopScheduler?: () => void;\n  prepareSchedulerRestart?: () => Promise<void>; '+SERVICE_MARKER+'\n'),
        ('    try { (deps.stopScheduler ?? stopWindows)(); } catch { /* not running */ }\n',
         '    try { (deps.stopScheduler ?? stopWindows)(); } catch { /* not running */ }\n'
         '    if (deps.verb === "restart") await deps.prepareSchedulerRestart?.(); '+SERVICE_MARKER+'\n'),
    ),
    Path('src/service/cli.ts'): (
        ('stopTrackedProxyForServiceCommand, installServiceSafely',
         'stopTrackedProxyForServiceCommand, prepareServiceInstall, installServiceSafely'),
        ('await repairService({ verb, supervisionLatch });',
         'await repairService({ verb, supervisionLatch, prepareSchedulerRestart: () => prepareServiceInstall("scheduler", { supervisionLatch }) });'),
    ),
}


def patch_source(source):
    original, patched = source.count(ORIGINAL), source.count(PATCHED)
    if original == 0 and patched == 1:
        return source
    if original != 1 or patched != 0:
        raise ValueError('알 수 없거나 중복된 이력 보존 검사입니다. 기존 소스를 보존합니다.')
    return source.replace(ORIGINAL, PATCHED, 1)


def patch_file(relative, source):
    if relative == RELATIVE_SOURCE:
        return patch_source(source)
    changes = SERVICE_CHANGES.get(relative)
    if changes is None:
        raise ValueError('패치 대상이 아닌 파일입니다.')
    applied = [new for old, new in changes if new in source]
    if len(applied) == len(changes):
        if source.count(SERVICE_MARKER) != sum(new.count(SERVICE_MARKER) for old, new in changes):
            raise ValueError('재시작 정리 마커가 예상 개수와 다릅니다. 기존 소스를 보존합니다.')
        return source
    if applied:
        raise ValueError('재시작 정리 수정이 일부만 존재합니다. 기존 소스를 보존합니다.')
    text = source
    for old, new in changes:
        if text.count(old) != 1:
            raise ValueError('알 수 없거나 중복된 재시작 경로입니다. 기존 소스를 보존합니다.')
        text = text.replace(old, new, 1)
    return text


def install(package_root):
    package_root = Path(package_root).resolve()
    package = json.loads((package_root/'package.json').read_text(encoding='utf-8-sig'))
    if package.get('name') != '@bitkyc08/opencodex' or package.get('version') != VERSION:
        raise ValueError('검증한 OpenCodex 2.95.0 설치에만 적용할 수 있습니다.')
    files, before = {}, {}
    for relative in (RELATIVE_SOURCE, *SERVICE_CHANGES):
        path = package_root/relative
        raw = path.read_bytes()
        text = raw.decode('utf-8-sig')
        newline = '\r\n' if '\r\n' in text else '\n'
        updated = patch_file(relative, text.replace('\r\n', '\n')).replace('\n', newline)
        if raw.startswith(b'\xef\xbb\xbf'):
            updated = chr(0xfeff)+updated
        files[path], before[path] = updated, raw
    backup, changed = publish_files(files, package_root/'.strata-search-replay', before)
    return {'changed_files': changed, 'backup': str(backup) if backup else None,
            'version': VERSION, 'runtime_reflection': 'restart_required' if changed else 'not_verified'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package_root', type=Path)
    args = parser.parse_args()
    try:
        result = install(args.package_root)
    except (OSError, UnicodeError, ValueError) as exc:
        print('검색 이력 수정 적용 실패: '+str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
