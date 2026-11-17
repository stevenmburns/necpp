@echo off
rem install-4nec2.cmd: install this nec2++ as 4nec2's NEC-2 engine.
rem
rem   install-4nec2.cmd [4nec2-exe-folder]      (default C:\4nec2\exe)
rem
rem 4nec2 runs nec2dxs500/1K5/3k0/5k0/8k0/11k.exe from its exe folder, chosen
rem by deck size. This backs up any existing nec2dxs*.exe there, then copies
rem the nec2++ exe beside this script (and any DLLs beside it, for the MSVC
rem build) into that folder under all six names. nec2++ reads 4nec2's file
rem names itself (arguments, stdin, or nec2d.tmp); see README.txt.
setlocal enableextensions
set "SRC=%~dp0"
set "DEST=%~1"
if "%DEST%"=="" set "DEST=C:\4nec2\exe"
if not exist "%DEST%\" (
  echo install-4nec2: folder not found: %DEST%
  exit /b 1
)
set "EXE="
for %%F in ("%SRC%nec2++-*.exe") do set "EXE=%%~fF"
if not defined EXE (
  echo install-4nec2: no nec2++-*.exe beside this script
  exit /b 1
)
for /f %%D in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "STAMP=%%D"
if exist "%DEST%\nec2dxs*.exe" (
  mkdir "%DEST%\nec2dxs-backup-%STAMP%" || exit /b 1
  copy /y "%DEST%\nec2dxs*.exe" "%DEST%\nec2dxs-backup-%STAMP%\" >nul || exit /b 1
  echo backed up the existing nec2dxs*.exe to %DEST%\nec2dxs-backup-%STAMP%\
)
for %%N in (nec2dxs500 nec2dxs1K5 nec2dxs3k0 nec2dxs5k0 nec2dxs8k0 nec2dxs11k) do (
  copy /y "%EXE%" "%DEST%\%%N.exe" >nul || exit /b 1
  echo installed %DEST%\%%N.exe
)
for %%F in ("%SRC%*.dll") do (
  copy /y "%%~fF" "%DEST%\" >nul || exit /b 1
  echo copied %%~nxF
)
echo done: 4nec2 now runs %EXE%
exit /b 0
