<#
.SYNOPSIS
Launch the local Understand Anything dashboard for AgentNest.
#>
[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 5174,
    [string]$PluginRoot = (Join-Path $HOME '.understand-anything-plugin')
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$dataDir = Join-Path $projectRoot '.ua'
if (Test-Path -LiteralPath (Join-Path $projectRoot '.understand-anything') -PathType Container) {
    $dataDir = Join-Path $projectRoot '.understand-anything'
}
if (-not (Test-Path -LiteralPath (Join-Path $dataDir 'knowledge-graph.json') -PathType Leaf)) {
    throw 'No knowledge graph yet. In Codex, run $understand in AgentNest first.'
}
$dashboardDir = Join-Path $PluginRoot 'packages\dashboard'
if (-not (Test-Path -LiteralPath $dashboardDir -PathType Container)) {
    throw 'Understand Anything is not installed. See docs/operations/understand-anything.md.'
}
$pnpm = Get-Command pnpm -ErrorAction Stop
$previousGraphDir = $env:GRAPH_DIR
Push-Location -LiteralPath $dashboardDir
try {
    $env:GRAPH_DIR = $projectRoot
    & $pnpm exec vite --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE -ne 0) {
        throw "Understand Anything dashboard exited with code $LASTEXITCODE."
    }
} finally {
    $env:GRAPH_DIR = $previousGraphDir
    Pop-Location
}
