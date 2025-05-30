import { exec } from "child_process";
import cors from "cors";
import dotenv from "dotenv";
// --- SOCKET.IO SERVER SETUP ---
import express from "express";
import fs from "fs";
import { promises as fsp } from "fs";
import axios from "axios";
import OpenAI from "openai";
import path from "path";
import { dirname } from 'path';
import { fileURLToPath } from 'url';
import net from 'net';
import { v4 as uuidv4 } from 'uuid';
import { spawn } from "child_process";
import os from "os";
import crypto from "crypto";
import multer from "multer";
import http from "http";
import { Server as SocketIOServer } from "socket.io";
import ffmpeg from 'fluent-ffmpeg';
import ffmpegInstaller from '@ffmpeg-installer/ffmpeg';

ffmpeg.setFfmpegPath(ffmpegInstaller.path);

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
let holoboxId = "testing"; // Restored for passing to LLM
let userQuestion = "" // May still be used for other purposes, or can be removed if solely for logging

import { io as ioClient } from "socket.io-client";
let lang; // Will be set by data from client
var startTime = 0
var history = []
console.log("Connecting to server...");
const socket = ioClient.connect("http://localhost:7006"); 

socket.on("connect", () => {
  console.log("Connected to server");
});
socket.on("disconnect", () => {
  console.log("Disconnected from server");
});
socket.on("error", (error) => {
  console.error("Error:", error);
});

dotenv.config();

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY || "-",
});

var starter = false

// --- EXPRESS + HTTP + SOCKET.IO SERVER ---
const app = express();
app.use(express.json());
app.use(cors());
const port = 3005;
const server = http.createServer(app);
const io = new SocketIOServer(server, {
  cors: {
    origin: "*",
    methods: ["GET", "POST"]
  }
});

