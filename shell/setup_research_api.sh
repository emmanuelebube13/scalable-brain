#!/bin/bash

# Quick Setup Guide for PostgreSQL Research Notes

echo "================================"
echo "Research Notes Setup"
echo "================================"
echo ""

# Change to project directory
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain

echo "1️⃣  Checking virtual environment..."
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found"
    echo "Creating .venv..."
    python3 -m venv .venv
fi

echo "✓ Virtual environment ready"
echo ""

echo "2️⃣  Installing dependencies..."
source .venv/bin/activate
pip install flask flask-cors psycopg2-binary python-dotenv -q
echo "✓ Dependencies installed"
echo ""

echo "3️⃣  Verifying PostgreSQL connection..."
python3 << 'EOF'
import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

try:
    conn = psycopg2.connect(
        host=os.getenv('DB_SERVER', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        database=os.getenv('DB_NAME', 'ForexBrainDB'),
        user=os.getenv('DB_USER', 'sa'),
        password=os.getenv('DB_PASS', '')
    )
    print("✓ PostgreSQL connection successful")
    
    # Check if research_notes table exists
    cur = conn.cursor()
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables 
            WHERE table_name = 'research_notes'
        )
    """)
    exists = cur.fetchone()[0]
    
    if exists:
        print("✓ research_notes table already exists")
    else:
        print("⏳ Table will be created on first API start")
    
    conn.close()
except Exception as e:
    print(f"❌ Connection failed: {e}")
    exit(1)
EOF

echo ""
echo "4️⃣  Starting Research Notes API..."
echo ""
echo "────────────────────────────────────────"
python src/research_notes_api.py
