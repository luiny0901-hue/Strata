"""Install the OpenCode v2 guard and opt existing JetBrains ACP entries into it."""
import argparse
import json
from pathlib import Path
import shutil
from configure_opencode_session_recovery import _atomic_write, _backup


def install(config, acp):
    source = Path(__file__).resolve().parents[1] / 'examples/opencode/acp-foreground-guard'
    target = config.parent / 'strata-acp-foreground-guard'
    settings = json.loads(config.read_text(encoding='utf-8-sig'))
    clients = json.loads(acp.read_text(encoding='utf-8-sig'))
    entries = []
    for name, entry in clients.get('agent_servers', {}).items():
        command = str(entry.get('command', '')).replace('\\', '/').rsplit('/', 1)[-1].lower()
        if command in ('opencode', 'opencode.exe') and 'acp' in entry.get('args', []):
            env = entry.setdefault('env', {})
            if not isinstance(env, dict):
                raise ValueError('ACP env must be an object')
            env['OPENCODE_ACP_FOREGROUND_GUARD'] = '1'
            entries.append(name)
    if not entries:
        raise ValueError('No existing OpenCode ACP entries found; no configuration changed')
    plugins = settings.setdefault('plugins', [])
    if not isinstance(plugins, list):
        raise ValueError('plugins must be an array')
    if str(target) not in plugins:
        plugins.append(str(target))
    target.mkdir(parents=True, exist_ok=True)
    for name in ('index.js', 'package.json'):
        dest = target / name
        if dest.exists() and dest.read_bytes() != (source / name).read_bytes():
            _backup(dest)
        shutil.copy2(source / name, dest)
    for path, data in ((config, settings), (acp, clients)):
        text = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
        if path.read_text(encoding='utf-8-sig') != text:
            _backup(path)
            _atomic_write(path, text)
    print('Installed guard for: ' + ', '.join(entries))
    print('Reconnect/restart the ACP client to inherit the new environment.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=Path.home() / '.config/opencode/opencode.json')
    parser.add_argument('--acp', type=Path, default=Path.home() / '.jetbrains/acp.json')
    args = parser.parse_args()
    install(args.config, args.acp)
