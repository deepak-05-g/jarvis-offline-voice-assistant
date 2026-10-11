# JARVIS 100% Local Offline Voice Assistant

A free, private, and 100% offline Windows desktop voice assistant powered by:
- **Speech-to-Text**: [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper) (runs locally on CPU)
- **Brain (LLM)**: [Ollama](https://ollama.com/) running `llama3.1` (or `llama3.2`)
- **Text-to-Speech**: [pyttsx3](https://pyttsx3.readthedocs.io/) (native Windows Microsoft SAPI5 voices)
- **GUI**: Lightweight Tkinter popup window

**Zero API keys or subscriptions required!**

---

## Prerequisites

1. **Python 3.10+** (already installed in `.venv`)
2. **Ollama** installed and running on Windows:
   - Download from [ollama.com](https://ollama.com/download)
   - Ensure the model is downloaded by running:
     ```powershell
     ollama pull llama3.1
     ```

---

## How to Run

From this project directory in PowerShell:

```powershell
.\.venv\Scripts\python.exe main.py
```

---

## How to Interact

- **Wake Word**: Say **"Jarvis, what time is it?"** or **"Jarvis, open downloads"**.
- **Push-to-Talk Hotkey**: Press **<kbd>Ctrl</kbd> + <kbd>Space</kbd>** and speak your command directly.

### Supported Fast Desktop Commands:
- **Folders**: *"open downloads"*, *"open desktop"*, *"open documents"*, *"open pictures"*, *"open music"*
- **Apps**: *"open notepad"*, *"open calculator"*, *"open chrome"*, *"open explorer"*, *"open terminal"*, *"open settings"*, *"open task manager"*
- **Time & Date**: *"what time is it"*, *"what's today's date"*
- **General Conversation**: Any question or conversational topic is answered naturally by the local `llama3.1` model.
