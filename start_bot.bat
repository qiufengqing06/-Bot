@echo off
chcp 65001 >nul
title NoneBot Agent

:loop
echo [%date% %time%] Starting Bot...
python bot.py
echo [%date% %time%] Bot exited with code %ERRORLEVEL%, restarting in 3 seconds...
timeout /t 3 /nobreak >nul
goto loop
