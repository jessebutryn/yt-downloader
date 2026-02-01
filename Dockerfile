FROM node:20-slim

# Install Python and other dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set up Python
RUN ln -s /usr/bin/python3 /usr/bin/python

WORKDIR /app

# Copy setup.py and install Python dependencies
COPY setup.py .
RUN pip install --no-cache-dir --break-system-packages .

# Copy application files
COPY app.py .
COPY templates/ templates/

# Create downloads directory
RUN mkdir -p /downloads

# Expose port 5000
EXPOSE 5000

# Run the Flask app
CMD ["python", "app.py"]
