@echo off
echo ==========================================
echo 正在檢查與安裝必要的程式庫，請稍候...
echo ==========================================

:: 1. 確保 pip 是最新的
python -m pip install --upgrade pip

:: 2. 自動安裝 requirements.txt 裡面的套件
python -m pip install -r requirements.txt

echo ==========================================
echo 安裝完成！正在啟動溫室系統...
echo ==========================================

:: 3. 啟動 Streamlit
python -m streamlit run app.py

pause