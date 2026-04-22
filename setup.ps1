# PowerShell Setup Script untuk venv

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Creating Virtual Environment (venv)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Hapus venv lama jika ada
if (Test-Path "venv") {
    Write-Host "Removing old venv..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force venv
}

# Buat venv baru
Write-Host "Creating new virtual environment..." -ForegroundColor Green
python -m venv venv

# Activate venv
Write-Host "Activating venv..." -ForegroundColor Green
& "venv\Scripts\Activate.ps1"

# Upgrade pip
Write-Host "Upgrading pip..." -ForegroundColor Green
python -m pip install --upgrade pip

# Install requirements
Write-Host "Installing requirements from requirements.txt..." -ForegroundColor Green
pip install -r requirements.txt

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "✓ Setup complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Run: python monitor_drives.py"
Write-Host ""
Write-Host "Or to activate venv later:" -ForegroundColor Cyan
Write-Host "   .\venv\Scripts\Activate.ps1"
Write-Host ""
