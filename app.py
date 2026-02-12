from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import os
from pathlib import Path
import threading
import queue
import subprocess
import glob
import json

app = Flask(__name__)

# Configuration
DOWNLOAD_DIR = Path("/downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Status directory for tracking long-running jobs
STATUS_DIR = Path("/downloads/.status")
STATUS_DIR.mkdir(exist_ok=True)

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

# Store download status in memory as fallback
download_status = {}
download_status_lock = threading.Lock()

# Download counter for unique ID generation
download_counter = 0
download_counter_lock = threading.Lock()

# Track active downloads
active_downloads = set()
active_downloads_lock = threading.Lock()


def safe_update_status(video_id, status_dict):
    """Update download status to both file and memory"""
    # Update memory
    with download_status_lock:
        download_status[video_id] = status_dict.copy()
    
    # Update file
    status_file = STATUS_DIR / f"{video_id}.json"
    try:
        with open(status_file, 'w') as f:
            json.dump(status_dict, f)
    except Exception as e:
        print(f"Error writing status file for {video_id}: {e}")


def get_status_from_file(video_id):
    """Read status from file if it exists"""
    status_file = STATUS_DIR / f"{video_id}.json"
    if status_file.exists():
        try:
            with open(status_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading status file for {video_id}: {e}")
    
    # Fallback to memory
    with download_status_lock:
        return download_status.get(video_id, {'status': 'not_found'})


def cleanup_old_status_files(max_age_seconds=86400):
    """Remove status files older than max_age_seconds (default 24 hours)"""
    import time
    current_time = time.time()
    try:
        for status_file in STATUS_DIR.glob('*.json'):
            if current_time - status_file.stat().st_mtime > max_age_seconds:
                status_file.unlink()
    except Exception as e:
        print(f"Error cleaning up status files: {e}")


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
            url, download_type, quality_preset, speed_limit_mbps, video_id = download_queue.get()
            # Clear any stale progress data before starting
            safe_update_status(video_id, {'status': 'queued', 'progress': 0})
            download_video(url, download_type, quality_preset, speed_limit_mbps, video_id)
            download_queue.task_done()
        except Exception as e:
            print(f"Worker error: {e}")
            download_queue.task_done()


def start_download_worker():
    """Start the download worker thread if not already running"""
    global download_worker_thread
    if download_worker_thread is None or not download_worker_thread.is_alive():
        # Clean up old status files on worker start
        cleanup_old_status_files()
        download_worker_thread = threading.Thread(target=download_worker, daemon=True)
        download_worker_thread.start()


def download_video(url, download_type, quality_preset, speed_limit_mbps, video_id):
    """Download video/audio in background"""
    try:
        # Create a local reference to video_id to ensure it's captured correctly in the closure
        current_video_id = video_id
        
        # Calculate rate limit in bytes/sec from MB/s (0 = unlimited)
        # 1 MB/s = 1,048,576 bytes/second
        if speed_limit_mbps == 0:
            rate_limit_bytes = None  # Unlimited - don't set ratelimit
        else:
            rate_limit_bytes = speed_limit_mbps * 1024 * 1024
        
        # Extract video title and expected size for progress messages
        video_title = "Unknown Video"
        expected_size = 0
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                video_title = info.get('title', 'Unknown Video')
                # Get expected file size (may not be accurate for all formats)
                expected_size = info.get('filesize') or info.get('filesize_approx', 0)
        except Exception as e:
            print(f"[INFO] Could not extract info for {url}: {e}")
        
        # Helper function for formatting file sizes
        def format_size(bytes_val):
            if bytes_val >= 1024 * 1024 * 1024:  # GB
                return f"{bytes_val / (1024 * 1024 * 1024):.1f} GB"
            elif bytes_val >= 1024 * 1024:  # MB
                return f"{bytes_val / (1024 * 1024):.1f} MB"
            elif bytes_val >= 1024:  # KB
                return f"{bytes_val / 1024:.1f} KB"
            else:  # B
                return f"{bytes_val} B"
        
        # Mark this download as active
        with active_downloads_lock:
            active_downloads.add(current_video_id)
            print(f"[DOWNLOAD] Added {current_video_id} to active_downloads. Active: {active_downloads}")
        
        safe_update_status(current_video_id, {
            'status': 'downloading',
            'progress': 0,
            'message': f'Starting download: {video_title}' + (f' ({format_size(expected_size)})' if expected_size > 0 else ''),
            'expected_size': expected_size,
            'video_title': video_title,
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
                speed = d.get('speed')  # Speed in bytes per second
                if speed is None:
                    speed = 0
                
                if total > 0:
                    progress = int((downloaded / total) * 100)
                    
                    # Format speed for display
                    if speed > 0:
                        if speed >= 1024 * 1024:  # Show in Mbps if >= 1 MB/s
                            speed_display = f"{speed / (1024 * 1024):.1f} MB/s"
                        elif speed >= 1024:  # Show in KB/s if >= 1 KB/s
                            speed_display = f"{speed / 1024:.1f} KB/s"
                        else:  # Show in B/s
                            speed_display = f"{speed:.0f} B/s"
                        speed_info = f" at {speed_display}"
                    else:
                        speed_info = ""
                    
                    if progress % 10 == 0 or progress > 95:  # Log every 10% or when near end
                        print(f"[HOOK] {current_video_id}: Downloading {progress}% ({downloaded}/{total})")
                    # Format size information
                    def format_size(bytes_val):
                        if bytes_val >= 1024 * 1024 * 1024:  # GB
                            return f"{bytes_val / (1024 * 1024 * 1024):.1f} GB"
                        elif bytes_val >= 1024 * 1024:  # MB
                            return f"{bytes_val / (1024 * 1024):.1f} MB"
                        elif bytes_val >= 1024:  # KB
                            return f"{bytes_val / 1024:.1f} KB"
                        else:  # B
                            return f"{bytes_val} B"
                    
                    size_info = f" ({format_size(downloaded)}/{format_size(total)})"
                    
                    safe_update_status(current_video_id, {
                        'status': 'downloading',
                        'progress': progress,
                        'message': f"{video_title} - Downloading: {progress}%{speed_info}{size_info}",
                    })
            elif d['status'] == 'processing':
                print(f"[HOOK] {current_video_id}: Processing")
                safe_update_status(current_video_id, {
                    'status': 'processing',
                    'progress': 50,
                    'message': f"{video_title} - Post-processing...",
                })
            elif d['status'] == 'finished':
                print(f"[HOOK] {current_video_id}: Finished downloading, encoding...")
                safe_update_status(current_video_id, {
                    'status': 'finished',
                    'progress': 100,
                    'message': f"{video_title} - Encoding...",
                })
        
        if download_type == 'audio':
            ydl_opts = {
                'format': 'bestaudio/best',
                'progress_hooks': [progress_hook],
                'outtmpl': output_template,
                'quiet': False,
                'socket_timeout': 30,
                'js_runtimes': {'node': {'path': '/usr/local/bin/node'}},
                'remote_components': ['ejs:github'],
                'restrictfilenames': True,  # Remove special characters from filenames
            }
            if rate_limit_bytes is not None:
                ydl_opts['ratelimit'] = rate_limit_bytes
            # Audio-only uses FFmpeg extraction
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        else:  # audio+video
            ydl_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'progress_hooks': [progress_hook],
                'outtmpl': output_template,
                'quiet': False,
                'socket_timeout': 30,
                'merge_output_format': 'mp4',
                'js_runtimes': {'node': {'path': '/usr/local/bin/node'}},
                'remote_components': ['ejs:github'],
                'restrictfilenames': True,  # Remove special characters from filenames
            }
            if rate_limit_bytes is not None:
                ydl_opts['ratelimit'] = rate_limit_bytes
        
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
                'message': f'{video_title} - Re-encoding for Minivan...'
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
                    
                    # First, get the duration of the input file using ffprobe
                    probe_cmd = [
                        'ffprobe', '-v', 'quiet', '-print_format', 'json', 
                        '-show_format', '-show_streams', latest_file
                    ]
                    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
                    if probe_result.returncode != 0:
                        print(f"[Minivan] ffprobe error: {probe_result.stderr}")
                        raise Exception("Failed to probe video duration")
                    
                    import json as json_lib
                    probe_data = json_lib.loads(probe_result.stdout)
                    duration = float(probe_data['format']['duration'])
                    print(f"[Minivan] Input duration: {duration} seconds")
                    
                    # Run ffmpeg re-encoding with real-time progress monitoring
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
                    
                    # Use Popen to monitor progress in real-time
                    process = subprocess.Popen(
                        cmd, 
                        stderr=subprocess.PIPE, 
                        stdout=subprocess.PIPE, 
                        text=True,
                        bufsize=1,
                        universal_newlines=True
                    )
                    
                    # Monitor FFmpeg progress from stderr
                    import re
                    time_pattern = re.compile(r'time=(\d+):(\d+):(\d+\.\d+)')
                    
                    while True:
                        line = process.stderr.readline()
                        if not line and process.poll() is not None:
                            break
                        
                        # Parse time from FFmpeg output
                        match = time_pattern.search(line)
                        if match:
                            hours, minutes, seconds = map(float, match.groups())
                            current_time = hours * 3600 + minutes * 60 + seconds
                            
                            # Calculate progress from 75% to 99% based on encoding progress
                            if duration > 0:
                                encoding_progress = min(current_time / duration, 1.0)
                                overall_progress = 75 + (encoding_progress * 24)  # 75% to 99%
                                
                                safe_update_status(current_video_id, {
                                    'status': 'processing',
                                    'progress': int(overall_progress),
                                    'message': f'{video_title} - Re-encoding for Minivan: {int(encoding_progress * 100)}%'
                                })
                    
                    # Check if FFmpeg succeeded
                    if process.returncode != 0:
                        stdout, stderr = process.communicate()
                        print(f"[Minivan] FFmpeg error:")
                        print(f"FFmpeg stderr: {stderr}")
                        print(f"FFmpeg stdout: {stdout}")
                        raise Exception("FFmpeg re-encoding failed")
                    
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
            'message': f'{video_title} - Complete!'
        })
    except Exception as e:
        with active_downloads_lock:
            active_downloads.discard(current_video_id)
            print(f"[DOWNLOAD] Error - Removed {current_video_id} from active_downloads. Active: {active_downloads}")
        safe_update_status(current_video_id, {
            'status': 'error',
            'progress': 0,
            'error': str(e),
            'message': f'{video_title} - Error: {str(e)}'
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
    download_type = data.get('type', 'audio+video')  # audio, audio+video
    quality_preset = data.get('quality', 'best')
    speed_limit_mbps = data.get('speed', 5)  # Default to 5 Mbps if not specified
    
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
        download_queue.put((url, download_type, quality_preset, speed_limit_mbps, video_id))
    
    return jsonify({'download_ids': download_ids})


@app.route('/api/download-status/<download_id>', methods=['GET'])
def get_download_status(download_id):
    """Get status of a download"""
    status = get_status_from_file(download_id)
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
            if f.is_file() and not f.name.startswith('.'):
                f.unlink()
                deleted_count += 1
        
        # Also clean up status files
        status_files = list(STATUS_DIR.glob('*.json'))
        for f in status_files:
            f.unlink()
        
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
