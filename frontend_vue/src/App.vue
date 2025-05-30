<template>
  <div id="app">
    <h1>Holobox Chatbot</h1>

    <div class="controls">
      <button @click="toggleRecording" :disabled="isProcessing" class="control-button" :class="{ 'is-recording': isRecording }">
        <span v-if="isRecording">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-stop-fill" viewBox="0 0 16 16">
            <path d="M5 3.5h6A1.5 1.5 0 0 1 12.5 5v6a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 11V5A1.5 1.5 0 0 1 5 3.5"/>
          </svg>
          Stop Recording
        </span>
        <span v-else>
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-mic-fill" viewBox="0 0 16 16">
            <path d="M5 3a3 3 0 0 1 6 0v5a3 3 0 0 1-6 0z"/>
            <path d="M3.5 6.5A.5.5 0 0 1 4 7v1a4 4 0 0 0 8 0V7a.5.5 0 0 1 1 0v1a5 5 0 0 1-4.5 4.975V15h3a.5.5 0 0 1 0 1h-7a.5.5 0 0 1 0-1h3v-2.025A5 5 0 0 1 3 8V7a.5.5 0 0 1 .5-.5"/>
          </svg>
          Start Recording
        </span>
      </button>
      <button @click="resetChat" :disabled="isRecording || isProcessing" class="control-button reset-button">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-arrow-counterclockwise" viewBox="0 0 16 16">
          <path fill-rule="evenodd" d="M8 3a5 5 0 1 1-4.546 2.914.5.5 0 0 0-.908-.417A6 6 0 1 0 8 2z"/>
          <path d="M8 4.466V.534a.25.25 0 0 0-.41-.192L5.23 2.308a.25.25 0 0 0 0 .384l2.36 1.966A.25.25 0 0 0 8 4.466"/>
        </svg>
        Reset Chat
      </button>
      <p v-if="isRecording" class="status-indicator recording-indicator">
        <span class="pulsing-dot"></span>Recording...
      </p>
      <p v-if="isProcessing" class="status-indicator processing-indicator">Processing audio...</p>
      <p v-if="statusMessage" class="status-message">{{ statusMessage }}</p>
    </div>

    <div class="conversation-area">
      <h2 class="conversation-title">Conversation</h2>
      <div class="messages-container">
        <div v-for="(message, index) in conversation" :key="index" :class="['message-bubble', message.role]">
          <span class="message-content">{{ message.content }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue';
import { io } from 'socket.io-client';

const SOCKET_URL = 'http://localhost:8001';
let socket = null;
let mediaRecorder = null;
let audioChunks = [];

// const selectedLang = ref('en'); // Language selector removed, defaulting to 'en'
const isRecording = ref(false);
const isProcessing = ref(false);
const conversation = ref([]);
const statusMessage = ref('');

// --- Socket.IO Connection ---
onMounted(() => {
  try {
    socket = io(SOCKET_URL);
    statusMessage.value = 'Connecting to backend...';

    socket.on('connect', () => {
      statusMessage.value = 'Connected to backend.';
      console.log('Socket connected:', socket.id);
    });

    socket.on('disconnect', () => {
      statusMessage.value = 'Disconnected from backend.';
      console.log('Socket disconnected');
    });

    socket.on('connect_error', (error) => {
      statusMessage.value = `Connection error: ${error.message}`;
      console.error('Socket connection error:', error);
    });

    socket.on('chat_response', async (data) => {
      isProcessing.value = false;
      if (data.error) {
        statusMessage.value = `Backend error: ${data.error}`;
        console.error('Backend error:', data.error);
        conversation.value.push({ role: 'system', content: `Error: ${data.error}` });
      } else {
        if (data.transcript) {
          // This is the user's transcribed speech
          conversation.value.push({ role: 'user', content: data.transcript });
        }
        if (data.chat && data.chat.answer) {
          conversation.value.push({ role: 'assistant', content: data.chat.answer });
        }
        statusMessage.value = 'Response received.';
      }
      await nextTick(); // Wait for DOM update
      scrollToBottom();
    });

    // --- AUDIO PLAYBACK HANDLING ---
    // Handle full audio event and play immediately
    socket.on('audio', (audioBuffer) => {
      // Deserialize Buffer if needed
      let data = audioBuffer;
      if (audioBuffer && audioBuffer.type === 'Buffer' && Array.isArray(audioBuffer.data)) {
        data = new Uint8Array(audioBuffer.data).buffer;
      }
      console.log('[FRONTEND] Received audio, length:', data.byteLength || data.length);

      // Create Blob and play via Audio object
      const blob = new Blob([data], { type: 'audio/wav' });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.play().catch(err => {
        console.warn('Audio playback failed:', err);
        statusMessage.value = 'Tap play to listen';
      });
    });

    // Streaming audio events are disabled for now due to browser limitations with WAV/PCM and MSE.
    // socket.on('audio_stream', ...) and socket.on('audio_stream_end', ...) are intentionally not handled.

  } catch (e) {
    statusMessage.value = `Failed to initialize socket: ${e.message}`;
    console.error("Socket initialization failed", e);
  }
});

onBeforeUnmount(() => {
  if (socket) {
    socket.disconnect();
  }
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop();
  }
});

