# PYAMBAR - Script de registro/desregistro no pyRevit
# Usado pelo MSI como CustomAction
# Uso: register.ps1 register | unregister

param([string]$Action = "register")

$INSTALL_PATH = "$env:APPDATA\pyRevit\Extensions"
$CONFIG_PATH  = "$env:APPDATA\pyRevit\pyRevit_config.ini"
$CLI_PATHS = @(
    "C:\Program Files\pyRevit-Master\bin\pyrevit.exe",
    "C:\Program Files\pyRevit\bin\pyrevit.exe",
    "$env:APPDATA\pyRevit-Master\bin\pyrevit.exe"
)

function Find-CLI {
    foreach ($p in $CLI_PATHS) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Register {
    $cli = Find-CLI
    if ($cli) {
        & $cli extensions paths add $INSTALL_PATH 2>$null
        return
    }
    if (-not (Test-Path $CONFIG_PATH)) { return }
    try {
        $content = Get-Content $CONFIG_PATH -Raw -Encoding UTF8
        $modified = $false
        if ($content -match 'userextensions\s*=\s*(\[.*?\])') {
            $list = $Matches[1] | ConvertFrom-Json
            $norm = $INSTALL_PATH.ToLower().Replace('\','/')
            if (-not ($list | Where-Object { $_.ToLower().Replace('\','/') -eq $norm })) {
                $list += $INSTALL_PATH
                $content = $content -replace 'userextensions\s*=\s*\[.*?\]', "userextensions = $($list | ConvertTo-Json -Compress)"
                $modified = $true
            }
        }
        $section = "[PYAMBAR.extension]"
        if ($content -notmatch [regex]::Escape($section)) {
            $content += "`n$section`ndisabled = false`nprivate_repo = false`nusername = `"`"`npassword = `"`"`n"
            $modified = $true
        }
        if ($modified) { Set-Content $CONFIG_PATH $content -Encoding UTF8 }
    } catch {}
}

function Unregister {
    $cli = Find-CLI
    if ($cli) {
        & $cli extensions paths remove $INSTALL_PATH 2>$null
        return
    }
    if (-not (Test-Path $CONFIG_PATH)) { return }
    try {
        $content = Get-Content $CONFIG_PATH -Raw -Encoding UTF8
        $modified = $false
        if ($content -match 'userextensions\s*=\s*(\[.*?\])') {
            $list = $Matches[1] | ConvertFrom-Json
            $norm = $INSTALL_PATH.ToLower().Replace('\','/')
            $new = $list | Where-Object { $_.ToLower().Replace('\','/') -ne $norm }
            if ($new.Count -ne $list.Count) {
                $content = $content -replace 'userextensions\s*=\s*\[.*?\]', "userextensions = $($new | ConvertTo-Json -Compress)"
                $modified = $true
            }
        }
        $content = $content -replace '\[PYAMBAR\.extension\][^\[]*', ''
        $modified = $true
        if ($modified) { Set-Content $CONFIG_PATH $content -Encoding UTF8 }
    } catch {}
}

if ($Action -eq "register") { Register }
elseif ($Action -eq "unregister") { Unregister }
