#!/bin/bash
# Setup script for YouTube Downloader systemd service
# Run this with sudo: sudo bash setup-systemd.sh

set -e

echo "=== YouTube Downloader Systemd Setup ==="

# Configuration
app_user_home="/home/yt-dl"
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
echo "3. Copying app to yt-dl home directory..."
echo "   Copying files from current directory to $app_user_home..."
cp -r ./* "$app_user_home/" 2>/dev/null || true
cp -r ./.git* "$app_user_home/" 2>/dev/null || true

# Verify setup.py exists
if [[ ! -f "$app_user_home/setup.py" ]]; then
    echo "   ERROR: setup.py not found in $app_user_home"
    echo "   Current directory: $(pwd)"
    echo "   Files in current directory:"
    ls -la
    echo "   Files in $app_user_home:"
    ls -la "$app_user_home/"
    exit 1
fi

chown -R "$app_user:$app_group" "$app_user_home"
chmod -R 755 "$app_user_home"
echo "   Files copied successfully"

echo ""
echo "4. Setting up Python virtual environment..."
venv_dir="$app_user_home/venv"

if [[ ! -f "$venv_dir/bin/activate" ]]; then
    echo "   Creating virtual environment at $venv_dir..."
    sudo -u "$app_user" python3 -m venv "$venv_dir" || { echo "Failed to create venv"; exit 1; }
    echo "   Created virtual environment"
fi

echo "   Installing dependencies..."
sudo -u "$app_user" "$venv_dir/bin/pip" install --upgrade pip
sudo -u "$app_user" "$venv_dir/bin/pip" install -e "$app_user_home"

echo ""
echo "5. Setting up configuration file..."
if [[ ! -f "$config_dir/yt-downloader.env" ]]; then
    cp "$app_user_home/yt-downloader.env.example" "$config_dir/yt-downloader.env"
    echo "   Created $config_dir/yt-downloader.env"
    echo "   Please edit it with your configuration"
else
    echo "   $config_dir/yt-downloader.env already exists"
fi

echo ""
echo "6. Installing systemd service..."
cp "$app_user_home/yt-downloader.service" /etc/systemd/system/
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

