@echo off
title SEO Brain
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\start.ps1"
if errorlevel 1 pause
