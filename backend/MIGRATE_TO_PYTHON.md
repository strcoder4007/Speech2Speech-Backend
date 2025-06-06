# Migration Guide: Porting `backend/backend.js` to Python

This document details the steps required to migrate the Node.js backend (`backend/backend.js`) to Python, ensuring all functionalities are preserved and using the best-fit libraries for a robust, working solution.

---

## 1. Prerequisites

- **Python 3.8+** installed.
- **ffmpeg** installed on your system (for audio processing).
- The following Python packages (install with pip):

  ```bash
  pip install flask flask-cors python-dotenv requests python-multipart fastapi silero-vad faster-whisper scipy ffmpeg-python python-socketio eventlet openai
  ```

---

## 2. Environment Variables

- Use `python-dotenv` to load environment variables from a `.env` file.

  ```python
  from dotenv import load_dotenv
  load_dotenv()
  import os
  OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "-")
  ```

---

## 3. Web Server and CORS

- Use **Flask** (or FastAPI) for the HTTP server.
- Use **flask-cors** for CORS support.

  ```python
  from flask import Flask
  from flask_cors import CORS

  app = Flask(__name__)
  CORS(app)
  ```

---

## 4. Socket.IO Server

- Use **python-socketio** for real-time communication.
- Use **eventlet** or **gevent** for async support.

  ```python
  import socketio
  import eventlet
  import eventlet.wsgi

  sio = socketio.Server(cors_allowed_origins='*', async_mode='eventlet')
  app = Flask(__name__)
  app = socketio.WSGIApp(sio, app)
  ```

---

## 5. Socket.IO Client (to connect to another server)

- Use **python-socketio** client to connect to the external server (`http://0.0.0.0:7006`).

  ```python
  import socketio

  client_sio = socketio.Client()
  client_sio.connect("http://0.0.0.0:7006")
  ```

---

## 6. Audio File Handling and Conversion

- Use **ffmpeg-python** or `subprocess` to convert audio formats (webm to wav, mono, 16kHz).
- Use `tempfile` for temporary files.

  ```python
  import ffmpeg
  import tempfile

  # Save buffer to temp file, convert, read back
  ```

---

## 7. File Uploads (if needed)

- Use Flask's file upload handling or FastAPI's `UploadFile`.

---

## 8. VAD and STT Requests

- Use **requests** to POST audio to VAD and STT endpoints, as in JS.
- Use `files` parameter for multipart/form-data.

  ```python
  import requests

  files = {'audio': ('audio.wav', wav_audio_buffer, 'audio/wav')}
  response = requests.post("http://0.0.0.0:8002/vad", files=files)
  ```

---

## 9. Retry Logic

- Use a loop with `try/except` and `time.sleep` for retrying STT requests.

---

## 10. LLM/Chatbot API Call

- Use **requests** to POST to the chatbot backend (`http://0.0.0.0:8003/chatbot`).

---

## 11. TTS via ElevenLabs

- Use **requests** to POST to ElevenLabs API.
- Use `stream=True` to handle audio streaming.
- Emit audio chunks to frontend via Socket.IO as they arrive.

  ```python
  response = requests.post(elevenlabs_url, json=payload, headers=headers, stream=True)
  for chunk in response.iter_content(chunk_size=4096):
      sio.emit("audio_stream", chunk)
  sio.emit("audio_stream_end")
  ```

---

## 12. Emit Events to Frontend

- Use `sio.emit()` to send events/data to connected clients (audio, chat_response, etc.).

---

## 13. Handle Incoming Events from Frontend

- Use `@sio.on("send_audio")` to handle audio uploads from frontend.
- Process audio, run VAD/STT, call chatbot, TTS, and emit results.

---

## 14. Handle Incoming Events from Socket.IO Client

- Use `@client_sio.on("message")` to handle messages from the other server.
- Accumulate message text, detect sentence boundaries, call TTS, and emit audio.

---

## 15. Utility Functions

- Use Python's `uuid`, `os`, `hashlib`, `tempfile`, and `logging` modules for utility tasks.

---

## 16. Obsolete/Unused Functions

- Omit or stub out functions like `lipSyncMessage` if not needed.

---

## 17. Start the Server

- Use `eventlet.wsgi.server()` to run the combined Flask + Socket.IO app.

  ```python
  if __name__ == "__main__":
      eventlet.wsgi.server(eventlet.listen(('', 8001)), app)
  ```

---

## 18. Testing

- Test all endpoints and events with your frontend.
- Ensure audio streaming, VAD/STT, chatbot, and TTS all work as expected.

---

## 19. (Optional) Refactor for FastAPI

- If you prefer async and type hints, you can use FastAPI with `python-socketio`'s ASGI integration.

---

### JS to Python Library Mapping

| JS/Node.js                | Python Equivalent                |
|---------------------------|----------------------------------|
| express                   | Flask / FastAPI                  |
| cors                      | flask-cors / FastAPI CORS        |
| socket.io                 | python-socketio                  |
| multer                    | Flask/FastAPI upload             |
| fluent-ffmpeg             | ffmpeg-python / subprocess       |
| axios                     | requests                         |
| openai                    | openai                           |
| dotenv                    | python-dotenv                    |
| uuid                      | uuid                             |
| os                        | os                               |
| crypto                    | hashlib / secrets                |
| fs                        | open, pathlib, os                |

---

## Example Directory Structure

```
backend/
  ├── app.py                # Main Flask + Socket.IO server
  ├── tts.py                # TTS (ElevenLabs) logic
  ├── audio_utils.py        # Audio conversion, VAD, STT helpers
  ├── requirements.txt
  └── .env
```

---

## Key Python Libraries to Use

- Flask / FastAPI
- flask-cors
- python-dotenv
- python-socketio
- eventlet
- requests
- ffmpeg-python
- openai
- uuid, os, tempfile, logging (stdlib)

---

**Follow these steps to migrate your backend to Python. For any code-level questions or implementation help, refer to the official documentation of each library or request a sample code skeleton.**
