# Research Notes System - PostgreSQL Backend

## Overview

Your research notes are now stored in **PostgreSQL** instead of just browser localStorage. This gives you:

✅ **Persistent Storage** - Notes survive browser clear/reset  
✅ **Database Queries** - Search and filter with full SQL capabilities  
✅ **Multi-Device Access** - Access notes from any device on your network  
✅ **Automatic Backups** - LocalStorage backup for offline fallback  
✅ **Categories & Tags** - Organize research by type  
✅ **Pin Important Notes** - Keep critical research at the top  

---

## Quick Start

### 1. Install Dependencies

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Start the API Server

```bash
bash shell/start_research_api.sh
```

Or manually:

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
source .venv/bin/activate
export FLASK_APP=src/research_notes_api.py
export RESEARCH_API_PORT=5001
python src/research_notes_api.py
```

### 3. Access the Research Hub

Open in your browser:
```
http://localhost/frontend/research.html
```

The page will automatically detect and connect to the PostgreSQL backend at `http://localhost:5001/api`

---

## API Endpoints

Base URL: `http://localhost:5001/api`

### Health Check
```
GET /api/health
```
Returns database connection status

### Get All Notes
```
GET /api/notes
```

Optional query parameters:
- `category=strategy` - Filter by category (strategy, analysis, research, planning, note)
- `search=text` - Search in title and content

Example:
```bash
curl "http://localhost:5001/api/notes?category=strategy&search=EMA"
```

### Get Single Note
```
GET /api/notes/{id}
```

### Create Note
```
POST /api/notes
Content-Type: application/json

{
  "title": "My Research Title",
  "category": "strategy",
  "content": "Detailed research content here...",
  "tags": "trend-following,h4"
}
```

### Update Note
```
PUT /api/notes/{id}
Content-Type: application/json

{
  "title": "Updated Title",
  "category": "analysis",
  "content": "Updated content...",
  "tags": "updated-tag"
}
```

### Delete Note
```
DELETE /api/notes/{id}
```

### Get Statistics
```
GET /api/notes/stats
```

Returns:
```json
{
  "total_notes": 15,
  "by_category": [
    {"category": "strategy", "count": 5},
    {"category": "analysis", "count": 3}
  ],
  "last_modified": "2026-05-07T14:32:00"
}
```

### Toggle Pin Status
```
PUT /api/notes/pin/{id}
```

---

## Database Schema

The system creates a `research_notes` table in your PostgreSQL database:

```sql
CREATE TABLE research_notes (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tags VARCHAR(500),
    is_pinned BOOLEAN DEFAULT FALSE
)
```

**Columns:**
- `id` - Unique note identifier (auto-incremented)
- `title` - Note title (required)
- `category` - Type of note (strategy, analysis, research, planning, note)
- `content` - Full note content (required)
- `created_at` - Timestamp when note was created
- `modified_at` - Timestamp of last modification
- `tags` - Optional comma-separated tags for organization
- `is_pinned` - Boolean to pin important notes to the top

---

## Configuration

### Environment Variables

Add to your `.env` file:

```env
# PostgreSQL Connection (already configured)
DB_SERVER=localhost
DB_USER=sa
DB_PASS=Emm5$manuel
DB_NAME=ForexBrainDB
DB_PORT=5432
DB_DRIVER=PostgreSQL

# Research API Configuration
RESEARCH_API_PORT=5001
FLASK_ENV=development
```

---

## Frontend Features

### Create Note
- Click "✚ New Note"
- Fill title, category, and content
- Save to PostgreSQL

### Search & Filter
- Search across all titles and content
- Filter by category: Strategy, Analysis, Research, Planning, Note
- Real-time filtering with live results

### Edit Note
- Click ✏️ Edit on any note card
- Update details
- Changes auto-save to PostgreSQL

### Delete Note
- Click 🗑️ Delete
- Confirmation required
- Permanent deletion from PostgreSQL

