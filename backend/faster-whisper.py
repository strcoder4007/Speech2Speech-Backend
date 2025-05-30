import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
import tempfile
import os
import time
from faster_whisper import WhisperModel
from flask import Flask, request, jsonify

# Silero VAD imports
from silero_vad import load_silero_vad, read_audio, get_speech_timestamps

app = Flask(__name__)

# Load Silero VAD model at startup
print("Loading Silero VAD model...")
vad_model = load_silero_vad()
print("Silero VAD model loaded.")

# Load the model once at startup "deepdml/faster-distil-whisper-large-v3.5"
print("Loading model (deepdml/faster-whisper-large-v3-turbo-ct2) on GPU...")
model = WhisperModel("deepdml/faster-whisper-large-v3-turbo-ct2", device="cuda", compute_type="int8_float16")
print("Model loaded.")

@app.route("/vad", methods=["POST"])
def vad_endpoint():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file uploaded"}), 400

    audio_file = request.files["audio"]
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmpfile:
        audio_file.save(tmpfile)
        audio_path = tmpfile.name

    try:
        wav = read_audio(audio_path)
        speech_timestamps = get_speech_timestamps(
            wav,
            vad_model,
            return_seconds=True,
        )
        return jsonify({"speech_timestamps": speech_timestamps})
    finally:
        os.remove(audio_path)

@app.route("/transcribe", methods=["POST"])
def transcribe_endpoint():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file uploaded"}), 400

    audio_file = request.files["audio"]
    # Get language from request, default to None for auto-detection
    lang_param = request.form.get("lang", None)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmpfile:
        audio_file.save(tmpfile)
        audio_path = tmpfile.name

    try:
        start_time = time.time()
        # Use the lang_param for transcription
        segments, info = model.transcribe(audio_path, language=lang_param)
        end_time = time.time()
        transcription_time = end_time - start_time

        transcript = ""
        for segment in segments:
            transcript += segment.text.strip() + " "

        transcript = transcript.strip()
        result = {
            "transcript": transcript,
            "transcription_time": transcription_time,
            "detected_language": info.language
        }
        return jsonify(result)
    finally:
        os.remove(audio_path)

def record_audio(duration=10, fs=16000):
    print(f"Recording for {duration} seconds...")
    audio = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='int16')
    sd.wait()
    return audio, fs

def save_wav(audio, fs, filename):
    wav.write(filename, fs, audio)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Faster Whisper STT")
    parser.add_argument("--record", action="store_true", help="Record from mic and transcribe")
    parser.add_argument("--file", type=str, help="Transcribe a given audio file")
    parser.add_argument("--serve", action="store_true", help="Run HTTP server")
    parser.add_argument("--duration", type=float, default=10, help="Recording duration (seconds)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Flask host")
    parser.add_argument("--port", type=int, default=8002, help="Flask port")
    parser.add_argument("--lang", type=str, default=None, help="Language code for transcription (e.g., 'en', 'hi'). If not specified, attempts auto-detection.")
    args = parser.parse_args()

    if args.serve:
        app.run(host=args.host, port=args.port)
        return

    if args.record:
        audio, fs = record_audio(duration=args.duration, fs=16000)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmpfile:
            save_wav(audio, fs, tmpfile.name)
            audio_path = tmpfile.name
        print("Transcribing recorded audio...")
        start_time = time.time()
        segments, info = model.transcribe(audio_path)
        end_time = time.time()
        transcription_time = end_time - start_time
        print(f"Detected language: {info.language}")
        print(f"Transcription took {transcription_time:.2f} seconds.")
        for segment in segments:
            print("[%.2fs -> %.2fs] %s" % (segment.start, segment.end, segment.text))
        os.remove(audio_path)
        return

    if args.file:
        audio_path = args.file
        print(f"Transcribing file: {audio_path}")
        start_time = time.time()
        segments, info = model.transcribe(audio_path)
        end_time = time.time()
        transcription_time = end_time - start_time
        print(f"Detected language: {info.language}")
        print(f"Transcription took {transcription_time:.2f} seconds.")
        for segment in segments:
            print("[%.2fs -> %.2fs] %s" % (segment.start, segment.end, segment.text))
        return

    parser.print_help()

if __name__ == "__main__":
    main()
