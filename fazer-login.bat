@echo off
title Login NotebookLM no Google Chrome
cd /d "F:\ATUAL 2026\Vibe Coding\API NotebookLM"
chcp 65001 > nul
echo ======================================================================
echo Abrindo o Google Chrome para autenticar rodrigo.gois@ifs.edu.br...
echo O Google Chrome vai abrir na sua tela.
echo Faça o login e a credencial será capturada e salva automaticamente.
echo ======================================================================
.\.venv\Scripts\notebooklm.exe login --master-token --browser chrome --account rodrigo.gois@ifs.edu.br
echo.
echo Login finalizado com sucesso!
pause
