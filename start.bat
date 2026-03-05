@echo off
echo ============================================
echo  Prediction Market Arbitrage Tool
echo ============================================
echo.

echo Starting Backend (FastAPI)...
start "ArbTool - Backend" cmd /k "cd /d %~dp0backend && python -m uvicorn main:app --reload --port 8000"

echo Waiting for backend to start...
timeout /t 3 /nobreak >nul

echo Starting Frontend (React)...
start "ArbTool - Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ============================================
echo  Backend:  http://localhost:8000
echo  Frontend: http://localhost:5173
echo  API Docs: http://localhost:8000/docs
echo  Health:   http://localhost:8000/health
echo ============================================
echo.
echo Press any key to exit this launcher window...
pause >nul
