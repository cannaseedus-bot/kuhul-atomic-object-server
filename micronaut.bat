@echo off
setlocal
set "KUHUL_MICRONAUT_ROOT=%~dp0"

if /i "%~1"=="bundle" goto build_bundle
if /i "%~1"=="kso" goto build_kso
if /i "%~1"=="help" goto usage
if not "%~1"=="" goto usage

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0micronaut\stop-before-launch.ps1"
if errorlevel 1 (
  echo Micronaut found an existing process it could not safely stop. No new menu was launched.
  exit /b 1
)

where powershell.exe >nul 2>nul
if not errorlevel 1 (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0micronaut\micronaut-command-menu-wpf.ps1"
  if not errorlevel 1 exit /b 0
  echo WPF command surface could not start. Opening the keyboard menu.
)

echo Micronaut WPF command surface is unavailable. Opening the keyboard menu.
:menu
echo.
echo 1. Daemon chat
echo 2. Bot orchestration
echo 3. FEL SVG replay
echo 4. Build micronaut.bson
echo 5. Build field.kso from neighborhood and attention JSONL
echo 6. Exit
choice /c 123456 /n /m "Select a command: "
if errorlevel 6 exit /b 0
if errorlevel 5 goto build_kso
if errorlevel 4 goto build_bundle
if errorlevel 3 goto replay
if errorlevel 2 goto orchestration
if errorlevel 1 goto chat
goto menu

:chat
powershell.exe -NoExit -NoProfile -ExecutionPolicy Bypass -Command "Import-Module (Join-Path $env:KUHUL_MICRONAUT_ROOT 'bus\Micronaut.CommandBus.psm1'); Invoke-MicronautCommand -Id 'daemon-chat'"
goto menu

:orchestration
powershell.exe -NoExit -NoProfile -ExecutionPolicy Bypass -Command "Import-Module (Join-Path $env:KUHUL_MICRONAUT_ROOT 'bus\Micronaut.CommandBus.psm1'); Invoke-MicronautCommand -Id 'bot-orchestration'"
goto menu

:replay
powershell.exe -NoExit -NoProfile -ExecutionPolicy Bypass -Command "Import-Module (Join-Path $env:KUHUL_MICRONAUT_ROOT 'bus\Micronaut.CommandBus.psm1'); Invoke-MicronautCommand -Id 'fel-svg-replay'"
goto menu

:build_bundle
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Micronaut.ps1" Bundle
exit /b %errorlevel%

:build_kso
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Micronaut.ps1" Package -InputPath "neighborhood.jsonl" -OutputPath "field.kso" -All
exit /b %errorlevel%

:usage
echo Usage: micronaut.bat [bundle^|kso^|help]
echo   bundle  Rebuild micronaut.bson
echo   kso     Convert neighborhood.jsonl plus neighborhood.attention.jsonl to field.kso
exit /b 2
