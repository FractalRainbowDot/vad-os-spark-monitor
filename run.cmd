@echo off
rem Launch VAD-OS Spark Monitor straight from this checkout.
rem Use "run.cmd --save-key" once to store the LiteLLM key.
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
exit /b %errorlevel%
