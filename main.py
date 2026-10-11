"""
JARVIS Voice-Activated Desktop Assistant (v5.3)
================================================
Features:
1. Desktop-attached: Guarantees the floating agent window renders directly onto the user's interactive monitor.
2. Prominent Visual Floating Agent:
   - Floats on top with Tony Stark HUD aesthetics (#080d1a dark glass, cyan glow).
   - Circular avatar + draggable window header.
   - Real-time animated audio waveform visualizer.
   - Live dialogue card showing user queries and JARVIS responses.
   - Push-to-talk button, hotkey (Ctrl+Space), and text command entry.
3. Windows App Paths & Registry Resolution:
   - Seamlessly opens Google Chrome, Microsoft Edge, Brave, VS Code, Notepad, Calculator, File Explorer, Paint, Task Manager, etc.
   - Automatically handles natural phrases like "open google chrome browser", "open brave browser", "open file explorer".
4. File Explorer & Folder Navigation:
   - Opens any standard or custom folder directly in Windows File Explorer ("open downloads in file explorer", "open folder atomquest", "open atomquest").
   - Opens specific files with phonetic punctuation support ("open the pdf cs underscore or underscore topics").
5. Application Termination:
   - Closes apps on voice command ("close notepad", "close chrome", "close calculator").
6. System & Media Controls:
   - Volume up/down, mute/unmute, play/pause media, next/previous track.
   - Time and date announcements.
   - Sleep / standby controls ("go to sleep", "one need buddy just be quiet").
   - YouTube and Google search ("play Queen on youtube", "search google for quantum computing").
7. Faster-Whisper Speech Recognition:
   - Biased vocabulary (initial_prompt) to eliminate mishearings ("Chrome" vs "strong", "Jarvis" vs "John").
8. 100% Offline AI Brain: Local Ollama (llama3.1) + Faster-Whisper (base.en) + Windows SAPI5 TTS (pyttsx3).
"""

import os
import io
import re
import json
import time
import math
import wave
import shutil
import difflib
import winreg
import subprocess
import threading
import tempfile
import datetime
import urllib.parse
import webbrowser
import collections
import ctypes
from pathlib import Path

# Attach thread to interactive user desktop immediately before initializing GUI
def attach_to_user_desktop():
    try:
        user32 = ctypes.windll.user32
        GENERIC_ALL = 0x10000000
        hdesk = user32.OpenDesktopW("Default", 0, False, GENERIC_ALL)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception as e:
        print(f"Desktop attach note: {e}")

attach_to_user_desktop()

import keyboard
import pyaudio
import numpy as np
from dotenv import load_dotenv

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw, ImageOps, ImageTk

from openai import OpenAI
import pyttsx3

try:
    import winsound
except ImportError:
    winsound = None

# ---------------------------------------------------------------------------
# Configuration & Paths
# ---------------------------------------------------------------------------
load_dotenv()

ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1")
ollama_api_key = os.getenv("OLLAMA_API_KEY", "ollama")

try:
    openai_client = OpenAI(api_key=ollama_api_key, base_url=ollama_base_url)
except Exception as exc:
    print(f"Ollama client warning: {exc}")
    openai_client = None

HOME = Path.home()
HOTKEY = "ctrl+space"
WAKE_PATTERNS = [
    r"\b(?:hey|hi|hello|ok|okay|yo)?\s*jarvis\b",
    r"\b(?:hey|hi|hello|ok|okay)?\s*javis\b",
    r"\b(?:hey|hi|hello|ok|okay)?\s*travis\b",
    r"\b(?:hey|hi|hello|ok|okay)?\s*john\b",
    r"\b(?:hey|hi|hello|ok|okay)?\s*service\b",
]

# Standard Windows application mappings
APP_MAP = {
    "google chrome": "chrome.exe",
    "chrome": "chrome.exe",
    "google strong": "chrome.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "brave": "brave.exe",
    "firefox": "firefox.exe",
    "vs code": "code.exe",
    "vscode": "code.exe",
    "code": "code.exe",
    "visual studio code": "code.exe",
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "this pc": "explorer.exe",
    "my computer": "explorer.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "terminal": "wt.exe",
    "powershell": "powershell.exe",
    "task manager": "taskmgr.exe",
    "taskmgr": "taskmgr.exe",
    "paint": "mspaint.exe",
    "snipping tool": "snippingtool.exe",
    "screenshot": "snippingtool.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "spotify": "spotify.exe",
    "settings": "ms-settings:",
}

# Standard user folders
STANDARD_FOLDERS = {
    "desktop": HOME / "Desktop",
    "documents": HOME / "Documents",
    "downloads": HOME / "Downloads",
    "pictures": HOME / "Pictures",
    "music": HOME / "Music",
    "videos": HOME / "Videos",
    "c drive": Path("C:\\"),
}

# Common web services
POPULAR_WEBSITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "github": "https://www.github.com",
    "reddit": "https://www.reddit.com",
    "wikipedia": "https://www.wikipedia.org",
    "gmail": "https://mail.google.com",
    "chatgpt": "https://chat.openai.com",
    "netflix": "https://www.netflix.com",
    "amazon": "https://www.amazon.com",
    "twitter": "https://twitter.com",
    "x": "https://x.com",
    "linkedin": "https://www.linkedin.com",
    "whatsapp": "https://web.whatsapp.com",
}

