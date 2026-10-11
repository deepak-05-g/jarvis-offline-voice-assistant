"""Windows desktop voice assistant with a wake word and safe desktop tools."""

from __future__ import annotations

import io
import json
import os
import queue
import shutil
import tempfile
import threading
import time
import wave
import winsound
from pathlib import Path
from typing import Any

import keyboard
import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
from openai import OpenAI
import tkinter as tk
from tkinter import ttk


SAMPLE_RATE = 16_000
CHANNELS = 1
WAKE_WORD = "jarvis"
HOTKEY = "ctrl+space"
HOME = Path.home()

KNOWN_APPLICATIONS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "command prompt": "cmd.exe",
    "terminal": "wt.exe",
}

SYSTEM_PROMPT = """You are JARVIS, a concise and friendly Windows desktop assistant.
You can answer general questions, but use tools for desktop actions.
Never invent that an action succeeded: rely on the tool result.
Only use open_folder for a folder path that the user supplied or that is clearly
an existing standard Windows folder (Desktop, Documents, Downloads, Pictures).
Only use open_application for the listed common applications or an executable
path supplied by the user. Never run shell commands, scripts, installers, or
unknown executables. Ask the user to provide a full path if needed.
After a successful action, briefly tell the user what you opened."""


class JarvisError(RuntimeError):
    """An expected, user-facing assistant error."""


def standard_folder(name: str) -> Path | None:
    folders = {
        "desktop": HOME / "Desktop",
        "documents": HOME / "Documents",
        "downloads": HOME / "Downloads",
        "pictures": HOME / "Pictures",
        "music": HOME / "Music",
        "videos": HOME / "Videos",
    }
    return folders.get(name.strip().lower())


def open_folder(path: str) -> str:
    """Open an existing folder in Windows Explorer."""
    candidate = standard_folder(path) or Path(path).expanduser()
    if not candidate.is_dir():
        return f"Folder not found: {path}"
    os.startfile(str(candidate))
    return f"Opened folder: {candidate}"


def open_application(application: str) -> str:
    """Open a safe, known application or an existing executable path."""
    normalized = application.strip().lower()
    target = KNOWN_APPLICATIONS.get(normalized)
    if target is None:
        candidate = Path(application).expanduser()
        if candidate.is_file() and candidate.suffix.lower() == ".exe":
            target = str(candidate)
        else:
            return (
                f"I can’t open '{application}'. Use a supported app name "
                "or provide the full path to an .exe file."
            )
    resolved = shutil.which(target) or target
    os.startfile(resolved)
    return f"Opened application: {application}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "open_folder",
            "description": "Open an existing folder in Windows Explorer.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Open a safe common Windows app or a supplied .exe path.",
            "parameters": {
                "type": "object",
                "properties": {"application": {"type": "string"}},
                "required": ["application"],
                "additionalProperties": False,
            },
        },
    },
]


