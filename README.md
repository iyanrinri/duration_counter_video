# Drive Monitor & Recording Metadata Logger

Script Python yang monitor drive USB/SD Card dan otomatis cari file `recording.mp4`, lalu simpan metadata ke file.

## Yang disimpan:
- ✅ **Timestamp** - Waktu deteksi file
- ✅ **MD5 Hash (1MB pertama)** - Untuk verifikasi integritas
- ✅ **Durasi video** - Dalam detik dan format readable (jam:menit:detik)
- ✅ **File path** - Lokasi lengkap file
- ✅ **File size** - Ukuran file

## Persiapan:

### 1. Setup Virtual Environment & Install Dependencies
Jalankan script setup untuk membuat virtual environment dan menginstall library yang dibutuhkan (hanya perlu dijalankan sekali):
- **Windows**: Klik dua kali file `setup_venv.bat`

Atau jika ingin setup manual melalui terminal:
```bash
python -m venv venv

# Aktifkan venv:
venv\Scripts\activate.bat   # Windows
# source venv/bin/activate  # Mac/Linux

# Install dependencies:
pip install -r requirements.txt
```

### 2. Install FFmpeg (untuk mendapat durasi video)
**Pilihan A - Menggunakan Winget (Windows):**
```bash
winget install ffmpeg
```

**Pilihan B - Download dari website:**
- Download dari https://ffmpeg.org/download.html
- Extract dan tambahkan path ke System Environment Variables

**Pilihan C - Verify installation:**
```bash
ffprobe -version
```

## Cara Pakai:

### 1. Jalankan Aplikasi
Setiap kali ingin menjalankan script, Anda **wajib** mengaktifkan virtual environment terlebih dahulu:

```bash
# 1. Aktifkan venv
venv\Scripts\activate.bat   # Windows
# source venv/bin/activate  # Mac/Linux

# 2. Jalankan aplikasi
python app.py
```

*(Tips Windows: Anda bisa langsung klik dua kali file `run_app.bat` untuk mengaktifkan venv dan menjalankan aplikasi secara otomatis).*

### 2. Menjalankan Otomatis Saat Komputer Nyala (Start on Boot)
Jika Anda ingin program ini berjalan secara otomatis di background (tersembunyi) setiap kali komputer Windows dinyalakan:
1. Klik kanan pada file `install_service.bat`
2. Pilih **Run as Administrator**
3. Program berhasil didaftarkan ke Task Scheduler dan akan berjalan otomatis saat Log In.

*(Untuk menghapus dari startup, jalankan `uninstall_service.bat` as Administrator).*

### 3. Connect SD Card / USB Drive
Script akan otomatis:
- Detect drive baru
- Scan untuk file `recording.mp4`
- Extract metadata
- Simpan ke `recording_metadata.jsonl`

### 4. Lihat hasil:
File `recording_metadata.jsonl` di folder yang sama, format JSON Lines (1 JSON per baris):

```json
{"timestamp": "2026-04-22T10:30:45.123456", "file_path": "E:\\recording.mp4", "file_size": 524288000, "md5_first_1mb": "a1b2c3d4e5f6...", "duration_seconds": 3661.5, "duration_formatted": "1h 1m 1s"}
{"timestamp": "2026-04-22T10:35:12.654321", "file_path": "F:\\Videos\\recording.mp4", "file_size": 1048576000, "md5_first_1mb": "f6e5d4c3b2a1...", "duration_seconds": 7322.0, "duration_formatted": "2h 2m 2s"}
```

## Customization:

Edit di bagian atas `monitor_drives.py`:
```python
CHECK_INTERVAL = 5  # Berapa detik sekali check (default 5s)
SEARCH_FILENAME = "recording.mp4"  # Nama file yang dicari (exact match)
LOG_FILE = "recording_metadata.jsonl"  # Nama output file
```

## Troubleshooting:

### "ffprobe tidak ditemukan"
→ Install FFmpeg sesuai instruksi di atas

### "No module named psutil"
→ Jalankan: `pip install psutil`

### Script tidak detect drive baru
→ Cek di File Explorer apakah drive terdeteksi
→ Tutup script dan jalankan ulang

## Notes:
- Script akan terus berjalan sampai ditekan `Ctrl+C`
- Log file append otomatis (tidak overwrite)
- Setiap drive baru akan scan recursive seluruh folder