SYSTEM_PROMPT_TEMPLATE = """You are JARVIS, Tony Stark's iconic, highly capable, and witty AI butler.
You are running locally on Windows as a personal desktop assistant.
Rules for your responses:
1. Address the user respectfully as 'sir' or 'boss'.
2. Tone: polite, intelligent, sharp, subtle British wit, and fiercely capable.
3. Be concise and conversational: 1 to 2 sentences maximum. Your reply will be spoken aloud via Text-to-Speech, so NEVER use markdown formatting, asterisks, bullet points, headers, or long lists.
4. If asked who you are: You are JARVIS (Just A Rather Very Intelligent System), at your service.
5. If asked what you can do: Mention you can open apps (Chrome, Edge, Brave, VS Code, Notepad, etc.), open folders in File Explorer, close applications, search YouTube and Google, control volume, tell the time and date, and answer questions.
6. The current local time is {current_time} and today's date is {current_date}."""


# ---------------------------------------------------------------------------
# Audio Chime
# ---------------------------------------------------------------------------
def play_chime():
    """Play a short, futuristic dual-tone Jarvis wake chime."""
    if winsound:
        def _beep():
            try:
                winsound.Beep(1100, 80)
                winsound.Beep(1700, 100)
            except Exception:
                pass
        threading.Thread(target=_beep, daemon=True).start()


# ---------------------------------------------------------------------------
# Application & Path Resolvers
# ---------------------------------------------------------------------------
def resolve_app(name: str) -> str | None:
    """Resolve an application name or alias to its executable path via Registry and system locations."""
    clean_name = name.lower().strip()
    clean_name = re.sub(r"\s+(?:browser|application|app|software|program)$", "", clean_name).strip()

    target = APP_MAP.get(clean_name, f"{clean_name}.exe" if not clean_name.endswith(".exe") else clean_name)
    if target == "ms-settings:":
        return target

    # 1. Search Windows Registry App Paths
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{target}") as key:
                val, _ = winreg.QueryValueEx(key, "")
                clean_val = val.strip('"')
                if clean_val and os.path.exists(clean_val):
                    return clean_val
        except Exception:
            pass

    # 2. Search System PATH
    which_path = shutil.which(target)
    if which_path:
        return which_path

    # 3. Search Common Windows Application Directories
    common = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
        r"C:\Windows\explorer.exe",
        r"C:\Windows\System32\notepad.exe",
        r"C:\Windows\System32\calc.exe",
        r"C:\Windows\System32\taskmgr.exe",
        r"C:\Windows\System32\cmd.exe",
        r"C:\Windows\System32\mspaint.exe",
    ]
    for p in common:
        if target.lower() in p.lower() and os.path.exists(p):
            return p
    return None


