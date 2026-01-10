@echo off
setlocal enabledelayedexpansion
REM Sync to GitHub Script (Windows)
REM Usage: sync-to-github.bat [optional description]
REM If no description provided, will auto-generate from changes

set "DESCRIPTION=%~1"

echo ================================
echo Syncing to GitHub
echo ================================

REM Add all changes first
git add .

REM Show what's changed
echo.
echo Files that will be committed:
git status --short

REM Generate description if not provided
if not defined DESCRIPTION (
    echo.
    echo Auto-generating commit description...
    for /f "delims=" %%i in ('git diff --cached --name-only') do (
        if not defined CHANGED_FILES (
            set "CHANGED_FILES=%%~nxi"
        ) else (
            set "CHANGED_FILES=!CHANGED_FILES!, %%~nxi"
        )
    )
    set "DESCRIPTION=Updated files: !CHANGED_FILES!"
)

REM Create commit with timestamp and description
for /f "tokens=*" %%a in ('powershell -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss'"') do set TIMESTAMP=%%a

echo.
echo Commit message: !DESCRIPTION!
echo.
echo Creating commit...
git commit -m "Update: !DESCRIPTION!" -m "" -m "Timestamp: %TIMESTAMP%" -m "Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

if errorlevel 1 (
    echo.
    echo No changes to commit.
    exit /b 0
)

REM Push to GitHub
echo.
echo Pushing to GitHub...
git push origin main

echo.
echo ================================
echo Successfully synced to GitHub
echo ================================
echo.
echo Your Raspberry Pi can now pull the latest version with:
echo   cd ~/dj-request-system
echo   git pull origin main
