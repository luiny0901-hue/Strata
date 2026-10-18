# OpenCode on another Windows PC or Apple Silicon Mac

> 현재 통합 설치/복원 진입점은 [OPENCODE_QUICKSTART_KO.md](OPENCODE_QUICKSTART_KO.md)입니다. 아래의 이전 수동 설정 예시보다 통합 설치기를 우선 사용하세요.

This setup keeps the Strata model on the RTX 3090 Ti Windows host. A client
Windows PC or Apple Silicon Mac runs its own OpenCode and its own CUA Driver.
OpenCode sends model requests over the private LAN to Strata; CUA Driver acts
on the client PC's local applications. The Windows CUA executable and its
policy files are never copied to another computer.

Fetch the portable settings from the public setup branch:

```sh
git clone --branch feature/iq4xs-opencode-setup https://github.com/luiny0901-hue/Strata.git
cd Strata
```

If the checkout already exists, pull that branch before copying the templates.

## Windows Strata host

1. Create the API key once from a normal PowerShell window in this checkout:

   ```powershell
   pwsh -NoProfile -ExecutionPolicy Bypass -File .\tools\windows\configure_strata_api_key.ps1 -Generate
   ```

   It creates `%USERPROFILE%\.config\strata\STRATA_API_KEY`, a 64-character
   random key. The file ACL allows only the current user, SYSTEM and local
   Administrators. It does not print the value. Do not put the key in Git,
   `opencode.json`, a BAT file or a chat transcript.

2. Add the narrow Windows Firewall rule once from an elevated PowerShell:

   ```powershell
   pwsh -NoProfile -ExecutionPolicy Bypass -File .\tools\windows\allow_strata_lan.ps1
   ```

   The rule allows TCP 8080 only on the Private profile and only from
   `LocalSubnet`, and blocks it on Domain/Public profiles. The script requires
   Windows Firewall enabled for all profiles and at least one active Private
   network. It narrows only the two specifically identified broad legacy rules
   (`llama-server-8080` and `llama.cpp API 8080 LAN`); it preserves the existing
   exact-IP `llama.cpp API 8080 Rider` rule. Unknown broad rules stop setup
   before any firewall changes.
   Do not change a public or guest network to Private just to make this work.

3. Start either IQ4_XS ON/OFF batch file. Each refuses to start if the key
   is missing or malformed, reads it from the protected file into the server
   process environment, and binds the API to `0.0.0.0`. The key is not passed
   as a command-line argument. It also runs a read-only firewall check and
   refuses to start if the scoped allow/block rules are missing or another
   broad 8080 rule remains. The server prints the current LAN URL; use its
   `from other devices` address because DHCP can change the host IP.

   The current Windows OpenCode continues using `127.0.0.1`; only remote
   clients use the LAN address.

## A Windows client

1. Install OpenCode and CUA Driver on that PC. The official CUA installer is:

   ```powershell
   irm https://cua.ai/driver/install.ps1 | iex
   ```

2. Copy the key into that PC's protected user file without adding it to a
   repository. From this checkout, run:

   ```powershell
   pwsh -NoProfile -ExecutionPolicy Bypass -File .\tools\windows\configure_strata_api_key.ps1 -Prompt
   ```

   Transfer the key from the host using a password manager or another private
   channel. On the host, reveal it locally only when you are ready to transfer:

   ```powershell
   Get-Content -Raw "$env:USERPROFILE\.config\strata\STRATA_API_KEY"
   ```

3. Use `docs/opencode-remote-windows.example.jsonc` as the base for
   `%USERPROFILE%\.config\opencode\opencode.json`. Set
   `STRATA_HOST_LAN_IP` to the host address printed by the batch file. Merge
   the template with an existing file instead of replacing unrelated local
   settings. Install the shared instructions and local command runners:

   ```powershell
   $globalConfig = Join-Path $HOME '.config\opencode'
   $scripts = Join-Path $globalConfig 'scripts'
   New-Item -ItemType Directory -Path $scripts -Force | Out-Null
   Copy-Item .\config\opencode\KOREAN_INSTRUCTIONS.md $globalConfig
   Copy-Item .\tools\opencode\run_bounded_command.ps1, .\tools\opencode\run_bounded_command.sh $scripts
   ```

   The template loads the instructions from
   `%USERPROFILE%\.config\opencode\KOREAN_INSTRUCTIONS.md`. The provider reads
   the key from the protected file path.