// --- Audio Recording ---
async function startRecording() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    statusMessage.value = 'getUserMedia not supported on your browser!';
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' }); // Browsers generally support webm or ogg for MediaRecorder
    audioChunks = [];

    mediaRecorder.ondataavailable = (event) => {
      audioChunks.push(event.data);
    };

    mediaRecorder.onstop = async () => {
      isProcessing.value = true;
      statusMessage.value = 'Processing audio...';
      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });

      const reader = new FileReader();
      reader.onloadend = () => {
        const arrayBuffer = reader.result;
        if (socket && socket.connected) {
          console.log(`Sending audio (${arrayBuffer.byteLength} bytes) for language: en`);
          socket.emit('send_audio', {
            audio: arrayBuffer, // Send as ArrayBuffer
            sample_rate: 16000, // Assuming 16000, MediaRecorder might use something else. This needs alignment.
            lang: 'en', // Hardcoded to English
            name: '' 
          });
        } else {
          statusMessage.value = 'Socket not connected. Cannot send audio.';
          isProcessing.value = false;
        }
      };
      reader.onerror = (error) => {
        console.error("FileReader error:", error);
        statusMessage.value = "Error reading audio file.";
        isProcessing.value = false;
      };
      reader.readAsArrayBuffer(audioBlob); // Read as ArrayBuffer to send bytes

      // Clean up stream tracks
      stream.getTracks().forEach(track => track.stop());
    };

    mediaRecorder.start();
    isRecording.value = true;
    statusMessage.value = 'Recording...';
  } catch (err) {
    console.error('Error accessing microphone:', err);
    statusMessage.value = `Error accessing microphone: ${err.message}. Please ensure permissions are granted.`;
    isRecording.value = false;
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop(); // This will trigger the onstop event
    isRecording.value = false;
    // statusMessage is handled by onstop
  }
}

function toggleRecording() {
  if (isRecording.value) {
    stopRecording();
  } else {
    startRecording();
  }
}

async function resetChat() {
  conversation.value = [];
  statusMessage.value = 'Chat reset.';
  if (isRecording.value) {
    stopRecording(); // Ensure recording stops if active
  }
  await nextTick();
  scrollToBottom(); // Should be empty, but good practice
}

function scrollToBottom() {
  const container = document.querySelector('.messages-container');
  if (container) {
    container.scrollTop = container.scrollHeight;
  }
}

</script>

<style>
:root {
  --primary-color: #007bff;
  --primary-hover-color: #0056b3;
  --danger-color: #dc3545;
  --danger-hover-color: #c82333;
  --light-bg: #f8f9fa;
  --dark-text: #212529;
  --light-text: #ffffff;
  --border-color: #dee2e6;
  --user-message-bg: #007bff;
  --assistant-message-bg: #e9ecef;
  --system-message-bg: #f8d7da;
  --system-message-text: #721c24;
  --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}

