@echo off
REM ---------------------------------------------------
REM Script para rodar o dashboard.py do Streamlit
REM ---------------------------------------------------

REM Vai para a pasta do projeto
cd /d "C:\Users\Windows 10\Documents\Projetos\SIARPO"

REM Ativa o ambiente virtual
call venv\Scripts\activate.bat

REM Verifica se o Streamlit está instalado
python -m pip show streamlit >nul 2>&1
IF ERRORLEVEL 1 (
    echo Streamlit nao encontrado. Instalando...
    python -m pip install streamlit
)

REM Roda o Streamlit usando o Python do venv
python -m streamlit run src\dashboard.py

REM Mantem a janela aberta
pause
