@echo off
setlocal
title PYAMBAR MSI Build

echo ========================================
echo  PYAMBAR MSI Build (WiX v6)
echo ========================================
echo.

:: Verificar WiX
wix --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Instalando WiX Toolset...
    dotnet tool install --global wix
    wix extension add WixToolset.UI.wixext/6.0.2
    wix extension add WixToolset.Util.wixext/6.0.2
)

:: Caminhos
set REPO_ROOT=%~dp0..\..
set EXTENSION_SRC=%REPO_ROOT%\PYAMBAR.extension
set WIX_DIR=%~dp0
set DIST_DIR=%WIX_DIR%dist

if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

:: Versao (lida do extension.json)
for /f "tokens=2 delims=:, " %%V in ('findstr "version" "%EXTENSION_SRC%\extension.json"') do (
    set VERSION=%%~V
    goto :version_found
)
set VERSION=2.0.0
:version_found
set VERSION=%VERSION:"=%
echo Versao: %VERSION%
echo.

:: Passo 1: Gerar Files.wxs com script Python
echo [1/3] Gerando Files.wxs...
python "%WIX_DIR%generate_files_wxs.py" "%EXTENSION_SRC%" "%WIX_DIR%Files.wxs"
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao gerar Files.wxs.
    goto :erro
)

:: Passo 2: Atualizar versao no .wxs principal
powershell -Command "(Get-Content '%WIX_DIR%PYAMBAR.wxs') -replace 'Version=""[0-9.]+""', 'Version=""%VERSION%""' | Set-Content '%WIX_DIR%PYAMBAR.wxs'"

:: Passo 3: Build MSI
echo [2/3] Compilando MSI...
wix build "%WIX_DIR%PYAMBAR.wxs" "%WIX_DIR%Files.wxs" ^
    -ext WixToolset.UI.wixext ^
    -ext WixToolset.Util.wixext ^
    -o "%DIST_DIR%\PYAMBAR_Installer.msi"
if %errorlevel% neq 0 (
    echo [ERRO] Falha no build.
    goto :erro
)

:: Passo 4: Copiar para releases
echo [3/3] Copiando para releases...
if not exist "%REPO_ROOT%\releases" mkdir "%REPO_ROOT%\releases"
copy "%DIST_DIR%\PYAMBAR_Installer.msi" "%REPO_ROOT%\releases\" /Y >nul

echo.
echo ========================================
echo  BUILD CONCLUIDO!
echo  MSI: %DIST_DIR%\PYAMBAR_Installer.msi
echo ========================================
echo.
pause
exit /b 0

:erro
echo.
echo [FALHOU] Verifique os erros acima.
pause
exit /b 1
