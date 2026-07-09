@echo off
echo ===================================================
echo   VendorPulse - Accounts Payable Automation Platform
echo ===================================================
echo.

echo [1/2] Starting FastAPI Backend on http://127.0.0.1:8000 ...
start "VendorPulse Backend" cmd /k "python Backend/main.py"

echo [2/2] Starting React Dev Server on http://localhost:5173 ...
start "VendorPulse Frontend" cmd /k "cd Frontend && npm run dev"

echo.
echo ===================================================
echo   All systems launching in separate windows!
echo   - Backend: http://127.0.0.1:8000/docs
echo   - Frontend: http://localhost:5173
echo ===================================================
echo.
pause