#app {
  font-family: var(--font-family);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: var(--dark-text);
  max-width: 700px; /* Increased max-width */
  margin: 40px auto; /* More margin */
  padding: 30px; /* More padding */
  background-color: var(--light-bg);
  border-radius: 12px; /* Softer border radius */
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08); /* Softer shadow */
  display: flex;
  flex-direction: column;
}

h1 {
  color: var(--primary-color);
  margin-bottom: 25px;
  font-size: 2rem; /* Larger title */
  text-align: center;
}

.controls {
  display: flex;
  gap: 15px; /* Spacing between buttons */
  margin-bottom: 25px;
  padding-bottom: 25px;
  border-bottom: 1px solid var(--border-color);
  align-items: center;
  justify-content: center; /* Center buttons */
}

.control-button {
  background-color: var(--primary-color);
  color: var(--light-text);
  border: none;
  padding: 12px 24px; /* Larger padding */
  font-size: 1rem;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.2s ease-in-out, transform 0.1s ease;
  display: flex;
  align-items: center;
  gap: 8px; /* Space between icon and text */
}

.control-button:hover:not(:disabled) {
  background-color: var(--primary-hover-color);
  transform: translateY(-1px);
}

.control-button:active:not(:disabled) {
  transform: translateY(0px);
}

.control-button:disabled {
  background-color: #ced4da;
  cursor: not-allowed;
}

.control-button.is-recording {
  background-color: var(--danger-color);
}
.control-button.is-recording:hover:not(:disabled) {
  background-color: var(--danger-hover-color);
}

.control-button.reset-button {
  background-color: #6c757d; /* Secondary color */
}
.control-button.reset-button:hover:not(:disabled) {
  background-color: #5a6268;
}


.status-indicator {
  display: flex;
  align-items: center;
  font-size: 0.9rem;
  margin-top: 5px; /* Adjusted from p tag default */
}

.recording-indicator {
  color: var(--danger-color);
}

.processing-indicator {
  color: var(--primary-color);
}

.pulsing-dot {
  width: 8px;
  height: 8px;
  background-color: var(--danger-color);
  border-radius: 50%;
  margin-right: 8px;
  animation: pulse 1.5s infinite ease-in-out;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.75); }
}

.status-message {
  margin-top: 15px;
  color: #495057;
  font-style: italic;
  text-align: center;
  width: 100%; /* Ensure it takes full width in flex context */
}

.conversation-area {
  background-color: #ffffff;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
  flex-grow: 1; /* Allow it to take available space */
  display: flex;
  flex-direction: column;
  min-height: 200px; /* Minimum height */
}

.conversation-title {
  font-size: 1.5rem;
  color: var(--dark-text);
  margin-bottom: 15px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-color);
  text-align: left;
}

.messages-container {
  flex-grow: 1;
  overflow-y: auto;
  padding-right: 10px; /* For scrollbar */
}

.message-bubble {
  padding: 10px 15px;
  margin-bottom: 12px;
  border-radius: 18px; /* More rounded bubbles */
  line-height: 1.5;
  max-width: 75%; /* Max width for bubbles */
  word-wrap: break-word; /* Break long words */
}

.message-bubble.user {
  background-color: var(--user-message-bg);
  color: var(--light-text);
  margin-left: auto; /* Align to right */
  border-bottom-right-radius: 6px; /* Chat bubble tail effect */
}

.message-bubble.assistant {
  background-color: var(--assistant-message-bg);
  color: var(--dark-text);
  margin-right: auto; /* Align to left */
  border-bottom-left-radius: 6px; /* Chat bubble tail effect */
}

.message-bubble.system {
  background-color: var(--system-message-bg);
  color: var(--system-message-text);
  font-style: italic;
  text-align: center;
  max-width: 100%;
  border-radius: 6px;
}

/* Scrollbar styling (optional, for a more modern look) */
.messages-container::-webkit-scrollbar {
  width: 8px;
}

.messages-container::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 10px;
}

.messages-container::-webkit-scrollbar-thumb {
  background: #ccc;
  border-radius: 10px;
}

.messages-container::-webkit-scrollbar-thumb:hover {
  background: #aaa;
}
</style>
