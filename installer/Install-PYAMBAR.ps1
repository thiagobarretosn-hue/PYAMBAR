# =============================================================================
# PYAMBAR Installer - PowerShell Script
# Alternativa ao instalador .exe para evitar bloqueios do Windows SmartScreen
#
# USO:
#   PowerShell -ExecutionPolicy Bypass -File Install-PYAMBAR.ps1
#
# Ou execute diretamente no PowerShell (como Admin):
#   Set-ExecutionPolicy Bypass -Scope Process -Force; .\Install-PYAMBAR.ps1
#
# VERSAO: 1.0.0
# AUTOR: Thiago Barreto Sobral Nunes
# =============================================================================

param(
    [string]$InstallPath = "",
    [switch]$SkipRegistration,
    [switch]$Silent
)

# Configuracao
$GITHUB_REPO = "thiagobarretosn-hue/PYAMBAR"
$GITHUB_BRANCH = "main"
$EXTENSION_NAME = "PYAMBAR.extension"
$APP_VERSION = "1.0.0"

# Caminhos padrao
$DEFAULT_EXTENSIONS_PATH = Join-Path $env:APPDATA "pyRevit-Master\Extensions"
$PYREVIT_CONFIG_PATH = Join-Path $env:APPDATA "pyRevit\pyRevit_config.ini"
$PYREVIT_CLI_PATHS = @(
    "C:\Program Files\pyRevit-Master\bin\pyrevit.exe",
    "C:\Program Files\pyRevit\bin\pyrevit.exe",
    (Join-Path $env:APPDATA "pyRevit-Master\bin\pyrevit.exe")
)

# =============================================================================
# FUNCOES AUXILIARES
# =============================================================================

function Write-ColorOutput {
    param(
        [string]$Message,
        [ConsoleColor]$Color = [ConsoleColor]::White
    )
    if (-not $Silent) {
        Write-Host $Message -ForegroundColor $Color
    }
}

function Write-Progress-Custom {
    param(
        [int]$Percent,
        [string]$Status
    )
    if (-not $Silent) {
        Write-Progress -Activity "Instalando PYAMBAR" -Status $Status -PercentComplete $Percent
    }
}

function Find-PyRevitCLI {
    foreach ($path in $PYREVIT_CLI_PATHS) {
        if (Test-Path $path) {
            return $path
        }
    }
    return $null
}

function Test-PyRevitInstalled {
    return ((Find-PyRevitCLI) -ne $null) -or (Test-Path $PYREVIT_CONFIG_PATH)
}

function Get-InstalledVersion {
    param([string]$Path)

    $extensionPath = Join-Path $Path $EXTENSION_NAME
    $jsonPath = Join-Path $extensionPath "extension.json"

    if (Test-Path $jsonPath) {
        try {
            $json = Get-Content $jsonPath -Raw | ConvertFrom-Json
            return $json.version
        } catch {
            return $null
        }
    }
    return $null
}

function Get-RemoteVersion {
    try {
        # Tenta releases primeiro
        $releaseUrl = "https://api.github.com/repos/$GITHUB_REPO/releases/latest"
        $headers = @{ "User-Agent" = "PYAMBAR-Installer" }
        $response = Invoke-RestMethod -Uri $releaseUrl -Headers $headers -TimeoutSec 10 -ErrorAction Stop
        return $response.tag_name -replace '^v', ''
    } catch {
        try {
            # Fallback: extension.json
            $rawUrl = "https://raw.githubusercontent.com/$GITHUB_REPO/$GITHUB_BRANCH/PYAMBAR.extension/extension.json"
            $response = Invoke-RestMethod -Uri $rawUrl -Headers @{ "User-Agent" = "PYAMBAR-Installer" } -TimeoutSec 10
            return $response.version
        } catch {
            return "?.?.?"
        }
    }
}