4. Register the local CUA Driver MCP server and verify it. The installer may
   require a new terminal before `cua-driver` is on `PATH`; use its official
   client configuration output if the executable name does not resolve:

   ```powershell
   cua-driver mcp-config --client opencode
   opencode mcp list
   ```

   If the generated configuration prints a different absolute executable path,
   use that path in the template's `mcp.servers.cua-driver.command`. Restart
   OpenCode/Rider after installation. CUA Driver controls this Windows client,
   not the Strata host.

## An Apple Silicon Mac client

1. Install OpenCode natively on macOS. Install CUA Driver and its local CLI:

   ```sh
   /bin/bash -c "$(curl -fsSL https://cua.ai/driver/install.sh)"
   open -n -g -a CuaDriver --args serve
   cua-driver permissions grant
   ```

   Approve CuaDriver under **Accessibility** and **Screen & System Audio
   Recording** in macOS System Settings. CUA Driver's published macOS builds
   are universal; the Mac must run macOS 14 or later.

2. From the checkout, save the same host key into the Mac user's file:

   ```sh
   bash tools/macos/configure_strata_api_key.sh
   ```

   The script prompts without echo, stores the file at
   `~/.config/strata/STRATA_API_KEY`, and applies directory mode 700/file mode
   600.

3. Use `docs/opencode-remote-macos.example.jsonc` as the base for
   `~/.config/opencode/opencode.json`. Replace `STRATA_HOST_LAN_IP` with the
   host address printed by the batch file. Merge it with any existing config.
   Install the shared instructions and bounded shell runner:

   ```sh
   mkdir -p ~/.config/opencode/scripts
   cp config/opencode/KOREAN_INSTRUCTIONS.md ~/.config/opencode/KOREAN_INSTRUCTIONS.md
   cp tools/opencode/run_bounded_command.sh ~/.config/opencode/scripts/run_bounded_command.sh
   chmod 700 ~/.config/opencode/scripts/run_bounded_command.sh
   ```

   The template loads the instructions from `~/.config/opencode/KOREAN_INSTRUCTIONS.md`.
   The template uses `/bin/zsh` and keeps the same Strata model, context/output
   limits, reasoning variants, compaction and Korean agent instructions.

4. Register the local CUA Driver with OpenCode and verify it:

   ```sh
   cua-driver mcp-config --client opencode
   opencode mcp list
   ```

   If the generated configuration prints a different absolute executable path,
   use that path in the template's `mcp.servers.cua-driver.command`. Start
   OpenCode after the CUA daemon is running. CUA operates the Mac's own apps;
   Strata receives only model API requests. OpenCode is not remotely
   controlling the Windows host desktop.

## Network and remaining limits

- This exposes an authenticated HTTP API to the trusted Private LAN. HTTP does
  not encrypt the API key or prompts. Do not forward port 8080 to the public
  internet or use this on a guest/public network. For off-LAN use, use a VPN
  and create a separate firewall rule restricted to the exact VPN peer/subnet;
  do not widen the `LocalSubnet` rule blindly.
- The Strata API key protects `/v1` requests. The server's web page and health
  endpoint are not equivalent to an authenticated OpenCode session, so the
  firewall limits all port-8080 access to local subnets and blocks Domain/Public
  profiles. Every device on the allowed local subnet can still reach those
  non-model endpoints.
- If a client cannot connect, first check that the server is running, use the
  exact current LAN URL printed by Strata, and confirm the Windows network is
  Private with the firewall script's rule installed. Do not stop another
  process that owns port 8080.
- The host model, 262K cap, ON/OFF profiles and GPU stay on the Windows host.
  The Mac is an API client; no Mac model download or GPU setup is required.
- CUA Driver setup is per machine and needs local OS permission grants. The
  current Windows background-only wrapper/policy is machine-specific and is
  not reproduced by copying the Windows OpenCode config. Review the CUA tools
  and permission mode on each new machine before unattended GUI work.
- This turn does not start Strata or test actual requests from a second PC or
  Mac. Those require the host launcher, firewall rule, and a client machine.
