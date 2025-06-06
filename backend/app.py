import os
import tempfile
import time
import logging
import requests
import ffmpeg
from flask import Flask, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv

# --- ENVIRONMENT SETUP ---
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "-")
HOLBOX_ID = "testing"
PORT = 8001

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("holobox-backend")

# --- FLASK + SOCKET.IO SERVER SETUP ---
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='eventlet')

# --- REMOVED: SOCKET.IO CLIENT TO 7006 ---
# --- HTTP ROUTE ---
@app.route("/", methods=["GET"])
def hello():
    return "Hello World!"

# --- UTILITY FUNCTIONS ---
def convert_webm_to_wav(input_bytes):
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(input_bytes)
        tmp.flush()
        in_path = tmp.name
    out_path = in_path.replace(".webm", ".wav")
    try:
        ffmpeg.input(in_path).output(out_path, format='wav', ac=1, ar='16k')\
            .run(quiet=True, overwrite_output=True)
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        for p in (in_path, out_path):
            try: os.unlink(p)
            except: pass

def vad_detect(wav_bytes):
    files = {'audio': ('audio.wav', wav_bytes, 'audio/wav')}
    try:
        start = time.time()
        resp = requests.post("http://0.0.0.0:8002/vad", files=files)
        logger.info(f"[VAD] {int((time.time()-start)*1000)} ms")
        data = resp.json()
        return bool(data.get("speech_timestamps"))
    except Exception as e:
        logger.error(f"[VAD] {e}")
        return False

def stt_transcribe(wav_bytes, lang=None):
    files = {'audio': ('audio.wav', wav_bytes, 'audio/wav')}
    data = {}
    if lang and lang.strip().lower() != "en":
        data["lang"] = lang
    for i in range(3):
        try:
            start = time.time()
            resp = requests.post("http://0.0.0.0:8002/transcribe", files=files, data=data)
            logger.info(f"[STT {i+1}] {int((time.time()-start)*1000)} ms")
            j = resp.json()
            if j.get("transcript"):
                return j["transcript"], j.get("detected_language")
        except Exception as e:
            logger.error(f"[STT {i+1}] {e}")
            time.sleep(0.3)
    return None, None

def call_llm(query, lang, name):
    url = "http://0.0.0.0:8003/chatbot"
    payload = {"query": query, "lang": lang, "name": name, "holoboxId": HOLBOX_ID}
    try:
        start = time.time()
        resp = requests.post(url, json=payload)
        logger.info(f"[LLM] {int((time.time()-start)*1000)} ms")
        return resp.json()
    except Exception as e:
        logger.error(f"[LLM] {e}")
        return None

def prepare_audio(message, lang, sid=None):
    if not isinstance(message, str) or not message.strip() or lang != "en":
        logger.warning(f"[TTS] Skipping TTS: invalid message or unsupported lang ({lang})")
        return None

    # Hardcoded API key and voice ID as in backend.js
    elevenlabs_api_key = "sk_c43245960f2abd4bc26e659bfae26931d7c4df8e6b82bd39"
    voice_id = "uQPOhlzA94sogqmhGLCI"
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"

    payload = {
        "text": message,
        "model_id": "eleven_flash_v2_5",
        "optimize_streaming_latency": 4,
        "voice_settings": {
            "speed": 1.2,
            "stability": 1,
            "similarity_boost": 1,
        },
    }
    headers = {
        "xi-api-key": elevenlabs_api_key,
        "Content-Type": "application/json",
        "Accept": "audio/wav",
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, stream=True, timeout=15)
        if resp.status_code != 200:
            logger.error(f"[TTS] ElevenLabs API error: {resp.status_code}")
            return None
        chunks = []
        total_length = 0
        for chunk in resp.iter_content(4096):
            if chunk:
                total_length += len(chunk)
                chunks.append(chunk)
                # Stream each chunk to the specific client if sid is provided
                if sid:
                    socketio.emit("audio_stream", chunk, room=sid, namespace="/")
                else:
                    socketio.emit("audio_stream", chunk, namespace="/")
        if sid:
            socketio.emit("audio_stream_end", room=sid, namespace="/")
        else:
            socketio.emit("audio_stream_end", namespace="/")
        wav_buffer = b"".join(chunks)
        logger.info(f"[TTS] Generated wav_buffer length: {len(wav_buffer)}")
        # Always emit the full audio buffer to the client for compatibility
        if sid and wav_buffer:
            socketio.emit("audio", wav_buffer, room=sid, namespace="/")
        return wav_buffer
    except Exception as e:
        logger.error(f"[TTS] {e}")
        return None

# --- SOCKET.IO EVENTS ---
@socketio.on("connect")
def on_connect():
    logger.info(f"Client connected: {request.sid}")

@socketio.on("disconnect")
def on_disconnect():
    logger.info(f"Client disconnected: {request.sid}")

@socketio.on("send_audio")
def handle_send_audio(data):
    sid = request.sid
    socketio.start_background_task(audio_pipeline, sid, data)

def audio_pipeline(sid, data):
    audio_bytes = data.get("audio")
    if not audio_bytes:
        socketio.emit("chat_response", {"error": "No audio data"}, room=sid, namespace="/")
        return
    lang = data.get("lang")
    name = data.get("name", "")
    wav = convert_webm_to_wav(audio_bytes)
    if not vad_detect(wav):
        socketio.emit("chat_response", {"error": "No speech detected"}, room=sid, namespace="/")
        return
    transcript, det_lang = stt_transcribe(wav, lang)
    if det_lang:
        lang = det_lang
    if not transcript:
        socketio.emit("chat_response", {"error": "Transcription failed"}, room=sid, namespace="/")
        return
    # REMOVED: client_sio.emit("json_obj", "START_THINKING")
    llm_res = call_llm(transcript, lang, name)
    if not llm_res:
        socketio.emit("chat_response", {"error": "LLM failed"}, room=sid, namespace="/")
        return
    answer = llm_res.get("answer", "")
    audio_buf = prepare_audio(answer, lang, sid=sid)
    socketio.emit("chat_response", {
        "transcript": transcript,
        "chat": {"script": "done", "answer": answer},
        "audio": audio_buf
    }, room=sid, namespace="/")
    time.sleep(1.85)
    # REMOVED: client_sio.emit("json_obj", "STOP_THINKING")

# --- START SERVER ---
if __name__ == "__main__":
    logger.info(f"Starting server on 0.0.0.0:{PORT}")
    socketio.run(app, host="0.0.0.0", port=PORT)
