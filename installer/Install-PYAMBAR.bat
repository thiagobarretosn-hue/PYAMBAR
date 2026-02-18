@echo off
setlocal enabledelayedexpansion
title PYAMBAR Installer

:: =============================================================================
:: PYAMBAR Installer - Batch Script (CMD)
:: Alternativa ao PowerShell para usuarios sem permissao de execucao de scripts
::
:: REQUISITOS: Windows 10 versao 1803 ou superior (curl e tar nativos)
::
:: VERSAO: 1.1.0
:: AUTOR: Thiago Barreto Sobral Nunes
:: =============================================================================

:: Configuracao
set GITHUB_REPO=thiagobarretosn-hue/PYAMBAR
set GITHUB_BRANCH=main
set EXTENSION_NAME=PYAMBAR.extension
set INSTALL_PATH=%APPDATA%\pyRevit\Extensions
set EXTENSION_PATH=%INSTALL_PATH%\%EXTENSION_NAME%
set TEMP_ZIP=%TEMP%\pyambar_download.zip
set TEMP_EXTRACT=%TEMP%\pyambar_extract

:: Localizar pyRevit
set PYREVIT_CONFIG=%APPDATA%\pyRevit\pyRevit_config.ini
set PYREVIT_CLI=
if exist "C:\Program Files\pyRevit-Master\bin\pyrevit.exe" set PYREVIT_CLI=C:\Program Files\pyRevit-Master\bin\pyrevit.exe
if exist "C:\Program Files\pyRevit\bin\pyrevit.exe"        set PYREVIT_CLI=C:\Program Files\pyRevit\bin\pyrevit.exe
if exist "%APPDATA%\pyRevit-Master\bin\pyrevit.exe"        set PYREVIT_CLI=%APPDATA%\pyRevit-Master\bin\pyrevit.exe

:: -----------------------------------------------------------------------
:: MENU PRINCIPAL
:: -----------------------------------------------------------------------
:menu
cls
echo.
echo =============================================
echo        PYAMBAR - Gerenciador
echo      Extensao pyRevit para BIM e MEP
echo =============================================
echo.

if exist "%EXTENSION_PATH%\extension.json" (
    echo  Status: INSTALADO
    echo  Pasta:  %EXTENSION_PATH%
) else (
    echo  Status: NAO INSTALADO
)
echo.
echo  [1] Instalar / Atualizar
echo  [2] Desinstalar
echo  [3] Sair
echo.
set /p OPCAO= Escolha uma opcao:

if "!OPCAO!"=="1" goto :instalar
if "!OPCAO!"=="2" goto :desinstalar
if "!OPCAO!"=="3" goto :sair
echo  Opcao invalida.
timeout /t 1 >nul
goto :menu

:: -----------------------------------------------------------------------
:: INSTALAR / ATUALIZAR
:: -----------------------------------------------------------------------
:instalar
echo.
echo =============================================
echo        INSTALAR / ATUALIZAR
echo =============================================
echo.

:: Verificar Windows 10 1803+
curl --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] curl nao encontrado. Obrigatorio: Windows 10 versao 1803+.
    goto :fim_erro
)
tar --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] tar nao encontrado. Obrigatorio: Windows 10 versao 1803+.
    goto :fim_erro
)

:: Status
if exist "%EXTENSION_PATH%\extension.json" (
    echo  Situacao: Atualizacao
) else (
    echo  Situacao: Primeira instalacao
)
echo  Destino:  %INSTALL_PATH%
echo.

set /p CONFIRM= Deseja continuar? [S/n]:
if /i "!CONFIRM!"=="n"   goto :menu
if /i "!CONFIRM!"=="nao" goto :menu
echo.

:: Passo 1 - Pasta
echo [1/5] Preparando pasta...
if not exist "%INSTALL_PATH%" (
    mkdir "%INSTALL_PATH%"
    if %errorlevel% neq 0 (
        echo [ERRO] Nao foi possivel criar: %INSTALL_PATH%
        goto :fim_erro
    )
)
echo       OK

