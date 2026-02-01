#!/bin/bash
# Setup script for YouTube Downloader systemd service
# Run this with sudo: sudo bash setup-systemd.sh

set -e

echo "=== YouTube Downloader Systemd Setup ==="

# Configuration
app_dir="/opt/yt-downloader"
app_user="yt-dl"
app_group="yt-dl"
download_dir="/downloads"
log_dir="/var/log/yt-downloader"
config_dir="/etc/yt-downloader"

# Check if running as root
if [[ $EUID -ne 0 ]]; then 
    echo "Please run as root (sudo bash setup-systemd.sh)"
    exit 1
fi

echo "1. Creating yt-dl user..."
if id "$app_user" &>/dev/null; then
    echo "   User $app_user already exists"
else
    useradd -r -s /bin/bash -m -d /home/yt-dl "$app_user"
    echo "   Created user $app_user"
fi

echo ""
echo "2. Setting up directories..."
mkdir -p "$download_dir"
mkdir -p "$log_dir"
mkdir -p "$config_dir"

echo "   Fixing permissions..."
chown "$app_user:$app_group" "$download_dir"
chown "$app_user:$app_group" "$log_dir"
chown "$app_user:$app_group" "$config_dir"
chmod 755 "$download_dir"
chmod 755 "$log_dir"

echo ""
echo "3. Setting up Python virtual environment..."
app_user_home="/home/yt-dl"
venv_dir="$app_user_home/venv"

if [[ ! -d "$venv_dir" ]]; then
    sudo -u "$app_user" python3 -m venv "$venv_dir"
    echo "   Created virtual environment"
fi

source "$venv_dir/bin/activate"
echo "   Installing dependencies..."
pip install --upgrade pip
pip install -e /home/jesse/git/yt-downloader

echo ""
echo "4. Copying app to production location..."
mkdir -p "$app_dir"
cp -r ./* "$app_dir/" 2>/dev/null || true
chown -R "$app_user:$app_group" "$app_dir"
chmod -R 755 "$app_dir"

echo ""
echo "5. Setting up configuration file..."
if [[ ! -f "$config_dir/yt-downloader.env" ]]; then
    cp yt-downloader.env.example "$config_dir/yt-downloader.env"
    echo "   Created $config_dir/yt-downloader.env"
    echo "   Please edit it with your configuration"
else
    echo "   $config_dir/yt-downloader.env already exists"
fi

echo ""
echo "6. Installing systemd service..."
cp yt-downloader.service /etc/systemd/system/
systemctl daemon-reload
echo "   Systemd service installed"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Edit configuration: sudo nano $config_dir/yt-downloader.env"
echo "2. Enable service: sudo systemctl enable yt-downloader"
echo "3. Start service: sudo systemctl start yt-downloader"
echo "4. Check status: sudo systemctl status yt-downloader"
echo "5. View logs: sudo journalctl -u yt-downloader -f"
echo ""
echo "Access the app at: http://localhost"

