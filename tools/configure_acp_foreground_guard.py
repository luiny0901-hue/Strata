"""Install the OpenCode v2 guard and opt existing JetBrains ACP entries into it."""
import argparse
import json
from pathlib import Path
from configure_opencode_session_recovery import _atomic_write, _backup
from opencode_runtime_assets import ACP_ENV, prepare_runtime_assets


def install(config, acp):
    settings = json.loads(config.read_text(encoding='utf-8-sig'))
    clients = json.loads(acp.read_text(encoding='utf-8-sig'))
    entries = []
    for name, entry in clients.get('agent_servers', {}).items():
        command = str(entry.get('command', '')).replace('\\', '/').rsplit('/', 1)[-1].lower()
        if command in ('opencode', 'opencode.exe') and 'acp' in entry.get('args', []):
            env = entry.setdefault('env', {})
            if not isinstance(env, dict):
                raise ValueError('ACP env must be an object')
            env.update(ACP_ENV)
            entries.append(name)
    if not entries:
        raise ValueError('No existing OpenCode ACP entries found; no configuration changed')
    files = prepare_runtime_assets(settings, config.parent, names=('acp',))
    for dest, data in files.items():
        if dest.exists() and dest.read_bytes() == data:
            continue
        if dest.exists():
            _backup(dest)
        _atomic_write(dest, data.decode('utf-8'))
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
