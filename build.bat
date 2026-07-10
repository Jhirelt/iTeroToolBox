@echo off
echo.
echo  iTero Support Toolbox - Building V1.1
echo  =======================================
echo.

echo [1/4] Installing dependencies...
python -m pip install pywebview==4.4.1 pywin32 psutil pyinstaller --quiet

echo [2/4] Verifying pyinstaller...
python -c "import PyInstaller; print('PyInstaller OK:', PyInstaller.__version__)"
if errorlevel 1 (
    echo ERROR: PyInstaller not installed correctly
    pause
    exit /b 1
)

echo [3/4] Building executable...
python -c "import PyInstaller.__main__; PyInstaller.__main__.run(['--onefile','--windowed','--name','iTero_Toolbox_V1_1','--add-data','itero_toolbox_v1.html;.','--add-data','data\kb_data.json;data','--add-data','Reference;Reference','--hidden-import','webview','--hidden-import','win32api','--hidden-import','win32con','--hidden-import','winreg','--hidden-import','psutil','itero_toolbox.py'])"

echo [4/4] Checking output...
if exist "dist\iTero_Toolbox_V1_1.exe" (
    copy "itero_toolbox_v1.html" "dist\" >nul 2>&1
    echo.
    echo  BUILD COMPLETE
    echo  Output: dist\iTero_Toolbox_V1_1.exe
    echo.
) else (
    echo.
    echo  BUILD FAILED - check output above
    echo.
)
pause
