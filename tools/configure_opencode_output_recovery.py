"""Install bounded Strata output recovery without replacing existing settings."""
import json
from pathlib import Path
from configure_opencode_session_recovery import _atomic_write, _backup
from opencode_runtime_assets import prepare_runtime_assets


def install(config_path):
    config = json.loads(config_path.read_text(encoding='utf-8-sig'))
    files = prepare_runtime_assets(config, config_path.parent, names=('output',))
    for dest, content in files.items():
        data = content.decode('utf-8')
        if dest.exists() and dest.read_text(encoding='utf-8') == data:
            continue
        if dest.exists():
            _backup(dest)
        _atomic_write(dest, data)
    text = json.dumps(config, ensure_ascii=False, indent=2) + '\n'
    if config_path.read_text(encoding='utf-8-sig') != text:
        _backup(config_path)
        _atomic_write(config_path, text)
    print('Installed Strata output recovery. Restart OpenCode/ACP to activate.')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=Path.home() / '.config/opencode/opencode.json')
    install(parser.parse_args().config)
