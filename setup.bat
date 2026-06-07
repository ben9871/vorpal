@echo off
setlocal

echo.
echo =====================================================
echo   vorpal - Windows Setup
echo =====================================================
echo.

:: -- Find a compatible Python (3.10-3.12; kokoro does not support 3.13) --
set PYCMD=
py -3.12 --version >nul 2>&1
if %errorlevel% equ 0 set PYCMD=py -3.12
if not defined PYCMD (
    py -3.11 --version >nul 2>&1
    if %errorlevel% equ 0 set PYCMD=py -3.11
)
if not defined PYCMD (
    py -3.10 --version >nul 2>&1
    if %errorlevel% equ 0 set PYCMD=py -3.10
)
if not defined PYCMD (
    echo ERROR: No compatible Python found. Install Python 3.10-3.12
    echo  - NOT 3.13+, the kokoro TTS engine does not support it yet:
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

:: -- Single canonical venv: .venv311 ------------------
if not exist venv311 (
    echo Creating virtual environment venv311 ...
    %PYCMD% -m venv venv311
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
)

call venv311\Scripts\activate.bat

echo Installing vorpal (editable) and dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)

:: -- External binaries (informational) ----------------
where tesseract >nul 2>&1
if %errorlevel% neq 0 if not exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
    echo.
    echo NOTE: Tesseract OCR not detected.
    echo   Install: https://github.com/UB-Mannheim/tesseract/wiki
)
where ffmpeg >nul 2>&1
if %errorlevel% neq 0 if not exist "C:\ffmpeg\bin\ffmpeg.exe" (
    echo.
    echo NOTE: ffmpeg not detected.
    echo   Install: https://www.gyan.dev/ffmpeg/builds/
)

echo.
echo =====================================================
echo   Setup complete.
echo   Usage:  vorpal build book.pdf
echo =====================================================
pause