// --- SOCKET.IO EVENTS FOR FRONTEND ---
io.on("connection", (client) => {
  console.log("Frontend connected via socket.io");

  client.on("send_audio", async (data) => {
    try {
      // Start total pipeline timer
      globalThis.pipelineStartTime = Date.now();
      // data: { audio: <Buffer>, sample_rate: number, lang: string, name: string }
      let transcript = "";
      try {
        const audioBuffer = Buffer.from(data.audio);
        const tempInputPath = path.join(os.tmpdir(), `input_${uuidv4()}.webm`);
        const tempOutputPath = path.join(os.tmpdir(), `output_${uuidv4()}.wav`);

        await fsp.writeFile(tempInputPath, audioBuffer);

        await new Promise((resolve, reject) => {
          ffmpeg(tempInputPath)
            .toFormat('wav')
            .audioChannels(1)
            .audioFrequency(16000)
            .on('error', (err) => {
              console.error('FFmpeg error:', err);
              reject(err);
            })
            .on('end', () => {
              resolve();
            })
            .save(tempOutputPath);
        });

        const wavAudioBuffer = await fsp.readFile(tempOutputPath);

        const FormData = (await import("form-data")).default;
        const form = new FormData();
        form.append("audio", wavAudioBuffer, {
          filename: `audio_${Date.now()}.wav`,
          contentType: "audio/wav"
        });
        // Only append "lang" if data.lang is set, not empty/null/undefined, and not "en"
        let langSent = "auto-detect";
        if (
          data.lang &&
          typeof data.lang === "string" &&
          data.lang.trim() !== "" &&
          data.lang.trim().toLowerCase() !== "en"
        ) {
          form.append("lang", data.lang);
          langSent = data.lang;
        }
        // Log for debugging
        console.log(`[Transcription] Language sent to backend: ${langSent}`);

        // --- VAD: Check for speech before transcription ---
        let vadDetected = false;
        let vadStart = Date.now();
        try {
          const vadForm = new FormData();
          vadForm.append("audio", wavAudioBuffer, {
            filename: `audio_${Date.now()}.wav`,
            contentType: "audio/wav"
          });
          const vadResponse = await axios.post(
            "http://localhost:5010/vad",
            vadForm,
            {
              headers: vadForm.getHeaders(),
              maxContentLength: Infinity,
              maxBodyLength: Infinity,
            }
          );
          let vadEnd = Date.now();
          let vadDuration = vadEnd - vadStart;
          console.log(`[VAD] Time taken: ${vadDuration} ms`);
          if (
            vadResponse.data &&
            Array.isArray(vadResponse.data.speech_timestamps) &&
            vadResponse.data.speech_timestamps.length > 0
          ) {
            vadDetected = true;
          }
        } catch (err) {
          let vadEnd = Date.now();
          let vadDuration = vadEnd - vadStart;
          console.log(`[VAD] Time taken: ${vadDuration} ms`);
          console.error("[VAD] Error calling /vad endpoint:", err.message);
        }

        if (!vadDetected) {
          client.emit("chat_response", { error: "No speech detected in audio." });
          // Clean up temporary files
          await fsp.unlink(tempInputPath);
          await fsp.unlink(tempOutputPath);
          return;
        }

        // Retry transcription up to 2 times if it fails
        let transcriptResponse = null;
        let sttError = null;
        let detectedLanguage = null;
        for (let attempt = 1; attempt <= 3; attempt++) {
          const sttStart = Date.now();
          try {
            transcriptResponse = await axios.post(
              "http://localhost:5010/transcribe",
              form,
              {
                headers: form.getHeaders(),
                maxContentLength: Infinity,
                maxBodyLength: Infinity,
              }
            );
            const sttEnd = Date.now();
            console.log(`==========\n[STT attempt ${attempt}]  ${sttEnd - sttStart} ms`);
            if (transcriptResponse.data && transcriptResponse.data.transcript) {
              transcript = transcriptResponse.data.transcript;
              detectedLanguage = transcriptResponse.data.detected_language || null;
              // Print the transcribed text
              console.log(`[Transcription] Transcript: ${transcript}`);
              break;
            }
          } catch (err) {
            sttError = err;
            console.error(`[Transcription] Attempt ${attempt} failed:`, err.message);
            if (attempt < 3) {
              // Wait 300ms before retrying
              await new Promise(res => setTimeout(res, 300));
            }
          }
        }
        // Set lang to detected language for downstream logic (TTS, etc.)
        if (detectedLanguage) {
          lang = detectedLanguage;
        }

        // Clean up temporary files
        await fsp.unlink(tempInputPath);
        await fsp.unlink(tempOutputPath);

      } catch (err) {
        console.error("Error processing audio or sending to transcription server:", err);
      }

      if (!transcript || transcript.trim() === "") {
        client.emit("chat_response", { error: "Transcription failed" });
        return;
      }

      // Call chat logic (simulate /chat endpoint)
      socket.emit("json_obj", 'START_THINKING');
      let userMessage = transcript;
      userQuestion = userMessage; // Retaining for now, might be used elsewhere or can be removed if not.
      lang = data.lang;
      let username = data.name || "";
      startTime = Date.now();


      let backUrl = "http://127.0.0.1:5009/chatbot"; // Ensure this matches the Python backend route


      const llmStart = Date.now();
      const [response] = await Promise.all([
        axios.post(backUrl, {
          query: userMessage,
          lang: lang,
          name: username,
          holoboxId: holoboxId // Pass holoboxId to LLM
        })
        // Add more parallel API calls here if needed
      ]);
      const llmEnd = Date.now();
      console.log(`[LLM]  ${llmEnd - llmStart} ms`);

      if (response) {
        let retrievalDuration = response?.data?.metadata?.retrievalDuration
        let rerankDuration = response?.data?.metadata?.rerankDuration
        let gptDuration = response?.data?.metadata?.gptDuration
        let totalDuration = response?.data?.metadata?.totalDuration

        // Always prepare audio for the LLM response
        let audioBuffer = null;
        try {
          audioBuffer = await prepareAudio(response?.data?.answer);
        } catch (err) {
          console.error(`[AGASTYA] Exception in prepareAudio (send_audio):`, err);
        }

        // Emit audio buffer to frontend for playback (for compatibility with frontend expectations)
        try {
          if (audioBuffer && audioBuffer.length > 0) {
            io.emit("audio", audioBuffer);
          } else {
            console.error(`[AGASTYA] Error: audioBuffer for LLM response is null or empty.`);
          }
        } catch (err) {
          console.error(`[AGASTYA] Exception after prepareAudio (send_audio):`, err);
        }

        setTimeout(() => {
          socket.emit("json_obj", 'STOP_THINKING')
        }, 1850);

        history.push({ human: userMessage, bot: response?.data?.answer })
        client.emit("chat_response", {
          transcript,
          chat: {
            script: "done",
            answer: response?.data?.answer,
            retrievalDuration,
            rerankDuration,
            "LLM Duration": gptDuration,
            "RAG Duration": totalDuration
          },
          audio: audioBuffer && audioBuffer.length > 0 ? audioBuffer : null
        });
      }
    } catch (err) {
      console.error("Error in send_audio socket event:", err);
      client.emit("chat_response", { error: "Internal server error", details: err.message });
    }
  });

  client.on("disconnect", () => {
    console.log("Frontend socket.io client disconnected");
  });
});

// --- END SOCKET.IO SERVER SETUP ---

// Multer setup for in-memory file upload (may be removed if not needed)
const upload = multer({ storage: multer.memoryStorage() });

app.get("/", (req, res) => {
  res.send("Hello World!");
});


const execCommand = (command) => {
  return new Promise((resolve, reject) => {
    exec(command, (error, stdout, stderr) => {
      if (error) reject(error);
      resolve(stdout);
    });
  });
};

const lipSyncMessage = async (message) => {
  console.warn("lipSyncMessage is obsolete and does nothing.");
};

