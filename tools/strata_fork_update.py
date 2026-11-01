"""Opt-in stable fork updates, staged beside the active bundle, activated only on owner startup.

No service owner, pip upgrade, model acquisition, live restart or client replay lives here.
The existing supervisor alone proves readiness and drains failed candidate processes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import time
from urllib.request import Request, urlopen
import zipfile

REPO = 'sergqwer/strata-nvfp4'
FEED = f'https://api.github.com/repos/{REPO}/releases?per_page=100'
DEFAULT_FORK = Path('forks/sergqwer-strata-nvfp4-v0.1.44.1-nvfp4.2/strata-nvfp4')
VERSION = re.compile(r'v?(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?-nvfp4\.(\d+)')
MAX_ZIP = 2 * 1024**3
MAX_EXPANDED = 4 * 1024**3
DAY = 86400


def read(path, default=None):
    if not path.exists():
        return default
    if path.is_symlink() or path.stat().st_size > 8 * 1024**2:
        raise ValueError('Invalid update record: ' + path.name)
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            h.update(block)
    return h.hexdigest()


def version(value):
    match = VERSION.fullmatch(str(value))
    if not match:
        raise ValueError('Not a stable NVFP4 fork version')
    return tuple(int(x or 0) for x in match.groups())


def safe_path(root, relative):
    if not isinstance(relative, str) or '\\' in relative or ':' in relative:
        raise ValueError('Unsafe update path')
    parts = PurePosixPath(relative)
    if parts.is_absolute() or not parts.parts or any(p in ('.', '..') for p in parts.parts):
        raise ValueError('Unsafe update path')
    if any(p.endswith((' ', '.')) or '\0' in p or re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', p)
           for p in parts.parts):
        raise ValueError('Unsupported Windows archive path')
    target = root.joinpath(*parts.parts)
    for part in (target, *target.parents):
        if part == root.parent:
            break
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            raise ValueError('Linked update paths are unsupported')
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('Update path escaped its root')
    return target


def update_dir(root):
    return safe_path(root, '.update/nvfp4-auto')


def selected_fork(root):
    active = read(update_dir(root) / 'active.json')
    if active is None:
        return root / DEFAULT_FORK
    version(active['version'])
    if not active['path'].startswith('forks/'):
        raise ValueError('Selected fork is outside the bundle directory')
    path = safe_path(root, active['path'])
    if read(path / 'release-manifest.json', {}).get('version') != active['version']:
        raise ValueError('Selected fork version does not match its manifest')
    return path


def latest_stable(releases):
    choices = []
    if not isinstance(releases, list):
        raise ValueError('Invalid fork release response')
    for release in releases:
        if not isinstance(release, dict) or release.get('draft') or release.get('prerelease'):
            continue
        try:
            key = version(release.get('tag_name'))
        except ValueError:
            continue  # GitHub can mark a tag containing "beta" as a final release.
        choices.append((key, release))
    return max(choices, key=lambda item: item[0])[1] if choices else None


def asset_for(release):
    tag = release['tag_name']
    version(tag)
    name = f'strata-nvfp4-{tag}-windows-x64.zip'
    expected = f'https://github.com/{REPO}/releases/download/{tag}/{name}'
    assets = [a for a in release.get('assets', []) if a.get('name') == name]
    if len(assets) != 1:
        raise ValueError('Release has no unique Windows NVFP4 bundle')
    asset = assets[0]
    if (asset.get('browser_download_url') != expected or type(asset.get('size')) is not int
            or not 0 < asset['size'] <= MAX_ZIP
            or not re.fullmatch(r'sha256:[0-9a-f]{64}', asset.get('digest') or '')):
        raise ValueError('Release asset identity, size or SHA-256 is unavailable')
    return asset


def fetch_releases():
    request = Request(FEED, headers={'User-Agent': 'Strata-managed-fork-update', 'Accept': 'application/vnd.github+json'})
    with urlopen(request, timeout=15) as response:
        raw = response.read(4 * 1024**2 + 1)
    if len(raw) > 4 * 1024**2:
        raise ValueError('Fork release response exceeded its limit')
    return json.loads(raw)


def download(asset, destination, stopped):
    deadline = time.monotonic() + 1800
    total = 0
    request = Request(asset['browser_download_url'], headers={'User-Agent': 'Strata-managed-fork-update'})
    # GitHub release downloads redirect to its asset CDN; no API key or client credentials are sent.
    with urlopen(request, timeout=15) as response, destination.open('xb') as stream:
        while True:
            if stopped() or time.monotonic() > deadline:
                raise RuntimeError('Update preparation interrupted')
            block = response.read(1024**2)
            if not block:
                break
            total += len(block)
            if total > asset['size']:
                raise ValueError('Release download exceeded declared size')
            stream.write(block)
    if total != asset['size'] or digest(destination) != asset['digest'][7:]:
        raise ValueError('Release download failed size/SHA-256 verification')


def unpack(archive, target):
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        if len(entries) > 20000 or sum(i.file_size for i in entries) > MAX_EXPANDED:
            raise ValueError('Release archive exceeded extraction limits')
        seen = set()
        for item in entries:
            if item.flag_bits & 1 or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('Encrypted or linked archive entry')
            # ZipInfo.filename silently normalizes Windows backslashes; validate raw names too.
            name = item.orig_filename
            path = safe_path(target, name.rstrip('/'))
            name = str(path.relative_to(target)).casefold()
            if name in seen or not item.filename.startswith('strata-nvfp4/'):
                raise ValueError('Duplicate or unexpected archive path')
            seen.add(name)
        source.extractall(target)
    return target / 'strata-nvfp4'


def inventory(root):
    """Only executable program/source and shipped data, never model/user/cache directories."""
    manifest = read(root / 'release-manifest.json')
    files = manifest['files']
    if not isinstance(files, dict) or len(files) > 20000:
        raise ValueError('Invalid release manifest')
    names = set(files) | {'release-manifest.json'}
    # Existing local server modules are not necessarily in the original release manifest.
    for p in (root / 'serve').rglob('*'):
        if (p.is_file() and p.suffix in ('.py', '.jinja') and '__pycache__' not in p.parts
                and not any(part.startswith('.') for part in p.relative_to(root).parts)):
            names.add(p.relative_to(root).as_posix())
    return {name: digest(safe_path(root, name)) for name in sorted(names)}


def preserve_customizations(old, new):
    before, after = read(old / 'release-manifest.json'), read(new / 'release-manifest.json')
    old_files, new_files = before['files'], after['files']
    for name, expected in new_files.items():
        if digest(safe_path(new, name)) != expected:
            raise ValueError('Release manifest verification failed: ' + name)
    baseline = inventory(old)
    for name, current in baseline.items():
        if name == 'release-manifest.json' or current == old_files.get(name):
            continue
        shipped = new_files.get(name)
        # Carry exact local edits only if their upstream base has not changed.
        if shipped not in (old_files.get(name), current):
            raise ValueError('Upstream conflicts with a local customization: ' + name)
        source, dest = safe_path(old, name), safe_path(new, name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    for name in ('requirements-serve.txt', 'requirements-model.txt'):
        if (old / name).read_bytes() != (new / name).read_bytes():
            raise ValueError('Python dependency changes require a reviewed maintenance update')
    # Validate existing hook contracts without importing or running candidate server code.
    if __package__:
        from .patch_nvfp4_server_effort import patch_source
        from .patch_nvfp4_vision_source_cache import patch_server as vision
        from .patch_nvfp4_response_guard import patch_server as guard, patch_structured
    else:
        from patch_nvfp4_server_effort import patch_source
        from patch_nvfp4_vision_source_cache import patch_server as vision
        from patch_nvfp4_response_guard import patch_server as guard, patch_structured
    source = (new / 'serve/server.py').read_text(encoding='utf-8-sig')
    source = guard(vision(patch_source(source)[0]))
    compile(source, 'candidate/serve/server.py', 'exec')
    compile(patch_structured((new / 'serve/structured.py').read_text(encoding='utf-8-sig')),
            'candidate/serve/structured.py', 'exec')
    for name in ('engine/strata.exe', 'engine/strata-vision.exe', 'data/uncensor/qwen-nvfp4-gptq-uncensored.gguf'):
        if not safe_path(new, name).is_file():
            raise ValueError('Required fork component is missing: ' + name)
    return baseline


class ForkUpdates:
    def __init__(self, root):
        self.root = root.resolve()
        self.directory = update_dir(self.root)

    def enabled(self):
        try:
            return read(self.directory / 'config.json', {}).get('enabled') is True
        except (OSError, ValueError, AttributeError):
            return False  # Update configuration must not prevent the existing service from starting.

    def check(self, *, releases=None, stopped=lambda: False, platform=None, force=False):
        if not self.enabled():
            return {'status': 'disabled'}
        state = read(self.directory / 'status.json', {})
        if not force and 0 <= time.time() - state.get('checked_at', 0) < DAY:
            return state
        now = time.time()
        try:
            rel = latest_stable(fetch_releases() if releases is None else releases)
            old = selected_fork(self.root)
            current = read(old / 'release-manifest.json')['version']
            result = {'checked_at': now, 'installed': current, 'channel': 'stable', 'status': 'current'}
            if rel is not None:
                result['latest'] = rel['tag_name']
            if rel is not None and version(rel['tag_name']) > version(current):
                rejected = read(self.directory / 'rejected.json', {})
                if rejected.get('version') == rel['tag_name'].removeprefix('v'):
                    result['status'] = 'rejected'
                elif (platform or sys.platform) != 'win32':
                    result['status'] = 'platform_unavailable'
                elif read(self.directory / 'pending.json'):
                    result['status'] = 'prepared'
                else:
                    self.prepare(old, rel, stopped)
                    result['status'] = 'prepared'
            if rel is None:
                result['status'] = 'no_stable_release'
        except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, SyntaxError, KeyError, TypeError) as exc:
            result = {'checked_at': now, 'status': 'deferred',
                      'reason': str(exc)[:300]}
        write(self.directory / 'status.json', result)
        return result

    def prepare(self, old, release, stopped):
        asset = asset_for(release)
        self.directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='prepare-', dir=self.directory) as temporary:
            folder = Path(temporary)
            archive = folder / 'release.zip'
            download(asset, archive, stopped)
            new = unpack(archive, folder / 'unpacked')
            target_version = release['tag_name'].removeprefix('v')
            if read(new / 'release-manifest.json')['version'] != target_version:
                raise ValueError('Downloaded version differs from selected release')
            baseline = preserve_customizations(old, new)
            if stopped():
                raise RuntimeError('Update preparation interrupted')
            relative = f'forks/auto-nvfp4-{target_version}/strata-nvfp4'
            target = safe_path(self.root, relative)
            if target.parent.exists():
                raise ValueError('Candidate directory already exists; inspect before retrying')
            target.parent.mkdir(parents=True)
            os.replace(new, target)
            write(self.directory / 'pending.json', {'version': target_version, 'path': relative,
                  'baseline': baseline, 'files': inventory(target),
                  'previous_path': old.relative_to(self.root).as_posix(),
                  'asset_sha256': asset['digest'][7:]})

    def restore(self, transaction, reason):
        pointer = self.directory / 'active.json'
        if transaction['previous'] is None:
            pointer.unlink(missing_ok=True)
        else:
            write(pointer, transaction['previous'])
        write(self.directory / 'rejected.json', {'version': transaction['candidate']['version'], 'reason': reason})
        write(self.directory / 'transaction.json', {**transaction, 'state': 'rolled_back'})
        (self.directory / 'pending.json').unlink(missing_ok=True)

    def activate(self, supervisor):
        """Called ONLY before the supervisor's initial start, after its owner lock/port check."""
        transaction = read(self.directory / 'transaction.json', {})
        if transaction.get('state') == 'starting':
            self.restore(transaction, 'Interrupted candidate startup')
        if not self.enabled():
            return None
        if supervisor.port_open() or supervisor.stopping.is_set():
            raise RuntimeError('Update activation requires a stopped, unoccupied server')
        old = selected_fork(self.root)
        try:
            pending = read(self.directory / 'pending.json')
            if not pending:
                return None
            candidate = safe_path(self.root, pending['path'])
            if not pending['path'].startswith('forks/auto-nvfp4-'):
                raise ValueError('Candidate is outside the prepared bundle directory')
            if (old.relative_to(self.root).as_posix() != pending['previous_path']
                    or inventory(old) != pending['baseline'] or inventory(candidate) != pending['files']):
                raise ValueError('Files changed after preparation')
            version(pending['version'])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            write(self.directory / 'status.json', {'status': 'deferred', 'reason': str(exc)[:300]})
            return None
        transaction = {'state': 'starting', 'previous': read(self.directory / 'active.json'),
                       'candidate': {'version': pending['version'], 'path': pending['path']}}
        write(self.directory / 'transaction.json', transaction)  # recovery before pointer publication
        write(self.directory / 'active.json', transaction['candidate'])
        return transaction

    def ready(self, transaction):
        write(self.directory / 'transaction.json', {**transaction, 'state': 'ready'})
        (self.directory / 'pending.json').unlink(missing_ok=True)
        write(self.directory / 'status.json', {'status': 'updated', 'installed': transaction['candidate']['version'],
                                             'checked_at': time.time()})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--strata-root', type=Path, required=True)
    parser.add_argument('action', choices=('enable', 'disable', 'status'))
    args = parser.parse_args(argv)
    updates = ForkUpdates(args.strata_root)
    if args.action != 'status':
        if args.action == 'enable' and not (updates.root / DEFAULT_FORK / 'release-manifest.json').is_file():
            parser.error('The existing pinned NVFP4 bundle is required before enabling updates')
        if args.action == 'enable':
            if __package__:
                from .configure_strata_managed_launchers import enable_managed_launchers
            else:
                from configure_strata_managed_launchers import enable_managed_launchers
            enable_managed_launchers(Path.home())
        write(updates.directory / 'config.json', {'enabled': args.action == 'enable', 'channel': 'stable',
                                                 'apply': 'next_owner_start', 'check_interval_seconds': DAY})
    print(json.dumps({'enabled': updates.enabled(), 'active_fork': str(selected_fork(updates.root)),
                      'last_check': read(updates.directory / 'status.json', {})}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
