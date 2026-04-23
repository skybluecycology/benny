@echo off
echo Starting Benny Development Environment...

echo [1/3] Starting Docker infrastructure (Marquez, Phoenix, Neo4j)...
docker-compose up -d

echo [2/3] Starting Backend API Server...
start "Benny Backend API" cmd /k "uvicorn benny.api.server:app --reload --host 0.0.0.0 --port 8005"

echo [3/3] Starting Frontend Development Server...
start "Benny Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo ========================================================
echo Benny has been started!
echo ========================================================
echo - API Server:        http://localhost:8005
echo - API Docs:          http://localhost:8005/docs
echo - Marquez Lineage:   http://localhost:3010
echo - Phoenix Tracing:   http://localhost:6006
echo - Neo4j Studio:      http://localhost:7474
echo.
echo Note: If frontend isn't installed yet, run 'npm install' in the frontend folder.
echo ========================================================
