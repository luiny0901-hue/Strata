"""Opt-in installation; never start, stop or adopt a running Strata server."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

if __package__:
    from .configure_opencode_session_recovery import DEFAULT_CONFIG, _atomic_write, _backup
    from .opencode_runtime_assets import prepare_runtime_assets
else:
    from configure_opencode_session_recovery import DEFAULT_CONFIG, _atomic_write, _backup
    from opencode_runtime_assets import prepare_runtime_assets


def configure(config_path, control_url, token_file):
    url = urlsplit(control_url)
    if (url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost', '::1')
            or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment):
        raise ValueError('Control URL must be a loopback HTTP origin')
    config = json.loads(config_path.read_text(encoding='utf-8'))
    files = prepare_runtime_assets(config, config_path.parent, names=('restart',))
    for index, entry in enumerate(config['plugins']):
        package = entry.get('package') if isinstance(entry, dict) else entry
        if package and Path(package).parent == config_path.parent / 'strata-server-lifecycle/versions':
            config['plugins'][index] = {'package':package,'options':{
                **(entry.get('options', {}) if isinstance(entry, dict) else {}),
                'controlURL':control_url, 'tokenFile':str(token_file.expanduser().resolve())}}
    # Versioned assets first, config last. Existing sessions remain pinned.
    for path, content in files.items():
        if not path.exists():
            _atomic_write(path,content.decode('utf-8'))
    serialized = json.dumps(config,ensure_ascii=False,indent=2)+'\n'
    if config_path.read_text(encoding='utf-8') != serialized:
        _backup(config_path)
        _atomic_write(config_path,serialized)


def enable_managed_launchers(home):
    """Opt in this server PC's ON/OFF BATs on their next launch; no process adoption."""
    flag=home/'.config/strata/server-control/managed-launchers.enabled'
    if not flag.exists():_atomic_write(flag,'Managed ON/OFF launcher opt-in. Remove this file to restore ordinary launch.\n')
    return flag


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=DEFAULT_CONFIG)
    parser.add_argument('--control-url',default='http://127.0.0.1:8768')
    parser.add_argument('--token-file',type=Path,default=Path.home()/'.config/strata/server-control/restart-control.key')
    parser.add_argument('--managed-launchers',action='store_true',help='Opt in normal ON/OFF BATs on this Windows server PC to managed mode on next launch; never stop the current server')
    args=parser.parse_args()
    configure(args.config,args.control_url,args.token_file)
    if args.managed_launchers:print('Next ON/OFF BAT launch uses managed mode: '+str(enable_managed_launchers(Path.home())))
    print('Restart tool installed. Restart OpenCode/ACP to load it; no server was restarted.')
