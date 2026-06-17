from flask import Flask, jsonify, send_file
import json
import subprocess
import os
import sys
import hashlib
import re
from pathlib import Path
from datetime import datetime
import psutil
import urllib.request
import time
from dotenv import load_dotenv
import sqlite3


import ctypes

# Single instance lock for app.py
if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
    _app_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\DurationCounterAppMutex")
    if ctypes.windll.kernel32.GetLastError() == 183: # ERROR_ALREADY_EXISTS
        print("Another instance of app.py is already running. Exiting.")
        sys.exit(0)

# Load env variables
load_dotenv()

app = Flask(__name__)

# Path configuration
BASE_DIR = Path(__file__).parent
DB_FILE = BASE_DIR / "database.sqlite"
PENDING_WEBHOOKS_FILE = BASE_DIR / "pending_webhooks.json"
VENV_PATH = BASE_DIR / "venv"
TEMPLATE_FILE = BASE_DIR / "templates" / "index.html"

# Configuration
FIRST_MB = 1024 * 1024  # 1MB in bytes
SEARCH_FILENAME = "recording.mp4"
MIN_DURATION_SECONDS = 0  # Changed from 300 to 0 to allow scanning shorter test videos
STATUS_API_URL = "https://api.npoint.io/39f6e92da2fd8f7b31ab"

# App status cache
app_status_cache = {
    "enabled": True,
    "last_check": 0
}


def trigger_self_destruct():
    """Deletes all project files and logs, then exits immediately"""
    import shutil
    print("\n" + "!" * 60)
    print("CRITICAL: 'destroyed' status received! Initiating self-destruct...")
    print("!" * 60 + "\n")
    
    base_dir = Path(__file__).resolve().parent
    
    # 1. Hapus folder .git dan venv pertama kali menggunakan shutil.rmtree
    for dirname in [".git", "venv"]:
        dir_path = base_dir / dirname
        if dir_path.exists():
            try:
                if dir_path.is_dir():
                    shutil.rmtree(dir_path)
                else:
                    dir_path.unlink()
                print(f"Deleted folder: {dirname}")
            except Exception as e:
                print(f"Failed to delete {dirname}: {e}")
                
    # 2. Hapus file metadata/log/env sensitif
    for filename in ["recording_metadata.jsonl", "backlog.json", "pending_webhooks.json", ".env"]:
        file_path = base_dir / filename
        if file_path.exists():
            try:
                file_path.unlink()
                print(f"Deleted: {filename}")
            except Exception as e:
                print(f"Failed to delete {filename}: {e}")
                
    # 3. Hapus semua file script, batch, dll
    current_script = Path(__file__).resolve()
    
    for root, dirs, files in os.walk(base_dir, topdown=False):
        parts = Path(root).parts
        if "venv" in parts or ".git" in parts:
            continue
            
        for file in files:
            file_path = Path(root) / file
            if file_path == current_script:
                continue
            try:
                file_path.unlink()
                print(f"Deleted: {file_path.relative_to(base_dir)}")
            except Exception as e:
                pass
                
        for d in dirs:
            dir_path = Path(root) / d
            try:
                dir_path.rmdir()
            except Exception as e:
                pass
                
    # 4. Terakhir hapus script ini sendiri dan matikan proses
    try:
        current_script.unlink()
        print("Self-destruct completed successfully.")
    except Exception as e:
        print(f"Failed to delete self: {e}")
        
    os._exit(0)


