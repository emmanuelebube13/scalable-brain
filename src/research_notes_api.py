"""
Research Notes API Backend
Stores and manages research notes in PostgreSQL
Provides REST API endpoints for CRUD operations
"""

import os
import json
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_SERVER', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME', 'ForexBrainDB'),
    'user': os.getenv('DB_USER', 'sa'),
    'password': os.getenv('DB_PASS', '')
}

def get_db_connection():
    """Get PostgreSQL database connection"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.Error as e:
        print(f"Database connection error: {e}")
        return None

def init_db():
    """Initialize database schema"""
    conn = get_db_connection()
    if not conn:
        print("Failed to connect to database")
        return False
    
    cur = conn.cursor()
    try:
        # Create research_notes table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS research_notes (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                category VARCHAR(50) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tags VARCHAR(500),
                is_pinned BOOLEAN DEFAULT FALSE
            )
        """)
        
        # Create index for faster searches
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_research_notes_category 
            ON research_notes(category)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_research_notes_created 
            ON research_notes(created_at DESC)
        """)
        
        conn.commit()
        print("✓ Database schema initialized successfully")
        return True
    except psycopg2.Error as e:
        print(f"Error initializing database: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

# ===== API ENDPOINTS =====

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        if conn:
            conn.close()
            return jsonify({'status': 'healthy', 'database': 'connected'}), 200
        else:
            return jsonify({'status': 'unhealthy', 'database': 'disconnected'}), 503
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/notes', methods=['GET'])
def get_notes():
    """Get all research notes with optional filtering"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 503
        
        category = request.args.get('category', None)
        search = request.args.get('search', None)
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        if category and search:
            query = """
                SELECT id, title, category, content, created_at, modified_at, tags, is_pinned 
                FROM research_notes 
                WHERE category = %s AND (title ILIKE %s OR content ILIKE %s)
                ORDER BY is_pinned DESC, created_at DESC
            """
            search_term = f"%{search}%"
            cur.execute(query, (category, search_term, search_term))
        elif category:
            query = """
                SELECT id, title, category, content, created_at, modified_at, tags, is_pinned 
                FROM research_notes 
                WHERE category = %s
                ORDER BY is_pinned DESC, created_at DESC
            """
            cur.execute(query, (category,))
        elif search:
            query = """
                SELECT id, title, category, content, created_at, modified_at, tags, is_pinned 
                FROM research_notes 
                WHERE title ILIKE %s OR content ILIKE %s
                ORDER BY is_pinned DESC, created_at DESC
            """
            search_term = f"%{search}%"
            cur.execute(query, (search_term, search_term))
        else:
            query = """
                SELECT id, title, category, content, created_at, modified_at, tags, is_pinned 
                FROM research_notes 
                ORDER BY is_pinned DESC, created_at DESC
            """
            cur.execute(query)
        
        notes = cur.fetchall()
        # Convert datetime objects to ISO format strings
        for note in notes:
            note['created_at'] = note['created_at'].isoformat() if note['created_at'] else None
            note['modified_at'] = note['modified_at'].isoformat() if note['modified_at'] else None
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'count': len(notes),
            'notes': notes
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notes/<int:note_id>', methods=['GET'])
def get_note(note_id):
    """Get a specific research note"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 503
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, title, category, content, created_at, modified_at, tags, is_pinned 
            FROM research_notes 
            WHERE id = %s
        """, (note_id,))
        
        note = cur.fetchone()
        cur.close()
        conn.close()
        
        if not note:
            return jsonify({'error': 'Note not found'}), 404
        
        note['created_at'] = note['created_at'].isoformat() if note['created_at'] else None
        note['modified_at'] = note['modified_at'].isoformat() if note['modified_at'] else None
        
        return jsonify({'success': True, 'note': note}), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notes', methods=['POST'])
