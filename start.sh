#!/bin/bash
# Simple start script for Heimdall
echo "🚀 Starting Heimdall Backend..."
source venv/bin/activate
uvicorn main:app --port 8000 --reload
