"""Install the existing Strata client stack; no inference or replacement agent loop."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import getpass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, HTTPRedirectHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
OPENCODEX_PACKAGE = '@bitkyc08/opencodex@2.92.0'
REA_PACKAGE = 'rea-agents@6.7.0'
CUA_VERSION = '0.36.0'
CUA_PS = 'https://cua.ai/driver/install.ps1'
CUA_SH = 'https://cua.ai/driver/install.sh'


class Pending(RuntimeError):
    """A resumable prerequisite, never a successful installation."""


def refresh_path():
    paths = [str(Path.home()/'.local/bin'), str(Path.home()/'AppData/Roaming/npm'),
             '/opt/homebrew/bin', '/usr/local/bin']
    if os.name == 'nt':
        paths.append(str(Path(os.environ.get('SystemRoot', 'C:/Windows'))/'System32/OpenSSH'))
        import winreg
        for hive, key in [(winreg.HKEY_CURRENT_USER, 'Environment'),
                          (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment')]:
            try:
                with winreg.OpenKey(hive, key) as handle:
                    paths.extend(os.path.expandvars(winreg.QueryValueEx(handle, 'Path')[0]).split(';'))
            except OSError:
                pass
    os.environ['PATH'] = os.pathsep.join([*paths, os.environ.get('PATH', '')])


def run(args, *, capture=False, timeout=1800, env=None):
    # No shell; credentials are never command-line arguments.
    result = subprocess.run([str(a) for a in args], check=True, text=True,
                            stdout=subprocess.PIPE if capture else None, timeout=timeout, env=env)
    return result.stdout if capture else result


@contextmanager
def install_lock(home):
    path = home/'.config/strata/integrated-install.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        if os.name == 'nt':
            import msvcrt
            if handle.seek(0, 2) == 0:
                handle.write(b'0'); handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise Pending('다른 통합 설치기가 실행 중입니다. 그 창에서 이어가세요.') from None
        else:
            import fcntl
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise Pending('다른 통합 설치기가 실행 중입니다. 그 창에서 이어가세요.') from None
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def download_script(url, directory, name):
    if url not in (CUA_PS, CUA_SH):
        raise ValueError('알려진 CUA 공식 설치 주소만 사용합니다.')
    with build_opener().open(url, timeout=60) as response:
        if not response.url.startswith('https://'):
            raise ValueError('설치 파일은 HTTPS만 사용합니다.')
        data = response.read(2*1024*1024+1)
    if not data or len(data) > 2*1024*1024:
        raise ValueError('설치 스크립트 크기를 확인할 수 없습니다.')
    path = Path(directory)/name
    path.write_bytes(data)
    return path


def npm_command(npx=False):
    node = shutil.which('node')
    name = 'npx' if npx else 'npm'
    located = shutil.which(name)
    if not node or not located:
        raise Pending('Node.js/npm 설치 후 새 터미널에서 통합 설치기를 다시 실행하세요.')
    if os.name == 'nt':
        script = Path(node).parent/'node_modules/npm/bin'/f'{name}-cli.js'
    else:
        script = Path(located).resolve()
    if not script.is_file():
        raise Pending('Node.js의 npm 실행 파일을 찾을 수 없습니다. Node.js 설치를 복구하세요.')
    return [node, str(script)]


def ocx_command(home):
    owner = home/'.opencodex/service-state.json'
    if owner.is_file():
        data = json.loads(owner.read_text(encoding='utf-8'))
        bun, cli = data.get('bunPath'), data.get('cliPath')
        if bun and cli and Path(bun).is_file() and Path(cli).is_file():
            return [bun, cli]
    root = Path(run([*npm_command(), 'root', '--global'], capture=True, timeout=30).strip())
    entry = root/'@bitkyc08/opencodex/bin/ocx.mjs'
    return [shutil.which('node'), str(entry)] if entry.is_file() else None


class Installer:
    def __init__(self, home, role, platform=None):
        self.home, self.role = home, role
        self.platform = platform or sys.platform
        self.path = home/'.config/strata/integrated-install.json'
        self.state = {'version': 1, 'role': role, 'status': 'preparing', 'steps': {}}
        if self.path.is_file():
            prior = json.loads(self.path.read_text(encoding='utf-8'))
            if prior.get('version') != 1:
                raise Pending('설치 기록 형식을 확인하세요. 기존 기록은 보존했습니다.')
            if prior.get('role') == role:
                self.state = prior

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                         delete=False) as stream:
            json.dump(self.state, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            temporary = Path(stream.name)
        temporary.chmod(0o600)
        os.replace(temporary, self.path)

    def step(self, name, operation):
        print(f'\n[{name}]', flush=True)
        self.retry_uncertain = (self.state['steps'].get(name) == 'uncertain' or
            (self.state.get('status') == 'running' and self.state.get('current_step') == name))
        self.state['status'], self.state['current_step'] = 'running', name
        self.save()
        try:
            operation()  # Re-probe actual state on resume; a receipt alone never skips work.
        except (Exception, KeyboardInterrupt) as error:
            self.state['status'] = 'waiting'
            self.state['steps'][name] = 'uncertain' if (self.retry_uncertain or isinstance(error, (subprocess.TimeoutExpired, KeyboardInterrupt))) else 'incomplete'
            self.save()
            raise
        self.state['steps'][name] = 'configured'
        self.save()

    def mutate(self, args, **kwargs):
        if getattr(self, 'retry_uncertain', False):
            if input('이전 설치의 결과가 불확실합니다. 해당 설치 창/프로세스가 끝났다면 "종료 확인"을 입력하세요: ').strip() != '종료 확인':
                raise Pending('이전 설치 종료를 확인할 때까지 중복 실행하지 않습니다.')
            self.retry_uncertain = False
        return run(args, **kwargs)

    def package(self, package, probe):
        if probe():
            print('이미 설치되어 있어 재사용합니다.')
            return
        if self.platform == 'win32':
            winget = shutil.which('winget')
            if not winget:
                raise Pending('Windows 앱 설치 관리자(winget)를 준비한 뒤 다시 실행하세요: https://aka.ms/getwinget')
            self.mutate([winget, 'install', '--exact', '--id', package, '--source', 'winget',
                 '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity', '--silent'])
        elif self.platform == 'darwin':
            brew = shutil.which('brew')
            if not brew:
                self.mutate(['bash', ROOT/'tools/install-agent.sh', '--bootstrap-brew'])
                refresh_path()
                brew = shutil.which('brew')
                if not brew:
                    raise Pending('Homebrew 설치를 확인하지 못했습니다. 같은 통합 설치기를 다시 실행하세요.')
            self.mutate([brew, 'install', *(['--cask'] if package == 'claude' else []), package])
        else:
            raise Pending('이 단계의 접속 PC는 Windows 또는 macOS여야 합니다.')
        refresh_path()
        if not probe():
            raise Pending('설치 후 실행 파일을 확인하지 못했습니다. OS 재시작 또는 새 터미널에서 재실행하세요.')

    def claude_installed(self):
        if self.platform == 'darwin':
            return any(p.is_dir() for p in [Path('/Applications/Claude.app'), self.home/'Applications/Claude.app'])
        script = "if ((Get-AppxPackage -Name Claude) -or (Test-Path ($env:LOCALAPPDATA+'\\AnthropicClaude\\claude.exe')) -or (Test-Path ($env:LOCALAPPDATA+'\\Programs\\Claude\\Claude.exe'))) { 'installed' }"
        return 'installed' in run(['powershell.exe', '-NoProfile', '-Command', script], capture=True, timeout=30)

    def client_dependencies(self):
        def node_ready():
            node = shutil.which('node')
            if not node or not shutil.which('npm'):
                return False
            try:
                return int(run([node, '-p', 'process.versions.node.split(".")[0]'], capture=True, timeout=10).strip()) >= 18
            except (ValueError, OSError, subprocess.SubprocessError):
                return False
        self.step('Node.js', lambda: self.package('OpenJS.NodeJS.LTS' if self.platform == 'win32' else 'node',
                                                  node_ready))
        self.step('Claude Desktop', lambda: self.package('Anthropic.Claude' if self.platform == 'win32' else 'claude',
                                                         self.claude_installed))
        def cua():
            from tools.claude_opencodex_client import local_cua_executable, read_json
            configured = read_json(self.home/'.claude/strata-mcp.json', {}).get('mcpServers', {}).get('cua-driver', {}).get('env', {}).get('CUA_DRIVER_EXE')
            try:
                local_cua_executable(configured)
                print('기존 CUA Driver를 재사용합니다.')
                return
            except ValueError:
                if os.environ.get('STRATA_CUA_DRIVER_EXE'):
                    raise  # An invalid explicit override is never fixed by installing elsewhere.
            environment = dict(os.environ)
            environment.setdefault('CUA_DRIVER_RS_VERSION', CUA_VERSION)
            with tempfile.TemporaryDirectory(prefix='strata-cua-install-') as directory:
                if self.platform == 'win32':
                    script = download_script(CUA_PS, directory, 'install.ps1')
                    self.mutate(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script], env=environment)
                else:
                    self.mutate(['bash', download_script(CUA_SH, directory, 'install.sh')], env=environment)
            refresh_path()
            local_cua_executable()
        self.step('CUA Driver', cua)
        def ocx():
            if ocx_command(self.home):
                print('기존 OpenCodex를 재사용합니다.')
            else:
                self.mutate([*npm_command(), 'install', '--global', OPENCODEX_PACKAGE])
            if not ocx_command(self.home):
                raise Pending('OpenCodex 실행 파일을 찾지 못했습니다.')
        self.step('OpenCodex', ocx)
        def rea():
            from tools.claude_mcp.rea_launcher import cached_entry
            roots = [self.home/'.npm/_npx', self.home/'AppData/Local/npm-cache/_npx']
            if os.environ.get('npm_config_cache'):
                roots.insert(0, Path(os.environ['npm_config_cache'])/'_npx')
            if not cached_entry(roots):
                self.mutate([*npm_command(npx=True), '--yes', REA_PACKAGE, '--help'])
        self.step('REA 패키지', rea)

    def proxy(self):
        command = ocx_command(self.home)
        status = json.loads(run([*command, 'service', 'status', '--json'], capture=True, timeout=30))
        if status.get('stale') or status.get('conflict'):
            raise Pending('기존 OpenCodex 서비스 소유 정보가 충돌합니다. 자동 재설치하지 않고 중단합니다.')
        if not status.get('installed'):
            self.mutate([*command, 'service', 'install'])
            status = json.loads(run([*command, 'service', 'status', '--json'], capture=True, timeout=30))
            if status.get('stale') or status.get('conflict'):
                raise Pending('서비스 설치 뒤 소유 정보가 충돌합니다. 다른 서비스로 대체하지 않습니다.')
        if not status.get('running'):
            self.mutate([*command, 'service', 'start'])
        from tools.claude_opencodex_client import read_json
        port = read_json(self.home/'.opencodex/config.json', {}).get('port', 10100)
        if type(port) is not int or not 1 <= port <= 65535:
            raise Pending('OpenCodex 포트 설정을 확인하세요.')
        self.base = f'http://127.0.0.1:{port}'
        deadline = time.monotonic()+30
        while True:
            try:
                status = get_json(self.base+'/healthz', {'Authorization': 'Bearer opencodex-proxy'})
                if status.get('status') != 'ok' or 'opencodex' not in status.get('service', '').lower():
                    raise Pending('해당 포트의 서비스가 OpenCodex가 아닙니다.')
                return
            except (OSError, ValueError):
                if time.monotonic() >= deadline:
                    raise Pending('OpenCodex 시작을 확인하지 못했습니다. 상태를 확인한 뒤 다시 실행하세요.') from None
                time.sleep(.5)

    def connect(self, connection=None, ssh_host=None):
        from tools import claude_opencodex_client as shared
        config = shared.read_json(self.home/'.opencodex/config.json', {})
        prior = config.get('providers', {}).get('strata', {})
        connection = connection or self.state.get('connection')
        if not connection:
            print('1: 이 PC의 서버  2: 외부 서버(SSH)  3: 이미 열린 SSH 터널')
            connection = {'1': 'local', '2': 'ssh', '3': 'forwarded'}.get(input('연결 방식 [1]: ').strip() or '1')
        if connection not in ('local', 'ssh', 'forwarded'):
            raise Pending('연결 방식을 다시 선택하세요.')
        self.state['connection'] = connection
        origin = 'http://127.0.0.1:'+('8080' if connection == 'local' else '18080')
        if connection == 'ssh':
            ssh_host = ssh_host or self.state.get('ssh_host') or input('서버 SSH 주소 (사용자@서버): ').strip()
            validate_ssh_host(ssh_host)
            self.state['ssh_host'] = ssh_host
            self.save()
            if not endpoint_exists(origin):
                self.ensure_ssh_client()
                launch_tunnel(ssh_host, self.platform)
                input('열린 SSH 창에서 로그인한 뒤 Enter를 누르세요. 창은 유지합니다. ')
        self.save()
        key = ''
        reused_key = False
        if prior.get('baseUrl', '').rstrip('/') == origin+'/v1':
            _, headers = shared.strata_upstream(self.home)
            key = headers.get('Authorization', '').removeprefix('Bearer ')
            reused_key = bool(key)
        elif connection == 'local':
            key_file = self.home/'.config/strata/STRATA_API_KEY'
            if key_file.is_file():
                key = key_file.read_text(encoding='utf-8').strip()
        if not key:
            key = getpass.getpass('Strata 서버 API 키 (키가 없으면 Enter, 화면에 표시되지 않음): ')
        headers = {'Authorization': 'Bearer '+key} if key else {}
        try:
            health = get_json(origin+'/health', headers)
        except (OSError, ValueError):
            raise Pending('Strata 접속 실패입니다. 서버·터널·API 키를 확인한 뒤 재실행하세요.') from None
        model, context = health.get('model'), health.get('max_context')
        if health.get('status') != 'ok' or health.get('loaded') is not True or not isinstance(model, str) or not model:
            raise Pending('서버 모델이 준비되지 않았습니다. 다른 모델로 대체하지 않습니다.')
        if type(context) is not int or context < 262144:
            raise Pending('서버의 262,144 컨텍스트 준비를 먼저 마치세요.')
        new = deepcopy(prior)
        new.update(adapter='anthropic', baseUrl=origin+'/v1', defaultModel=model, allowPrivateNetwork=True,
                   authMode='key' if key else 'local')
        # Preserve a pre-existing file/env reference when it still describes this credential.
        new['apiKey'] = prior['apiKey'] if reused_key else key
        if new == prior:
            self.model = model
            return
        result, error = shared.management_json(self.home, self.base, '/api/providers', body={'name': 'strata', 'provider': new})
        if error or not isinstance(result, dict) or result.get('success') is False:
            raise Pending('OpenCodex 공급자 저장을 확인하지 못했습니다. 키를 설치 기록에는 저장하지 않았습니다.')
        self.model = model

    def ensure_ssh_client(self):
        if shutil.which('ssh'):
            return
        if self.platform != 'win32':
            raise Pending('이 PC의 OpenSSH 클라이언트를 준비하세요.')
        import base64
        print('OpenSSH 클라이언트를 설치합니다. 나타나는 UAC 확인은 직접 처리하세요.')
        payload = "$ErrorActionPreference='Stop'; try { Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0 | Out-Null; exit 0 } catch { exit 2 }"
        encoded = base64.b64encode(payload.encode('utf-16le')).decode('ascii')
        script = "$p=Start-Process powershell.exe -Verb RunAs -WindowStyle Hidden -Wait -PassThru -ArgumentList @('-NoProfile','-EncodedCommand','"+encoded+"'); exit $p.ExitCode"
        self.mutate(['powershell.exe', '-NoProfile', '-Command', script])
        refresh_path()
        if not shutil.which('ssh'):
            raise Pending('OpenSSH 클라이언트 설치 후 새 터미널에서 이어서 실행하세요.')

    def client_config(self):
        from tools import claude_opencodex_client as shared
        from tools import strata_client_settings as clients
        state_path = self.home/'.claude'/shared.STATE
        existing = shared.diagnose(self.home) if state_path.is_file() else {}
        if not existing.get('ready'):
            shared.setup(self.home)  # Existing backups, merge rules and manual-edit protection.
        else:
            print('기존 공통 연결 설정을 재사용합니다. 사용자 지침은 재생성하지 않습니다.')
        clients.sync_model(self.home)
        ocx = ocx_command(self.home)
        run([*ocx, 'claude', 'desktop', 'default', 'opus', 'strata/'+self.model])
        run([*ocx, 'claude', 'desktop', 'apply', '--gateway'])
        result = shared.diagnose(self.home)
        if not result.get('ready') or not result.get('desktop_ready'):
            raise Pending('설치됐지만 연결 진단이 완료되지 않았습니다. 기존 doctor로 남은 항목을 확인하세요.')

    def client(self, connection=None, ssh_host=None):
        self.client_dependencies()
        self.step('OpenCodex 서비스', self.proxy)
        self.step('Strata 서버 연결', lambda: self.connect(connection, ssh_host))
        self.step('Claude 공통 설정·Desktop 연결', self.client_config)
        self.state['status'] = 'configured'
        self.save()
        print('\n설치·연결 설정 완료. Claude Desktop Code의 새 세션에서 사용하세요.')
        print('폴더 신뢰·최초 MCP 확인·OS 권한과 실제 GUI 조작은 별도 확인이 필요합니다.')
        if self.platform == 'darwin':
            print('CUA의 접근성·화면 기록 권한은 직접 허용하세요: cua-driver permissions grant')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def get_json(url, headers=None):
    with build_opener(NoRedirect()).open(Request(url, headers=headers or {}), timeout=5) as response:
        raw = response.read(256*1024+1)
    if len(raw) > 256*1024:
        raise ValueError('서버 응답이 너무 큽니다.')
    return json.loads(raw)


def endpoint_exists(origin):
    # Any response means an occupied tunnel endpoint: never stack another SSH process.
    import socket
    from urllib.parse import urlsplit
    parsed = urlsplit(origin)
    try:
        with socket.create_connection((parsed.hostname, parsed.port), timeout=1):
            pass
        return True
    except OSError:
        return False


def validate_ssh_host(host):
    if (not re.fullmatch(r'[A-Za-z0-9_.@:\[\]%-]+', host or '') or host.startswith('-')
            or host.count('@') > 1 or ('@' in host and not re.fullmatch(r'[A-Za-z0-9_.-]+', host.split('@')[0]))):
        raise ValueError('SSH 주소는 사용자@서버 형식이며 공백·명령 옵션을 포함할 수 없습니다.')


def launch_tunnel(host, platform):
    validate_ssh_host(host)
    ssh = shutil.which('ssh')
    if not ssh:
        raise Pending('OpenSSH 클라이언트가 필요합니다. Windows 선택적 기능에서 OpenSSH 클라이언트를 추가하세요.')
    args = [ssh, '-N', '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=30',
            '-o', 'ServerAliveCountMax=3', '-L', '127.0.0.1:18080:127.0.0.1:8080', host]
    if platform == 'win32':
        subprocess.Popen(args, creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        import shlex
        command = shlex.join(args).replace('\\', '\\\\').replace('"', '\\"')
        run(['/usr/bin/osascript', '-e', 'tell application "Terminal" to do script "'+command+'"'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=['client', 'server'])
    parser.add_argument('--plan', action='store_true', help='설치·파일 변경 없이 준비 단계 표시')
    parser.add_argument('--connection', choices=['local', 'ssh', 'forwarded'])
    parser.add_argument('--ssh-host')
    args = parser.parse_args(argv)
    role = args.role or ('server' if sys.platform.startswith('linux') else 'client')
    if not args.role and not args.plan and sys.platform == 'win32' and sys.stdin.isatty():
        print('1: Claude로 작업할 접속 PC 설치  2: NVIDIA Strata 서버 복구·준비')
        choice = input('이 PC의 역할 [1]: ').strip() or '1'
        if choice not in ('1', '2'):
            print('1 또는 2를 선택하세요.', file=sys.stderr)
            return 2
        role = 'client' if choice == '1' else 'server'
    supported = (sys.platform in ('win32', 'darwin') if role == 'client' else sys.platform in ('win32', 'linux'))
    if not supported:
        print('이 NVFP4 서버는 Windows/Linux, 접속 PC 통합 설치는 Windows/Mac을 사용하세요.', file=sys.stderr)
        return 2
    if args.plan:
        print(json.dumps({'platform': sys.platform, 'role': role, 'changes': False,
              'steps': ['Python', 'Node.js', 'Claude Desktop', 'CUA Driver', 'OpenCodex', 'REA',
                        '서버 연결', '기존 Claude 설정기'] if role == 'client' else
                       ['Python 가상환경', '서버 의존성', 'Visual C++ 실행 환경(Windows)', 'NVIDIA 드라이버 확인·GPU 선택', '동일 포크·모델·Pack 복구 확인', '기존 프로필 준비']}, ensure_ascii=False, indent=2))
        return 0
    refresh_path()
    if args.ssh_host:
        validate_ssh_host(args.ssh_host)
    installer = None
    try:
        with install_lock(Path.home()):
            installer = Installer(Path.home(), role)
            if role == 'client':
                if sys.platform not in ('win32', 'darwin'):
                    raise Pending('접속 PC 통합 설치는 Windows·macOS를 지원합니다. Linux는 --role server를 사용하세요.')
                installer.client(args.connection, args.ssh_host)
            else:
                prepare_server(installer)
        return 0
    except (Pending, ValueError, OSError, subprocess.SubprocessError) as error:
        print('설치 대기: '+(str(error) if isinstance(error, (Pending, ValueError)) else type(error).__name__), file=sys.stderr)
        if installer:
            print('현재 단계 기록: '+str(installer.path), file=sys.stderr)
        print('문제를 해결한 뒤 같은 통합 설치기를 다시 실행하세요.', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('설치를 중지했습니다. 다시 실행하면 실제 설치 상태를 확인해 이어갑니다.', file=sys.stderr)
        return 130


def prepare_server(installer):
    """Reuse exact restored assets and existing profile/server preparers."""
    from tools.strata_iq4xs_profiles import FORK_RELATIVE, SHARD_NAMES, DEFAULT_MANIFEST, MODEL_REVISION, render_profile
    if installer.platform not in ('win32', 'linux'):
        raise Pending('이 NVFP4 서버 설치 경로는 Windows·Linux NVIDIA 서버 전용입니다.')
    windows = installer.platform == 'win32'
    fork, data = ROOT/FORK_RELATIVE, installer.home/'Strata-data'
    python = ROOT/('.venv/Scripts/python.exe' if windows else '.venv/bin/python')
    def environment():
        if windows:
            if not python.is_file():
                if (ROOT/'.venv').exists():
                    raise Pending('기존 .venv가 다른 OS이거나 불완전합니다. 기존 폴더를 보존하고 새 체크아웃에서 설치하세요.')
                installer.mutate([sys.executable, '-m', 'venv', ROOT/'.venv'])
            installer.mutate([python, '-m', 'pip', 'install', '-r', ROOT/'requirements.txt'])
        else:
            installer.mutate(['sh', ROOT/'tools/bootstrap-linux-server.sh', '--mode', 'on'])
        if (fork/'requirements.txt').is_file():
            installer.mutate([python, '-m', 'pip', 'install', '-r', fork/'requirements.txt'])
    installer.step('서버 Python 의존성', environment)
    if windows:
        def vc_runtime():
            script = "if ((Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\VisualStudio\\14.0\\VC\\Runtimes\\x64' -ErrorAction SilentlyContinue).Installed -eq 1) { 'installed' }"
            return 'installed' in run(['powershell.exe', '-NoProfile', '-Command', script], capture=True, timeout=30)
        installer.step('Visual C++ 실행 환경', lambda: installer.package('Microsoft.VCRedist.2015+.x64', vc_runtime))
    def driver():
        smi = shutil.which('nvidia-smi')
        if not smi:
            raise Pending('NVIDIA 드라이버 설치·재부팅을 먼저 마치세요: https://www.nvidia.com/en-us/drivers/ . 설치 기록과 모델 파일은 보존했습니다.')
        rows = run([smi, '--query-gpu=index,name', '--format=csv,noheader'], capture=True, timeout=30).splitlines()
        choices = [line.split(',', 1) for line in rows if ',' in line]
        ti = [index.strip() for index, name in choices if '3090 Ti' in name]
        if len(ti) == 1:
            gpu = int(ti[0])
        else:
            print('\n'.join(rows))
            gpu = int(input('AI 서버에 사용할 GPU 번호: '))
        if str(gpu) not in [index.strip() for index, _ in choices]:
            raise Pending('표시된 GPU 번호를 선택하세요.')
        installer.state['gpu'] = gpu
    installer.step('GPU 드라이버·장치 선택', driver)
    def artifacts():
        engine = fork/'engine'/('strata.exe' if windows else 'strata')
        vision = fork/'engine'/('strata-vision.exe' if windows else 'strata-vision')
        required = [fork/'serve/server.py', fork/'release-manifest.json', engine, vision,
                    data/'packs/unsloth-ud-iq4_xs/index.txt', data/'packs/unsloth-ud-iq4_xs/tokenizer/tokenizer.json',
                    data/'models/mmproj-Qwen3.8-Flash-Next-BF16.gguf', ROOT/'data/expert-profile.bin',
                    fork/'data/uncensor/qwen-nvfp4-gptq-uncensored.gguf',
                    *[data/'models/unsloth-UD-IQ4_XS'/name for name in SHARD_NAMES],
                    *[data/'mtp/rt'/name for name in ('dense.bin', 'experts.bin', 'draft_vocab.bin')]]
        missing = [str(p) for p in required if not p.is_file()]
        if missing:
            print('\n'.join(missing))
            raise Pending('위 동일 포크·모델·Pack 백업 파일을 복원한 뒤 다시 실행하세요. 다른 모델·OS 바이너리로 대체하지 않습니다.')
        manifest = json.loads((ROOT/DEFAULT_MANIFEST).read_text(encoding='utf-8'))
        if manifest.get('model', {}).get('revision') != MODEL_REVISION:
            raise Pending('복구 파일 명세의 모델 버전을 확인하세요.')
        roots = {'strata': ROOT, 'fork': fork, 'data': data,
                 'model': data/'models/unsloth-UD-IQ4_XS', 'pack': data/'packs/unsloth-ud-iq4_xs'}
        invalid = []
        for row in manifest['files']:
            if row['root'] == 'fork' and not windows:
                continue  # Windows release sizes are not Linux executable evidence.
            path = roots[row['root']]/row['path']
            if not path.is_file() or path.stat().st_size != row['size']:
                invalid.append(str(path))
        if invalid:
            print('\n'.join(invalid))
            raise Pending('위 복구 파일이 없거나 크기가 다릅니다. 실제 백업을 확인하세요. 전체 해시 검증은 별도입니다.')
    installer.step('동일 포크·모델·Pack 복원 확인', artifacts)
    def profiles():
        gpu = installer.state['gpu']
        if windows:
            os.environ['STRATA_SERVER_GPU'] = str(gpu)
            for mode in ('on', 'off'):
                render_profile(ROOT, mode, ROOT, data,
                    Path(os.environ.get('LOCALAPPDATA', installer.home/'AppData/Local'))/'Strata/profiles'/f'strata-unsloth-ud-iq4_xs-nvfp4fork-uncensored-{mode}.json')
            run(['setx.exe', 'STRATA_SERVER_GPU', str(gpu)])
            run(['setx.exe', 'STRATA_SERVER_LOCAL_ONLY', '1'])
            ensure_server_key(installer.home)
        else:
            for mode in ('on', 'off'):
                run([python, ROOT/'tools/linux_nvfp4_server.py', 'prepare', '--mode', mode, '--gpu', str(gpu)])
            from tools.claude_opencodex_client import publish_files
            directory = Path(os.environ.get('XDG_CONFIG_HOME', installer.home/'.config'))/'strata'
            path = directory/'server-gpu'
            original = path.read_bytes() if path.exists() else None
            publish_files({path: str(gpu)+'\n'}, directory, {path: original})
    installer.step('기존 ON/OFF 프로필·키 준비', profiles)
    installer.state['status'] = 'configured'
    installer.save()
    print('서버 의존성·프로필 준비 완료. 기존 ON/OFF 실행기로 서버를 시작하세요.')
    print('실제 모델 로딩·성능·외부 접속 검증은 아직 수행하지 않았습니다.')


def ensure_server_key(home):
    import secrets
    path = home/'.config/strata/STRATA_API_KEY'
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise Pending('API 키 경로가 심볼릭 링크입니다. 기존 파일을 보존했습니다.')
    try:
        with open(path, 'x', encoding='utf-8', opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
            stream.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    key = path.read_text(encoding='utf-8')
    if not re.fullmatch(r'[0-9a-fA-F]{64}', key):
        raise Pending('기존 서버 API 키 형식을 확인하세요. 키를 덮어쓰지 않았습니다.')
    if os.name == 'nt':
        sid = run(['powershell.exe', '-NoProfile', '-Command',
                   '[Security.Principal.WindowsIdentity]::GetCurrent().User.Value'], capture=True, timeout=30).strip()
        if not re.fullmatch(r'S-1-[0-9-]+', sid):
            raise Pending('서버 API 키 소유자를 확인할 수 없습니다.')
        run(['icacls.exe', path, '/inheritance:r', '/grant:r', '*'+sid+':(F)',
             '/grant:r', '*S-1-5-18:(F)'])
    else:
        path.chmod(0o600)


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
