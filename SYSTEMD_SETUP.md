# Systemd Setup for YouTube Downloader

This guide will help you set up the YouTube Downloader as a systemd service for local production use.

## Prerequisites

- Ubuntu/Debian-based Linux system
- sudo access
- Python 3.8+
- git (already cloned)

## Quick Setup

### 1. Prepare the Setup Script

Make the setup script executable:
```bash
chmod +x setup-systemd.sh
```

### 2. Run the Setup Script

```bash
sudo bash setup-systemd.sh
```

This script will:
- Create a dedicated `yt-downloader` user
- Set up directories with proper permissions
- Create a Python virtual environment
- Install dependencies including gunicorn
- Copy the app to `/opt/yt-downloader`
- Install the systemd service file

### 3. Configure the Service

Edit the environment configuration:
```bash
sudo nano /etc/yt-downloader/yt-downloader.env
```

Set any environment variables needed for your setup.

## Managing the Service

### Start the service
```bash
sudo systemctl start yt-downloader
```

### Stop the service
```bash
sudo systemctl stop yt-downloader
```

### Restart the service
```bash
sudo systemctl restart yt-downloader
```

### Enable on boot (auto-start)
```bash
sudo systemctl enable yt-downloader
```

### Disable auto-start
```bash
sudo systemctl disable yt-downloader
```

### Check service status
```bash
sudo systemctl status yt-downloader
```

## Viewing Logs

View recent logs:
```bash
sudo journalctl -u yt-downloader -n 50
```

Follow logs in real-time:
```bash
sudo journalctl -u yt-downloader -f
```

View logs with timestamps:
```bash
sudo journalctl -u yt-downloader --since "2 hours ago" -o short-precise
```

## Accessing the Application

Once running, access the web interface at:
```
http://localhost:5000
http://<your-vm-ip>:5000
```

## Troubleshooting

### Service fails to start
Check the logs:
```bash
sudo journalctl -u yt-downloader -n 100 | grep -i error
```

### Permission denied errors
Verify ownership of directories:
```bash
ls -la /downloads
ls -la /var/log/yt-downloader
```

If needed, fix permissions:
```bash
sudo chown -R yt-downloader:yt-downloader /downloads
sudo chown -R yt-downloader:yt-downloader /var/log/yt-downloader
```

### Port already in use
If port 5000 is already in use, modify the gunicorn_config.py:
```python
bind = "0.0.0.0:8080"  # Change to a different port
```

Then restart the service:
```bash
sudo systemctl restart yt-downloader
```

## Updating the Application

When you update the code:

1. Pull the latest changes:
```bash
cd /home/jesse/git/yt-downloader
git pull
```

2. Update the production copy:
```bash
sudo bash setup-systemd.sh
```

3. Restart the service:
```bash
sudo systemctl restart yt-downloader
```

## Security Considerations

The systemd service includes several security features:

- Runs as unprivileged `yt-downloader` user
- No new privileges allowed
- Read-only filesystem (except for download and log directories)
- Isolated /tmp
- Resource limits (file descriptors, processes)

For additional security on a local network:

1. **Use a reverse proxy** (nginx):
```bash
sudo apt-get install nginx
# Configure nginx as reverse proxy to localhost:5000
```

2. **Add authentication** to the Flask app if exposed beyond localhost

3. **Use HTTPS** (uncomment SSL lines in gunicorn_config.py and provide certs)

4. **Firewall** the port:
```bash
sudo ufw allow 5000/tcp  # Allow from specific IPs
```

## Performance Tuning

Edit `/opt/yt-downloader/gunicorn_config.py` to adjust:

- `workers`: Number of worker processes (default: CPU count / 2)
- `timeout`: Request timeout in seconds (default: 300 for long downloads)
- `worker_connections`: Max simultaneous connections per worker

Changes take effect after restart:
```bash
sudo systemctl restart yt-downloader
```

## Backup and Recovery

### Backup downloads
```bash
sudo tar -czf yt-downloader-backup.tar.gz /downloads
```

### Backup configuration
```bash
sudo tar -czf yt-downloader-config-backup.tar.gz /etc/yt-downloader /opt/yt-downloader
```

## Uninstalling

To completely remove the service:

```bash
# Stop and disable service
sudo systemctl stop yt-downloader
sudo systemctl disable yt-downloader

# Remove service file
sudo rm /etc/systemd/system/yt-downloader.service
sudo systemctl daemon-reload

# Remove user and directories (optional)
sudo userdel -r yt-downloader
sudo rm -rf /opt/yt-downloader
sudo rm -rf /etc/yt-downloader
```
