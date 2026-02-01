from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import os
from pathlib import Path
import threading
import queue
import subprocess
import glob

app = Flask(__name__)

# Configuration
DOWNLOAD_DIR = Path("/downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Download queue to limit concurrent downloads
download_queue = queue.Queue()
download_worker_thread = None

# Quality presets for different devices
QUALITY_PRESETS = {
    'minivan': {
        'name': 'Minivan (720p H.264 AAC)',
        'format_spec': 'best[height<=720]/best',
        'post_args': {
            'width': 1280,
            'height': 720,
            'video_codec': 'libx264',
            'audio_codec': 'aac',
            'video_bitrate': '706k',
            'audio_bitrate': '192k'
        }
    },
    '1080p': {
        'name': '1080p HD',
        'format_spec': 'best[height<=1080]/best',
    },
    '720p': {
        'name': '720p',
        'format_spec': 'best[height<=720]/best',
    },
    '480p': {
        'name': '480p (Low Quality)',
        'format_spec': 'best[height<=480]/best',
    },
    'best': {
        'name': 'Best Available',
        'format_spec': 'best',
    },
    'worst': {
        'name': 'Worst Available',
        'format_spec': 'worst',
    }
}

# Store download status
download_status = {}
download_status_lock = threading.Lock()
active_downloads = set()  # Track which downloads are currently in progress
active_downloads_lock = threading.Lock()
download_counter = 0  # Monotonically increasing counter for unique download IDs
download_counter_lock = threading.Lock()


def safe_update_status(video_id, status_dict):
    """Thread-safe update of download status"""
    with download_status_lock:
        download_status[video_id] = status_dict.copy()


def get_video_info(url):
    """Get video info without downloading"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'url': url,
                'formats': get_available_formats(info)
            }
    except Exception as e:
        return {'error': str(e)}


def get_available_formats(info):
    """Extract available audio and video formats"""
    formats = {
        'video_formats': [],
        'audio_formats': []
    }
    
    # Get video formats
    if info.get('formats'):
        for fmt in info['formats']:
            # Video formats
            if fmt.get('vcodec') != 'none' and fmt.get('height'):
                formats['video_formats'].append({
                    'format_id': fmt['format_id'],
                    'resolution': f"{fmt['height']}p",
                    'fps': fmt.get('fps', 'unknown'),
                    'ext': fmt.get('ext', 'unknown')
                })
            # Audio formats
            elif fmt.get('acodec') != 'none':
                formats['audio_formats'].append({
                    'format_id': fmt['format_id'],
                    'abr': fmt.get('abr', 'unknown'),
                    'ext': fmt.get('ext', 'unknown')
                })
    
    # Remove duplicates and sort
    seen_video = set()
    seen_audio = set()
    unique_video = []
    unique_audio = []
    
    for fmt in formats['video_formats']:
        key = fmt['resolution']
        if key not in seen_video:
            seen_video.add(key)
            unique_video.append(fmt)
    
    for fmt in formats['audio_formats']:
        key = fmt.get('abr', 'unknown')
        if key not in seen_audio:
            seen_audio.add(key)
            unique_audio.append(fmt)
    
    return {
        'video_formats': sorted(unique_video, key=lambda x: int(x['resolution'].replace('p', '')), reverse=True)[:5],
        'audio_formats': unique_audio[:5]
    }


def download_worker():
    """Worker thread that processes downloads from queue sequentially"""
    while True:
        try:
            url, download_type, quality_preset, video_id = download_queue.get()
            # Clear any stale progress data before starting
            safe_update_status(video_id, {'status': 'queued', 'progress': 0})
            download_video(url, download_type, quality_preset, video_id)
            download_queue.task_done()
        except Exception as e:
            print(f"Worker error: {e}")
            download_queue.task_done()


def start_download_worker():
    """Start the download worker thread if not already running"""
    global download_worker_thread
    if download_worker_thread is None or not download_worker_thread.is_alive():
        download_worker_thread = threading.Thread(target=download_worker, daemon=True)
        download_worker_thread.start()


def download_video(url, download_type, quality_preset, video_id):
    """Download video/audio in background"""
    try:
        # Create a local reference to video_id to ensure it's captured correctly in the closure
        current_video_id = video_id
        
        # Mark this download as active
        with active_downloads_lock:
            active_downloads.add(current_video_id)
            print(f"[DOWNLOAD] Added {current_video_id} to active_downloads. Active: {active_downloads}")
        
        safe_update_status(current_video_id, {
            'status': 'downloading',
            'progress': 0,
            'message': f'Starting download: {url}',
        })
        
        # Include quality preset in filename to avoid overwriting different qualities
        output_template = str(DOWNLOAD_DIR / f'%(title)s_{quality_preset}.%(ext)s')
        
        def progress_hook(d):
            """Update progress information"""
            # Only update if this download is still active
            with active_downloads_lock:
                if current_video_id not in active_downloads:
                    print(f"[HOOK] {current_video_id} not in active_downloads, ignoring callback")
                    return
                
            # Use current_video_id from the enclosing scope to ensure correct tracking
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    progress = int((downloaded / total) * 100)
                    if progress % 10 == 0 or progress > 95:  # Log every 10% or when near end
                        print(f"[HOOK] {current_video_id}: Downloading {progress}% ({downloaded}/{total})")
                    safe_update_status(current_video_id, {
                        'status': 'downloading',
                        'progress': progress,
                        'message': f"{url} - Downloading: {progress}%",
                    })
            elif d['status'] == 'processing':
                print(f"[HOOK] {current_video_id}: Processing")
                safe_update_status(current_video_id, {
                    'status': 'processing',
                    'progress': 50,
                    'message': f"{url} - Post-processing...",
                })
            elif d['status'] == 'finished':
                print(f"[HOOK] {current_video_id}: Finished downloading, encoding...")
                safe_update_status(current_video_id, {
                    'status': 'finished',
                    'progress': 100,
                    'message': f"{url} - Encoding...",
                })
        
        if download_type == 'audio':
            ydl_opts = {
                'format': 'bestaudio/best',
                'ratelimit': 2097152,  # 2 Mbps in bytes/sec
                'progress_hooks': [progress_hook],
                'outtmpl': output_template,
                'quiet': False,
                'socket_timeout': 30,
                'js_runtimes': {'node': {'path': '/usr/local/bin/node'}},
                'remote_components': ['ejs:github'],
                'restrictfilenames': True,  # Remove special characters from filenames
            }
            # Audio-only uses FFmpeg extraction
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        else:  # audio+video
            ydl_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'ratelimit': 2097152,  # 2 Mbps in bytes/sec
                'progress_hooks': [progress_hook],
                'outtmpl': output_template,
                'quiet': False,
                'socket_timeout': 30,
                'merge_output_format': 'mp4',
                'js_runtimes': {'node': {'path': '/usr/local/bin/node'}},
                'remote_components': ['ejs:github'],
                'restrictfilenames': True,  # Remove special characters from filenames
            }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        print(f"[DOWNLOAD] {current_video_id}: yt-dlp download complete. Type={download_type}, Preset={quality_preset}")
        
        minivan_success = True
        # Post-process for minivan preset if needed (audio+video only)
        if download_type == 'audio+video' and quality_preset == 'minivan':
            print(f"[DOWNLOAD] {current_video_id}: Entering minivan re-encoding block")
            safe_update_status(current_video_id, {
                'status': 'processing',
                'progress': 75,
                'message': f'{url} - Re-encoding for Minivan...'
            })
            
            try:
                # Find the most recently downloaded file matching the pattern
                pattern = str(DOWNLOAD_DIR / f'*_{quality_preset}.mp4')
                files = glob.glob(pattern)
                print(f"[Minivan] Looking for: {pattern}")
                print(f"[Minivan] Found files: {files}")
                
                if files:
                    # Get the most recently modified file
                    latest_file = max(files, key=lambda f: os.path.getmtime(f))
                    print(f"[Minivan] Selected file: {latest_file}")
                    temp_file = latest_file + '.temp.mp4'
                    
                    # Run ffmpeg re-encoding
                    print(f"[Minivan] Starting re-encode...")
                    cmd = [
                        'ffmpeg', '-i', latest_file,
                        '-vf', 'scale=1280:720:force_original_aspect_ratio=1',
                        '-c:v', 'libx264',
                        '-b:v', '706k',
                        '-c:a', 'aac',
                        '-b:a', '192k',
                        '-y', temp_file
                    ]
                    print(f"[Minivan] Running FFmpeg command...")
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode != 0:
                        print(f"[Minivan] FFmpeg error:")
                        print(f"FFmpeg stderr: {result.stderr}")
                        print(f"FFmpeg stdout: {result.stdout}")
                        result.check_returncode()  # Raise exception
                    print(f"[Minivan] FFmpeg complete, replacing original file...")
                    os.replace(temp_file, latest_file)
                    print(f"[Minivan] Re-encoding complete: {latest_file}")
                else:
                    print(f"[Minivan] No files found! Checked pattern: {pattern}")
                    minivan_success = False
            except Exception as encode_error:
                print(f"Re-encoding error: {encode_error}")
                import traceback
                traceback.print_exc()
                minivan_success = False
                # Continue anyway - file already downloaded
        
        # Mark this download as no longer active (prevents stale progress updates)
        with active_downloads_lock:
            active_downloads.discard(current_video_id)
            print(f"[DOWNLOAD] Removed {current_video_id} from active_downloads. Active: {active_downloads}")
        
        # Always set final completion status
        safe_update_status(current_video_id, {
            'status': 'completed',
            'progress': 100,
            'message': f'{url} - Complete!'
        })
    except Exception as e:
        with active_downloads_lock:
            active_downloads.discard(current_video_id)
            print(f"[DOWNLOAD] Error - Removed {current_video_id} from active_downloads. Active: {active_downloads}")
        safe_update_status(current_video_id, {
            'status': 'error',
            'progress': 0,
            'error': str(e),
            'message': f'{url} - Error: {str(e)}'
        })


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/quality-presets', methods=['GET'])
def get_quality_presets():
    """Get available quality presets"""
    presets = [
        {'id': key, 'name': value['name']} 
        for key, value in QUALITY_PRESETS.items()
    ]
    return jsonify(presets)


@app.route('/api/video-info', methods=['POST'])
def video_info():
    """Get video info for a URL"""
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    info = get_video_info(url)
    return jsonify(info)


@app.route('/api/download', methods=['POST'])
def download():
    """Start download in background (queued)"""
    data = request.json
    urls = data.get('urls', [])
    download_type = data.get('type', 'audio')  # audio, audio+video
    quality_preset = data.get('quality', 'best')
    
    if not urls:
        return jsonify({'error': 'No URLs provided'}), 400
    
    # Start the worker thread
    start_download_worker()
    
    download_ids = []
    for idx, url in enumerate(urls):
        with download_counter_lock:
            global download_counter
            video_id = f"download_{download_counter}"
            download_counter += 1
        
        download_ids.append(video_id)
        safe_update_status(video_id, {'status': 'queued', 'progress': 0})
        
        # Add to download queue instead of starting thread directly
        download_queue.put((url, download_type, quality_preset, video_id))
    
    return jsonify({'download_ids': download_ids})


@app.route('/api/download-status/<download_id>', methods=['GET'])
def get_download_status(download_id):
    """Get status of a download"""
    status = download_status.get(download_id, {'status': 'not_found'})
    if status.get('status') in ['downloading', 'processing']:
        print(f"[STATUS] {download_id}: {status}")
    return jsonify(status)


@app.route('/api/downloads', methods=['GET'])
def list_downloads():
    """List downloaded files"""
    try:
        files = list(DOWNLOAD_DIR.glob('*'))
        file_list = [
            {
                'name': f.name,
                'size': f.stat().st_size,
                'path': f'/download/{f.name}'
            }
            for f in files if f.is_file()
        ]
        return jsonify(file_list)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/downloads/clear', methods=['POST'])
def clear_downloads():
    """Delete all downloaded files"""
    try:
        files = list(DOWNLOAD_DIR.glob('*'))
        deleted_count = 0
        for f in files:
            if f.is_file():
                f.unlink()
                deleted_count += 1
        return jsonify({'success': True, 'deleted': deleted_count})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    """Download a file"""
    file_path = DOWNLOAD_DIR / filename
    if file_path.exists() and file_path.is_file():
        return send_file(file_path, as_attachment=True)
    return jsonify({'error': 'File not found'}), 404


@app.route('/api/downloads/<filename>', methods=['DELETE'])
def delete_file(filename):
    """Delete a specific file"""
    try:
        file_path = DOWNLOAD_DIR / filename
        if file_path.exists() and file_path.is_file():
            file_path.unlink()
            return jsonify({'success': True})
        return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('APP_PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'prod'
    app.run(host='0.0.0.0', port=port, debug=debug)
