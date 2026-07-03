# Research Notes System - Quick Start Guide

## What's New?
You now have a **PostgreSQL-backed research notes system** integrated with your Scalable Brain project. Store, edit, and manage your research, strategies, and analysis persistently.

## Prerequisites
✓ PostgreSQL running on localhost:5432
✓ Python 3.8+
✓ Your .env file has database credentials (ForexBrainDB)

## Getting Started in 3 Steps

### Step 1: Start the API Backend
```bash
bash shell/setup_research_api.sh
```

This script will:
- Create/verify Python virtual environment
- Install dependencies (Flask, psycopg2, flask-cors)
- Test PostgreSQL connection
- Start the Flask API server on `http://localhost:5001`

**Expected output:**
```
✓ Virtual environment ready
✓ Dependencies installed
✓ PostgreSQL connection successful
✓ research_notes table already exists
────────────────────────────────────────
 * Running on http://localhost:5001
```

### Step 2: Open the Research Notes UI
Once the API is running, navigate to:
```
http://localhost/scalable-brain/frontend/research.html
```

Or open file directly:
```
/home/emmanuel/Documents/Scalable_Brain/scalable-brain/frontend/research.html
```

### Step 3: Start Using
1. **Create a Note:** Click "New Research Note" button
2. **Choose Category:** Strategy, Analysis, Research, Planning, or Note
3. **Write Content:** Use the editor to document your thoughts
4. **Save:** Click Save - it goes directly to PostgreSQL
5. **Manage:** Edit, delete, search, and filter your notes

## Features

### Categories
- 📋 **Strategy** - Trading strategy ideas and rules
- 📊 **Analysis** - Market analysis and observations  
- 🔍 **Research** - Indicator research and backtesting
- 📝 **Planning** - Implementation and development plans
- 📌 **Note** - General notes and references

### Dashboard
- **Total Notes:** See how many notes you've created
- **By Category:** Breakdown of notes by type
- **Last Updated:** Timestamp of most recent change
- **Search:** Filter notes by keyword
- **Quick Filter:** Select category to view only those notes

### Data Persistence
- ✓ Notes saved to PostgreSQL (not browser memory)
- ✓ Accessible from any device on your network
- ✓ Full version history with created/modified timestamps
- ✓ No data loss on browser clear or app restart

## API Endpoints (for advanced users)

The backend provides REST API at `http://localhost:5001`:

```
GET    /api/notes              # Fetch all notes
POST   /api/notes              # Create new note
PUT    /api/notes/{id}         # Update note
DELETE /api/notes/{id}         # Delete note
GET    /api/stats              # Get statistics
GET    /api/health             # Check API status
```

## Troubleshooting

**Issue: "Failed to connect to API"**
- Check if Flask server is running: `curl http://localhost:5001/api/health`
- Verify PostgreSQL is running: `psql -U sa -d ForexBrainDB`
- Check firewall: port 5001 should be accessible

**Issue: "Database error" in notes UI**
- Restart the API backend script
- Check PostgreSQL connection credentials in .env file
- Verify research_notes table exists in ForexBrainDB

**Issue: Notes not saving**
- Open browser developer console (F12)
- Check Network tab for failed API requests
- Look for error messages in Flask console output

## Architecture

```
User Browser
     ↓
research.html (Fetch API)
     ↓
Flask Backend (localhost:5001)
     ↓
PostgreSQL (ForexBrainDB.research_notes)
```

## Files Modified/Created

- ✅ `frontend/research.html` - Updated UI with PostgreSQL integration
- ✅ `src/research_notes_api.py` - Flask backend (new)
- ✅ `shell/setup_research_api.sh` - Automated setup (new)
- ✅ `docs/RESEARCH_NOTES_POSTGRESQL.md` - Full technical docs
- ✅ `index.html` - Updated with Layer 4-5 status

## Next Steps

1. **Run the setup script** and start the API
2. **Test the UI** by creating a few sample notes
3. **Bookmark the research.html page** for quick access
4. (Optional) Set up a systemd service or cron job to auto-start the API on server restart

For detailed technical documentation, see: `docs/RESEARCH_NOTES_POSTGRESQL.md`

---

**Last Updated:** May 7, 2026  
**Status:** Production Ready ✓  
**Database:** PostgreSQL (ForexBrainDB)  
**API:** Flask 2.3+
