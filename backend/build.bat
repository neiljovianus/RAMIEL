@echo off
echo ==========================================
echo Building RAMIEL AI (EXE)
echo ==========================================

echo.
echo 1. Activating Anaconda environment (ramiel)...
call "D:\Programs\VS Code\Anaconda\Scripts\activate.bat" "D:\Programs\VS Code\Anaconda\envs\ramiel"

echo.
echo 2. Checking PyInstaller availability...
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo PyInstaller not found. Installing...
    pip install pyinstaller
)

echo.
echo 3. Running PyInstaller (bundling backend + frontend)...
pyinstaller --noconfirm --onefile --console --name "RAMIEL_AI" --add-data "../frontend;frontend" main.py

echo.
echo 4. Moving EXE to current folder (backend)...
move /Y "dist\RAMIEL_AI.exe" ".\RAMIEL_AI.exe"

echo.
echo 5. Cleaning up build artifacts...
rmdir /S /Q dist
rmdir /S /Q build
del /Q RAMIEL_AI.spec

echo.
echo ==========================================
echo BUILD COMPLETE!
echo.
echo RAMIEL_AI.exe is ready.
echo Make sure "config.txt" is in the same folder as the EXE.
echo ==========================================
pause
