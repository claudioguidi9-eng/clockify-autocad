@echo off
chcp 65001 >nul
title ClockIn AutoCAD - Controle de Horas por Projeto
cd /d "%~dp0"
echo =================================================================
echo   INICIANDO CLOCKIN AUTOCAD (PAINEL + RASTREADOR AUTOMATICO)
echo =================================================================
python server.py
pause
