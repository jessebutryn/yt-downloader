FROM jrottenberg/ffmpeg:6.0-nvidia

ENV DEBIAN_FRONTEND=noninteractive

# Install Python, pip and Node.js (Node used by yt-dlp for JS runtimes)
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    curl \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 20.x
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get update && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Ensure `python` points to python3
RUN ln -s /usr/bin/python3 /usr/bin/python || true

WORKDIR /app

# Copy setup.py and install Python dependencies
COPY setup.py requirements.txt .
# Install Python package dependencies from requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY templates/ templates/

# Create downloads directory
RUN mkdir -p /downloads

# Expose port 5000
EXPOSE 5000

# Clear any ENTRYPOINT from base image (jrottenberg/ffmpeg uses ffmpeg as entrypoint)
ENTRYPOINT []

# Default command
CMD ["python3", "app.py"]
