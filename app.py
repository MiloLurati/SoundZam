from flask import Flask, render_template, request, Response, jsonify
import os
import re
import sys
from pydub import AudioSegment
from shazamio import Shazam
from sclib import SoundcloudAPI, Track
from tqdm.asyncio import tqdm as tqdm_asyncio
import asyncio
from youtubesearchpython import VideosSearch
import json
import webbrowser
import threading

app = Flask(__name__)

# Global variable to store progress
progress = {"value": 0, "status": ""}

def set_progress(value, status):
    global progress
    progress["value"] = value
    progress["status"] = status

async def identify_tracks(audio_path):
    print("Identifying tracks...")
    shazam = Shazam()
    audio = AudioSegment.from_file(audio_path)
    duration = len(audio)
    segment_duration = 60000  # 60 seconds
    tracks = []
    seen_track_ids = set()
    total_segments = duration // segment_duration

    for i, start_time in enumerate(range(0, duration, segment_duration)):
        segment = audio[start_time:start_time + segment_duration]
        segment_path = "temp_segment.mp3"
        segment.export(segment_path, format="mp3")

        result = await shazam.recognize(segment_path)
        if 'track' in result:
            track = result['track']
            track_id = track['key']
            if track_id not in seen_track_ids:
                tracks.append(track)
                seen_track_ids.add(track_id)
        
        # Update progress
        progress_value = int((i + 1) / total_segments * 100)
        set_progress(progress_value, f"Processing segment {i + 1} of {total_segments}")

    return tracks

def sanitize_filename(filename):
    """
    Remove or replace invalid characters in a filename.
    """
    # Replace invalid characters with an underscore or other suitable character
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    return sanitized

def download_soundcloud_audio(url):
    print("Downloading audio from SoundCloud...")
    api = SoundcloudAPI()
    track = api.resolve(url)

    if type(track) is not Track:
        raise Exception("The URL does not resolve to a track.")

    # Create a sanitized filename
    filename = f'{track.artist} - {track.title}.mp3'
    sanitized_filename = sanitize_filename(filename)

    audio_path = os.path.join(os.getcwd(), sanitized_filename)

    with open(audio_path, 'wb+') as file:
        track.write_mp3_to(file)

    return audio_path

def get_youtube_link(artist, title):
    search_query = f"{artist} - {title}"
    videos_search = VideosSearch(search_query, limit=1)
    results = videos_search.result()
    
    if results['result']:
        video = results['result'][0]
        return video['link'], video['id']
    return None, None

def open_browser():
    webbrowser.open_new('http://127.0.0.1:5000/')

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Reset progress at the start of each request
        set_progress(0, "Starting...")
        soundcloud_url = request.form['soundcloud_url']
        try:
            set_progress(5, "Downloading audio from SoundCloud...")
            audio_path = download_soundcloud_audio(soundcloud_url)
            
            set_progress(10, "Starting track identification...")
            tracks = asyncio.run(identify_tracks(audio_path))
            
            set_progress(90, "Fetching YouTube links...")
            results = []
            for track in tracks:
                artist = track['subtitle']
                title = track['title']
                youtube_link, youtube_id = get_youtube_link(artist, title)
                results.append({
                    'artist': artist,
                    'title': title,
                    'youtube_link': youtube_link,
                    'youtube_id': youtube_id
                })
            
            os.remove(audio_path)
            if os.path.exists("temp_segment.mp3"):
                os.remove("temp_segment.mp3")
            
            set_progress(100, "Complete")
            return jsonify({'results': results})
        except Exception as e:
            error_message = str(e)
            set_progress(0, "Error occurred")
            return jsonify({'error': error_message}), 400
    
    return render_template('index.html')

@app.route('/progress')
def progress_stream():
    def generate():
        while True:
            yield f"data: {json.dumps(progress)}\n\n"
            if progress['value'] == 100:
                break
            asyncio.sleep(0.5)
    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    # Open the browser after a short delay
    threading.Timer(1.5, open_browser).start()
    # Run the Flask app
    app.run(debug=True, threaded=True)