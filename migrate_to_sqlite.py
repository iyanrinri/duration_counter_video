import sqlite3
import json
from pathlib import Path
import os

BASE_DIR = Path(__file__).parent
METADATA_FILE = BASE_DIR / "recording_metadata.jsonl"
DB_FILE = BASE_DIR / "database.sqlite"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recordings (
            hash TEXT PRIMARY KEY,
            file_path TEXT,
            drive_name TEXT,
            file_size INTEGER,
            duration_seconds REAL,
            recorded_date TEXT,
            camera_id TEXT,
            folder_name TEXT,
            timestamp TEXT,
            file_modified_at TEXT
        )
    ''')
    conn.commit()
    return conn

def migrate():
    print(f"Checking for existing JSON log: {METADATA_FILE}")
    if not METADATA_FILE.exists():
        print("No existing metadata JSON file found. Starting fresh.")
        init_db()
        return

    conn = init_db()
    cursor = conn.cursor()
    
    count = 0
    with open(METADATA_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                h = item.get("md5_first_1mb")
                if not h:
                    continue
                
                cursor.execute('''
                    INSERT INTO recordings (
                        hash, file_path, drive_name, file_size, duration_seconds, 
                        recorded_date, camera_id, folder_name, timestamp, file_modified_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(hash) DO UPDATE SET
                        file_path=excluded.file_path,
                        drive_name=excluded.drive_name,
                        file_size=excluded.file_size,
                        duration_seconds=excluded.duration_seconds,
                        recorded_date=excluded.recorded_date,
                        camera_id=excluded.camera_id,
                        folder_name=excluded.folder_name,
                        timestamp=excluded.timestamp,
                        file_modified_at=excluded.file_modified_at
                ''', (
                    h,
                    item.get("file_path"),
                    item.get("drive_name"),
                    item.get("file_size"),
                    item.get("duration_seconds"),
                    item.get("recorded_date"),
                    item.get("camera_id"),
                    item.get("folder_name"),
                    item.get("timestamp"),
                    item.get("file_modified_at")
                ))
                count += 1
            except Exception as e:
                print(f"Error parsing line: {e}")
                
    conn.commit()
    conn.close()
    
    print(f"Successfully migrated {count} records to {DB_FILE}")
    
    # Rename old files to keep as backup
    try:
        os.rename(METADATA_FILE, str(METADATA_FILE) + ".backup")
        backlog_file = BASE_DIR / "backlog.json"
        if backlog_file.exists():
            os.rename(backlog_file, str(backlog_file) + ".backup")
        print("Backed up old JSON files.")
    except Exception as e:
        print(f"Failed to backup JSON files: {e}")

if __name__ == "__main__":
    migrate()
