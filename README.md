# YouTube Downloader

A Flask-based web application for downloading videos and audio from YouTube, running in Docker.

## Features

- 🎬 Download YouTube videos in various qualities
- 🎵 Extract audio as MP3 from videos
- ⚙️ Choose between audio-only, video-only, or combined downloads
- 🐳 Fully containerized with Docker
- 🌐 Clean, modern web interface
- 📥 Download multiple videos at once
- 💾 Download completed files directly from the web interface

## Prerequisites

- Docker
- Docker Compose

## Quick Start

1. **Build and run the container:**
   ```bash
   docker-compose up --build
   ```

2. **Access the application:**
   Open your browser and navigate to `http://localhost:5000`

3. **Download videos:**
   - Paste one or more YouTube URLs (one per line)
   - Select download type (audio-only, video-only, or both)
   - Choose quality preferences
   - Click "Download"

## Usage

### Downloading

1. Enter YouTube URLs in the text area (one URL per line)
2. Select your preferred download type:
   - **Audio Only**: Downloads video audio as MP3
   - **Video Only**: Downloads video without audio
   - **Audio + Video**: Downloads complete video with audio
3. Choose quality preferences:
   - Audio quality (for audio-only or audio+video)
   - Video quality (for video-only or audio+video)
4. Click the "Download" button

### Downloading completed files

Completed downloads appear in the "Downloaded Files" section. Click the "Download" button next to any file to download it to your computer.

## File Structure

```
yt-downloader/
├── app.py              # Flask application
├── setup.py            # Python package configuration
├── Dockerfile          # Docker image configuration
├── docker-compose.yml  # Docker Compose configuration
├── templates/
│   └── index.html      # Web interface
├── downloads/          # Downloaded files (created at runtime)
└── README.md           # This file
```

## Configuration

### Environment Variables

You can customize the following in `docker-compose.yml`:

- `FLASK_ENV`: Set to `production` for production deployments
- Port mapping: Change `5000:5000` to use a different port (e.g., `8080:5000`)

### Volume Mapping

By default, downloaded files are stored in `./downloads` on your host machine. You can change this in `docker-compose.yml`:

```yaml
volumes:
  - ./your-downloads-folder:/downloads
```

## Stopping the Container

```bash
docker-compose down
```

## Building Without Docker Compose

If you prefer to build and run manually:

```bash
# Build the image
docker build -t yt-downloader .

# Run the container
docker run -p 5000:5000 -v $(pwd)/downloads:/downloads --name yt-downloader yt-downloader
```

## Troubleshooting

### Permission Denied

If you get permission errors when downloading, ensure the `downloads` folder has proper permissions:

```bash
chmod 777 downloads
```

### Port Already in Use

If port 5000 is already in use, change it in `docker-compose.yml`:

```yaml
ports:
  - "8080:5000"  # Access at http://localhost:8080
```

### Container Won't Start

Check the logs:

```bash
docker-compose logs -f yt-downloader
```

## Dependencies

- **Flask**: Web framework
- **yt-dlp**: YouTube downloader
- **FFmpeg**: Audio/video processing (installed in Docker image)

## Notes

- Downloads run in the background; the web interface will remain responsive
- Large video files may take some time to download depending on your internet speed
- Downloaded files are stored on the host machine in the `downloads` folder
- The application respects YouTube's terms of service; only download content you have the right to download

## License

See LICENSE file for details.