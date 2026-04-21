@echo off
echo ========================================
echo  BIM Manager Installer - Build Script
echo ========================================
echo.

:: Verificar se PyInstaller esta instalado
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [INFO] Instalando PyInstaller...
    pip install pyinstaller
)

echo.
echo [BUILD] Criando executavel...
echo.

:: Build com PyInstaller
pyinstaller --onefile ^
    --windowed ^
    --name "BIMManager_Installer" ^
    --icon "icon.ico" ^
    --add-data "icon.ico;." ^
    --clean ^
    pyambar_installer.py

echo.
echo ========================================
if exist "dist\BIMManager_Installer.exe" (
    echo [OK] Build concluido com sucesso!
    echo.
    echo Executavel: dist\BIMManager_Installer.exe
    echo.

    :: Copiar para pasta releases
    if not exist "..\releases" mkdir "..\releases"
    copy "dist\BIMManager_Installer.exe" "..\releases\" /Y
    echo Copiado para: ..\releases\BIMManager_Installer.exe
) else (
    echo [ERRO] Falha no build!
)
echo ========================================
echo.
pause