def clean_text_for_speech(text: str) -> str:
    """Strip markdown formatting, URLs, code blocks, and symbols before TTS."""
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]*`", "", text)
    text = re.sub(r"https?://\S+|www\.\S+", "", text)
    text = re.sub(r"[#*_~>]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def close_application(raw_query: str) -> str | None:
    """Terminate a running application by name via taskkill."""
    lower = raw_query.lower().strip(" .!?")
    m = re.match(
        r"^(?:close|exit|terminate|kill|shut(?:\s+down)?)\s+(?:the\s+)?(?:application\s+|app\s+|browser\s+)?(.+?)(?:\s+browser|\s+application|\s+app|\s+now|\s+please|\s+jarvis)*$",
        lower
    )
    if not m:
        return None

    target_name = m.group(1).strip()
    resolved = resolve_app(target_name)
    exe_name = Path(resolved).name if resolved and resolved != "ms-settings:" else f"{target_name}.exe"

    try:
        subprocess.run(["taskkill", "/IM", exe_name, "/F"], capture_output=True, check=False)
        return f"Closed {target_name.capitalize()} for you, sir."
    except Exception as e:
        return f"Failed to close {target_name}: {e}"


def smart_open(raw_query: str) -> str:
    """Intelligently resolve and open apps, folders in File Explorer, files, or websites."""
    lower = raw_query.lower().strip(" .!?")

    if lower in ["now", "it", "this", "that", "here", "something"]:
        return "Please specify what you would like me to open, sir."

    # 1. Clean conversational prefixes
    cleaned = re.sub(
        r"^(?:i\s+told\s+you\s+to\s+|please\s+|could\s+you\s+|can\s+you\s+|can\s+|could\s+|would\s+you\s+|would\s+|just\s+|open\s+|launch\s+|start\s+|show\s+|view\s+|with\s+|in\s+one\s+|upon\s+)+",
        "", lower
    )
    # 2. Clean leading descriptors
    cleaned = re.sub(r"^(?:the\s+)?(?:folder|file|pdf|doc|document|app|application|browser)\s+", "", cleaned)

    # 3. Clean trailing noise ("in file explorer", "folder", "browser", "jarvis", "for me")
    cleaned = re.sub(r"\s+(?:in\s+file\s+explorer|in\s+explorer|folder|file|pdf|doc|document|browser|jarvis|please|now|for me)$", "", cleaned)
    cleaned = re.sub(r"\s+(?:in\s+file\s+explorer|in\s+explorer|folder|file|pdf|doc|document|browser|jarvis|please|now|for me)$", "", cleaned)

    # 4. Handle phonetic pronunciations of punctuation ("underscore" -> "_", "dot" -> ".")
    cleaned = cleaned.replace("underscore", "_").replace("dot", ".").replace("dash", "-")
    cleaned = cleaned.strip(" .!?_")

    if not cleaned:
        return "Please specify what you would like me to open, sir."

    # Step A: Check Standard Folders (open in File Explorer)
    folder_target = STANDARD_FOLDERS.get(cleaned)
    if folder_target and folder_target.is_dir():
        try:
            os.startfile(str(folder_target))
            return f"Opening {cleaned.capitalize()} folder in File Explorer for you, sir."
        except Exception as e:
            return f"Failed to open {cleaned} folder: {e}"

    # Step B: Check Applications (Chrome, Edge, Brave, VS Code, Notepad, Calc, etc.)
    resolved_app = resolve_app(cleaned)
    if resolved_app:
        try:
            os.startfile(resolved_app)
            display_name = re.sub(r"\s+(?:browser|app|application)$", "", cleaned).capitalize()
            return f"Opening {display_name} for you, sir."
        except Exception as e:
            return f"Failed to open {cleaned}: {e}"

    # Step C: Check Popular Websites or URLs
    if cleaned in POPULAR_WEBSITES:
        webbrowser.open(POPULAR_WEBSITES[cleaned])
        return f"Opening {cleaned.capitalize()} in your browser, sir."

    if re.search(r"\.(?:com|org|net|io|edu|gov|in|co)\b", cleaned):
        url = cleaned if cleaned.startswith("http") else f"https://{cleaned}"
        webbrowser.open(url)
        return f"Opening {cleaned} in your browser, sir."

    # Step D: Search Local User Directories for Folders and Files
    search_dirs = [HOME / "Downloads", HOME / "Desktop", HOME / "Documents", Path.cwd()]
    all_items = []
    for s_dir in search_dirs:
        if s_dir.exists():
            try:
                all_items.extend(list(s_dir.iterdir()))
            except Exception:
                pass

    # 1. Exact or stem match
    for item in all_items:
        fn_lower = item.name.lower()
        if cleaned == fn_lower or cleaned == item.stem.lower():
            try:
                os.startfile(str(item))
                if item.is_dir():
                    return f"Opening folder {item.name} in File Explorer for you, sir."
                return f"Opening file {item.name} for you, sir."
            except Exception as e:
                return f"Found {item.name}, but failed to launch: {e}"

    # 2. Token boundary match (e.g. "cs" and "topics" matches "cs_core_topics.pdf")
    token_str = re.sub(r"[^a-z0-9]+", " ", cleaned)
    tokens = [
        t for t in token_str.split()
        if len(t) > 1 and t not in ["the", "or", "and", "in", "of", "to", "for", "with", "a", "an"]
    ]
    if tokens:
        for item in all_items:
            fn_lower = item.name.lower()
            if all(re.search(r"(?:^|[_\s.-])" + re.escape(t), fn_lower) for t in tokens):
                try:
                    os.startfile(str(item))
                    if item.is_dir():
                        return f"Opening folder {item.name} in File Explorer for you, sir."
                    return f"Opening file {item.name} for you, sir."
                except Exception as e:
                    return f"Found {item.name}, but failed to launch: {e}"

    # 3. Fuzzy alphanumeric match (e.g. "autumn quest" -> "atomquest")
    clean_alpha = re.sub(r"[^a-z0-9]", "", cleaned)
    if len(clean_alpha) >= 4:
        item_map = {re.sub(r"[^a-z0-9]", "", item.name.lower()): item for item in all_items}
        matches = difflib.get_close_matches(clean_alpha, list(item_map.keys()), n=3, cutoff=0.60)
        for m in matches:
            ratio = difflib.SequenceMatcher(None, clean_alpha, m).ratio()
            if ratio >= 0.70:
                matched_item = item_map[m]
                try:
                    os.startfile(str(matched_item))
                    if matched_item.is_dir():
                        return f"Opening folder {matched_item.name} in File Explorer for you, sir."
                    return f"Opening file {matched_item.name} for you, sir."
                except Exception as e:
                    return f"Found {matched_item.name}, but failed to launch: {e}"

    # Fallback attempt on raw string
    try:
        os.startfile(cleaned)
        return f"Opening {cleaned} for you, sir."
    except Exception:
        pass

    return f"I could not find an application, folder, or file named '{cleaned}', sir."


# ---------------------------------------------------------------------------
# Audio Recording
# ---------------------------------------------------------------------------
def record_audio(
    max_wait_seconds: float = 6.0,
    max_speech_seconds: float = 12.0,
    threshold: float = 12.0
) -> bytes | None:
    """Record microphone audio with a 10-chunk pre-roll buffer and sensitive thresholding."""
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    SILENCE_DURATION = 0.9

    p = pyaudio.PyAudio()
    try:
        sample_size = p.get_sample_size(FORMAT)
        stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    except Exception as e:
        print(f"PyAudio open error: {e}")
        p.terminate()
        return None

    frames = []
    preroll = collections.deque(maxlen=10)
    started = False
    silent_chunks = 0
    start_time = time.time()
    speech_start_time = None

    while True:
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
        except Exception:
            break

        audio_data = np.frombuffer(data, dtype=np.int16)
        volume = float(np.abs(audio_data).mean())

        if volume > threshold:
            if not started:
                started = True
                speech_start_time = time.time()
                frames.extend(preroll)
            silent_chunks = 0
        elif started:
            silent_chunks += 1
        else:
            preroll.append(data)

        if started:
            frames.append(data)

        if started and (silent_chunks * CHUNK / RATE) > SILENCE_DURATION:
            break

        if started and speech_start_time and (time.time() - speech_start_time) > max_speech_seconds:
            break

        if not started and (time.time() - start_time) > max_wait_seconds:
            break

    try:
        stream.stop_stream()
        stream.close()
    except Exception:
        pass
    p.terminate()

    if not frames or len(frames) < int(RATE / CHUNK * 0.3):
        return None

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(sample_size)
        wf.setframerate(RATE)
        wf.writeframes(b"".join(frames))
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Visual Floating Desktop Agent (Tkinter)
# ---------------------------------------------------------------------------
class JarvisFloatingAgent:
    """Interactive Floating Desktop Assistant that renders prominently on the user's active monitor."""

    def __init__(self, assistant_ref=None) -> None:
        attach_to_user_desktop()
        self.assistant = assistant_ref
        self.root = tk.Tk()
        self.root.title("JARVIS • Floating Agent")
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#080d1a")

        # Position in top-right of the desktop
        self.width = 510
        self.height = 340
        sw = self.root.winfo_screenwidth()
        pos_x = max(50, sw - self.width - 40)
        pos_y = 60
        self.root.geometry(f"{self.width}x{self.height}+{pos_x}+{pos_y}")
        self.root.minsize(460, 300)

        # Minimize rather than terminate on close
        self.root.protocol("WM_DELETE_WINDOW", self.hide)

        # Variables for dragging window
        self._drag_x = 0
        self._drag_y = 0

        # 1. Header Bar (Draggable)
        hdr = tk.Frame(self.root, bg="#080d1a", cursor="fleur")
        hdr.pack(fill="x", padx=14, pady=(10, 4))
        hdr.bind("<ButtonPress-1>", self._start_drag)
        hdr.bind("<B1-Motion>", self._on_drag)

        lbl_title = tk.Label(
            hdr, text="⚡ J.A.R.V.I.S. FLOATING AGENT", fg="#00e5ff", bg="#080d1a",
            font=("Segoe UI", 11, "bold"), cursor="fleur"
        )
        lbl_title.pack(side="left")
        lbl_title.bind("<ButtonPress-1>", self._start_drag)
        lbl_title.bind("<B1-Motion>", self._on_drag)

        # Controls on right: Close, Minimize, Pin, Status
        btn_close = tk.Button(
            hdr, text="✕", command=self.hide, bg="#080d1a", fg="#ff5252",
            activebackground="#ff1744", activeforeground="white",
            relief="flat", font=("Segoe UI", 9, "bold"), padx=6, pady=0, cursor="hand2"
        )
        btn_close.pack(side="right", padx=(6, 0))

        btn_min = tk.Button(
            hdr, text="—", command=self.hide, bg="#080d1a", fg="#90a4ae",
            activebackground="#1e293b", activeforeground="white",
            relief="flat", font=("Segoe UI", 9, "bold"), padx=6, pady=0, cursor="hand2"
        )
        btn_min.pack(side="right", padx=(4, 0))

        self.always_on_top = tk.BooleanVar(value=True)
        top_chk = tk.Checkbutton(
            hdr, text="Pin", variable=self.always_on_top,
            command=self._toggle_topmost, bg="#080d1a", fg="#90a4ae",
            selectcolor="#141e2e", activebackground="#080d1a",
            activeforeground="#00e5ff", font=("Segoe UI", 8)
        )
        top_chk.pack(side="right", padx=(6, 2))

        self.status_text = tk.StringVar(value="🟢 STANDBY")
        self.status_badge = tk.Label(
            hdr, textvariable=self.status_text, fg="#00e676", bg="#121c2d",
            font=("Segoe UI", 9, "bold"), padx=10, pady=3, relief="flat"
        )
        self.status_badge.pack(side="right")

        # 2. Main Agent Body
        body = tk.Frame(self.root, bg="#080d1a")
        body.pack(fill="both", expand=True, padx=14, pady=4)

        # Left Column: Avatar & Push-To-Talk
        left_col = tk.Frame(body, bg="#080d1a", width=130)
        left_col.pack(side="left", fill="y", padx=(0, 12))

        self._load_avatar(left_col)

        # Animated Audio Equalizer Waveform Bars
        self.wave_canvas = tk.Canvas(
            left_col, width=110, height=22, bg="#080d1a", highlightthickness=0
        )
        self.wave_canvas.pack(pady=(2, 4))
        self.wave_bars = []
        for i in range(7):
            x = 14 + i * 14
            bar = self.wave_canvas.create_line(x, 11, x, 11, fill="#00e5ff", width=2)
            self.wave_bars.append(bar)

        self.anim_phase = 0.0
        self.is_animating_waves = False

        self.btn_ptt = tk.Button(
            left_col, text="🎙️  Speak", command=self._on_ptt_click,
            bg="#00838f", fg="white", activebackground="#00acc1",
            activeforeground="white", font=("Segoe UI", 9, "bold"),
            relief="flat", padx=12, pady=4, cursor="hand2"
        )
        self.btn_ptt.pack(fill="x", pady=(2, 0))

        # Right Column: Speech & Dialogue Card
        right_col = tk.Frame(body, bg="#0f172a", padx=14, pady=12, bd=1, relief="solid")
        right_col.pack(side="right", fill="both", expand=True)

        self.user_var = tk.StringVar(value="YOU: Say \"Hey Jarvis\" or press Ctrl+Space")
        self.lbl_user = tk.Label(
            right_col, textvariable=self.user_var, fg="#80deea", bg="#0f172a",
            font=("Segoe UI", 9), anchor="w"
        )
        self.lbl_user.pack(fill="x")

        sep = tk.Frame(right_col, bg="#1e293b", height=1)
        sep.pack(fill="x", pady=6)

        self.jarvis_var = tk.StringVar(value="JARVIS: At your service, sir. What task shall I execute for you?")
        self.lbl_jarvis = tk.Label(
            right_col, textvariable=self.jarvis_var, fg="#ffffff", bg="#0f172a",
            font=("Segoe UI", 10, "bold"), wraplength=310, justify="left", anchor="nw"
        )
        self.lbl_jarvis.pack(fill="both", expand=True)

        # 3. Bottom Quick Command Input Bar
        bottom_bar = tk.Frame(self.root, bg="#080d1a")
        bottom_bar.pack(fill="x", padx=14, pady=(4, 10))

        self.entry_cmd = tk.Entry(
            bottom_bar, bg="#141e2e", fg="white", insertbackground="#00e5ff",
            font=("Segoe UI", 9), relief="flat"
        )
        self.entry_cmd.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 8))
        self.entry_cmd.bind("<Return>", lambda e: self._on_send_text())

        btn_send = tk.Button(
            bottom_bar, text="Send ➤", command=self._on_send_text,
            bg="#00838f", fg="white", activebackground="#00acc1",
            activeforeground="white", font=("Segoe UI", 9, "bold"),
            relief="flat", padx=12, pady=3, cursor="hand2"
        )
        btn_send.pack(side="right")

        self._start_wave_loop()
        self.force_bring_to_front()

    def set_assistant(self, assistant) -> None:
        self.assistant = assistant

    def _start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag(self, event):
        deltax = event.x - self._drag_x
        deltay = event.y - self._drag_y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")

    def _toggle_topmost(self) -> None:
        self.root.attributes("-topmost", self.always_on_top.get())

    def _load_avatar(self, parent) -> None:
        try:
            img = Image.open("avatar.png").convert("RGBA")
            size = (90, 90)
            img = img.resize(size, Image.Resampling.LANCZOS)
            mask = Image.new("L", size, 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size[0], size[1]), fill=255)
            circular = ImageOps.fit(img, mask.size, centering=(0.5, 0.5))
            circular.putalpha(mask)
            self.avatar_img = ImageTk.PhotoImage(circular)
            self.avatar_label = tk.Label(
                parent, image=self.avatar_img, bg="#080d1a", bd=0, cursor="hand2"
            )
            self.avatar_label.pack(pady=2)
            self.avatar_label.bind("<Button-1>", lambda e: self._on_ptt_click())
        except Exception as e:
            print("Avatar load note:", e)

    def _on_ptt_click(self) -> None:
        if self.assistant:
            self.assistant.trigger_hotkey()

    def _on_send_text(self) -> None:
        text = self.entry_cmd.get().strip()
        if not text:
            return
        self.entry_cmd.delete(0, tk.END)
        if self.assistant:
            threading.Thread(target=self.assistant.handle_typed_command, args=(text,), daemon=True).start()

    def set_status(self, text: str, state_type: str = "standby") -> None:
        colors = {
            "standby": ("#00e676", "#121c2d"),
            "listening": ("#00e5ff", "#0c283d"),
            "thinking": ("#ffd600", "#332a0d"),
            "speaking": ("#b388ff", "#29153d"),
            "error": ("#ff5252", "#3a1313"),
        }
        fg, bg = colors.get(state_type, ("#00e5ff", "#121c2d"))
        self.is_animating_waves = state_type in ["listening", "speaking"]
        self.root.after(0, self._set_status_ui, text, fg, bg)

    def _set_status_ui(self, text: str, fg: str, bg: str) -> None:
        self.status_text.set(text)
        self.status_badge.configure(fg=fg, bg=bg)

    def update_dialogue(self, user_text: str = None, jarvis_text: str = None) -> None:
        self.root.after(0, self._update_dialogue_ui, user_text, jarvis_text)

    def _update_dialogue_ui(self, user_text: str, jarvis_text: str) -> None:
        if user_text is not None:
            self.user_var.set(f"YOU: {user_text}")
        if jarvis_text is not None:
            self.jarvis_var.set(f"JARVIS: {jarvis_text}")

    def pop_open(self) -> None:
        self.root.after(0, self._pop_open_ui)

    def _pop_open_ui(self) -> None:
        try:
            self.root.deiconify()
            self.root.lift()
            if self.always_on_top.get():
                self.root.attributes("-topmost", True)
            self.force_bring_to_front()
            self.root.focus_force()
        except Exception:
            pass

    def force_bring_to_front(self) -> None:
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, "JARVIS • Floating Agent")
            if hwnd:
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_SHOWWINDOW = 0x0040
                HWND_TOPMOST = -1
                user32.ShowWindow(hwnd, 5)
                user32.SetForegroundWindow(hwnd)
                user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        except Exception:
            pass

    def hide(self) -> None:
        try:
            self.root.after(0, self.root.withdraw)
        except Exception:
            pass

    def _start_wave_loop(self) -> None:
        self.anim_phase += 0.25
        if self.is_animating_waves:
            for i, bar in enumerate(self.wave_bars):
                h = 2 + int(abs(math.sin(self.anim_phase + i * 0.7)) * 8)
                x = 14 + i * 14
                self.wave_canvas.coords(bar, x, 11 - h, x, 11 + h)
        else:
            for i, bar in enumerate(self.wave_bars):
                x = 14 + i * 14
                self.wave_canvas.coords(bar, x, 11, x, 11)
        self.root.after(50, self._start_wave_loop)


# ---------------------------------------------------------------------------
# Assistant Brain & Audio Handler
# ---------------------------------------------------------------------------
class Assistant:
    """Manages audio transcription, intent matching, conversational LLM, and TTS."""

    def __init__(self, ui: JarvisFloatingAgent):
        self.ui = ui
        self.busy = threading.Lock()
        self.is_busy = False
        self.is_in_conversation = False
        self.last_interaction_time = time.time()
        self.model = ollama_model
        self.client = openai_client
        self.messages = []

        print("Preloading Faster-Whisper base.en model...")
        self.whisper_model = None
        for model_name in ["base.en", "base"]:
            try:
                from faster_whisper import WhisperModel
                self.whisper_model = WhisperModel(model_name, device="cpu", compute_type="int8")
                print(f"Faster-Whisper '{model_name}' ready!")
                break
            except Exception as exc:
                print(f"Whisper load attempt ({model_name}) error: {exc}")

    def update_conversation_log(self, role: str, content: str):
        try:
            conv = []
            if os.path.exists("conversation.json"):
                try:
                    with open("conversation.json", "r", encoding="utf-8") as f:
                        conv = json.load(f)
                except Exception:
                    conv = []
            conv.append({
                "role": role,
                "content": content,
                "time": datetime.datetime.now().strftime("%H:%M:%S")
            })
            if len(conv) > 100:
                conv = conv[-100:]
            with open("conversation.json", "w", encoding="utf-8") as f:
                json.dump(conv, f, indent=2)
        except Exception as e:
            print(f"Log update error: {e}")

    def transcribe(self, audio: bytes) -> str:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio)
            audio_path = tmp.name

        try:
            if self.whisper_model is None:
                from faster_whisper import WhisperModel
                self.whisper_model = WhisperModel("base.en", device="cpu", compute_type="int8")

            # Bias Whisper vocabulary with expected assistant commands and names
            segments, _ = self.whisper_model.transcribe(
                audio_path,
                beam_size=3,
                language="en",
                initial_prompt="Hey Jarvis, Jarvis, Google Chrome, Chrome browser, Microsoft Edge, Brave, File Explorer, Downloads, Notepad, Calculator, VS Code, Atomquest, CS Core Topics, sleep, be quiet.",
                condition_on_previous_text=False
            )
            transcript = " ".join(segment.text for segment in segments).strip()
            return transcript
        finally:
            try:
                os.unlink(audio_path)
            except FileNotFoundError:
                pass

    def try_direct_action(self, text: str) -> str | None:
        """Handle direct desktop operations with strict, accurate priority routing."""
        lower = text.lower().strip(" .!?")

        # 1. Close / Sleep / Quiet commands
        if any(w in lower for w in [
            "go to sleep", "sleep", "close window", "minimize", "goodbye", "dismiss",
            "exit", "be quiet", "quiet", "stop talking", "shut up", "no need", "one need"
        ]):
            self.is_in_conversation = False
            self.ui.set_status("🟢 STANDBY", "standby")
            self.ui.hide()
            return "Standing by in the background, sir."

        # 2. Application Termination ("close chrome", "close notepad", "close edge", etc.)
        if any(lower.startswith(p) for p in ["close ", "terminate ", "kill ", "shut down ", "shut "]):
            close_res = close_application(lower)
            if close_res:
                return close_res

        # 3. System Volume & Media Controls
        if any(w in lower for w in ["volume up", "increase volume", "louder", "raise volume"]):
            for _ in range(4):
                keyboard.send("volume up")
            return "Increasing system volume, sir."

        if any(w in lower for w in ["volume down", "decrease volume", "quieter", "lower volume"]):
            for _ in range(4):
                keyboard.send("volume down")
            return "Decreasing system volume, sir."

        if any(w in lower for w in ["mute audio", "mute volume", "mute sound", "unmute", "mute"]):
            keyboard.send("volume mute")
            return "Toggling audio mute, sir."

        if any(w in lower for w in ["pause music", "pause song", "resume music", "play music", "play song", "pause audio"]):
            keyboard.send("play/pause media")
            return "Toggling media playback, sir."

        if any(w in lower for w in ["next track", "next song", "skip track", "skip song"]):
            keyboard.send("next track")
            return "Skipping to next track, sir."

        if any(w in lower for w in ["previous track", "previous song", "last track"]):
            keyboard.send("previous track")
            return "Playing previous track, sir."

        # 4. Time query
        if any(w in lower for w in ["what time", "current time", "time is it", "time now", "what's the time", "the time"]):
            now_str = datetime.datetime.now().strftime("%I:%M %p")
            return f"It is currently {now_str}, sir."

        # 5. Date query
        if any(w in lower for w in ["what date", "today's date", "what is today's date", "what day is today", "what day is it"]):
            today_str = datetime.datetime.now().strftime("%A, %B %d, %Y")
            return f"Today is {today_str}, sir."

        # 6. YouTube search / play
        m_yt = re.search(r"\b(?:play|search)\s+(.+?)\s+on\s+youtube\b", lower)
        if m_yt:
            query = m_yt.group(1).strip()
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
            webbrowser.open(url)
            return f"Playing {query} on YouTube, sir."

        # 7. Wikipedia search
        m_wiki = re.search(r"\b(?:search\s+wikipedia\s+for|who\s+is|what\s+is)\s+(.+?)\s+on\s+wikipedia\b", lower)
        if m_wiki:
            query = m_wiki.group(1).strip()
            url = f"https://en.wikipedia.org/wiki/Special:Search?search={urllib.parse.quote(query)}"
            webbrowser.open(url)
            return f"Searching Wikipedia for {query}, sir."

        # 8. Google search (only when user explicitly commands search, NOT when opening apps/sites)
        if not any(lower.startswith(p) for p in ["open ", "launch ", "start ", "show ", "view ", "run ", "close "]):
            m_search = re.search(r"^(?:search\s+(?:google\s+for|the\s+web\s+for|for)?|google\s+search\s+for|google)\s+(.+)$", lower)
            if m_search and not m_search.group(1).startswith(("chrome", "drive", "docs", "sheets")):
                query = m_search.group(1).strip()
                url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
                webbrowser.open(url)
                return f"Searching Google for {query}, sir."

        # 9. Lock workstation
        if "lock" in lower and ("screen" in lower or "pc" in lower or "computer" in lower or "workstation" in lower):
            try:
                ctypes.windll.user32.LockWorkStation()
            except Exception:
                os.system("rundll32.exe user32.dll,LockWorkStation")
            return "Locking your workstation now, sir."

        # 10. Screenshot
        if "screenshot" in lower or "snipping tool" in lower or "capture screen" in lower:
            try:
                os.startfile("snippingtool.exe")
            except Exception:
                os.system("start snippingtool")
            return "Opening the Snipping Tool for a screenshot, sir."

        # 11. Direct application, folder, or file check (e.g. user just says "atomquest", "downloads", "notepad", "google chrome")
        open_res = smart_open(lower)
        if open_res and open_res.startswith("Opening "):
            return open_res

        # If user explicitly phrased it as an opener command, return the smart_open response even if not found
        is_explicit_opener = (
            any(lower.startswith(p) for p in [
                "open ", "launch ", "start ", "show ", "view ", "run ", "with ", "in one ", "upon "
            ])
            or "open " in lower
        )
        if is_explicit_opener:
            return open_res

        # Not a direct desktop command: pass to LLM
        return None

    def generate_response(self, transcript: str) -> str:
        direct_reply = self.try_direct_action(transcript)
        if direct_reply:
            return direct_reply

        if self.client is None:
            return "Local Ollama is not reachable, sir. Please ensure Ollama is running."

        now = datetime.datetime.now()
        current_time = now.strftime("%I:%M %p")
        current_date = now.strftime("%A, %B %d, %Y")
        system_instruction = SYSTEM_PROMPT_TEMPLATE.format(current_time=current_time, current_date=current_date)

        if not self.messages:
            self.messages = [{"role": "system", "content": system_instruction}]
        else:
            self.messages[0] = {"role": "system", "content": system_instruction}

        self.messages.append({"role": "user", "content": transcript})
        if len(self.messages) > 10:
            self.messages = [self.messages[0]] + self.messages[-9:]

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                temperature=0.7,
                max_tokens=150
            )
            reply = completion.choices[0].message.content or "I am at your service, sir."
            self.messages.append({"role": "assistant", "content": reply})
            return reply.strip()
        except Exception as exc:
            print(f"Ollama generation error: {exc}")
            return f"I encountered an error communicating with my core: {exc}"

    def speak(self, text: str) -> None:
        try:
            spoken_text = clean_text_for_speech(text)
            if not spoken_text:
                return

            self.ui.set_status("🔊 SPEAKING", "speaking")
            engine = pyttsx3.init()
            engine.setProperty("rate", 185)

            voices = engine.getProperty("voices")
            for voice in voices:
                if "david" in voice.name.lower():
                    engine.setProperty("voice", voice.id)
                    break

            engine.say(spoken_text)
            engine.runAndWait()
            engine.stop()
        except Exception as exc:
            print(f"TTS error: {exc}")
        finally:
            if self.is_in_conversation:
                self.ui.set_status("🎙️ LISTENING (Ready for command)", "listening")
            else:
                self.ui.set_status("🟢 STANDBY", "standby")

    def _execute_command(self, query: str):
        """Execute a validated query, update the visual popup, and speak."""
        print(f"\n[USER]: {query}")
        self.ui.update_dialogue(user_text=query, jarvis_text="Processing request...")
        self.ui.set_status("🧠 THINKING", "thinking")
        self.update_conversation_log("USER", query)

        answer = self.generate_response(query)
        print(f"[JARVIS]: {answer}\n")
        self.ui.update_dialogue(jarvis_text=answer)
        self.update_conversation_log("JARVIS", answer)

        self.speak(answer)
        self.last_interaction_time = time.time()

    def handle_typed_command(self, text: str):
        if not self.busy.acquire(blocking=False):
            return
        self.is_busy = True
        try:
            self.ui.pop_open()
            self.is_in_conversation = True
            self._execute_command(text)
        finally:
            self.is_busy = False
            self.busy.release()

    def process_voice_turn(self, audio: bytes, require_wake_word: bool = False):
        """Handle incoming speech: check wake-word, pop up UI, execute command, and sustain conversation."""
        if not self.busy.acquire(blocking=False):
            return
        self.is_busy = True
        try:
            transcript = self.transcribe(audio)
            if not transcript or len(transcript.strip()) < 2:
                if not self.is_in_conversation:
                    self.ui.set_status("🟢 STANDBY", "standby")
                return

            lower = transcript.lower()

            if require_wake_word and not self.is_in_conversation:
                matched = False
                matched_pat = None
                for pat in WAKE_PATTERNS:
                    m = re.search(pat, lower)
                    if m:
                        matched = True
                        matched_pat = pat
                        break

                if not matched:
                    return

                # Wake word detected: POP UP ON SCREEN & CHIME!
                play_chime()
                self.ui.pop_open()
                self.is_in_conversation = True
                self.last_interaction_time = time.time()

                cmd = re.sub(matched_pat, "", lower).strip(" ,.!?")
                cmd = re.sub(r"^(?:please|could you|can you|would you mind|just)\s+", "", cmd).strip()

                if not cmd:
                    # User only said "Hey Jarvis"
                    self.ui.update_dialogue(user_text="Hey Jarvis", jarvis_text="Yes, sir? What can I do for you?")
                    self.ui.set_status("🎙️ LISTENING", "listening")
                    self.speak("Yes, sir?")

                    # Listen immediately for the follow-up command
                    followup = record_audio(max_wait_seconds=8.0, threshold=12.0)
                    if followup:
                        cmd_text = self.transcribe(followup)
                        if cmd_text and len(cmd_text.strip()) > 1:
                            self._execute_command(cmd_text)
                    return
                else:
                    # User said wake word and command together
                    query = cmd
            else:
                # Already in multi-turn conversation
                self.ui.pop_open()
                self.is_in_conversation = True
                self.last_interaction_time = time.time()
                query = transcript

            self._execute_command(query)

        except Exception as exc:
            print(f"Voice processing error: {exc}")
            self.ui.set_status("🟢 STANDBY", "standby")
        finally:
            self.is_busy = False
            self.busy.release()
            time.sleep(0.15)

    def listen_loop(self):
        """Continuous background listening loop."""
        print("JARVIS voice listener is active. Say 'Hey Jarvis' or press Ctrl+Space...")
        while True:
            if self.is_busy:
                time.sleep(0.15)
                continue

            # Auto-timeout active conversation after 20 seconds of inactivity
            if self.is_in_conversation and (time.time() - self.last_interaction_time) > 20.0:
                print("Conversation idle timeout. Returning to background standby.")
                self.is_in_conversation = False
                self.ui.set_status("🟢 STANDBY", "standby")

            try:
                require_wake = not self.is_in_conversation
                audio = record_audio(max_wait_seconds=5.0, threshold=12.0)
                if audio and not self.is_busy:
                    self.process_voice_turn(audio, require_wake_word=require_wake)
            except Exception as e:
                time.sleep(0.4)

    def trigger_hotkey(self):
        threading.Thread(target=self._hotkey_action, daemon=True).start()

    def _hotkey_action(self):
        if not self.busy.acquire(blocking=False):
            return
        self.is_busy = True
        try:
            play_chime()
            self.ui.pop_open()
            self.is_in_conversation = True
            self.last_interaction_time = time.time()
            self.ui.set_status("🎙️ LISTENING", "listening")
            self.ui.update_dialogue(user_text="Listening...", jarvis_text="Speak your command, sir...")

            audio = record_audio(max_wait_seconds=8.0, threshold=12.0)
            if audio:
                self.ui.set_status("🧠 THINKING", "thinking")
                transcript = self.transcribe(audio)
                if transcript and len(transcript.strip()) > 1:
                    self._execute_command(transcript)
                else:
                    self.ui.set_status("🎙️ LISTENING (Ready for command)", "listening")
            else:
                self.ui.set_status("🎙️ LISTENING (Ready for command)", "listening")
        except Exception as e:
            print("Hotkey error:", e)
            self.ui.set_status("🟢 STANDBY", "standby")
        finally:
            self.is_busy = False
            self.busy.release()
            time.sleep(0.15)


# ---------------------------------------------------------------------------
# Application Entry Point
# ---------------------------------------------------------------------------
def main():
    attach_to_user_desktop()

    print("=" * 60)
    print("  JARVIS Desktop Floating Agent (v5.3)")
    print("  Powered by Ollama (llama3.1) + Faster-Whisper + PyTTSx3")
    print("=" * 60)
    print(f"  Model:       {ollama_model}")
    print("  Wake Words:  'Hey Jarvis' or 'Jarvis'")
    print(f"  Hotkey:      {HOTKEY.upper()}")
    print("  Status:      Floating Agent Live on Desktop")
    print("=" * 60)

    ui = JarvisFloatingAgent()
    assistant = Assistant(ui)
    ui.set_assistant(assistant)

    try:
        keyboard.add_hotkey(HOTKEY, assistant.trigger_hotkey)
    except Exception as e:
        print(f"Hotkey note: {e}")

    # Launch background listening thread
    threading.Thread(target=assistant.listen_loop, daemon=True).start()

    # Start Tkinter event loop
    ui.root.mainloop()


if __name__ == "__main__":
    main()