### Statistics Dashboard
- Total notes count
- Notes by category
- Last updated timestamp
- All stats synced from PostgreSQL

---

## Fallback to LocalStorage

If the PostgreSQL API is unavailable, the system automatically falls back to browser localStorage:

1. Frontend detects API unavailability
2. Switches to localStorage backup
3. Shows all data locally
4. Syncs back to PostgreSQL when API comes online

This ensures you never lose your research notes!

---

## Querying Notes Directly

Connect to PostgreSQL to query notes directly:

```bash
psql -h localhost -U sa -d ForexBrainDB -W
```

Then run queries:

```sql
-- Get all research notes
SELECT id, title, category, created_at FROM research_notes ORDER BY created_at DESC;

-- Find notes by category
SELECT title, content FROM research_notes WHERE category = 'strategy';

-- Search for keyword
SELECT * FROM research_notes WHERE title ILIKE '%EMA%' OR content ILIKE '%EMA%';

-- Get pinned notes
SELECT * FROM research_notes WHERE is_pinned = true;

-- Get statistics
SELECT category, COUNT(*) FROM research_notes GROUP BY category;
```

---

## Troubleshooting

### API Not Connecting
- Check if Flask is running: `ps aux | grep research_notes_api`
- Verify port 5001 is open: `lsof -i :5001`
- Check PostgreSQL connection in `.env`
- View Flask logs for errors

### Database Connection Error
- Verify PostgreSQL is running: `psql -U sa -d ForexBrainDB`
- Check credentials in `.env`
- Ensure `ForexBrainDB` database exists

### Notes Not Saving
- Check browser console for errors (F12)
- Verify API is responding: `curl http://localhost:5001/api/health`
- Check Flask server logs
- Notes will fallback to localStorage if API fails

### LocalStorage Fallback Active
- System switched to localStorage (API unavailable)
- Check if Flask process crashed
- Restart API server: `bash shell/start_research_api.sh`
- Sync notes back to PostgreSQL

---

## Performance Tips

### Indexing
Automatic indexes created on:
- `category` - Fast category filtering
- `created_at` - Fast sorting by date

### Backup
- Notes automatically backed up to localStorage
- Consider regular PostgreSQL backups for production

### Optimization
For large note collections (100+), use:
- Specific category filters
- Search terms to narrow results
- Pagination via API queries

---

## Extension Ideas

The PostgreSQL backend enables advanced features:

- **Full-text search** across all notes
- **Advanced analytics** on research patterns
- **Export to PDF** of research collection
- **Collaboration** by adding user ownership
- **Versioning** to track note changes
- **Templates** for common research structures
- **Integration** with Layer 3 ML analysis
- **Automated tagging** based on content

---

## Architecture

```
┌─────────────────────────────────────────────┐
│         Browser (frontend/research.html)    │
│         - Create/Edit/Delete UI             │
│         - Search & Filter                   │
│         - Statistics Dashboard              │
└──────────────┬──────────────────────────────┘
               │
        HTTP API (localhost:5001)
               │
┌──────────────▼──────────────────────────────┐
│  Flask Backend (research_notes_api.py)      │
│  - CRUD Operations                          │
│  - Database Transactions                    │
│  - Stats & Search                           │
│  - Automatic Schema Init                    │
└──────────────┬──────────────────────────────┘
               │
        PostgreSQL Driver
               │
┌──────────────▼──────────────────────────────┐
│    PostgreSQL Database (ForexBrainDB)       │
│    - research_notes table                   │
│    - Persistent Storage                     │
│    - Full Query Support                     │
└─────────────────────────────────────────────┘
```

---

## Files Overview

- `src/research_notes_api.py` - Flask backend API (complete CRUD)
- `frontend/research.html` - UI with API integration
- `shell/start_research_api.sh` - Startup script
- `requirements.txt` - Python dependencies
- `.env` - PostgreSQL configuration

---

**Created:** May 7, 2026  
**Version:** 1.0  
**Status:** Production Ready
