@echo off
chcp 65001 >nul
title ClockIn AutoCAD - Controle de Horas por Projeto
cd /d "%~dp0"
echo =================================================================
echo   INICIANDO CLOCKIN AUTOCAD (PAINEL + AUTO-RASTREADOR)
echo   Para ativar o Auto-Rastreador: clique em START na aba
echo   "Auto-Rastreador (CAD)" e confirme para deixa-lo ligado.
echo =================================================================
python server.py
pause
