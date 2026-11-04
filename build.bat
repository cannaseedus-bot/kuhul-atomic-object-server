@echo off
setlocal

set "ROOT=%~dp0"
set "VSROOT=C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools"
set "VCVARS=%VSROOT%\VC\Auxiliary\Build\vcvars64.bat"
set "CMAKE=C:\Program Files\CMake\bin\cmake.exe"
set "BUILD=%ROOT%kuhul\build"
set "EXE=%BUILD%\Release\kuhul_phase_runtime.exe"

if not exist "%VCVARS%" (
  echo ERROR: Visual Studio x64 environment script not found: "%VCVARS%"
  exit /b 1
)
if not exist "%CMAKE%" (
  echo ERROR: CMake not found: "%CMAKE%"
  exit /b 1
)

call "%VCVARS%"
if errorlevel 1 exit /b %errorlevel%

where cl.exe
if errorlevel 1 exit /b 1

"%CMAKE%" -S "%ROOT%kuhul" -B "%BUILD%" -G "Visual Studio 17 2022" -A x64
if errorlevel 1 exit /b %errorlevel%

"%CMAKE%" --build "%BUILD%" --config Release --target kuhul_phase_runtime_cli
if errorlevel 1 exit /b %errorlevel%

"%EXE%" "%ROOT%examples\starter.kbnf" "%ROOT%examples\starter.kgf" "%ROOT%examples\starter.kl"
if errorlevel 1 exit /b %errorlevel%

echo Build and example validation succeeded.
exit /b 0
