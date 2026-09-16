@echo off
setlocal
cd /d "%~dp0"

rem Tu chon interpreter co du thu vien (cv2 + fitz), khong phu thuoc venv dang bat.
set "PY="
for %%P in (
  "%~dp0..\venv\Scripts\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
  "python"
) do (
  if not defined PY (
    %%P -c "import cv2, fitz" >nul 2>&1 && set "PY=%%~P"
  )
)

if not defined PY (
  echo Khong tim thay Python nao co du thu vien cv2 + pymupdf.
  echo Cai bang:  python -m pip install opencv-python pymupdf
  pause
  exit /b 1
)

echo Dang dung: %PY%
"%PY%" server.py
pause
