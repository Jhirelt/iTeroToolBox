@echo off
echo.
echo  iTero Support Toolbox - Building V1.2.2
echo  =======================================
echo.

echo [1/4] Installing dependencies from requirements.txt...
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ERROR: Failed to install one or more requirements.txt packages
    pause
    exit /b 1
)

echo [2/4] Verifying pyinstaller...
python -c "import PyInstaller; print('PyInstaller OK:', PyInstaller.__version__)"
if errorlevel 1 (
    echo ERROR: PyInstaller not installed correctly
    pause
    exit /b 1
)

echo [3/4] Building executable...
REM --onefile bundles Python itself plus every dependency below into the
REM exe, so the target PC needs nothing pre-installed (no Python, no pip
REM packages) — it just runs. --collect-all is used (not just
REM --hidden-import) for selenium/openpyxl/Pillow because those three ship
REM extra non-.py data (selenium's bundled Selenium Manager binary,
REM openpyxl's chart XML templates, Pillow's image codec plugins) that a
REM plain hidden-import wouldn't pull in — missing any of it would only
REM surface at runtime on the *other* PC, not here at build time.
REM pywebview's PyInstaller hook conservatively bundles every GUI backend
REM it could possibly use (Qt, GTK...) since it can't tell ahead of time
REM which one gui= will pick at runtime. This app always passes
REM gui="edgechromium" (WebView2, the only backend that makes sense on
REM Windows), so the others are excluded — this alone cuts tens of MB of
REM dead weight (PyQt5 etc.) out of the exe.
python -c "import PyInstaller.__main__; PyInstaller.__main__.run(['--onefile','--windowed','--name','iTero_Toolbox_V1_2_2','--icon','Reference\iterologo2.ico','--add-data','itero_toolbox_v1.html;.','--add-data','data;data','--add-data','Reference;Reference','--add-data','Catalog;Catalog','--hidden-import','webview','--hidden-import','win32api','--hidden-import','win32con','--hidden-import','win32crypt','--hidden-import','winreg','--hidden-import','psutil','--collect-all','selenium','--collect-all','openpyxl','--collect-all','PIL','--exclude-module','PyQt5','--exclude-module','PyQt6','--exclude-module','PySide2','--exclude-module','PySide6','--exclude-module','gi','itero_toolbox.py'])"

echo [4/4] Checking output...
if exist "dist\iTero_Toolbox_V1_2_2.exe" (
    echo.
    echo  BUILD COMPLETE
    echo  Output: dist\iTero_Toolbox_V1_2_2.exe
    echo  This single exe is self-contained — copy it anywhere and run it,
    echo  no Python or pip install needed on the target PC.
    echo.
) else (
    echo.
    echo  BUILD FAILED - check output above
    echo.
)
pause
