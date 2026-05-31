#!/bin/bash
# Incident Response Agent — one-click startup for macOS
# Run from the project root: ./start.sh

PROJECT="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "  Incident Response Agent"
echo "  ========================"
echo ""

# ── Backend ──────────────────────────────────────────────────────────
echo "  Starting backend  (http://localhost:8000) ..."
osascript -e "tell app \"Terminal\" to do script \"cd '$PROJECT' && source .venv/bin/activate && uvicorn backend.api.main:api --reload --port 8000\""

sleep 1

# ── Frontend ─────────────────────────────────────────────────────────
echo "  Starting frontend (http://localhost:5173) ..."
osascript -e "tell app \"Terminal\" to do script \"cd '$PROJECT/frontend' && npm run dev\""

echo ""
echo "  Both servers starting. Open http://localhost:5173 in your browser."
echo "  Close the two Terminal windows to stop."
echo ""