:: Passo 2 - Backup
echo [2/5] Backup...
if exist "%EXTENSION_PATH%" (
    set BACKUP_PATH=%EXTENSION_PATH%_backup
    if exist "!BACKUP_PATH!" rmdir /s /q "!BACKUP_PATH!"
    xcopy "%EXTENSION_PATH%" "!BACKUP_PATH!\" /E /I /Q >nul 2>&1
    echo       Backup criado em: !BACKUP_PATH!
) else (
    echo       Sem backup necessario
)

:: Passo 3 - Download
echo [3/5] Baixando do GitHub...
if exist "%TEMP_ZIP%" del /q "%TEMP_ZIP%"
curl -L -o "%TEMP_ZIP%" "https://github.com/%GITHUB_REPO%/archive/refs/heads/%GITHUB_BRANCH%.zip" --progress-bar 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Falha no download. Verifique sua conexao.
    goto :fim_erro
)
echo       Concluido.

:: Passo 4 - Extrair e instalar
echo [4/5] Instalando...
if exist "%TEMP_EXTRACT%" rmdir /s /q "%TEMP_EXTRACT%"
mkdir "%TEMP_EXTRACT%"
tar -xf "%TEMP_ZIP%" -C "%TEMP_EXTRACT%" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao extrair o ZIP.
    goto :fim_erro
)

set REPO_DIR=
for /d %%D in ("%TEMP_EXTRACT%\*") do if not defined REPO_DIR set REPO_DIR=%%D

if not defined REPO_DIR (
    echo [ERRO] Pasta do repositorio nao encontrada.
    goto :fim_erro
)
if not exist "%REPO_DIR%\%EXTENSION_NAME%" (
    echo [ERRO] %EXTENSION_NAME% nao encontrada no ZIP.
    goto :fim_erro
)

if exist "%EXTENSION_PATH%" rmdir /s /q "%EXTENSION_PATH%"
xcopy "%REPO_DIR%\%EXTENSION_NAME%" "%EXTENSION_PATH%\" /E /I /Q >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao copiar arquivos.
    goto :fim_erro
)

del /q "%TEMP_ZIP%" >nul 2>&1
rmdir /s /q "%TEMP_EXTRACT%" >nul 2>&1
echo       Instalado.

:: Passo 5 - Registrar
echo [5/5] Registrando no pyRevit...
if not "%PYREVIT_CLI%"=="" (
    "%PYREVIT_CLI%" extensions paths add "%INSTALL_PATH%" >nul 2>&1
    echo       Registrado via pyRevit CLI.
    goto :install_ok
)

py --version >nul 2>&1
if %errorlevel% equ 0 (
    py -c "
import sys, os, re, json
cfg = os.path.join(os.environ['APPDATA'], 'pyRevit', 'pyRevit_config.ini')
install_path = r'%INSTALL_PATH%'
if not os.path.exists(cfg): sys.exit(0)
with open(cfg, 'r', encoding='utf-8') as f: content = f.read()
modified = False
m = re.search(r'userextensions\s*=\s*(\[.*?\])', content)
if m:
    paths = json.loads(m.group(1))
    norm = lambda p: p.lower().replace(chr(92),'/')
    if not any(norm(p) == norm(install_path) for p in paths):
        paths.append(install_path)
        content = content[:m.start(1)] + json.dumps(paths) + content[m.end(1):]
        modified = True
section = '[PYAMBAR.extension]'
if section not in content:
    content += chr(10) + section + chr(10) + 'disabled = false' + chr(10) + 'private_repo = false' + chr(10) + 'username = \"\"' + chr(10) + 'password = \"\"' + chr(10)
    modified = True
if modified:
    with open(cfg, 'w', encoding='utf-8') as f: f.write(content)
" 2>nul
    echo       Registrado via config.ini.
    goto :install_ok
)

echo       [!] Registro automatico indisponivel.
echo           Ative manualmente: pyRevit ^> Extension Manager ^> Add Folder
echo           Pasta: %INSTALL_PATH%

