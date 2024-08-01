from flask import Flask, request, render_template, jsonify
import os
import re
import asyncio
from pydub import AudioSegment
from shazamio import Shazam
from sclib import SoundcloudAPI, Track
from tqdm.asyncio import tqdm as tqdm_asyncio
from pytube import YouTube
import time
import yt_dlp

app = Flask(__name__)

# Global variables to store progress and result
download_progress = 0
analysis_progress = 0
result = None

def identify_tracks(audio_path):
    global analysis_progress
    print("Identifying tracks...")
    shazam = Shazam()
    audio = AudioSegment.from_file(audio_path)
    duration = len(audio)
    segment_duration = 120000  # 120 seconds
    tracks = []
    seen_track_ids = set()

    total_segments = duration // segment_duration
    for i, start_time in enumerate(range(0, duration, segment_duration)):
        segment = audio[start_time:start_time + segment_duration]
        segment_path = "temp_segment.mp3"
        segment.export(segment_path, format="mp3")

        result = asyncio.run(shazam.recognize(segment_path))
        if 'track' in result:
            track = result['track']
            track_id = track['key']
            if track_id not in seen_track_ids:
                tracks.append(track)
                seen_track_ids.add(track_id)
        
        analysis_progress = int((i + 1) / total_segments * 100)
        print(f"Analysis Progress: {analysis_progress}%")

    return tracks

def sanitize_filename(filename):
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    return sanitized

def download_soundcloud_audio(url):
    global download_progress
    print("Downloading audio from SoundCloud...")
    download_progress = 50  # Set to 50% when download starts
    api = SoundcloudAPI()
    track = api.resolve(url)

    if type(track) is not Track:
        raise Exception("The URL does not resolve to a track.")

    filename = f'{track.artist} - {track.title}.mp3'
    sanitized_filename = sanitize_filename(filename)

    audio_path = os.path.join(os.getcwd(), sanitized_filename)

    with open(audio_path, 'wb+') as file:
        track.write_mp3_to(file)

    download_progress = 100  # Set to 100% when download completes
    return audio_path

def download_youtube_audio(url):
    global download_progress
    print("Downloading audio from YouTube...")
    download_progress = 50  # Set to 50% when download starts
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': '%(title)s.%(ext)s',
            'progress_hooks': [yt_dlp_progress_hook],
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            audio_path = os.path.splitext(filename)[0] + '.mp3'
        
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Failed to download audio to {audio_path}")
        
        download_progress = 100  # Set to 100% when download completes
        return audio_path
    except Exception as e:
        print(f"Error in download_youtube_audio: {str(e)}")
        raise

def yt_dlp_progress_hook(d):
    global download_progress
    if d['status'] == 'finished':
        download_progress = 90
    elif d['status'] == 'downloading':
        download_progress = 50 + int(d['downloaded_bytes'] * 40 / d['total_bytes'])

@app.route('/progress')
def get_progress():
    global analysis_progress
    return jsonify({"progress": analysis_progress})

@app.route('/', methods=['GET', 'POST'])
def index():
    global download_progress, analysis_progress, result
    if request.method == 'POST':
        url = request.form['url']
        try:
            download_progress = 0
            analysis_progress = 0
            
            if 'soundcloud.com' in url:
                audio_path = download_soundcloud_audio(url)
            elif 'youtube.com' in url or 'youtu.be' in url:
                try:
                    audio_path = download_youtube_audio(url)
                    print(f"YouTube audio downloaded to: {audio_path}")
                except Exception as yt_error:
                    return jsonify({"error": f"YouTube download error: {str(yt_error)}"}), 400
            else:
                raise ValueError("Unsupported URL. Please provide a SoundCloud or YouTube link.")
            
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"Audio file not found at {audio_path}")
            
            try:
                tracks = identify_tracks(audio_path)
            except Exception as identify_error:
                return jsonify({"error": f"Track identification error: {str(identify_error)}"}), 400
            
            result = [{"artist": track['subtitle'], "title": track['title']} for track in tracks]
            os.remove(audio_path)
            if os.path.exists("temp_segment.mp3"):
                os.remove("temp_segment.mp3")
            response = jsonify({"result": result})
            analysis_progress = 0  # Reset progress after sending response
            return response
        except Exception as e:
            analysis_progress = 0  # Reset progress in case of error
            return jsonify({"error": str(e)}), 400
    return render_template('index.html')

if __name__ == "__main__":
    app.run(debug=True)