@echo off
setlocal
title RAW LEAKS - Automation Toolkit
cd /d "%~dp0"

rem Keep the banner glyphs intact in legacy cmd.exe.
chcp 65001 >nul 2>nul

where py >nul 2>nul
if not errorlevel 1 goto :py
where python >nul 2>nul
if not errorlevel 1 goto :python

echo [RAW LEAKS] ERROR Python 3 was not found on PATH.
echo             Install it from https://www.python.org/downloads/ and tick
echo             "Add python.exe to PATH", then run this file again.
set "CODE=1"
goto :done

:py
py -3 main.py %*
set "CODE=%ERRORLEVEL%"
goto :done

:python
python main.py %*
set "CODE=%ERRORLEVEL%"

:done
rem Double-clicked? Then keep the window open so the summary stays readable.
echo %cmdcmdline% | find /i "/c" >nul
if not errorlevel 1 pause
exit /b %CODE%
