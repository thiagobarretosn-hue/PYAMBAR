@echo off
setlocal enabledelayedexpansion
title PYAMBAR Installer

:: =============================================================================
:: PYAMBAR Installer - Batch Script (CMD)
:: Alternativa ao PowerShell para usuarios sem permissao de execucao de scripts
::
:: REQUISITOS: Windows 10 versao 1803 ou superior (curl e tar nativos)
::
:: VERSAO: 1.0.0
:: AUTOR: Thiago Barreto Sobral Nunes
:: =============================================================================

:: Configuracao
set GITHUB_REPO=thiagobarretosn-hue/PYAMBAR
set GITHUB_BRANCH=main
set EXTENSION_NAME=PYAMBAR.extension
set INSTALL_PATH=%APPDATA%\pyRevit-Master\Extensions
set EXTENSION_PATH=%INSTALL_PATH%\%EXTENSION_NAME%
set TEMP_ZIP=%TEMP%\pyambar_download.zip
set TEMP_EXTRACT=%TEMP%\pyambar_extract

:: Banner
echo.
echo =============================================
echo        PYAMBAR Installer
echo      Extensao pyRevit para BIM e MEP
echo =============================================
echo.
echo Pasta de instalacao: %INSTALL_PATH%
echo.

:: Verificar Windows 10 1803+ (curl nativo)
curl --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] curl nao encontrado.
    echo        Obrigatorio: Windows 10 versao 1803 ou superior.
    echo.
    echo        Alternativa: use o instalador .exe ou o script PowerShell.
    goto :fim_erro
)

:: Verificar tar nativo
tar --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] tar nao encontrado.
    echo        Obrigatorio: Windows 10 versao 1803 ou superior.
    goto :fim_erro
)

:: Verificar pyRevit instalado
set PYREVIT_CONFIG=%APPDATA%\pyRevit\pyRevit_config.ini
set PYREVIT_CLI=
if exist "C:\Program Files\pyRevit-Master\bin\pyrevit.exe" set PYREVIT_CLI=C:\Program Files\pyRevit-Master\bin\pyrevit.exe
if exist "C:\Program Files\pyRevit\bin\pyrevit.exe"        set PYREVIT_CLI=C:\Program Files\pyRevit\bin\pyrevit.exe
if exist "%APPDATA%\pyRevit-Master\bin\pyrevit.exe"         set PYREVIT_CLI=%APPDATA%\pyRevit-Master\bin\pyrevit.exe

if exist "%PYREVIT_CONFIG%" (
    echo [OK] pyRevit detectado
) else if not "%PYREVIT_CLI%"=="" (
    echo [OK] pyRevit CLI detectado
) else (
    echo [!] pyRevit nao encontrado - instale primeiro em pyrevitlabs.io
)
echo.

:: Mostrar versao instalada se existir
if exist "%EXTENSION_PATH%\extension.json" (
    echo Situacao: Atualizacao detectada
) else (
    echo Situacao: Primeira instalacao
)
echo.

:: Confirmacao do usuario
set /p CONFIRM=Deseja continuar com a instalacao? [S/n]:
if /i "!CONFIRM!"=="n" goto :cancelado
if /i "!CONFIRM!"=="nao" goto :cancelado
echo.

:: -----------------------------------------------------------------------
:: PASSO 1 - Preparar pasta
:: -----------------------------------------------------------------------
echo [1/5] Preparando pasta de instalacao...
if not exist "%INSTALL_PATH%" (
    mkdir "%INSTALL_PATH%"
    if %errorlevel% neq 0 (
        echo [ERRO] Nao foi possivel criar a pasta: %INSTALL_PATH%
        goto :fim_erro
    )
)
echo       OK

:: -----------------------------------------------------------------------
:: PASSO 2 - Backup (se for atualizacao)
:: -----------------------------------------------------------------------
echo [2/5] Verificando backup...
if exist "%EXTENSION_PATH%" (
    set BACKUP_PATH=%EXTENSION_PATH%_backup
    if exist "!BACKUP_PATH!" rmdir /s /q "!BACKUP_PATH!"
    xcopy "%EXTENSION_PATH%" "!BACKUP_PATH!\" /E /I /Q >nul 2>&1
    echo       Backup criado em: !BACKUP_PATH!
) else (
    echo       Sem backup necessario ^(primeira instalacao^)
)

:: -----------------------------------------------------------------------
:: PASSO 3 - Download do GitHub
:: -----------------------------------------------------------------------
echo [3/5] Baixando do GitHub...
set DOWNLOAD_URL=https://github.com/%GITHUB_REPO%/archive/refs/heads/%GITHUB_BRANCH%.zip
echo       URL: %DOWNLOAD_URL%

