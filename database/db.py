import sqlite3
from datetime import datetime
import json

SCHEMA = '''
CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY,
    company TEXT,
    recruiter_name TEXT,
    recruiter_phone TEXT,
    role TEXT,
    location TEXT,
    salary_min INTEGER,
    salary_max INTEGER,
    notice_period TEXT,
    interview_date TEXT,
    status TEXT,
    score INTEGER,
    created_at DATETIME
);
CREATE TABLE IF NOT EXISTS transcripts (
    id INTEGER PRIMARY KEY,
    opportunity_id INTEGER,
    transcript TEXT,
    audio_path TEXT,
    created_at DATETIME
);
CREATE TABLE IF NOT EXISTS processed_files (
    file_hash TEXT PRIMARY KEY,
    file_name TEXT,
    processed_at DATETIME
);
'''

def get_conn(db_path):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path):
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.executescript(SCHEMA)
    conn.commit()
    conn.close()

def file_processed(conn, file_hash):
    cur = conn.cursor()
    cur.execute('SELECT 1 FROM processed_files WHERE file_hash=?', (file_hash,))
    return cur.fetchone() is not None

def mark_file_processed(conn, file_hash, file_name):
    cur = conn.cursor()
    cur.execute('INSERT OR REPLACE INTO processed_files(file_hash,file_name,processed_at) VALUES(?,?,?)',
                (file_hash, file_name, datetime.utcnow()))
    conn.commit()

def save_opportunity(conn, data):
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO opportunities(company,recruiter_name,recruiter_phone,role,location,salary_min,salary_max,notice_period,interview_date,status,score,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
        (
            data.get('company'),
            data.get('recruiter_name'),
            data.get('recruiter_phone'),
            data.get('role'),
            data.get('location'),
            data.get('salary_min'),
            data.get('salary_max'),
            data.get('notice_period'),
            data.get('interview_date'),
            data.get('status') or 'NEW',
            data.get('score'),
            datetime.utcnow(),
        ),
    )
    conn.commit()
    return cur.lastrowid

def save_transcript(conn, opportunity_id, transcript, audio_path):
    cur = conn.cursor()
    cur.execute('INSERT INTO transcripts(opportunity_id,transcript,audio_path,created_at) VALUES(?,?,?,?)',
                (opportunity_id, transcript, audio_path, datetime.utcnow()))
    conn.commit()

def list_opportunities(conn, limit=100):
    cur = conn.cursor()
    cur.execute('SELECT * FROM opportunities ORDER BY created_at DESC LIMIT ?', (limit,))
    return [dict(row) for row in cur.fetchall()]

def get_opportunity(conn, opp_id):
    cur = conn.cursor()
    cur.execute('SELECT * FROM opportunities WHERE id=?', (opp_id,))
    row = cur.fetchone()
    if not row:
        return None
    opp = dict(row)
    cur.execute('SELECT * FROM transcripts WHERE opportunity_id=? ORDER BY created_at DESC', (opp_id,))
    opp['transcripts'] = [dict(r) for r in cur.fetchall()]
    return opp
