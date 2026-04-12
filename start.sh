#!/bin/bash
# Simple start script for Heimdall - Institutional Grade
echo "🛑 Cleaning up port 8000..."
lsof -ti:8000 | xargs kill -9 2>/dev/null

echo "🚀 Starting Heimdall Backend..."
source venv/bin/activate
uvicorn main:app --port 8000 --reload