function Register-ExtensionPyRevit {
    param([string]$ExtensionPath)

    $parentPath = Split-Path $ExtensionPath -Parent

    # Tenta usar CLI primeiro
    $cli = Find-PyRevitCLI
    if ($cli) {
        try {
            & $cli extensions paths add $parentPath 2>$null
        } catch {}
    }

    # Edita config.ini diretamente
    if (Test-Path $PYREVIT_CONFIG_PATH) {
        try {
            $content = Get-Content $PYREVIT_CONFIG_PATH -Raw -Encoding UTF8
            $modified = $false

            # 1. Adiciona ao userextensions
            if ($content -match 'userextensions\s*=\s*(\[.*?\])') {
                $currentList = $Matches[1] | ConvertFrom-Json
                $normalizedParent = $parentPath.ToLower().Replace('\', '/')
                $exists = $currentList | Where-Object { $_.ToLower().Replace('\', '/') -eq $normalizedParent }

                if (-not $exists) {
                    $currentList += $parentPath
                    $newListStr = ($currentList | ConvertTo-Json -Compress)
                    $content = $content -replace 'userextensions\s*=\s*\[.*?\]', "userextensions = $newListStr"
                    $modified = $true
                }
            }

            # 2. Cria secao [PYAMBAR.extension] se nao existe
            $sectionName = "[PYAMBAR.extension]"
            if ($content -notmatch [regex]::Escape($sectionName)) {
                $extensionConfig = @"

$sectionName
disabled = false
private_repo = false
username = ""
password = ""
"@
                $content += $extensionConfig
                $modified = $true
            }

            if ($modified) {
                Set-Content -Path $PYREVIT_CONFIG_PATH -Value $content -Encoding UTF8
            }

            return $true
        } catch {
            Write-ColorOutput "Aviso: Nao foi possivel registrar automaticamente. Registre manualmente via Extension Manager." -Color Yellow
            return $false
        }
    }
    return $false
}

# =============================================================================
# INSTALACAO PRINCIPAL
# =============================================================================

function Install-PYAMBAR {
    # Banner
    Write-ColorOutput ""
    Write-ColorOutput "=============================================" -Color Cyan
    Write-ColorOutput "       PYAMBAR Installer v$APP_VERSION" -Color Cyan
    Write-ColorOutput "     Extensao pyRevit para BIM e MEP" -Color Cyan
    Write-ColorOutput "=============================================" -Color Cyan
    Write-ColorOutput ""

    # Verificar pyRevit
    if (Test-PyRevitInstalled) {
        Write-ColorOutput "[OK] pyRevit detectado" -Color Green
    } else {
        Write-ColorOutput "[!] pyRevit nao encontrado - instale primeiro em pyrevitlabs.io" -Color Yellow
    }

    # Definir caminho de instalacao
    if ([string]::IsNullOrEmpty($InstallPath)) {
        $InstallPath = $DEFAULT_EXTENSIONS_PATH
    }

    # Verificar versoes
    $installedVersion = Get-InstalledVersion -Path $InstallPath
    $remoteVersion = Get-RemoteVersion

    Write-ColorOutput ""
    Write-ColorOutput "Versao instalada: $(if ($installedVersion) { $installedVersion } else { 'Nao instalado' })" -Color White
    Write-ColorOutput "Versao disponivel: $remoteVersion" -Color Green
    Write-ColorOutput "Pasta de instalacao: $InstallPath" -Color White
    Write-ColorOutput ""

    # Confirmacao (se nao for silent)
    if (-not $Silent) {
        $confirm = Read-Host "Deseja continuar? [S/n]"
        if ($confirm -eq 'n' -or $confirm -eq 'N') {
            Write-ColorOutput "Instalacao cancelada." -Color Yellow
            return
        }
    }

    $extensionPath = Join-Path $InstallPath $EXTENSION_NAME
    $isUpdate = Test-Path $extensionPath

    try {
        # 1. Criar pasta
        Write-Progress-Custom -Percent 5 -Status "Preparando pasta de instalacao..."
        if (-not (Test-Path $InstallPath)) {
            New-Item -ItemType Directory -Path $InstallPath -Force | Out-Null
        }

        # 2. Backup se atualizacao
        if ($isUpdate) {
            Write-Progress-Custom -Percent 10 -Status "Criando backup..."
            $backupPath = "${extensionPath}_backup"
            if (Test-Path $backupPath) {
                Remove-Item $backupPath -Recurse -Force
            }
            Copy-Item $extensionPath $backupPath -Recurse
            Write-ColorOutput "[OK] Backup criado em: $backupPath" -Color Gray
        }

        # 3. Download
        Write-Progress-Custom -Percent 20 -Status "Baixando do GitHub..."
        $zipUrl = "https://github.com/$GITHUB_REPO/archive/refs/heads/$GITHUB_BRANCH.zip"
        $zipPath = Join-Path $InstallPath "pyambar_download.zip"

        # Usar .NET WebClient para progresso
        $webClient = New-Object System.Net.WebClient
        $webClient.Headers.Add("User-Agent", "PYAMBAR-Installer")

        Write-ColorOutput "Baixando de: $zipUrl" -Color Gray
        $webClient.DownloadFile($zipUrl, $zipPath)
        Write-ColorOutput "[OK] Download concluido" -Color Green

        # 4. Extrair
        Write-Progress-Custom -Percent 60 -Status "Extraindo arquivos..."
        $extractPath = Join-Path $InstallPath "pyambar_extract"

        if (Test-Path $extractPath) {
            Remove-Item $extractPath -Recurse -Force
        }

        Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force
        Write-ColorOutput "[OK] Arquivos extraidos" -Color Green

        # 5. Instalar
        Write-Progress-Custom -Percent 80 -Status "Instalando extensao..."

        # Encontrar pasta extraida
        $repoFolder = Get-ChildItem $extractPath | Select-Object -First 1
        $sourceExtension = Join-Path $repoFolder.FullName $EXTENSION_NAME

        if (Test-Path $sourceExtension) {
            # Remover versao antiga
            if (Test-Path $extensionPath) {
                Remove-Item $extensionPath -Recurse -Force
            }

            # Copiar nova versao
            Copy-Item $sourceExtension $extensionPath -Recurse
            Write-ColorOutput "[OK] Extensao instalada" -Color Green
        } else {
            throw "Pasta $EXTENSION_NAME nao encontrada no arquivo baixado"
        }

        # 6. Limpar
        Write-Progress-Custom -Percent 90 -Status "Limpando arquivos temporarios..."
        Remove-Item $zipPath -Force
        Remove-Item $extractPath -Recurse -Force

        # 7. Registrar
        if (-not $SkipRegistration) {
            Write-Progress-Custom -Percent 95 -Status "Registrando no pyRevit..."
            Register-ExtensionPyRevit -ExtensionPath $extensionPath
            Write-ColorOutput "[OK] Extensao registrada no pyRevit" -Color Green
        }

        # 8. Concluido
        Write-Progress-Custom -Percent 100 -Status "Concluido!"

        $action = if ($isUpdate) { "atualizado" } else { "instalado" }

        Write-ColorOutput ""
        Write-ColorOutput "=============================================" -Color Green
        Write-ColorOutput "       INSTALACAO CONCLUIDA!" -Color Green
        Write-ColorOutput "=============================================" -Color Green
        Write-ColorOutput ""
        Write-ColorOutput "PYAMBAR foi $action com sucesso!" -Color White
        Write-ColorOutput "Pasta: $extensionPath" -Color Gray
        Write-ColorOutput ""
        Write-ColorOutput ">>> REINICIE O REVIT para carregar a extensao <<<" -Color Yellow
        Write-ColorOutput ""

    } catch {
        Write-ColorOutput ""
        Write-ColorOutput "[ERRO] $($_.Exception.Message)" -Color Red
        Write-ColorOutput ""
        Write-ColorOutput "Se o problema persistir, tente a instalacao manual:" -Color Yellow
        Write-ColorOutput "1. Baixe: https://github.com/$GITHUB_REPO/archive/refs/heads/$GITHUB_BRANCH.zip" -Color White
        Write-ColorOutput "2. Extraia PYAMBAR.extension para: $InstallPath" -Color White
        Write-ColorOutput "3. Reinicie o Revit" -Color White
        Write-ColorOutput ""
    }
}

# =============================================================================
# EXECUCAO
# =============================================================================

Install-PYAMBAR

# Pausar se nao for silent
if (-not $Silent) {
    Write-Host ""
    Write-Host "Pressione qualquer tecla para sair..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}