:install_ok
echo.
echo =============================================
echo        INSTALACAO CONCLUIDA!
echo =============================================
echo.
echo PYAMBAR instalado com sucesso!
echo.
echo >>> REINICIE O REVIT para carregar a extensao <<<
echo.
pause
goto :menu

:: -----------------------------------------------------------------------
:: DESINSTALAR
:: -----------------------------------------------------------------------
:desinstalar
echo.
echo =============================================
echo        DESINSTALAR
echo =============================================
echo.

if not exist "%EXTENSION_PATH%" (
    echo  PYAMBAR nao esta instalado neste computador.
    echo.
    pause
    goto :menu
)

echo  Sera removido: %EXTENSION_PATH%
echo.
set /p CONFIRM= Tem certeza que deseja desinstalar? [s/N]:
if /i "!CONFIRM!"=="s"   goto :fazer_desinstalar
if /i "!CONFIRM!"=="sim" goto :fazer_desinstalar
echo  Desinstalacao cancelada.
pause
goto :menu

:fazer_desinstalar
echo.

:: Remover pasta da extensao
echo [1/2] Removendo arquivos...
rmdir /s /q "%EXTENSION_PATH%"
if %errorlevel% neq 0 (
    echo [ERRO] Nao foi possivel remover: %EXTENSION_PATH%
    echo        O Revit pode estar aberto. Feche o Revit e tente novamente.
    pause
    goto :menu
)
echo       Arquivos removidos.

:: Desregistrar do pyRevit
echo [2/2] Desregistrando do pyRevit...
if not "%PYREVIT_CLI%"=="" (
    "%PYREVIT_CLI%" extensions paths remove "%INSTALL_PATH%" >nul 2>&1
    echo       Desregistrado via pyRevit CLI.
    goto :desinstalar_ok
)

py --version >nul 2>&1
if %errorlevel% equ 0 (
    py -c "
import sys, os, re, json
cfg = os.path.join(os.environ['APPDATA'], 'pyRevit', 'pyRevit_config.ini')
install_path = r'%INSTALL_PATH%'
if not os.path.exists(cfg): sys.exit(0)
with open(cfg, 'r', encoding='utf-8') as f: content = f.read()
modified = False
m = re.search(r'userextensions\s*=\s*(\[.*?\])', content)
if m:
    paths = json.loads(m.group(1))
    norm = lambda p: p.lower().replace(chr(92),'/')
    new_paths = [p for p in paths if norm(p) != norm(install_path)]
    if len(new_paths) != len(paths):
        content = content[:m.start(1)] + json.dumps(new_paths) + content[m.end(1):]
        modified = True
section = '[PYAMBAR.extension]'
if section in content:
    content = re.sub(r'\[PYAMBAR\.extension\][^\[]*', '', content)
    modified = True
if modified:
    with open(cfg, 'w', encoding='utf-8') as f: f.write(content)
" 2>nul
    echo       Desregistrado via config.ini.
    goto :desinstalar_ok
)

echo       [!] Remova manualmente do pyRevit Extension Manager se necessario.

:desinstalar_ok
echo.
echo =============================================
echo        DESINSTALACAO CONCLUIDA!
echo =============================================
echo.
echo PYAMBAR foi removido com sucesso.
echo.
echo >>> REINICIE O REVIT para aplicar a remocao <<<
echo.
pause
goto :menu

:: -----------------------------------------------------------------------
:: COMPARTILHADOS
:: -----------------------------------------------------------------------
:fim_erro
echo.
echo Instalacao manual:
echo   1. Baixe: https://github.com/%GITHUB_REPO%/archive/refs/heads/%GITHUB_BRANCH%.zip
echo   2. Extraia %EXTENSION_NAME% para: %INSTALL_PATH%
echo   3. Registre no pyRevit Extension Manager
echo   4. Reinicie o Revit
echo.
pause
goto :menu

:sair
exit /b 0
