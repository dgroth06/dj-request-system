@echo off
REM Sync to GitHub Script (Windows)
REM Usage: sync-to-github.bat "Brief description of changes"

if "%~1"=="" (
    echo Error: Please provide a description of your changes
    echo Usage: sync-to-github.bat "Your change description"
    exit /b 1
)

set DESCRIPTION=%~1

echo ================================
echo Syncing to GitHub
echo ================================

REM Show what's changed
echo.
echo Files that will be committed:
git status --short

REM Add all changes
echo.
echo Adding files to git...
git add .

REM Create commit with timestamp and description
for /f "tokens=*" %%a in ('powershell -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss'"') do set TIMESTAMP=%%a

echo.
echo Creating commit...
git commit -m "Update: %DESCRIPTION%" -m "" -m "Timestamp: %TIMESTAMP%" -m "Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

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
echo   git pull origin main
