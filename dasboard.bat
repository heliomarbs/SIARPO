@echo off
cd /d "C:\Users\Windows 10\Documents\Projetos\SIARPO - FUNCIONANDO"
call venv\Scripts\activate.bat
streamlit run src\dashboard.py
pause