def wav_bytes(samples: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(CHANNELS)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
        output.writeframes(pcm.tobytes())
    return buffer.getvalue()


def record_until_silence(max_seconds: float = 12.0) -> bytes:
    """Record after speech starts and stop after a short silence."""
    chunks: list[np.ndarray] = []
    started = False
    silent_for = 0.0
    chunk_seconds = 0.25
    threshold = 0.015
    deadline = time.monotonic() + max_seconds

    with sd.InputStream(
        samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32",
        blocksize=int(SAMPLE_RATE * chunk_seconds),
    ) as stream:
        while time.monotonic() < deadline:
            data, _ = stream.read(int(SAMPLE_RATE * chunk_seconds))
            chunk = data[:, 0].copy()
            loud = float(np.sqrt(np.mean(chunk * chunk)))
            if loud >= threshold:
                started = True
                silent_for = 0.0
            elif started:
                silent_for += chunk_seconds
            if started:
                chunks.append(chunk)
            if started and silent_for >= 1.0:
                break

    if not chunks:
        raise JarvisError("I did not hear anything.")
    return wav_bytes(np.concatenate(chunks))


class JarvisUI:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("JARVIS")
        self.root.geometry("420x180")
        self.root.attributes("-topmost", True)
        self.root.withdraw()
        self.status = tk.StringVar(value="Waiting for “Jarvis”…")
        self.message = tk.StringVar(value="")
        ttk.Label(self.root, text="JARVIS", font=("Segoe UI", 22, "bold")).pack(pady=(18, 4))
        ttk.Label(self.root, textvariable=self.status, font=("Segoe UI", 11)).pack()
        ttk.Label(self.root, textvariable=self.message, wraplength=380).pack(pady=12)

    def show(self, status: str, message: str = "") -> None:
        self.root.after(0, self._show, status, message)

    def _show(self, status: str, message: str) -> None:
        self.status.set(status)
        self.message.set(message)
        self.root.deiconify()
        self.root.lift()

    def hide(self) -> None:
        self.root.after(0, self.root.withdraw)


class Jarvis:
    def __init__(self, ui: JarvisUI) -> None:
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise JarvisError("OPENAI_API_KEY is missing. Add it to .env and restart.")
        self.client = OpenAI(api_key=api_key)
        self.ui = ui
        self.events: queue.Queue[str] = queue.Queue()
        self.busy = threading.Lock()

    def transcribe(self, audio: bytes) -> str:
        result = self.client.audio.transcriptions.create(
            model=os.getenv("OPENAI_TRANSCRIPTION_MODEL", "whisper-1"),
            file=("recording.wav", audio, "audio/wav"),
        )
        return result.text.strip()

    def speak(self, text: str) -> None:
        response = self.client.audio.speech.create(
            model=os.getenv("OPENAI_TTS_MODEL", "tts-1"),
            voice=os.getenv("OPENAI_TTS_VOICE", "alloy"),
            input=text[:4000],
            response_format="wav",
        )
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as audio_file:
            audio_file.write(response.content)
            audio_path = audio_file.name
        try:
            winsound.PlaySound(audio_path, winsound.SND_FILENAME)
        finally:
            os.unlink(audio_path)

    def respond(self, transcript: str) -> str:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": transcript},
        ]
        for _ in range(3):
            completion = self.client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )
            assistant = completion.choices[0].message
            messages.append(assistant.model_dump(exclude_none=True))
            if not assistant.tool_calls:
                return assistant.content or "I’m not sure how to help with that."
            for call in assistant.tool_calls:
                arguments = json.loads(call.function.arguments)
                try:
                    result = (
                        open_folder(**arguments)
                        if call.function.name == "open_folder"
                        else open_application(**arguments)
                    )
                except OSError as exc:
                    result = f"Windows could not open that item: {exc}"
                messages.append({
                    "role": "tool", "tool_call_id": call.id, "content": result,
                })
        raise JarvisError("I could not finish that request.")

    def process(self, audio: bytes, require_wake_word: bool = False) -> None:
        if not self.busy.acquire(blocking=False):
            return
        try:
            self.ui.show("Transcribing…")
            transcript = self.transcribe(audio)
            if require_wake_word and WAKE_WORD not in transcript.lower():
                self.ui.hide()
                return
            if require_wake_word:
                transcript = transcript.lower().split(WAKE_WORD, 1)[1].strip(" ,.!?")
            self.ui.show("Thinking…", transcript)
            answer = self.respond(transcript)
            self.ui.show("Speaking…", answer)
            self.speak(answer)
            self.ui.show("Ready", answer)
            time.sleep(2)
            self.ui.hide()
        except (JarvisError, OSError, ValueError) as exc:
            self.ui.show("Error", str(exc))
            time.sleep(3)
            self.ui.hide()
        finally:
            self.busy.release()

    def listen_for_wake_word(self) -> None:
        while True:
            try:
                self.ui.show("Listening for “Jarvis”…")
                audio = record_until_silence(max_seconds=5)
                threading.Thread(
                    target=self.process, args=(audio, True), daemon=True
                ).start()
            except (JarvisError, OSError):
                time.sleep(1)

    def listen_for_command(self) -> None:
        threading.Thread(
            target=self._record_command, daemon=True
        ).start()

    def _record_command(self) -> None:
        self.ui.show("Listening…", "Speak your command")
        try:
            self.process(record_until_silence())
        except (JarvisError, OSError, ValueError) as exc:
            self.ui.show("Error", str(exc))


def main() -> None:
    ui = JarvisUI()
    try:
        assistant = Jarvis(ui)
    except JarvisError as exc:
        ui.show("Setup required", str(exc))
        ui.root.after(100, ui.root.deiconify)
        ui.root.mainloop()
        return

    keyboard.add_hotkey(HOTKEY, assistant.listen_for_command)
    threading.Thread(target=assistant.listen_for_wake_word, daemon=True).start()
    ui.show("Ready", f"Say “Jarvis” or press {HOTKEY}.")
    ui.root.mainloop()


if __name__ == "__main__":
    main()