def create_note():
    """Create a new research note"""
    try:
        data = request.json
        
        if not data or 'title' not in data or 'content' not in data:
            return jsonify({'error': 'Title and content are required'}), 400
        
        title = data['title'].strip()
        category = data.get('category', 'note').strip()
        content = data['content'].strip()
        tags = data.get('tags', '').strip()
        
        if not title or not content:
            return jsonify({'error': 'Title and content cannot be empty'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 503
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            INSERT INTO research_notes (title, category, content, tags)
            VALUES (%s, %s, %s, %s)
            RETURNING id, title, category, content, created_at, modified_at, tags, is_pinned
        """, (title, category, content, tags if tags else None))
        
        note = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        note['created_at'] = note['created_at'].isoformat() if note['created_at'] else None
        note['modified_at'] = note['modified_at'].isoformat() if note['modified_at'] else None
        
        return jsonify({
            'success': True,
            'message': 'Note created successfully',
            'note': note
        }), 201
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notes/<int:note_id>', methods=['PUT'])
def update_note(note_id):
    """Update an existing research note"""
    try:
        data = request.json
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        title = data.get('title', '').strip()
        category = data.get('category', '').strip()
        content = data.get('content', '').strip()
        tags = data.get('tags', '').strip()
        is_pinned = data.get('is_pinned', False)
        
        if not title or not content:
            return jsonify({'error': 'Title and content cannot be empty'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 503
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            UPDATE research_notes 
            SET title = %s, category = %s, content = %s, tags = %s, 
                is_pinned = %s, modified_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id, title, category, content, created_at, modified_at, tags, is_pinned
        """, (title, category, content, tags if tags else None, is_pinned, note_id))
        
        note = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        if not note:
            return jsonify({'error': 'Note not found'}), 404
        
        note['created_at'] = note['created_at'].isoformat() if note['created_at'] else None
        note['modified_at'] = note['modified_at'].isoformat() if note['modified_at'] else None
        
        return jsonify({
            'success': True,
            'message': 'Note updated successfully',
            'note': note
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notes/<int:note_id>', methods=['DELETE'])
def delete_note(note_id):
    """Delete a research note"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 503
        
        cur = conn.cursor()
        
        # Check if note exists
        cur.execute("SELECT id FROM research_notes WHERE id = %s", (note_id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'error': 'Note not found'}), 404
        
        # Delete note
        cur.execute("DELETE FROM research_notes WHERE id = %s", (note_id,))
        conn.commit()
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Note deleted successfully'
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notes/stats', methods=['GET'])
def get_stats():
    """Get research notes statistics"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 503
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Total notes
        cur.execute("SELECT COUNT(*) as total FROM research_notes")
        total = cur.fetchone()['total']
        
        # Notes by category
        cur.execute("""
            SELECT category, COUNT(*) as count 
            FROM research_notes 
            GROUP BY category 
            ORDER BY count DESC
        """)
        by_category = cur.fetchall()
        
        # Last modified
        cur.execute("""
            SELECT MAX(modified_at) as last_modified 
            FROM research_notes
        """)
        result = cur.fetchone()
        last_modified = result['last_modified'].isoformat() if result['last_modified'] else None
        
        cur.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'total_notes': total,
            'by_category': by_category,
            'last_modified': last_modified
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notes/pin/<int:note_id>', methods=['PUT'])
def toggle_pin_note(note_id):
    """Toggle pin status of a note"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'error': 'Database connection failed'}), 503
        
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            UPDATE research_notes 
            SET is_pinned = NOT is_pinned, modified_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id, title, category, content, created_at, modified_at, tags, is_pinned
        """, (note_id,))
        
        note = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        if not note:
            return jsonify({'error': 'Note not found'}), 404
        
        note['created_at'] = note['created_at'].isoformat() if note['created_at'] else None
        note['modified_at'] = note['modified_at'].isoformat() if note['modified_at'] else None
        
        return jsonify({
            'success': True,
            'message': 'Note pin status updated',
            'note': note
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Initialize database on startup
    init_db()
    
    # Run Flask app
    port = int(os.getenv('RESEARCH_API_PORT', 5001))
    debug = os.getenv('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
