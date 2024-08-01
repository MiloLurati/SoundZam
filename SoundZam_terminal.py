import os
import re
import sys
from pydub import AudioSegment
from shazamio import Shazam
from sclib import SoundcloudAPI, Track
from tqdm.asyncio import tqdm as tqdm_asyncio
import asyncio

async def identify_tracks(audio_path):
    print("Identifying tracks...")
    shazam = Shazam()
    audio = AudioSegment.from_file(audio_path)
    duration = len(audio)
    segment_duration = 60000  # 60 seconds
    tracks = []
    seen_track_ids = set()
    total_segments = duration // segment_duration

    for start_time in tqdm_asyncio(range(0, duration, segment_duration), desc="Processing segments"):
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

def main():
    if len(sys.argv) != 2:
        print("Usage: python SoundZam.py <soundcloud_url>")
        sys.exit(1)

    soundcloud_url = sys.argv[1]
    audio_path = download_soundcloud_audio(soundcloud_url)

    tracks = asyncio.run(identify_tracks(audio_path))

    for track in tracks:
        print(f"{track['subtitle']} - {track['title']}")

    os.remove(audio_path)
    if os.path.exists("temp_segment.mp3"):
        os.remove("temp_segment.mp3")

if __name__ == "__main__":
    main()
