import multiprocessing

# Gunicorn configuration
bind = "0.0.0.0:80"
workers = max(2, multiprocessing.cpu_count() // 2)
worker_class = "sync"
worker_connections = 1000
timeout = 300  # 5 minutes for long downloads
keepalive = 5

# Logging
accesslog = "/var/log/yt-downloader/access.log"
errorlog = "/var/log/yt-downloader/error.log"
loglevel = "info"

# Process naming
proc_name = "yt-downloader"

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None  # Run as yt-downloader user via systemd
group = None

# SSL (optional, comment out if not needed)
# keyfile = "/etc/yt-downloader/ssl/key.pem"
# certfile = "/etc/yt-downloader/ssl/cert.pem"