if exist "%TEMP_ZIP%" del /q "%TEMP_ZIP%"
curl -L -o "%TEMP_ZIP%" "%DOWNLOAD_URL%" --progress-bar 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Falha no download. Verifique sua conexao com a internet.
    goto :fim_erro
)
echo       Download concluido.

:: -----------------------------------------------------------------------
:: PASSO 4 - Extrair e instalar
:: -----------------------------------------------------------------------
echo [4/5] Extraindo e instalando...
if exist "%TEMP_EXTRACT%" rmdir /s /q "%TEMP_EXTRACT%"
mkdir "%TEMP_EXTRACT%"

tar -xf "%TEMP_ZIP%" -C "%TEMP_EXTRACT%" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao extrair o arquivo ZIP.
    goto :fim_erro
)

:: Encontrar pasta do repositorio extraido (ex: PYAMBAR-main)
set REPO_DIR=
for /d %%D in ("%TEMP_EXTRACT%\*") do (
    if not defined REPO_DIR set REPO_DIR=%%D
)

if not defined REPO_DIR (
    echo [ERRO] Pasta do repositorio nao encontrada apos extracao.
    goto :fim_erro
)

set SOURCE_EXT=%REPO_DIR%\%EXTENSION_NAME%
if not exist "%SOURCE_EXT%" (
    echo [ERRO] %EXTENSION_NAME% nao encontrada no arquivo baixado.
    goto :fim_erro
)

:: Remover versao antiga e instalar nova
if exist "%EXTENSION_PATH%" rmdir /s /q "%EXTENSION_PATH%"
xcopy "%SOURCE_EXT%" "%EXTENSION_PATH%\" /E /I /Q >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao copiar os arquivos da extensao.
    goto :fim_erro
)

:: Limpar temporarios
del /q "%TEMP_ZIP%" >nul 2>&1
rmdir /s /q "%TEMP_EXTRACT%" >nul 2>&1
echo       Extensao instalada com sucesso.

:: -----------------------------------------------------------------------
:: PASSO 5 - Registrar no pyRevit
:: -----------------------------------------------------------------------
echo [5/5] Registrando no pyRevit...

:: Tenta via CLI primeiro
if not "%PYREVIT_CLI%"=="" (
    "%PYREVIT_CLI%" extensions paths add "%INSTALL_PATH%" >nul 2>&1
    echo       Registrado via pyRevit CLI.
    goto :concluido
)

:: Fallback: editar pyRevit_config.ini diretamente com Python (se disponivel)
py --version >nul 2>&1
if %errorlevel% equ 0 (
    py -c "
import sys, os, re
cfg = os.path.join(os.environ['APPDATA'], 'pyRevit', 'pyRevit_config.ini')
install_path = r'%INSTALL_PATH%'
if not os.path.exists(cfg): sys.exit(0)
with open(cfg, 'r', encoding='utf-8') as f: content = f.read()
modified = False
m = re.search(r'userextensions\s*=\s*(\[.*?\])', content)
if m:
    import json
    paths = json.loads(m.group(1))
    norm = lambda p: p.lower().replace('\\\\','/')
    if not any(norm(p) == norm(install_path) for p in paths):
        paths.append(install_path)
        content = content[:m.start(1)] + json.dumps(paths) + content[m.end(1):]
        modified = True
section = '[PYAMBAR.extension]'
if section not in content:
    content += '\n' + section + '\ndisabled = false\nprivate_repo = false\nusername = \"\"\npassword = \"\"\n'
    modified = True
if modified:
    with open(cfg, 'w', encoding='utf-8') as f: f.write(content)
    print('Config atualizado.')
" 2>nul
    echo       Registrado via config.ini.
    goto :concluido
)

:: Sem CLI nem Python - instrucoes manuais
echo       [!] Registro automatico nao disponivel.
echo       Para ativar manualmente:
echo         pyRevit ^> Extension Manager ^> Add Folder
echo         Pasta: %INSTALL_PATH%

:: -----------------------------------------------------------------------
:: CONCLUIDO
:: -----------------------------------------------------------------------
:concluido
echo.
echo =============================================
echo        INSTALACAO CONCLUIDA!
echo =============================================
echo.
echo PYAMBAR instalado com sucesso!
echo Pasta: %EXTENSION_PATH%
echo.
echo >>> REINICIE O REVIT para carregar a extensao <<<
echo.
pause
exit /b 0

:cancelado
echo.
echo Instalacao cancelada pelo usuario.
pause
exit /b 0

:fim_erro
echo.
echo Se o problema persistir, instale manualmente:
echo   1. Baixe: https://github.com/%GITHUB_REPO%/archive/refs/heads/%GITHUB_BRANCH%.zip
echo   2. Extraia %EXTENSION_NAME% para: %INSTALL_PATH%
echo   3. Registre no pyRevit Extension Manager
echo   4. Reinicie o Revit
echo.
pause
exit /b 1
