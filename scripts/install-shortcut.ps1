<#
.SYNOPSIS
    Put a Recall shortcut on the Desktop and in the Start Menu.

.DESCRIPTION
    Points at Recall.cmd with the generated icon, so Recall launches like any
    other installed app and is findable from the Start Menu search.

.PARAMETER Remove
    Delete the shortcuts instead of creating them.
#>
[CmdletBinding()]
param([switch]$Remove)

$ErrorActionPreference = 'Stop'

$Root   = Split-Path -Parent $PSScriptRoot
$Target = Join-Path $Root 'Recall.cmd'
$Icon   = Join-Path $PSScriptRoot 'recall.ico'

$links = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Recall.lnk'),
    (Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs\Recall.lnk')
)

if ($Remove) {
    foreach ($link in $links) {
        if (Test-Path $link) { Remove-Item $link -Force; Write-Host "removed $link" }
    }
    return
}

if (-not (Test-Path $Target)) { throw "Recall.cmd not found at $Target" }

$shell = New-Object -ComObject WScript.Shell
foreach ($link in $links) {
    $parent = Split-Path -Parent $link
    if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Force $parent | Out-Null }

    $shortcut = $shell.CreateShortcut($link)
    $shortcut.TargetPath       = $Target
    $shortcut.WorkingDirectory = $Root
    $shortcut.Description      = 'Recall - lecture recorder, transcriber and tutor'
    if (Test-Path $Icon) { $shortcut.IconLocation = $Icon }
    $shortcut.Save()
    Write-Host "created $link"
}
