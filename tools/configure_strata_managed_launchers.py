"""Opt this Windows server's ON/OFF launchers into managed mode on next start."""
from __future__ import annotations

import argparse
from pathlib import Path


def enable_managed_launchers(home: Path) -> Path:
    """Create the local opt-in flag without touching a running server."""
    flag = home / '.config' / 'strata' / 'server-control' / 'managed-launchers.enabled'
    if flag.exists():
        return flag
    flag.parent.mkdir(parents=True, exist_ok=True)
    try:
        with flag.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write('Managed ON/OFF launcher opt-in. Remove this file to restore ordinary launch.\n')
    except FileExistsError:
        pass
    return flag


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--managed-launchers', action='store_true',
                        help='Use the managed Strata supervisor for normal ON/OFF BAT launches.')
    args = parser.parse_args()
    if not args.managed_launchers:
        parser.error('select --managed-launchers to opt in')
    print('Next ON/OFF BAT launch uses managed mode: ' +
          str(enable_managed_launchers(Path.home())))
