from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import os
import uuid
import threading
import time

app = Flask(__name__)
CORS(app)

# Thư mục lưu video tạm thời
DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# Dictionary lưu trạng thái download
downloads = {}

def clean_old_files():
    """Xóa file cũ sau 30 phút"""
    while True:
        time.sleep(1800)  # 30 phút
        current_time = time.time()
        for filename in os.listdir(DOWNLOAD_FOLDER):
            file_path = os.path.join(DOWNLOAD_FOLDER, filename)
            if os.path.isfile(file_path):
                file_age = current_time - os.path.getmtime(file_path)
                if file_age > 1800:  # 30 phút
                    try:
                        os.remove(file_path)
                    except:
                        pass

# Bắt đầu thread dọn dẹp
cleanup_thread = threading.Thread(target=clean_old_files, daemon=True)
cleanup_thread.start()

@app.route('/api/info', methods=['POST'])
def get_video_info():
    """Lấy thông tin video"""
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Lấy các format có sẵn
            formats = []
            if 'formats' in info:
                for f in info['formats']:
                    if f.get('ext') and f.get('format_note'):
                        formats.append({
                            'format_id': f.get('format_id'),
                            'ext': f.get('ext'),
                            'quality': f.get('format_note', 'unknown'),
                            'filesize': f.get('filesize', 0),
                            'type': 'video' if f.get('vcodec') != 'none' else 'audio'
                        })
            
            video_info = {
                'id': info.get('id'),
                'title': info.get('title'),
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration'),
                'formats': formats,
                'webpage_url': info.get('webpage_url')
            }
            
        return jsonify(video_info)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/download', methods=['POST'])
def download_video():
    """Tải video"""
    data = request.json
    url = data.get('url')
    format_id = data.get('format_id', 'best')
    download_type = data.get('type', 'video')  # 'video' hoặc 'audio'
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    # Tạo ID duy nhất cho file
    file_id = str(uuid.uuid4())
    downloads[file_id] = {'status': 'downloading', 'filename': None}
    
    try:
        if download_type == 'audio':
            # Tải audio MP3
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': f'{DOWNLOAD_FOLDER}/{file_id}.%(ext)s',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': True,
                'no_warnings': True
            }
        else:
            # Tải video với format cụ thể
            ydl_opts = {
                'format': format_id if format_id != 'best' else 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': f'{DOWNLOAD_FOLDER}/{file_id}.%(ext)s',
                'merge_output_format': 'mp4',
                'quiet': True,
                'no_warnings': True
            }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Tìm file đã tải
            if download_type == 'audio':
                filename = f"{file_id}.mp3"
                filepath = os.path.join(DOWNLOAD_FOLDER, filename)
            else:
                filename = f"{file_id}.mp4"
                filepath = os.path.join(DOWNLOAD_FOLDER, filename)
            
            if os.path.exists(filepath):
                downloads[file_id] = {
                    'status': 'completed',
                    'filename': filename,
                    'filepath': filepath,
                    'title': info.get('title', 'video')
                }
            else:
                # Tìm file với extension phù hợp
                for f in os.listdir(DOWNLOAD_FOLDER):
                    if f.startswith(file_id):
                        filepath = os.path.join(DOWNLOAD_FOLDER, f)
                        downloads[file_id] = {
                            'status': 'completed',
                            'filename': f,
                            'filepath': filepath,
                            'title': info.get('title', 'video')
                        }
                        break
        
        return jsonify({
            'success': True,
            'file_id': file_id,
            'title': info.get('title', 'video')
        })
    
    except Exception as e:
        downloads[file_id]['status'] = 'error'
        return jsonify({'error': str(e)}), 400

@app.route('/api/download/<file_id>', methods=['GET'])
def get_file(file_id):
    """Trả file cho người dùng tải về"""
    if file_id not in downloads or downloads[file_id]['status'] != 'completed':
        return jsonify({'error': 'File not ready'}), 404
    
    filepath = downloads[file_id]['filepath']
    filename = downloads[file_id]['title']
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    
    # Lấy extension
    ext = os.path.splitext(filepath)[1]
    download_name = f"{filename}{ext}"
    
    return send_file(
        filepath,
        as_attachment=True,
        download_name=download_name,
        mimetype='application/octet-stream'
    )

@app.route('/api/status/<file_id>', methods=['GET'])
def check_status(file_id):
    """Kiểm tra trạng thái download"""
    if file_id in downloads:
        return jsonify(downloads[file_id])
    return jsonify({'error': 'File ID not found'}), 404

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