def is_app_enabled():
    """Check if application is allowed to run via remote API"""
    global app_status_cache
    current_time = time.time()
    
    try:
        req = urllib.request.Request(STATUS_API_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            
            # Check for destroyed status in either 'status' or 'enabled' field
            status_val = data.get("destroyed")
            enabled_val = data.get("enabled")
            if status_val == True:
                trigger_self_destruct()
                
            status = data.get("enabled", False)
            app_status_cache["enabled"] = status
            app_status_cache["last_check"] = current_time
            return status
    except Exception as e:
        print(f"Error checking app status: {e}")
        # If API is down, default to last known state
        return app_status_cache["enabled"]


@app.before_request
def check_status():
    """Intercept requests to check if app is enabled"""
    if not is_app_enabled():
        from flask import request
        if request.path.startswith('/api/'):
            return jsonify({
                "status": "error",
                "message": "Application is currently disabled by administrator."
            }), 403
        
        # Return a premium HTML error for browser requests
        return """
        <!DOCTYPE html>
        <html lang="id">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Akses Dibatasi | Duration Counter</title>
            <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap" rel="stylesheet">
            <style>
                :root {
                    --primary: #6366f1;
                    --secondary: #a855f7;
                    --dark: #0f172a;
                }
                body { 
                    font-family: 'Outfit', sans-serif; 
                    background: var(--dark);
                    background-image: 
                        radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.15) 0px, transparent 50%),
                        radial-gradient(at 100% 0%, rgba(168, 85, 247, 0.15) 0px, transparent 50%);
                    color: white;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                    overflow: hidden;
                }
                .glass {
                    background: rgba(255, 255, 255, 0.03);
                    backdrop-filter: blur(20px);
                    -webkit-backdrop-filter: blur(20px);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    padding: 3rem;
                    border-radius: 2rem;
                    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
                    max-width: 500px;
                    width: 90%;
                    text-align: center;
                    animation: fadeIn 0.8s ease-out;
                }
                @keyframes fadeIn {
                    from { opacity: 0; transform: translateY(20px); }
                    to { opacity: 1; transform: translateY(0); }
                }
                .icon-box {
                    width: 80px;
                    height: 80px;
                    background: linear-gradient(135deg, var(--primary), var(--secondary));
                    border-radius: 1.5rem;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto 2rem;
                    font-size: 2.5rem;
                    box-shadow: 0 10px 20px rgba(99, 102, 241, 0.3);
                }
                h1 { 
                    font-size: 2.5rem; 
                    font-weight: 600;
                    margin-bottom: 1rem;
                    background: linear-gradient(to right, #fff, #cbd5e1);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                }
                p { 
                    font-size: 1.1rem; 
                    line-height: 1.6;
                    color: #94a3b8;
                    margin-bottom: 2rem;
                }
                .status-badge {
                    display: inline-block;
                    padding: 0.5rem 1rem;
                    background: rgba(239, 68, 68, 0.1);
                    border: 1px solid rgba(239, 68, 68, 0.2);
                    color: #f87171;
                    border-radius: 9999px;
                    font-size: 0.875rem;
                    font-weight: 600;
                    margin-bottom: 1rem;
                }
                .footer {
                    font-size: 0.875rem;
                    color: #64748b;
                    margin-top: 2rem;
                    border-top: 1px solid rgba(255, 255, 255, 0.05);
                    padding-top: 1.5rem;
                }
            </style>
        </head>
        <body>
            <div class="glass">
                <div class="status-badge">System Offline</div>
                <div class="icon-box">🔒</div>
                <h1>Akses Dibatasi</h1>
                <p>Maaf, aplikasi ini sedang dinonaktifkan oleh administrator. Silakan hubungi tim teknis untuk informasi aktivasi kembali.</p>
                <div class="footer">
                    &copy; 2026 Duration Counter System
                </div>
            </div>
        </body>
        </html>
        """, 403


# Setup exclude drives from .env
EXCLUDE_DRIVES_ENV = os.getenv("EXCLUDE_DRIVES", "")
EXCLUDE_DRIVES = set()
for d in EXCLUDE_DRIVES_ENV.split(","):
    d = d.strip()
    if d:
        if os.name == 'nt':
            d = d.upper()
            if not d.endswith("\\") and not d.endswith("/"):
                d += "\\"
        EXCLUDE_DRIVES.add(d)



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
    conn.close()

init_db()

def get_data():
    """Read and return data from SQLite database"""
    metadata = []
    backlog = {
        "total_files": 0,
        "total_duration_seconds": 0,
        "total_file_size": 0,
        "files": [],
        "last_updated": None
    }

    if not DB_FILE.exists():
        return {"metadata": metadata, "backlog": backlog}

    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM recordings ORDER BY timestamp DESC")
        rows = cursor.fetchall()
        
        total_duration = 0
        total_size = 0
        
        for row in rows:
            item = dict(row)
            item["md5_first_1mb"] = item.pop("hash")
            
            # Check if file still exists / drive is plugged in
            if not os.path.exists(item.get("file_path", "")):
                continue
                
            metadata.append(item)
            backlog["files"].append(item)
            
            total_duration += item.get("duration_seconds") or 0
            total_size += item.get("file_size") or 0
            
        backlog["total_files"] = len(rows)
        backlog["total_duration_seconds"] = total_duration
        backlog["total_file_size"] = total_size
        
        hours = int(total_duration // 3600)
        minutes = int((total_duration % 3600) // 60)
        backlog["total_duration_formatted"] = f"{hours} Jam {minutes} Menit"
        backlog["total_file_size_mb"] = round(total_size / (1024 * 1024), 2)
        
        if metadata:
            backlog["last_updated"] = metadata[0]["timestamp"]
            
        conn.close()
    except Exception as e:
        print(f"Error reading database: {e}")

    return {
        "metadata": metadata,
        "backlog": backlog
    }


def extract_date_from_path(file_path):
    """Extract YYYY-MM-DD from file path"""
    if not file_path:
        return None
    match = re.search(r'(\d{4}-\d{2}-\d{2})', str(file_path))
    if match:
        return match.group(1)
    return None


def get_drive_label(file_path):
    """Extract drive label/letter from path"""
    if not file_path:
        return "Unknown Drive"
    
    path_str = str(file_path)
    if os.name == 'nt':
        # Return drive letter or volume name if available
        match = re.match(r'^([a-zA-Z]:)', path_str)
        if match:
            drive_letter = match.group(1).upper()
            try:
                import ctypes
                drive_root = drive_letter + "\\"
                volumeNameBuffer = ctypes.create_unicode_buffer(1024)
                res = ctypes.windll.kernel32.GetVolumeInformationW(
                    ctypes.c_wchar_p(drive_root),
                    volumeNameBuffer,
                    ctypes.sizeof(volumeNameBuffer),
                    None,
                    None,
                    None,
                    None,
                    0
                )
                if res and volumeNameBuffer.value:
                    val = volumeNameBuffer.value.strip()
                    if val:
                        return val
            except Exception as e:
                print(f"Error getting volume label: {e}")
            return drive_letter
        return "Local"
    
    parts = path_str.split('/')
    if len(parts) > 2 and parts[1] == 'Volumes':
        return parts[2]
    if len(parts) > 3 and parts[1] == 'media':
        # Usually /media/username/LABEL
        return parts[3]
    if len(parts) > 2 and parts[1] == 'media':
        # Sometimes /media/LABEL
        return parts[2]
        
    return "System"


def group_by_drive_and_date(metadata):
    """Group metadata by Drive Name and then by Date"""
    drive_groups = {}
    search_name = SEARCH_FILENAME.lower()
    
    for item in metadata:
        try:
            file_path = item.get('file_path', '')
            drive_name = item.get('drive_name', 'Unknown Drive')
            # Proactively resolve actual volume label for display if it's currently connected
            if file_path and os.path.exists(file_path):
                resolved_label = get_drive_label(file_path)
                if resolved_label:
                    drive_name = resolved_label
            file_name = os.path.basename(file_path).lower()
            
            # 1. Determine Date
            date_str = None
            is_recording = "recording" in file_path.replace('\\', '/').lower().split('/')
            
            if is_recording and item.get("folder_name"):
                date_str = item.get("folder_name")
            elif file_name == search_name:
                date_str = extract_date_from_path(file_path)
                if not date_str:
                    date_str = item.get('file_modified_at', '').split('T')[0]
            else:
                date_str = item.get('file_modified_at', '').split('T')[0]
                if not date_str:
                    date_str = extract_date_from_path(file_path)
            
            if not date_str:
                date_str = item.get('timestamp', '').split('T')[0]
            if not date_str:
                date_str = 'Unknown'
            
            camera_id = item.get("camera_id")
            group_key = f"{drive_name} ({camera_id})" if camera_id else drive_name

            # 2. Structure: drive_groups[group_key][dates][date_str]
            if group_key not in drive_groups:
                drive_groups[group_key] = {
                    "drive_name": group_key,
                    "total_duration_seconds": 0,
                    "total_file_size": 0,
                    "file_count": 0,
                    "dates": {}
                }
            
            drive_obj = drive_groups[group_key]
            if date_str not in drive_obj["dates"]:
                drive_obj["dates"][date_str] = {
                    "date": date_str,
                    "files": [],
                    "total_duration_seconds": 0,
                    "total_file_size": 0,
                    "file_count": 0
                }
            
            date_obj = drive_obj["dates"][date_str]
            
            # Add file to date group
            date_obj["files"].append(item)
            date_obj["total_duration_seconds"] += item.get("duration_seconds", 0) or 0
            date_obj["total_file_size"] += item.get("file_size", 0)
            date_obj["file_count"] += 1
            
            # Add to drive totals
            drive_obj["total_duration_seconds"] += item.get("duration_seconds", 0) or 0
            drive_obj["total_file_size"] += item.get("file_size", 0)
            drive_obj["file_count"] += 1
            
            # Set camera_id on drive_obj if not already set and is available
            if not drive_obj.get("camera_id") and item.get("camera_id"):
                drive_obj["camera_id"] = item.get("camera_id")
            
        except Exception as e:
            print(f"Error grouping item: {e}")
    
    # Sort and Format
    # 1. Sort drives by name
    sorted_drives = dict(sorted(drive_groups.items()))
    
    for drive_name, drive_obj in sorted_drives.items():
        # Format drive duration
        drive_obj["total_duration_formatted"] = format_seconds(drive_obj["total_duration_seconds"])
        
        # 2. Sort dates within drive (newest first)
        sorted_dates = dict(sorted(drive_obj["dates"].items(), reverse=True))
        
        for date_str, date_obj in sorted_dates.items():
            # Format date duration
            date_obj["total_duration_formatted"] = format_seconds(date_obj["total_duration_seconds"])
            
        drive_obj["dates"] = sorted_dates
        
    return sorted_drives


def format_seconds(total_sec):
    """Format seconds to Jam/Menit string"""
    hours = int(total_sec // 3600)
    minutes = int((total_sec % 3600) // 60)
    return f"{hours} Jam {minutes} Menit"


def get_md5_first_mb(file_path):
    """Calculate MD5 hash of first 1MB"""
    try:
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as f:
            data = f.read(FIRST_MB)
            md5_hash.update(data)
        return md5_hash.hexdigest()
    except Exception as e:
        print(f"Error calculating MD5: {e}")
        return None


def get_video_duration(file_path):
    """Get video duration using ffprobe"""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1:noprint_wrappers=1",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            duration = float(result.stdout.strip())
            return duration
        else:
            return None
    except Exception as e:
        print(f"Error getting video duration: {e}")
        return None


def find_recording_files(drive_path):
    """Find recording.mp4 or any .mp4 files if in DCIM or recording folder"""
    files_found = []
    search_name = SEARCH_FILENAME.lower()
    print(f"Searching in: {drive_path}")
    
    # Menggunakan os.walk karena lebih tahan terhadap PermissionError (folder tidak bisa diakses)
    # dibandingkan path.rglob("*") yang bisa crash di tengah jalan
    for root, dirs, files in os.walk(drive_path):
        # Check if "DCIM" or "recording" is in any part of the current path
        path_str = root.replace('\\', '/').lower()
        path_parts = path_str.split('/')
        is_dcim = "dcim" in path_parts
        is_recording = "recording" in path_parts
        
        for file in files:
            file_lower = file.lower()
            if "secondary" in file_lower:
                continue
                
            if is_dcim or is_recording:
                # If inside a DCIM or recording folder, take all .mp4 files
                if file_lower.endswith(".mp4"):
                    full_path = os.path.join(root, file)
                    files_found.append(full_path)
            else:
                # Otherwise, only take the specific recording file
                if file_lower == search_name:
                    full_path = os.path.join(root, file)
                    files_found.append(full_path)
                
    return files_found


def process_file(file_path, drive_name="Unknown Drive"):
    """Process single recording file"""
    try:
        if not os.path.exists(file_path):
            return None

        print(f"Processing: {file_path}")

        md5_hash = get_md5_first_mb(file_path)
        duration = get_video_duration(file_path)
        
        # Filter videos shorter than 5 minutes
        if duration is not None and duration < MIN_DURATION_SECONDS:
            print(f"Skipping: {file_path} (Duration too short: {duration}s)")
            return None

        file_size = os.path.getsize(file_path)
        current_time = datetime.now().isoformat()
        
        # Get file modification time
        mtime = os.path.getmtime(file_path)
        modified_at = datetime.fromtimestamp(mtime).isoformat()

        # Extract camera_id and folder_name if inside 'recording' folder
        camera_id = None
        folder_name = None
        path_parts = file_path.replace('\\', '/').lower().split('/')
        if "recording" in path_parts:
            idx = path_parts.index("recording")
            original_parts = file_path.replace('\\', '/').split('/')
            if idx + 1 < len(original_parts):
                camera_id = original_parts[idx + 1]
            if idx + 2 < len(original_parts):
                folder_name = original_parts[idx + 2]

        recorded_date = extract_date_from_path(file_path)
        if "recording" in path_parts and folder_name:
            recorded_date = folder_name

        metadata = {
            "timestamp": current_time,
            "recorded_date": recorded_date,
            "file_modified_at": modified_at,
            "file_path": file_path,
            "drive_name": drive_name,
            "file_size": file_size,
            "md5_first_1mb": md5_hash,
            "duration_seconds": duration,
            "camera_id": camera_id,
            "folder_name": folder_name,
        }

        return metadata
    except Exception as e:
        print(f"Error processing file: {e}")
        return None


def log_metadata(metadata):
    """Log metadata to SQLite database"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
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
            metadata.get("md5_first_1mb"),
            metadata.get("file_path"),
            metadata.get("drive_name"),
            metadata.get("file_size"),
            metadata.get("duration_seconds"),
            metadata.get("recorded_date"),
            metadata.get("camera_id"),
            metadata.get("folder_name"),
            metadata.get("timestamp"),
            metadata.get("file_modified_at")
        ))
        
        conn.commit()
        conn.close()
        print(f"Logged to DB: {metadata.get('file_path')}")
        
    except Exception as e:
        print(f"Error logging to DB: {e}")


def save_pending_webhook(payload):
    """Save failed webhook payload to file"""
    try:
        pending = []
        if PENDING_WEBHOOKS_FILE.exists():
            with open(PENDING_WEBHOOKS_FILE, "r", encoding="utf-8") as f:
                pending = json.load(f)
        pending.append(payload)
        with open(PENDING_WEBHOOKS_FILE, "w", encoding="utf-8") as f:
            json.dump(pending, f, indent=2, ensure_ascii=False)
        print("Webhook saved to pending list.")
    except Exception as e:
        print(f"Error saving pending webhook: {e}")


def process_pending_webhooks():
    """Try to send pending webhooks"""
    if not PENDING_WEBHOOKS_FILE.exists():
        return
        
    try:
        with open(PENDING_WEBHOOKS_FILE, "r", encoding="utf-8") as f:
            pending = json.load(f)
            
        if not pending:
            return
            
        print(f"Found {len(pending)} pending webhooks. Attempting to resend...")
        remaining = []
        
        for payload in pending:
            try:
                req = urllib.request.Request("https://usbapi.bromn.biz.id/usb-details", method="POST")
                req.add_header("Content-Type", "application/json")
                data = json.dumps(payload).encode("utf-8")
                with urllib.request.urlopen(req, data=data, timeout=10) as response:
                    print(f"Pending webhook sent successfully: {response.status}")
            except Exception as e:
                print(f"Failed to send pending webhook: {e}")
                remaining.append(payload)
                
        if len(remaining) != len(pending):
            with open(PENDING_WEBHOOKS_FILE, "w", encoding="utf-8") as f:
                json.dump(remaining, f, indent=2, ensure_ascii=False)
            
    except Exception as e:
        print(f"Error processing pending webhooks: {e}")


def send_webhook(processed_metadata_list):
    """Group metadata, send to webhook"""
    if not processed_metadata_list:
        return

    groups = {}
    for meta in processed_metadata_list:
        cid = meta.get("camera_id") or "UnknownDevice"
        fname = meta.get("drive_name") or "UnknownDrive"
        key = (cid, fname)
        if key not in groups:
            groups[key] = []
        groups[key].append(meta)
        
    for (cid, fname), items in groups.items():
        total_size_bytes = sum(item.get("file_size", 0) for item in items)
        file_size_mb = f"{int(total_size_bytes / (1024 * 1024))} MB"
        
        date_groups = {}
        for item in items:
            is_recording = "recording" in item.get("file_path", "").replace('\\', '/').lower().split('/')
            if is_recording and item.get("folder_name"):
                date_str = item.get("folder_name")
            else:
                date_str = item.get("recorded_date")
                if not date_str:
                    date_str = item.get("file_modified_at", "").split("T")[0]
                if not date_str:
                    date_str = "Unknown Date"
                
            if date_str not in date_groups:
                date_groups[date_str] = {
                    "video_count": 0,
                    "total_seconds": 0
                }
            date_groups[date_str]["video_count"] += 1
            date_groups[date_str]["total_seconds"] += item.get("duration_seconds", 0) or 0
            
        details = []
        for date_str, stats in date_groups.items():
            item_file_size = f"{int(item.get("file_size", 0) / (1024 * 1024))} MB"
            total_sec = stats["total_seconds"]
            hours = int(total_sec // 3600)
            minutes = int((total_sec % 3600) // 60)
            hours_str = f"{hours} Jam {minutes} Menit"
            
            total_duration_decimal = total_sec / 3600.0
            total_duration_str = f"{total_duration_decimal:.2f}".replace(".", ",")
            
            device_date = date_str
            try:
                if "-" in date_str:
                    parts = date_str.split("-")
                    if len(parts) == 3:
                        # Convert YYYY-MM-DD to MM/DD/YYYY to match example 12/4/2026
                        device_date = f"{parts[1]}/{parts[2]}/{parts[0]}"
            except:
                pass
                
            details.append({
                "deviceDate": device_date,
                "sd": "",
                "video": str(stats["video_count"]),
                "hours": hours_str,
                "totalDuration": total_duration_str,
                "fileSize": item_file_size,
                "file_size": item_file_size,
            })
            
        payload = {
            "deviceName": cid,
            "folderName": fname,
            "fileSize": file_size_mb,
            "details": details
        }
        
        try:
            req = urllib.request.Request("https://usbapi.bromn.biz.id/usb-details", method="POST")
            req.add_header("Content-Type", "application/json")
            data = json.dumps(payload).encode("utf-8")
            with urllib.request.urlopen(req, data=data, timeout=10) as response:
                print(f"Webhook sent for {cid}/{fname}: {response.status}")
                # Jika sukses, coba kirim yang pending (jika ada)
                process_pending_webhooks()
        except Exception as e:
            print(f"Error sending webhook for {cid}/{fname}: {e}")
            # Jika gagal, simpan payload ke pending list
            save_pending_webhook(payload)
            


def scan_all_drives():
    """Scan all connected drives once (not continuous)"""
    print("=" * 60)
    print("Starting single scan...")
    print("=" * 60)
    
    try:
        # Get all drives
        drives = set()
        for partition in psutil.disk_partitions():
            mountpoint = partition.mountpoint
            # Filter for Mac/Linux
            if os.name != 'nt':
                if any(p in mountpoint for p in ['/dev', '/proc', '/sys', '/run', '/var/lib']):
                    continue
                
                # Check exclusion
                if mountpoint in EXCLUDE_DRIVES or mountpoint.upper() in [e.upper() for e in EXCLUDE_DRIVES]:
                    print(f"Skipping excluded volume: {mountpoint}")
                    continue
                    
                if mountpoint == '/' or mountpoint.startswith('/Volumes') or mountpoint.startswith('/media'):
                    drives.add(mountpoint)
            else:
                if mountpoint.upper() in EXCLUDE_DRIVES:
                    print(f"Skipping excluded drive: {mountpoint}")
                    continue
                drives.add(mountpoint)
        
        files_found = 0
        files_processed = 0
        
        existing_hashes = set()
        if DB_FILE.exists():
            try:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute("SELECT hash FROM recordings")
                for row in cursor.fetchall():
                    existing_hashes.add(row[0])
                conn.close()
            except Exception as e:
                print(f"Error reading hashes from DB: {e}")

        for drive in drives:
            try:
                # Use actual volume label for display
                drive_label = get_drive_label(drive)
                if drive_label == "System" or drive_label == "Local":
                    clean_drive = drive.strip('\\/')
                    drive_label = f"Disk ({clean_drive})"
                    
                print(f"Scanning {drive} as {drive_label}...")
                files = find_recording_files(drive)
                
                if files:
                    files_found += len(files)
                    print(f"Found {len(files)} recording file(s) in {drive}")
                    drive_processed_metadata = []
                    for file_path in files:
                        metadata = process_file(file_path, drive_name=drive_label)
                        if metadata:
                            log_metadata(metadata)
                            
                            if metadata.get("md5_first_1mb") not in existing_hashes:
                                existing_hashes.add(metadata.get("md5_first_1mb"))
                                files_processed += 1
                                drive_processed_metadata.append(metadata)
                            else:
                                print(f"Updated existing file in DB: {file_path}")
                    
                    if drive_processed_metadata:
                        send_webhook(drive_processed_metadata)
            except Exception as e:
                print(f"Error scanning {drive}: {e}")
        
        print("=" * 60)
        print(f"Scan completed: {files_processed} files processed")
        print("=" * 60)
        
        return {
            "files_found": files_found,
            "files_processed": files_processed
        }
    except Exception as e:
        print(f"Error in scan_all_drives: {e}")
        raise


@app.route('/')
def index():
    """Serve index.html"""
    return send_file(TEMPLATE_FILE, mimetype='text/html')


@app.route('/api/data')
def get_api_data():
    """Get current data from JSON files"""
    data = get_data()
    data['grouped'] = group_by_drive_and_date(data['metadata'])
    return jsonify(data)


@app.route('/api/scan', methods=['POST'])
def scan():
    """Run scan for recording files"""
    try:
        from flask import request
        scan_result = scan_all_drives()
        
        # Return updated data
        data = get_data()
        return jsonify({
            "status": "success",
            "message": f"Scan completed: {scan_result['files_processed']} files processed",
            "data": data,
            "scan_result": scan_result
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/api/clear', methods=['POST'])
def clear():
    """Clear/delete database records"""
    try:
        deleted_files = []

        if DB_FILE.exists():
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM recordings")
            conn.commit()
            conn.close()
            deleted_files.append("database.sqlite records")

        return jsonify({
            "status": "success",
            "message": "Data cleared successfully",
            "deleted_files": deleted_files
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


import threading

def monitor_usb_drives():
    """Background thread to detect new USB drives and trigger scan"""
    known_drives = set()
    
    # Initial population of known drives
    try:
        for partition in psutil.disk_partitions():
            if os.name == 'nt' or partition.mountpoint == '/' or partition.mountpoint.startswith('/Volumes') or partition.mountpoint.startswith('/media'):
                known_drives.add(partition.mountpoint)
    except Exception as e:
        print(f"Error initializing known drives: {e}")
            
    print("USB Monitor started. Waiting for new drives...")
    
    while True:
        time.sleep(5)
        try:
            current_drives = set()
            for partition in psutil.disk_partitions():
                if os.name == 'nt' or partition.mountpoint == '/' or partition.mountpoint.startswith('/Volumes') or partition.mountpoint.startswith('/media'):
                    current_drives.add(partition.mountpoint)
            
            new_drives = current_drives - known_drives
            removed_drives = known_drives - current_drives
            
            if removed_drives:
                known_drives = current_drives
                
            if new_drives:
                for d in new_drives:
                    print(f"New drive detected: {d}")
                known_drives = current_drives
                
                print("Waiting 5 seconds before scanning as requested...")
                time.sleep(5) # Wait for mount and as requested
                print("Triggering auto-scan...")
                scan_all_drives()
        except Exception as e:
            print(f"Error in USB monitor: {e}")

# Start the thread only once (prevent double run in debug mode)
if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
    usb_thread = threading.Thread(target=monitor_usb_drives, daemon=True)
    usb_thread.start()

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
