import customtkinter as ctk
import os
import json
import subprocess
import winreg
import threading
import urllib.parse
import shutil
import psutil
import keyboard
import pystray
import speech_recognition as sr
from PIL import Image, ImageDraw

# SES KONTROLÜ İÇİN GEREKLİ MODÜLLER
from ctypes import cast, POINTER

HISTORY_FILE = "nexus_history.json"
MEMORY_FILE  = "nexus_memory.json"

class NexusAI_UI(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- MAIN WINDOW SETTINGS ---
        self.title("Nexus AI")
        self.geometry("950x650")

        self.protocol('WM_DELETE_WINDOW', self.hide_to_tray)
        keyboard.add_hotkey('ctrl+space', self.toggle_window)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ==========================================
        # SIDEBAR (HISTORY AREA)
        # ==========================================
        self.sidebar_frame = ctk.CTkFrame(self, width=250, corner_radius=0, fg_color=("gray95", "gray13"))
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(2, weight=1)

        self.new_chat_btn = ctk.CTkButton(
            self.sidebar_frame, text="+ New Chat",
            font=("Segoe UI", 15, "bold"),
            fg_color=("gray85", "gray20"), text_color=("black", "white"),
            hover_color=("gray75", "gray30"), corner_radius=8, height=40,
            command=self.clear_chat
        )
        self.new_chat_btn.grid(row=0, column=0, padx=20, pady=(20, 20), sticky="ew")

        # History label + Clear All butonu yan yana
        history_header = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        history_header.grid(row=1, column=0, padx=10, pady=(0, 5), sticky="ew")
        history_header.grid_columnconfigure(0, weight=1)

        self.history_label = ctk.CTkLabel(
            history_header, text="History",
            font=("Segoe UI", 12, "bold"), text_color=("gray40", "gray60")
        )
        self.history_label.grid(row=0, column=0, padx=15, sticky="w")

        self.clear_all_btn = ctk.CTkButton(
            history_header, text="Clear All",
            font=("Segoe UI", 11), width=75, height=24,
            fg_color=("gray80", "gray25"), text_color=("black", "gray70"),
            hover_color=("#FF4444", "#CC2222"), corner_radius=6,
            command=self._clear_all_history
        )
        self.clear_all_btn.grid(row=0, column=1, padx=5, sticky="e")

        self.history_frame = ctk.CTkScrollableFrame(
            self.sidebar_frame, fg_color="transparent", corner_radius=0
        )
        self.history_frame.grid(row=2, column=0, padx=10, pady=0, sticky="nsew")

        self.theme_switch = ctk.CTkSegmentedButton(
            self.sidebar_frame, values=["Dark", "Light"], command=self.change_theme
        )
        self.theme_switch.grid(row=3, column=0, padx=20, pady=20, sticky="ew")
        self.theme_switch.set("Dark")

        # ==========================================
        # MAIN CHAT AREA
        # ==========================================
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=("white", "#0F0F11"))
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)

        self.chat_display = ctk.CTkTextbox(
            self.main_frame, wrap="word", font=("Segoe UI", 15),
            fg_color="transparent", text_color=("black", "white")
        )
        self.chat_display.grid(row=0, column=0, padx=40, pady=(40, 10), sticky="nsew")
        self.chat_display.configure(state="disabled")

        self.input_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.input_frame.grid(row=1, column=0, padx=40, pady=(10, 30), sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            self.input_frame, placeholder_text="Give Nexus a command...",
            height=50, font=("Segoe UI", 15), corner_radius=25,
            fg_color=("gray90", "gray15"), border_width=2,
            border_color=("#111111", "#00D2FF")
        )
        self.entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.entry.bind("<Return>", lambda event: self.process_command())
        self.entry.bind("<FocusIn>",  lambda e: self.entry.configure(border_color=("#000000", "#00FFFF")))
        self.entry.bind("<FocusOut>", lambda e: self.entry.configure(border_color=("#111111", "#00D2FF")))

        # ==========================================
        # DİNAMİK İKONLAR VE HOVER EFEKTLERİ
        # ==========================================
        try:
            self.send_icon_default = ctk.CTkImage(
                light_image=Image.open("send_black.png"),
                dark_image=Image.open("send_white.png"), size=(24, 24)
            )
            self.mic_icon_default = ctk.CTkImage(
                light_image=Image.open("mic_black.png"),
                dark_image=Image.open("mic_white.png"), size=(24, 24)
            )
            self.send_icon_hover = ctk.CTkImage(
                light_image=Image.open("send_white.png"),
                dark_image=Image.open("send_white.png"), size=(24, 24)
            )
            self.mic_icon_hover = ctk.CTkImage(
                light_image=Image.open("mic_white.png"),
                dark_image=Image.open("mic_white.png"), size=(24, 24)
            )
        except Exception:
            print("Uyarı: İkon png dosyaları bulunamadı!")
            self.send_icon_default = self.mic_icon_default = None
            self.send_icon_hover  = self.mic_icon_hover  = None

        self.send_btn = ctk.CTkButton(
            self.input_frame,
            image=self.send_icon_default, text="" if self.send_icon_default else "▶",
            width=50, height=50, corner_radius=25,
            fg_color="transparent", hover_color="#111111",
            command=self.process_command
        )
        self.send_btn.grid(row=0, column=1)

        self.mic_btn = ctk.CTkButton(
            self.input_frame,
            image=self.mic_icon_default, text="" if self.mic_icon_default else "🎤",
            width=50, height=50, corner_radius=25,
            fg_color="transparent", hover_color="#111111",
            command=self.start_listening_thread
        )
        self.mic_btn.grid(row=0, column=2, padx=(10, 0))

        if self.send_icon_default:
            self.send_btn.bind("<Enter>", lambda e: self.send_btn.configure(image=self.send_icon_hover))
            self.send_btn.bind("<Leave>", lambda e: self.send_btn.configure(image=self.send_icon_default))
            self.mic_btn.bind("<Enter>",  lambda e: self.mic_btn.configure(image=self.mic_icon_hover))
            self.mic_btn.bind("<Leave>",  lambda e: self.mic_btn.configure(image=self.mic_icon_default))

        self.recognizer = sr.Recognizer()

        # ==========================================
        # BAŞLANGIÇTA MEMORY & HISTORY YÜKLE
        # ==========================================
        self._load_history_to_sidebar()
        self._load_memory_to_chat()

        self.animate_text("Nexus AI: Universal control interface active.\nPress Ctrl+Space anywhere to summon or hide me.")

    # ==========================================
    # JSON KAYIT & YÜKLEME
    # ==========================================
    def _load_json(self, filepath):
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_json(self, filepath, data):
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"JSON kayıt hatası: {e}")

    def _load_history_to_sidebar(self):
        """nexus_history.json'daki geçmiş komutları sidebar'a yükler."""
        history = self._load_json(HISTORY_FILE)
        for item in history:
            self._add_history_btn(item.get("text", ""))

    def _load_memory_to_chat(self):
        """nexus_memory.json'daki önceki konuşmayı chat'e yükler."""
        memory = self._load_json(MEMORY_FILE)
        if not memory:
            return
        self.chat_display.configure(state="normal")
        for entry in memory:
            prefix = "You" if entry.get("is_user") else "Nexus AI"
            self.chat_display.insert("end", f"{prefix}: {entry.get('text', '')}\n\n")
        self.chat_display.configure(state="disabled")
        self.chat_display.see("end")

    def _append_memory(self, user_text, response_text):
        """Her konuşmayı nexus_memory.json'a ekler."""
        memory = self._load_json(MEMORY_FILE)
        memory.append({"text": user_text,      "is_user": True})
        memory.append({"text": response_text,  "is_user": False})
        self._save_json(MEMORY_FILE, memory)

    def _append_history(self, user_text):
        """Komutu nexus_history.json'a ekler."""
        history = self._load_json(HISTORY_FILE)
        history.append({"text": user_text})
        self._save_json(HISTORY_FILE, history)

    # ==========================================
    # 🎬 ADVANCED UI ANIMATIONS
    # ==========================================
    def animate_text(self, target_text, current_index=0):
        if current_index == 0:
            self.chat_display.configure(state="normal")

        if current_index < len(target_text):
            self.chat_display.configure(state="normal")
            self.chat_display.insert("end", target_text[current_index])
            self.chat_display.configure(state="disabled")
            self.chat_display.see("end")
            self.after(12, self.animate_text, target_text, current_index + 1)
        else:
            self.chat_display.configure(state="normal")
            self.chat_display.insert("end", "\n\n")
            self.chat_display.configure(state="disabled")
            self.chat_display.see("end")

    # ==========================================
    # GHOST PROTOCOL (TRAY & HOTKEY)
    # ==========================================
    def create_tray_icon(self):
        image = Image.new('RGB', (64, 64), color=(15, 15, 17))
        draw  = ImageDraw.Draw(image)
        draw.ellipse((8,  8,  56, 56), fill=(0, 210, 255))
        draw.ellipse((16, 16, 48, 48), fill=(15, 15, 17))

        menu = pystray.Menu(
            pystray.MenuItem('Aç (Ctrl+Space)', self.show_from_tray),
            pystray.MenuItem('Tamamen Kapat',   self.quit_app)
        )
        self.tray_icon = pystray.Icon("NexusAI", image, "Nexus AI", menu)
        self.tray_icon.run()

    def hide_to_tray(self):
        self.withdraw()
        threading.Thread(target=self.create_tray_icon, daemon=True).start()

    def show_from_tray(self, icon=None, item=None):
        if hasattr(self, 'tray_icon') and self.tray_icon:
            self.tray_icon.stop()
        self.after(0, self.deiconify)
        self.after(0,   lambda: self.attributes('-topmost', 1))
        self.after(100, lambda: self.attributes('-topmost', 0))
        self.after(100, self.entry.focus)

    def toggle_window(self):
        """FİX: Pencere görünürse gizle, gizliyse göster."""
        if self.state() == 'withdrawn':
            self.show_from_tray()
        else:
            self.hide_to_tray()

    def quit_app(self, icon=None, item=None):
        if hasattr(self, 'tray_icon') and self.tray_icon:
            self.tray_icon.stop()
        self.quit()

    # ==========================================
    # VOICE COMMAND PROTOCOL
    # ==========================================
    def start_listening_thread(self):
        threading.Thread(target=self.listen_to_mic, daemon=True).start()

    def listen_to_mic(self):
        self.entry.delete(0, "end")
        self.entry.insert(0, "Listening...")
        self.mic_btn.configure(state="disabled")

        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=7)
                text  = self.recognizer.recognize_google(audio, language="en-US")
                self.entry.delete(0, "end")
                self.entry.insert(0, text)
                self.after(0, self.process_command)
        except sr.UnknownValueError:
            self.entry.delete(0, "end")
            self.update_ui("Nexus AI: Could not understand audio.")
        except sr.RequestError:
            self.entry.delete(0, "end")
            self.update_ui("Nexus AI: API connection failed.")
        except Exception as e:
            self.entry.delete(0, "end")
            if "timeout" not in str(e).lower():
                self.update_ui(f"Nexus AI: Microphone error -> {e}")

        self.mic_btn.configure(state="normal")

    # ==========================================
    # HARDWARE CONTROLS (VOLUME) — DÜZELTİLDİ
    # ==========================================
    def _set_volume(self, level, user_text):
        """
        FIX: pycaw'ın AudioDevice.Activate() hatası yerine
        doğrudan ctypes + comtypes ile Windows Audio API çağrısı.
        """
        try:
            import comtypes
            comtypes.CoInitialize()

            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            from comtypes import CLSCTX_ALL

            # GetSpeakers() bir IMMDevice döndürür — doğrudan .Activate() çağır
            speakers = AudioUtilities.GetSpeakers()
            interface = speakers.Activate(
                IAudioEndpointVolume._iid_,
                CLSCTX_ALL,
                None
            )
            volume_ctrl = cast(interface, POINTER(IAudioEndpointVolume))
            volume_ctrl.SetMute(0, None)
            scalar = max(0.0, min(1.0, level / 100.0))
            volume_ctrl.SetMasterVolumeLevelScalar(scalar, None)
            response = f"Nexus AI: Volume set to {level}%."

        except ImportError:
            # pycaw yoksa nircmd ile fallback
            try:
                nircmd = shutil.which("nircmd")
                if nircmd:
                    val = int(65535 * level / 100)
                    subprocess.run([nircmd, "setsysvolume", str(val)], check=True)
                    response = f"Nexus AI: Volume set to {level}% (via nircmd)."
                else:
                    response = "Nexus AI: pycaw not installed. Run: pip install pycaw"
            except Exception as e2:
                response = f"Nexus AI: Volume fallback error -> {e2}"

        except Exception as e:
            response = f"Nexus AI: Volume error -> {e}"

        finally:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass

        self.after(0, self._safe_update_ui, response, user_text)

    # ==========================================
    # SYSTEM DIAGNOSTICS & APPS
    # ==========================================
    def get_system_health(self):
        cpu  = psutil.cpu_percent(interval=0.5)
        ram  = psutil.virtual_memory()
        disk = psutil.disk_usage('C:\\')
        status = ("WARNING: System under heavy load!"
                  if cpu > 85 or ram.percent > 85
                  else "All systems operating normally.")
        return (f"--- NEXUS HARDWARE DIAGNOSTICS ---\n"
                f"CPU  Usage : {cpu}%\n"
                f"RAM  Usage : {ram.percent}%\n"
                f"Disk C     : {disk.percent}% Full\n"
                f"----------------------------------\n"
                f"Status: {status}")

    def search_local_files(self, filename):
        user_profile = os.environ.get("USERPROFILE", "C:\\Users")
        safe_dirs    = ["Desktop", "Downloads", "Documents", "Pictures", "Videos"]
        for d in safe_dirs:
            target_dir = os.path.join(user_profile, d)
            if not os.path.exists(target_dir):
                continue
            for root, dirs, files in os.walk(target_dir):
                for file in files:
                    if filename.lower() in file.lower():
                        return os.path.join(root, file)
        return None

    def find_application_path(self, app_name):
        """
        FIX: Çok katmanlı uygulama arama:
        1) Bilinen kısayollar (UWP + yaygın uygulamalar)
        2) Registry App Paths
        3) PATH (shutil.which)
        4) Program Files klasörlerinde fuzzy .exe arama
        """
        app_name_lower = app_name.lower().strip()

        # --- 1. Bilinen kısayollar ---
        known = {
            # UWP / protokol
            "spotify":        "spotify:",
            "whatsapp":       "whatsapp:",
            "settings":       "ms-settings:",
            "calculator":     "calc.exe",
            "paint":          "mspaint.exe",
            "notepad":        "notepad.exe",
            "cmd":            "cmd.exe",
            "powershell":     "powershell.exe",
            "task manager":   "taskmgr.exe",
            "file explorer":  "explorer.exe",
            "explorer":       "explorer.exe",
            # Office
            "word":           r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
            "excel":          r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
            "powerpoint":     r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
            "outlook":        r"C:\Program Files\Microsoft Office\root\Office16\OUTLOOK.EXE",
            "onenote":        r"C:\Program Files\Microsoft Office\root\Office16\ONENOTE.EXE",
            # Tarayıcılar
            "chrome":         r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "firefox":        r"C:\Program Files\Mozilla Firefox\firefox.exe",
            "edge":           r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            # Diğer
            "vlc":            r"C:\Program Files\VideoLAN\VLC\vlc.exe",
            "vscode":         r"C:\Users\{user}\AppData\Local\Programs\Microsoft VS Code\Code.exe",
            "vs code":        r"C:\Users\{user}\AppData\Local\Programs\Microsoft VS Code\Code.exe",
            "discord":        r"C:\Users\{user}\AppData\Local\Discord\Update.exe",
            "steam":          r"C:\Program Files (x86)\Steam\steam.exe",
            "obs":            r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
        }

        user = os.environ.get("USERNAME", "")
        if app_name_lower in known:
            path = known[app_name_lower].replace("{user}", user)
            if os.path.exists(path):
                return path
            # Dosya yoksa yine de dene (calc.exe, notepad.exe gibi sistem araçları)
            if not path.startswith("C:\\"):
                return path
            # Yol yoksa devam et (Office farklı versiyonda olabilir)

        # --- 2. Registry App Paths ---
        candidates = [app_name_lower, f"{app_name_lower}.exe",
                      app_name, f"{app_name}.exe"]
        for name in candidates:
            reg_path = f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{name}"
            for root_key in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    key    = winreg.OpenKey(root_key, reg_path)
                    val, _ = winreg.QueryValueEx(key, "")
                    if val and os.path.exists(val):
                        return val
                except Exception:
                    continue

        # --- 3. PATH araması (sistem araçları hariç) ---
        BLOCKED_PATH = {"cmd", "cmd.exe", "powershell", "powershell.exe",
                        "pwsh", "pwsh.exe", "wt", "wt.exe", "wsl", "wsl.exe"}
        for candidate in [app_name_lower, f"{app_name_lower}.exe",
                          app_name, f"{app_name}.exe"]:
            if candidate.lower() in BLOCKED_PATH:
                continue
            found = shutil.which(candidate)
            if found:
                return found

        # --- 4. Program Files fuzzy .exe araması ---
        # Sistem araçlarını fuzzy eşleştirmeden koru
        BLOCKED_EXE = {
            "cmd", "conhost", "powershell", "pwsh", "wsl", "wt",
            "taskmgr", "msiexec", "svchost", "lsass", "csrss",
            "winlogon", "explorer", "rundll32", "regsvr32",
            "dllhost", "sihost", "fontdrvhost"
        }
        search_roots = [
            os.environ.get("PROGRAMFILES",      r"C:\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
        ]
        for root in search_roots:
            if not root or not os.path.exists(root):
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                depth = dirpath.replace(root, "").count(os.sep)
                if depth > 4:
                    dirnames.clear()
                    continue
                for fname in filenames:
                    if fname.lower().endswith(".exe"):
                        exe_stem = fname[:-4].lower()
                        if exe_stem in BLOCKED_EXE:
                            continue
                        if app_name_lower in exe_stem or exe_stem in app_name_lower:
                            return os.path.join(dirpath, fname)

        return None

    # ==========================================
    # SYSTEM CORE — KOMUTLAR GENİŞLETİLDİ
    # ==========================================
    def process_command(self):
        user_text = self.entry.get().strip()
        if not user_text:
            return
        self.entry.delete(0, "end")
        self.chat_display.configure(state="normal")
        self.chat_display.insert("end", f"You: {user_text}\n")
        self.chat_display.configure(state="disabled")
        threading.Thread(target=self.execute_system_logic, args=(user_text,), daemon=True).start()

    def execute_system_logic(self, user_text):
        cmd = user_text.lower().strip()
        response = "Nexus AI: Command not recognized."

        try:
            # ----- SYSTEM STATUS -----
            if cmd in ["system status", "health", "status", "cpu", "ram"]:
                response = f"Nexus AI:\n{self.get_system_health()}"
                self.update_ui(response, user_text)

            # ----- VOLUME — FİX -----
            elif "volume" in cmd:
                if "max" in cmd:
                    level = 100
                elif "min" in cmd or "mute" in cmd:
                    level = 0
                else:
                    nums  = ''.join(filter(str.isdigit, cmd))
                    level = int(nums) if nums else -1

                if 0 <= level <= 100:
                    # Ana thread yerine doğrudan yeni thread'de çalıştır
                    threading.Thread(
                        target=self._set_volume, args=(level, user_text), daemon=True
                    ).start()
                    return
                else:
                    response = "Nexus AI: Please specify a volume level (e.g. 'volume 50', 'volume max')."
                    self.update_ui(response, user_text)

            # ----- SHUTDOWN / RESTART / SLEEP / LOCK -----
            elif cmd in ["shutdown", "shut down", "close pc", "turn off pc", "power off"]:
                response = "Nexus AI: Shutting down in 10 seconds..."
                self.update_ui(response, user_text)
                subprocess.Popen("shutdown /s /t 10", shell=True)

            elif cmd in ["restart", "reboot", "restart pc"]:
                response = "Nexus AI: Restarting in 10 seconds..."
                self.update_ui(response, user_text)
                subprocess.Popen("shutdown /r /t 10", shell=True)

            elif cmd in ["sleep", "sleep mode", "hibernate"]:
                response = "Nexus AI: Putting system to sleep..."
                self.update_ui(response, user_text)
                subprocess.Popen("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True)

            elif cmd in ["lock", "lock pc", "lock screen"]:
                response = "Nexus AI: Locking workstation..."
                self.update_ui(response, user_text)
                subprocess.Popen("rundll32.exe user32.dll,LockWorkStation", shell=True)

            elif cmd in ["cancel shutdown", "abort shutdown"]:
                response = "Nexus AI: Shutdown cancelled."
                self.update_ui(response, user_text)
                subprocess.Popen("shutdown /a", shell=True)

            # ----- CHROME SEARCH -----
            elif "open chrome" in cmd and "search" in cmd:
                query         = cmd.split("search", 1)[1].strip()
                encoded_query = urllib.parse.quote(query)
                subprocess.Popen(
                    f'start chrome "https://www.google.com/search?q={encoded_query}"',
                    shell=True
                )
                response = f"Nexus AI: Chrome opened. Searching for '{query}'..."
                self.update_ui(response, user_text)

            # ----- FILE SEARCH -----
            elif cmd.startswith("find ") or cmd.startswith("search file "):
                filename = cmd.replace("find ", "").replace("search file ", "").strip()
                path     = self.search_local_files(filename)
                if path:
                    response = f"Nexus AI: File found → {path}"
                else:
                    response = f"Nexus AI: '{filename}' not found in user folders."
                self.update_ui(response, user_text)

            # ----- OPEN APP -----
            elif cmd.startswith("open "):
                app_name = user_text[5:].strip()
                app_path = self.find_application_path(app_name)
                if app_path:
                    os.startfile(app_path)
                    response = f"Nexus AI: Opening '{app_name}'..."
                else:
                    response = f"Nexus AI: '{app_name}' could not be found."
                self.update_ui(response, user_text)

            # ----- BILINMEYEN KOMUT -----
            else:
                self.update_ui(response, user_text)

        except Exception as e:
            response = f"Nexus AI: Error occurred: {str(e)}"
            self.update_ui(response, user_text)

    # ==========================================
    # UI HELPERS
    # ==========================================
    def update_ui(self, response_text, user_text=None):
        self.after(0, self._safe_update_ui, response_text, user_text)

    def _safe_update_ui(self, response_text, user_text):
        self.animate_text(response_text)
        if user_text:
            self._append_history(user_text)
            self._append_memory(user_text, response_text)
            self._add_history_btn(user_text)

    def _add_history_btn(self, text):
        """Her history item'ı: [komut metni] [❌] şeklinde gösterir."""
        row_frame = ctk.CTkFrame(self.history_frame, fg_color="transparent")
        row_frame.pack(pady=2, fill="x", padx=5)
        row_frame.grid_columnconfigure(0, weight=1)

        btn = ctk.CTkButton(
            row_frame,
            text=text.capitalize()[:28],
            fg_color="transparent",
            text_color=("black", "gray80"),
            anchor="w",
            hover_color=("gray85", "gray20"),
            height=32, corner_radius=6,
            command=lambda t=text: self._replay_history(t)
        )
        btn.grid(row=0, column=0, sticky="ew")

        del_btn = ctk.CTkButton(
            row_frame,
            text="✕",
            width=28, height=28,
            fg_color="transparent",
            text_color=("gray50", "gray50"),
            hover_color=("#FF4444", "#CC2222"),
            corner_radius=6,
            command=lambda rf=row_frame, t=text: self._delete_history_item(rf, t)
        )
        del_btn.grid(row=0, column=1, padx=(2, 0))

    def _replay_history(self, text):
        """History'deki bir komuta tıklanınca entry'e yazar."""
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self.entry.focus()

    def _delete_history_item(self, row_frame, text):
        """Tek bir history item'ını UI'dan ve JSON'dan sil."""
        row_frame.destroy()
        history = self._load_json(HISTORY_FILE)
        # İlk eşleşeni sil
        for i, item in enumerate(history):
            if item.get("text", "") == text:
                history.pop(i)
                break
        self._save_json(HISTORY_FILE, history)

    def _clear_all_history(self):
        """Tüm history'yi temizle."""
        for widget in self.history_frame.winfo_children():
            widget.destroy()
        self._save_json(HISTORY_FILE, [])

    # Eski isim → geriye dönük uyumluluk
    def add_history_item(self, text):
        self._add_history_btn(text)

    def clear_chat(self):
        self.chat_display.configure(state="normal")
        self.chat_display.delete("1.0", "end")
        self.chat_display.configure(state="disabled")
        self.animate_text("Nexus AI: Chat cleared. Awaiting new command...")

    def change_theme(self, new_mode: str):
        ctk.set_appearance_mode(new_mode)


if __name__ == "__main__":
    ctk.set_appearance_mode("Dark")
    app = NexusAI_UI()
    app.mainloop()