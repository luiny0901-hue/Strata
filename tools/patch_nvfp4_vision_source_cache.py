"""Install the existing opt-in image source cache in a known NVFP4 Vision layout."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.claude_opencodex_client import publish_files


CHANGES = (
    ('        self.cache: dict[str, tuple[Path, int]] = {}',
     '        self.cache: dict[str, tuple[Path, int]] = {}\n'
     '        self.source_cache = {} if cfg.get("source_cache") is True else None'),
    ('        data = self.normalize(source if isinstance(source, bytes) else self.load(source))',
     '''        aliases = getattr(self, "source_cache", None)
        raw = source if isinstance(source, bytes) else self.load(source)
        raw_key = hashlib.sha256(raw).hexdigest() if aliases is not None else None
        if aliases is not None:
            with self.lock:
                cached_key = aliases.get(raw_key)
                if cached_key in self.cache:
                    self.cache[cached_key] = self.cache.pop(cached_key)
                    return self.cache[cached_key]
        data = self.normalize(raw)'''),
    ('''        with self.lock:
            if key in self.cache:
                self.cache[key] = self.cache.pop(key)                  # most recently used last
                return self.cache[key]''',
     '''        with self.lock:
            def remember_source():
                if aliases is not None:
                    aliases.pop(raw_key, None)
                    aliases[raw_key] = key
                    while len(aliases) > 64:
                        aliases.pop(next(iter(aliases)))
            if key in self.cache:
                self.cache[key] = self.cache.pop(key)                  # most recently used last
                remember_source()
                return self.cache[key]'''),
    ('            self.cache[key] = (out, int(line.split()[1]))',
     '            self.cache[key] = (out, int(line.split()[1]))\n            remember_source()'),
)


class PatchError(ValueError):
    pass


def patch_server(source):
    complete = [source.count(new) == 1 for _, new in CHANGES]
    if all(complete):
        return source
    if any(complete):
        raise PatchError('partial image source cache; preserve and inspect the fork before editing')
    counts = [source.count(old) for old, _ in CHANGES]
    if counts != [1] * len(CHANGES):
        raise PatchError(f'unknown Vision layout; expected one of each hook, found {counts}')
    for old, new in CHANGES:
        source = source.replace(old, new, 1)
    return source


def install(server):
    server = Path(server).resolve()
    original = server.read_bytes()
    text = original.decode('utf-8-sig')
    newline = '\r\n' if '\r\n' in text else '\n'
    patched = patch_server(text.replace('\r\n', '\n'))
    compile(patched, str(server), 'exec')
    payload = ('\ufeff' if original.startswith(b'\xef\xbb\xbf') else '') + patched.replace('\n', newline)
    backup, changed = publish_files({server: payload}, server.parent/'.vision-source-cache', {server: original})
    return {'changed': changed, 'backup': str(backup) if backup else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('server', type=Path)
    args = parser.parse_args()
    try:
        result = install(args.server)
    except (OSError, UnicodeError, ValueError, SyntaxError) as exc:
        print('[strata] cannot prepare image source cache: '+str(exc), file=sys.stderr)
        return 2
    print('[strata] image source cache integration ready; changed files='+str(result['changed']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