async function prepareAudio(message) {
  console.log(`[TTS - ElevenLabs] prepareAudio called for message: "${message}"`);

  const elevenLabsApiKey = "sk_c43245960f2abd4bc26e659bfae26931d7c4df8e6b82bd39";
  const elevenLabsApiUrlBase = "https://api.elevenlabs.io/v1/text-to-speech/uQPOhlzA94sogqmhGLCI/stream";
  if (typeof message !== "string" || !message.trim()) {
    console.error(`[TTS] Error: Message is invalid or empty. Value:`, message);
    return null;
  }

  if (lang !== "en") {
    console.warn(`[TTS] Unsupported language: "${lang}". No TTS will be performed for message: "${message}"`);
    return null;
  }

  try {
    const elevenLabsRequestData = {
      text: message,
      model_id: "eleven_flash_v2_5",
      optimize_streaming_latency: 4,
      voice_settings: {
        speed: 1.2,
        stability: 1,
        similarity_boost: 1,
      },
    };
    const elevenLabsHeaders = {
      "xi-api-key": elevenLabsApiKey,
      "Content-Type": "application/json",
      "Accept": "audio/wav"
    };

    // Stream audio from ElevenLabs and emit chunks to frontend as soon as they arrive
    const response = await axios.post(
      elevenLabsApiUrlBase,
      elevenLabsRequestData,
      {
        headers: elevenLabsHeaders,
        responseType: "stream",
        timeout: 15000,
      }
    );

    if (response.status === 200 && response.data) {
      // Emit audio chunks as they arrive
      return new Promise((resolve, reject) => {
        let totalLength = 0;
        let chunks = [];
        response.data.on('data', (chunk) => {
          totalLength += chunk.length;
          chunks.push(chunk);
          // Emit each chunk to all connected clients
          io.emit("audio_stream", chunk);
        });
        response.data.on('end', () => {
          // Optionally, emit an event to signal end of stream
          io.emit("audio_stream_end");
          // Log audio generation details
          console.log(`[TTS - ElevenLabs] Chunk count: ${chunks.length}, totalLength: ${totalLength}`);
          const wavBuffer = Buffer.concat(chunks, totalLength);
          console.log(`[TTS - ElevenLabs] Generated wavBuffer length: ${wavBuffer.length}`);
          resolve(wavBuffer);
        });
        response.data.on('error', (err) => {
          console.error('[TTS - ElevenLabs] Stream error:', err);
          reject(err);
        });
      });
    } else {
      console.error(`[TTS - ElevenLabs] API error for message "${message}": Status ${response.status}`);
      return null;
    }
  } catch (error) {
    console.error("[TTS - ElevenLabs] Error:", error.message, error.stack);
    return null;
  }
}


async function prepareMessage(index) {
  const message = sentences[index];
  return {
    text: message,
    index: index
  };
}

async function audioFileToBase64(fileName) {
  try {
    const audioData = await fs.readFile(fileName);
    return audioData.toString("base64");
  } catch (error) {
    console.error("Error converting audio file to Base64:", error.message);
    return null;
  }
}

async function readJsonTranscript(jsonFile) {
  try {
    const jsonData = await fs.readFile(jsonFile, "utf-8");
    return JSON.parse(jsonData);
  } catch (error) {
    console.error("Error reading JSON transcript:", error.message);
    return null;
  }
}

let messageText = "";
let sentences = [];
let sendFirst = false;

import FormData from "form-data";

socket.on("message", async (msg) => {
  messageText = messageText + msg; // Accumulate message parts

  // Check if the accumulated messageText forms a complete sentence
  // Ends with . ! ? | : OR ends with Dr. or Smt.
  const isEndOfSentence = /[.!?|:]$/.test(messageText) || /Dr\.$/.test(messageText) || /Smt\.$/.test(messageText);

  if (isEndOfSentence) {
    const currentSentence = messageText.trim();
    if (currentSentence.length > 0) {
      sentences.push(currentSentence);
      messageText = ""; // Reset for the next sentence

      // Only process the first sentence (sentences array is cleared after each)
      try {
        console.log(`[AGASTYA] About to call prepareAudio for: "${sentences[0]}"`);
      } catch (err) {
        console.error(`[AGASTYA] Exception before prepareAudio:`, err);
      }
      let audioBuffer = null;
      try {
        audioBuffer = await prepareAudio(sentences[0]);
      } catch (err) {
        console.error(`[AGASTYA] Exception in prepareAudio:`, err);
      }

      try {
        if (audioBuffer && audioBuffer.length > 0) {
          // Emit the audio buffer to the frontend for playback as soon as it's ready
          console.log(`[AGASTYA] Emitting audio buffer to frontend, length: ${audioBuffer.length}`);
          io.emit("audio", audioBuffer);
        } else {
          console.error(`[AGASTYA] Error: audioBuffer for sentence "${currentSentence}" is null or empty.`);
        }
      } catch (err) {
        console.error(`[AGASTYA] Exception after prepareAudio:`, err);
      }
      // Clear sentences array after processing this one to handle one sentence at a time.
      sentences = [];
    }
  }
});

// Removed HTTP POST endpoints for /namaste, /language, /chat, /send_audio

// Start the HTTP + Socket.IO server
server.listen(port, () => {
  console.log(`(Socket.IO) listening on port ${port}`);
});
