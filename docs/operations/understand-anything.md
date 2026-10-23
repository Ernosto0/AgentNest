# Understand Anything

[Understand Anything](https://github.com/Egonex-AI/Understand-Anything) is optional
development tooling for exploring AgentNest's architecture. It runs separately
from the API, worker, frontend, and public landing page.

## Installed on this Windows machine

- Source: `$HOME\.understand-anything\repo`, version 2.9.7,
  commit `e24fcf6d371bcfa529bc110bacb1bb43de1b8d33`.
- All nine Codex skills: junctions under `$HOME\.codex\skills\understand*`.
- Universal plugin junction: `$HOME\.understand-anything-plugin`.
- Dependencies and the core/dashboard builds live in that external checkout.

Skills become available on the next Codex turn. If the IDE does not discover
them, restart its Codex session.

## Analyze and explore

Open AgentNest in Codex and run:

```text
$understand
$understand-dashboard
```

The first command generates `.ua/knowledge-graph.json`; initial graph generation
is separate from installation and has not been run as part of this setup. The
skill asks you to review `.ua/.understandignore` before a full analysis. The
current scope includes the backend, frontend, landing page, tests, migrations,
evals, and docs, while excluding secrets, dependencies, runtime data, generated
API types/specification, test reports, and analysis artifacts.

`.ua/config.json` selects English to match the engineering docs and disables
automatic updates. Re-run `$understand` after code changes; later analyses are
incremental by default. No Git hooks are installed by this setup.

Other useful commands:

```text
$understand-chat How do approval checks protect outbound Instagram operations?
$understand-explain backend/app/reporting/service.py
$understand-diff
$understand-onboard
$understand-domain
```

Once the graph exists, the dashboard can also run directly from PowerShell,
without an AI session:

```powershell
.\scripts\understand-dashboard.ps1
# Optional: .\scripts\understand-dashboard.ps1 -Port 5180
```

This launcher uses port 5174 to avoid AgentNest's frontend on 5173. Vite chooses
another free port if necessary. Use the tokenized URL printed in the terminal;
the dashboard opens in your browser. Press Ctrl+C to stop it.

## Setup on another Windows machine

Requires Git, Node.js >= 22, and pnpm >= 10. The upstream checkout pins its pnpm
version through Corepack. Download and inspect the upstream Windows installer,
then run it for Codex:

```powershell
$installer = Join-Path $env:TEMP 'install-understand-anything.ps1'
Invoke-WebRequest 'https://raw.githubusercontent.com/Egonex-AI/Understand-Anything/main/install.ps1' -OutFile $installer
Get-Content -LiteralPath $installer
& $installer codex
Push-Location (Join-Path $HOME '.understand-anything\repo')
try {
    pnpm install --frozen-lockfile
    pnpm --filter '@understand-anything/dashboard' build
} finally {
    Pop-Location
}
```

The upstream installer uses `$HOME\.agents\skills` for its Codex junctions;
both that location and this machine's `$HOME\.codex\skills` serve the same
skills. Choose one installation location to avoid duplicate entries.

## Update and share

Update the external checkout and rebuild from PowerShell:

```powershell
git -C (Join-Path $HOME '.understand-anything\repo') pull --ff-only
Push-Location (Join-Path $HOME '.understand-anything\repo')
try {
    pnpm install --frozen-lockfile
    pnpm --filter '@understand-anything/dashboard' build
} finally {
    Pop-Location
}
```

Skill junctions follow the updated checkout. Restart the Codex session to refresh
loaded instructions. Re-run `$understand` to refresh the project's graph.

Configuration and generated graph artifacts can be committed for teammates.
`.gitignore` excludes intermediate files, temporary output, trash directories,
and the local diff overlay. Review generated artifacts before sharing them.
