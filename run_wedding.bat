@echo off
setlocal EnableExtensions EnableDelayedExpansion
rem Giữ nguyên tiếng Việt trong đường dẫn
chcp 65001 >nul

rem ====== CONFIG ======
set "PROJ_DIR=C:\Users\Administrator\Desktop\WEDDING"
set "PY_EXE=C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe"
set "NGROK_EXE=%PROJ_DIR%\ngrok.exe"
set "NGROK_CFG=%PROJ_DIR%\ngrok_wedding.yml"
set "LOG_DIR=%PROJ_DIR%\logs"

set "RETAIN_LOG_DAYS=3"          rem Giữ log 3 ngày
set "CLEAN_INTERVAL_SEC=7200"    rem 2 giờ
set /a CLEAN_PINGS=%CLEAN_INTERVAL_SEC%+1

rem ====== PREP ======
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
cd /d "%PROJ_DIR%"

>>"%LOG_DIR%\service.log" echo [%date% %time%] Booting WEDDING service...

rem ====== Dọn log nền giống app cũ =====
start "" /b cmd /c "for /l %%# in (1,1,9999999) do ( ^
  forfiles /p "%LOG_DIR%" /m *.* /d -%RETAIN_LOG_DAYS% /c "cmd /c del /q @file" >nul 2>&1 ^
  & ping -n %CLEAN_PINGS% 127.0.0.1 >nul ^
)"

rem ====== START FLASK (Wedding.py) ======
>>"%LOG_DIR%\service.log" echo [%date% %time%] Starting Flask (Wedding.py)...
start "" /b cmd /c ""%PY_EXE%" "%PROJ_DIR%\Wedding.py" 1>>"%LOG_DIR%\flask.out" 2>>"%LOG_DIR%\flask.err""

rem Chờ Flask ~15 giây cho chắc (tránh TIMEOUT / 502)
ping -n 16 127.0.0.1 >nul

rem ====== START NGROK (port 5001) ======
if not exist "%NGROK_EXE%" (
  >>"%LOG_DIR%\service.log" echo [%date% %time%] ERROR: ngrok.exe not found at "%NGROK_EXE%"
  exit /b 1
)
>>"%LOG_DIR%\service.log" echo [%date% %time%] Starting ngrok for Wedding...
start "" /b cmd /c ""%NGROK_EXE%" http 127.0.0.1:5001 --config "%NGROK_CFG%" --log=stdout 1>>"%LOG_DIR%\ngrok.log" 2>&1"
>>"%LOG_DIR%\service.log" echo [%date% %time%] ngrok started OK (Wedding).

exit /b 0
