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


# Load env variables
load_dotenv()

app = Flask(__name__)

# Path configuration
BASE_DIR = Path(__file__).parent
METADATA_FILE = BASE_DIR / "recording_metadata.jsonl"
BACKLOG_FILE = BASE_DIR / "backlog.json"
VENV_PATH = BASE_DIR / "venv"
TEMPLATE_FILE = BASE_DIR / "templates" / "index.html"

# Configuration
FIRST_MB = 1024 * 1024  # 1MB in bytes
SEARCH_FILENAME = "recording.mp4"
MIN_DURATION_SECONDS = 300  # 5 minutes
STATUS_API_URL = "https://api.npoint.io/39f6e92da2fd8f7b31ab"

# App status cache
app_status_cache = {
    "enabled": True,
    "last_check": 0
}


def is_app_enabled():
    """Check if application is allowed to run via remote API"""
    global app_status_cache
    current_time = time.time()
    
    try:
        req = urllib.request.Request(STATUS_API_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
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



def get_data():
    """Read and return data from JSON files"""
    metadata = []
    backlog = {}

    # Read recording metadata
    if METADATA_FILE.exists():
        try:
            with open(METADATA_FILE, 'r') as f:
                for line in f:
                    if line.strip():
                        metadata.append(json.loads(line))
        except Exception as e:
            print(f"Error reading metadata: {e}")

    # Read backlog
    if BACKLOG_FILE.exists():
        try:
            with open(BACKLOG_FILE, 'r') as f:
                backlog = json.load(f)
        except Exception as e:
            print(f"Error reading backlog: {e}")

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
        # Return drive letter (e.g. D:)
        match = re.match(r'^([a-zA-Z]:)', path_str)
        return match.group(1).upper() if match else "Local"
    
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
            drive_name = item.get('drive_name', 'Unknown Drive')
            file_path = item.get('file_path', '')
            file_name = os.path.basename(file_path).lower()
            
            # 1. Determine Date
            date_str = None
            if file_name == search_name:
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
            
            # 2. Structure: drive_groups[drive_name][dates][date_str]
            if drive_name not in drive_groups:
                drive_groups[drive_name] = {
                    "drive_name": drive_name,
                    "total_duration_seconds": 0,
                    "total_file_size": 0,
                    "file_count": 0,
                    "dates": {}
                }
            
            drive_obj = drive_groups[drive_name]
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
    """Find recording.mp4 or any .mp4 files if in DCIM folder"""
    files_found = []
    search_name = SEARCH_FILENAME.lower()
    print(f"Searching in: {drive_path}")
    
    # Menggunakan os.walk karena lebih tahan terhadap PermissionError (folder tidak bisa diakses)
    # dibandingkan path.rglob("*") yang bisa crash di tengah jalan
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
            "recorded_date": extract_date_from_path(file_path),
            "file_modified_at": modified_at,
            "file_path": file_path,
            "drive_name": drive_name,
            "file_size": file_size,
            "md5_first_1mb": md5_hash,
            "duration_seconds": duration,
        }

        return metadata
    except Exception as e:
        print(f"Error processing file: {e}")
        return None


def log_metadata(metadata):
    """Log metadata ke file (JSON Lines format)"""
    try:
        with open(METADATA_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(metadata) + "\n")
        print(f"Logged: {metadata['file_path']}")
        
        # Update backlog.json
        update_backlog(metadata)
    except Exception as e:
        print(f"Error logging metadata: {e}")


def update_backlog(metadata):
    """Update backlog.json dengan summary/total"""
    try:
        # Load existing backlog
        if BACKLOG_FILE.exists():
            with open(BACKLOG_FILE, "r", encoding="utf-8") as f:
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
            "recorded_date": metadata.get("recorded_date"),
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
        
        backlog["total_duration_formatted"] = f"{hours} Jam {minutes} Menit"
        backlog["total_file_size_mb"] = round(backlog["total_file_size"] / (1024 * 1024), 2)
        
        # Save backlog
        with open(BACKLOG_FILE, "w", encoding="utf-8") as f:
            json.dump(backlog, f, indent=2, ensure_ascii=False)
        
        print(f"Backlog updated: {backlog['total_files']} files, {backlog['total_duration_formatted']}")
    except Exception as e:
        print(f"Error updating backlog: {e}")


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
        
        for drive in drives:
            try:
                # Use actual volume label for display
                drive_label = get_drive_label(drive)
                if drive_label == "System" or drive_label == "Local":
                    drive_label = f"Disk ({drive.strip('\\/')})"
                    
                print(f"Scanning {drive} as {drive_label}...")
                files = find_recording_files(drive)
                
                if files:
                    files_found += len(files)
                    print(f"Found {len(files)} recording file(s) in {drive}")
                    for file_path in files:
                        metadata = process_file(file_path, drive_name=drive_label)
                        if metadata:
                            log_metadata(metadata)
                            files_processed += 1
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
    """Clear/delete JSON files"""
    try:
        deleted_files = []

        if METADATA_FILE.exists():
            METADATA_FILE.unlink()
            deleted_files.append("recording_metadata.jsonl")

        if BACKLOG_FILE.exists():
            BACKLOG_FILE.unlink()
            deleted_files.append("backlog.json")

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


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
