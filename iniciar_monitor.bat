@echo off
title Monitor ANA Meia Ponte
color 0B

echo ===================================================
echo     INICIANDO O SISTEMA DE MONITORAMENTO ANA
echo ===================================================
echo.

echo [1] Ligando o Servidor Python (Backend)...
start cmd /k "cd /d "%~dp0" && uvicorn main:app --reload"

echo [2] Ligando a Interface Visual (Frontend)...
start cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo Aguardando 3 segundos para os servidores ligarem...
timeout /t 3 /nobreak >nul

echo [3] Abrindo o Painel no Navegador...
start http://localhost:5173

echo.
echo Tudo pronto! Voce ja pode fechar esta janelinha preta.
timeout /t 5 >nul
exit
