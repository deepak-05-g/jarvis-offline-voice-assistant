import json
import time
import threading
from taipy.gui import Gui, State, invoke_callback
import os

conversation = []

page = """
<|container|
# JARVIS Conversation

<|{conversation}|table|columns=role;content|show_all|width=100%|>
|>
"""

def update_state(state, val):
    state.conversation = val

def watch_file(gui_instance):
    last_len = -1
    while True:
        time.sleep(1)
        try:
            if os.path.exists("conversation.json"):
                with open("conversation.json", "r", encoding="utf-8") as f:
                    conv = json.load(f)
                if len(conv) != last_len:
                    last_len = len(conv)
                    invoke_callback(gui_instance, update_state, (conv,))
        except Exception as e:
            pass

gui = Gui(page=page)

if __name__ == "__main__":
    print("Starting Taipy display...")
    if os.path.exists("conversation.json"):
        # Clear old conversation on start
        with open("conversation.json", "w", encoding="utf-8") as f:
            json.dump([], f)
    
    threading.Thread(target=watch_file, args=(gui,), daemon=True).start()
    gui.run(port=5000, title="JARVIS", use_reloader=False)
