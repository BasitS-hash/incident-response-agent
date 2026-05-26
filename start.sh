#!/bin/bash
# Start the full incident response agent stack

echo "Starting Incident Response Agent..."

# Activate venv
source .venv/bin/activate

# Start FastAPI backend in background
echo "[1/2] Starting FastAPI backend on port 8000..."
uvicorn backend.api.main:api --reload --port 8000 &
BACKEND_PID=$!

# Start React frontend
echo "[2/2] Starting React frontend on port 5173..."
cd frontend && npm run dev &
FRONTEND_PID=$!

echo ""
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo "API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both servers."

trap "kill $BACKEND_PID $FRONTEND_PID" EXIT
wait
