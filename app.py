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
    match = re.search(r'(\d{4}-\d{2}-\d{2})', file_path)
    if match:
        return match.group(1)
    return None


def group_by_date(metadata):
    """Group metadata by date"""
    grouped = {}
    
    for item in metadata:
        try:
            # Extract date from path first, fallback to timestamp
            date_str = extract_date_from_path(item.get('file_path', ''))
            
            if not date_str:
                # Fallback to scan timestamp (YYYY-MM-DD)
                date_str = item.get('timestamp', '').split('T')[0]
            
            if not date_str:
                date_str = 'Unknown'
            
            if date_str not in grouped:
                grouped[date_str] = {
                    "date": date_str,
                    "files": [],
                    "total_duration_seconds": 0,
                    "total_file_size": 0,
                    "file_count": 0
                }
            
            grouped[date_str]["files"].append(item)
            grouped[date_str]["total_duration_seconds"] += item.get("duration_seconds", 0) or 0
            grouped[date_str]["total_file_size"] += item.get("file_size", 0)
            grouped[date_str]["file_count"] += 1
        except Exception as e:
            print(f"Error grouping item: {e}")
    
    # Sort by date descending (newest first)
    sorted_grouped = dict(sorted(grouped.items(), reverse=True))
    
    # Format duration for each group
    for date_key in sorted_grouped:
        group = sorted_grouped[date_key]
        total_sec = group["total_duration_seconds"]
        hours = int(total_sec // 3600)
        minutes = int((total_sec % 3600) // 60)
        seconds = int(total_sec % 60)
        group["total_duration_formatted"] = f"{hours}h {minutes}m {seconds}s"
    
    return sorted_grouped


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
    """Find recording.mp4 files in drive"""
    files_found = []
    search_name = SEARCH_FILENAME.lower()
    print(f"Searching in: {drive_path}")
    
    # Menggunakan os.walk karena lebih tahan terhadap PermissionError (folder tidak bisa diakses)
    # dibandingkan path.rglob("*") yang bisa crash di tengah jalan
    for root, dirs, files in os.walk(drive_path):
        for file in files:
            if file.lower() == search_name:
                full_path = os.path.join(root, file)
                files_found.append(full_path)
                
    return files_found


def process_file(file_path):
    """Process single recording file"""
    try:
        if not os.path.exists(file_path):
            return None

        print(f"Processing: {file_path}")

        md5_hash = get_md5_first_mb(file_path)
        duration = get_video_duration(file_path)
        file_size = os.path.getsize(file_path)
        current_time = datetime.now().isoformat()

        metadata = {
            "timestamp": current_time,
            "recorded_date": extract_date_from_path(file_path),
            "file_path": file_path,
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
            drives.add(partition.mountpoint)
        
        files_found = 0
        files_processed = 0
        
        for drive in drives:
            try:
                print(f"Scanning {drive}...")
                files = find_recording_files(drive)
                
                if files:
                    files_found += len(files)
                    print(f"Found {len(files)} recording file(s) in {drive}")
                    for file_path in files:
                        metadata = process_file(file_path)
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
    data['grouped'] = group_by_date(data['metadata'])
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
