# maker-bridge 2 in einem (neuen) Claude-Code-Konto einrichten.
# Aufruf aus dem Ordner maker-bridge-2:   powershell -ExecutionPolicy Bypass -File claude\install.ps1
# Optional:  -Bestellliste "C:\Pfad\Bestellliste.html"   (sonst sammeln die Agenten Kaufteile in projekt.md)
#            -NurPruefen                                  (nichts kopieren, nur Werkzeuge pruefen)
param([string]$Bestellliste = "", [switch]$NurPruefen)
$ErrorActionPreference = 'Stop'
$MB2 = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Home2 = Join-Path $env:USERPROFILE '.claude'
Write-Host "mb2-Ordner: $MB2"

# 1. uv + Python-Umgebung
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) { $uv = Join-Path $env:USERPROFILE '.local\bin\uv.exe' }
if (-not (Test-Path $uv)) {
    Write-Host 'uv fehlt. Installieren:  powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  und neu starten.'
    exit 1
}
Push-Location $MB2
& $uv sync --all-groups
if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Host 'uv sync fehlgeschlagen.'; exit 1 }

# 2. Externe Programme pruefen (CalculiX, Elmer, MPI, KiCad, PrusaSlicer, Java, Freerouting, Blender)
Write-Host "`n--- Werkzeuge ---"
& $uv run python -m mb2.werkzeuge
Pop-Location
if ($NurPruefen) { exit 0 }

# 3. Agenten + Skill mit eingesetzten Pfaden nach ~/.claude kopieren
if ($Bestellliste) { $bl = $Bestellliste } else { $bl = '(keine Bestellliste: neue Kaufteile in projekt.md unter "Bestellen" sammeln)' }
$ziele = @(
    @{ von = Join-Path $PSScriptRoot 'agents'; nach = Join-Path $Home2 'agents' },
    @{ von = Join-Path $PSScriptRoot 'skills\idee-zu-druck-2'; nach = Join-Path $Home2 'skills\idee-zu-druck-2' }
)
foreach ($z in $ziele) {
    New-Item -ItemType Directory -Force $z.nach | Out-Null
    foreach ($f in Get-ChildItem $z.von -Filter *.md) {
        $t = [IO.File]::ReadAllText($f.FullName, [Text.Encoding]::UTF8)
        $t = $t.Replace('{MB2}', $MB2).Replace('{BESTELLLISTE}', $bl)
        $ziel = Join-Path $z.nach $f.Name
        [IO.File]::WriteAllText($ziel, $t, (New-Object Text.UTF8Encoding $false))
        Write-Host "kopiert: $ziel"
    }
}

# 4. MCP-Server mb2 fuer alle Projekte (scope user) eintragen
$claude = (Get-Command claude -ErrorAction SilentlyContinue).Source
if ($claude) {
    & $claude mcp remove mb2 --scope user 2>$null | Out-Null
    & $claude mcp add mb2 --scope user -- $uv run --directory $MB2 python -m mb2.server
} else {
    $json = @{ mcpServers = @{ mb2 = @{ type = 'stdio'; command = $uv; args = @('run', '--directory', $MB2, 'python', '-m', 'mb2.server') } } } | ConvertTo-Json -Depth 5
    Write-Host "`nclaude-CLI nicht im PATH. Diesen Block in $env:USERPROFILE\.claude.json unter mcpServers eintragen:`n$json"
}
Write-Host "`nFertig. Claude Code neu starten, dann: 'mcp__mb2__tools_status' aufrufen lassen."
