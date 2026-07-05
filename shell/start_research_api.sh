#!/bin/bash

# Research Notes API Startup Script
# Starts the Flask backend for PostgreSQL-backed research notes

set -e

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

echo "================================"
echo "Research Notes API Startup"
echo "================================"
echo ""

# Check if .env exists
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo "❌ Error: .env file not found at $PROJECT_ROOT/.env"
    echo "Please create a .env file with PostgreSQL connection details."
    exit 1
fi

# Activate virtual environment if it exists
VENV_PATH="$PROJECT_ROOT/.venv"
if [ -d "$VENV_PATH" ]; then
    echo "📦 Activating virtual environment..."
    source "$VENV_PATH/bin/activate"
else
    echo "⚠️  Virtual environment not found at $VENV_PATH"
    echo "Please create one: python -m venv $VENV_PATH"
fi

# Check if required packages are installed
echo "🔍 Checking dependencies..."
python -c "import flask, flask_cors, psycopg2" 2>/dev/null || {
    echo "📥 Installing required packages..."
    pip install flask flask-cors psycopg2-binary python-dotenv
}

# Set environment variables
export FLASK_ENV=development
export FLASK_APP=src/research_notes_api.py
export RESEARCH_API_PORT=5001

# Print configuration
echo ""
echo "📋 Configuration:"
echo "  - API Port: $RESEARCH_API_PORT"
echo "  - Environment: $FLASK_ENV"
echo "  - Database: Reading from .env"
echo ""

# Start the API
echo "🚀 Starting Research Notes API..."
echo "📍 API will be available at: http://localhost:$RESEARCH_API_PORT"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

python src/research_notes_api.py
