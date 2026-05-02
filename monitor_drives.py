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


# Load env variables
load_dotenv()

# Configuration
LOG_FILE = "recording_metadata.jsonl"
CHECK_INTERVAL = 5  # seconds
FIRST_MB = 1024 * 1024  # 1MB in bytes
SEARCH_FILENAME = "recording.mp4"  # Exact filename only
MIN_DURATION_SECONDS = 300  # 5 minutes
STATUS_API_URL = "https://api.npoint.io/39f6e92da2fd8f7b31ab"

# Status cache
status_cache = {"enabled": True, "last_check": 0}


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
        # Return drive letter (e.g. D:)
        match = re.match(r'^([a-zA-Z]:)', path_str)
        return match.group(1).upper() if match else "Local"
    
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
    """Find recording.mp4 or any .mp4 files if in DCIM folder"""
    files_found = []
    search_name = SEARCH_FILENAME.lower()
    
    try:
        # Menggunakan os.walk karena lebih tahan terhadap PermissionError
        for root, dirs, files in os.walk(drive_path):
            # Check if "DCIM" is in any part of the current path
            path_parts = root.upper().replace('\\', '/').split('/')
            is_dcim = "DCIM" in path_parts
            
            for file in files:
                file_lower = file.lower()
                if is_dcim:
                    # If inside a DCIM folder, take all .mp4 files
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

        metadata = {
            "timestamp": current_time,
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
        }

        return metadata
    except Exception as e:
        print(f"Error processing file: {e}")
        return None


def log_metadata(metadata):
    """Log metadata ke file (JSON Lines format)"""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(metadata) + "\n")
        print(f"Logged: {metadata['file_path']}")
        
        # Update backlog.json
        update_backlog(metadata)
    except Exception as e:
        print(f"Error logging metadata: {e}")


def update_backlog(metadata):
    """Update backlog.json dengan summary/total"""
    try:
        backlog_file = "backlog.json"
        
        # Load existing backlog
        if os.path.exists(backlog_file):
            with open(backlog_file, "r", encoding="utf-8") as f:
                backlog = json.load(f)
        else:
            backlog = {
                "total_files": 0,
                "total_duration_seconds": 0,
                "total_file_size": 0,
                "files": [],
                "last_updated": None
            }
        
        # Update totals
        backlog["total_files"] += 1
        backlog["total_duration_seconds"] += metadata.get("duration_seconds", 0) or 0
        backlog["total_file_size"] += metadata.get("file_size", 0)
        backlog["last_updated"] = datetime.now().isoformat()
        
        # Add file entry
        backlog["files"].append({
            "timestamp": metadata["timestamp"],
            "file_path": metadata["file_path"],
            "drive_name": metadata.get("drive_name", "Unknown Drive"),
            "md5_first_1mb": metadata["md5_first_1mb"],
            "duration_seconds": metadata["duration_seconds"],
            "file_size": metadata["file_size"]
        })
        
        # Calculate formatted totals
        total_seconds = backlog["total_duration_seconds"]
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        
        backlog["total_duration_formatted"] = f"{hours}h {minutes}m {seconds}s"
        backlog["total_file_size_mb"] = round(backlog["total_file_size"] / (1024 * 1024), 2)
        
        # Save backlog
        with open(backlog_file, "w", encoding="utf-8") as f:
            json.dump(backlog, f, indent=2, ensure_ascii=False)
        
        print(f"Backlog updated: {backlog['total_files']} files, {backlog['total_duration_formatted']}")
    except Exception as e:
        print(f"Error updating backlog: {e}")


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
        
        for drive in new_drives:
            # Use actual volume label for display
            drive_label = get_drive_label(drive)
            if drive_label == "System" or drive_label == "Local":
                drive_label = f"Disk ({drive.strip('\\/')})"
            
            print(f"Scanning {drive} as {drive_label}...")
            files = find_recording_files(drive)

            if files:
                print(f"Found {len(files)} recording file(s)")
                for file_path in files:
                    metadata = process_file(file_path, drive_name=drive_label)
                    if metadata:
                        log_metadata(metadata)
            else:
                print(f"No recording files found in {drive}")

    previous_drives = current_drives


def monitor_loop():
    """Main monitoring loop"""
    print("Starting drive monitor...")
    print(f"Log file: {os.path.abspath(LOG_FILE)}")
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
    print(f"Output file: {LOG_FILE}")
    print(f"Searching for: {SEARCH_FILENAME}")
    print("=" * 60 + "\n")

    # Initial check
    if not is_app_enabled():
        print("ALERT: Monitoring is currently disabled via remote API. Waiting for activation...")
    
    monitor_loop()
