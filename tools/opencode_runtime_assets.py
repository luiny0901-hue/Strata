"""Shared, non-mutating preparation of the installed OpenCode runtime plugins."""
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[1]
ACP_ENV = {'OPENCODE_ACP_FOREGROUND_GUARD': '1', 'OPENCODE_ACP_TURN_GUARD': '1', 'OPENCODE_ACP_TERMINAL_GUARD': '1'}
PLUGINS = {'acp': ('acp-foreground-guard', 'strata-acp-foreground-guard'),
           'output': ('output-recovery', 'strata-output-recovery')}


def prepare_runtime_assets(config, directory, names=('acp', 'output')):
    """Validate/read assets before callers publish config, credentials or ACP entries."""
    plugins = config.setdefault('plugins', [])
    if not isinstance(plugins, list):
        raise ValueError('plugins must be an array')
    files = {}
    for name in names:
        source_name, installed_name = PLUGINS[name]
        base = directory / installed_name
        assets = {}
        for filename in ('package.json', 'index.js'):
            assets[filename] = (ROOT / 'examples/opencode' / source_name / filename).read_bytes()
        if name == 'acp':
            for filename in ('powershell-bootstrap.ps1', 'powershell-preflight.ps1'):
                assets[filename] = (ROOT / 'tools/opencode' / filename).read_bytes()
        digest = hashlib.sha256()
        for filename, content in sorted(assets.items()):
            digest.update(filename.encode() + b'\0' + len(content).to_bytes(8, 'big') + content)
        target = base / 'versions' / digest.hexdigest()
        for filename, content in assets.items():
            dest = target / filename
            if dest.exists() and dest.read_bytes() != content:
                raise ValueError(f'Immutable runtime asset changed: {dest}; no configuration published')
            files[dest] = content
        def owned(value):
            ref = value.get('package') if isinstance(value, dict) else value
            if not isinstance(ref, str):
                return False
            candidate = Path(ref)
            return candidate == base or (candidate.parent == base / 'versions')
        matches = [i for i, value in enumerate(plugins) if owned(value)]
        previous = plugins[matches[0]] if matches else None
        entry = str(target)
        if name == 'acp' or isinstance(previous, dict):
            options = dict(previous.get('options', {})) if isinstance(previous, dict) else {}
            if name == 'acp':
                options['bootstrapPath'] = str(target / 'powershell-bootstrap.ps1')
            entry = {**(previous if isinstance(previous, dict) else {}), 'package': str(target), 'options': options}
        if matches:
            plugins[matches[0]] = entry
            for index in reversed(matches[1:]):
                del plugins[index]
        else:
            plugins.append(entry)
    return files


def prepare_terminal_assets(directory):
    return {directory / 'scripts' / name: (ROOT / 'tools/opencode' / name).read_bytes().replace(b'\r\n', b'\n')
            for name in ('run_bounded_command.ps1', 'run_bounded_command.sh', 'powershell-bootstrap.ps1', 'powershell-preflight.ps1')}
