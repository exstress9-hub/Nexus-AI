# ============================================================
#  NEXUS AI — Mobile (Kivy)
#  Özellikler: Sesli komut, Uygulama açma,
#               Ses kontrolü, Sistem durumu
# ============================================================

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.widget import Widget
from kivy.graphics import Color, RoundedRectangle, Rectangle
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.utils import get_color_from_hex

import threading
import os
import json
import psutil

# Android'e özgü import'lar (sadece Android'de çalışır)
try:
    from android.permissions import request_permissions, Permission
    from jnius import autoclass
    IS_ANDROID = True
except ImportError:
    IS_ANDROID = False

# Ses tanıma
try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False

# ── Renkler ──────────────────────────────────────────────
BG_DARK      = get_color_from_hex("#0F0F11")
SIDEBAR_BG   = get_color_from_hex("#161618")
ACCENT_CYAN  = get_color_from_hex("#00D2FF")
TEXT_WHITE   = get_color_from_hex("#EFEFEF")
TEXT_GRAY    = get_color_from_hex("#888888")
BTN_BG       = get_color_from_hex("#1E1E22")
BTN_HOVER    = get_color_from_hex("#2A2A30")
RED          = get_color_from_hex("#FF4444")

HISTORY_FILE = "nexus_history.json"
MEMORY_FILE  = "nexus_memory.json"

Window.clearcolor = BG_DARK


# ══════════════════════════════════════════════════════════
#  Yardımcı widget'lar
# ══════════════════════════════════════════════════════════

class RoundedButton(Button):
    def __init__(self, bg_color=None, radius=18, **kwargs):
        self.bg_color = bg_color or BTN_BG
        self.radius   = radius
        super().__init__(**kwargs)
        self.background_color = (0, 0, 0, 0)
        self.color            = TEXT_WHITE
        self.font_name        = "Roboto"
        self.font_size        = dp(14)
        self.bind(pos=self._redraw, size=self._redraw)

    def _redraw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.bg_color)
            RoundedRectangle(pos=self.pos, size=self.size,
                             radius=[self.radius])

    def on_press(self):
        self.bg_color = BTN_HOVER
        self._redraw()

    def on_release(self):
        self.bg_color = BTN_BG
        self._redraw()


class HistoryItem(BoxLayout):
    """Tek satır: [komut etiketi] [✕ butonu]"""
    def __init__(self, text, on_tap, on_delete, **kwargs):
        super().__init__(orientation="horizontal",
                         size_hint_y=None, height=dp(42),
                         spacing=dp(4), **kwargs)
        self.text = text

        lbl_btn = RoundedButton(
            text=text[:32],
            size_hint_x=1,
            halign="left",
            padding_x=dp(12),
        )
        lbl_btn.bind(on_release=lambda *_: on_tap(text))
        self.add_widget(lbl_btn)

        del_btn = RoundedButton(
            text="✕",
            size_hint_x=None, width=dp(40),
            bg_color=get_color_from_hex("#2A1A1A"),
        )
        del_btn.bind(on_release=lambda *_: on_delete(self, text))
        self.add_widget(del_btn)


# ══════════════════════════════════════════════════════════
#  Ana Layout
# ══════════════════════════════════════════════════════════

class NexusLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="horizontal", **kwargs)
        self.recognizer = sr.Recognizer() if SR_AVAILABLE else None
        self._build_ui()
        self._load_history()
        self._animate_welcome()

    # ── UI İnşası ─────────────────────────────────────────

    def _build_ui(self):
        # ---- SIDEBAR ----
        self.sidebar = BoxLayout(
            orientation="vertical",
            size_hint_x=None, width=dp(220),
            padding=dp(10), spacing=dp(8)
        )
        with self.sidebar.canvas.before:
            Color(*SIDEBAR_BG)
            self._sb_rect = Rectangle(pos=self.sidebar.pos,
                                      size=self.sidebar.size)
        self.sidebar.bind(pos=self._upd_sb, size=self._upd_sb)

        new_btn = RoundedButton(
            text="＋  New Chat",
            size_hint_y=None, height=dp(48),
            bg_color=get_color_from_hex("#1A2A2A"),
            font_size=dp(15),
        )
        new_btn.bind(on_release=lambda *_: self._clear_chat())
        self.sidebar.add_widget(new_btn)

        # History başlık satırı
        hdr = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(6))
        hdr.add_widget(Label(text="History", color=TEXT_GRAY,
                             font_size=dp(12), bold=True,
                             size_hint_x=1, halign="left",
                             valign="middle"))
        clear_all = RoundedButton(
            text="Clear All",
            size_hint_x=None, width=dp(75),
            size_hint_y=None, height=dp(28),
            bg_color=get_color_from_hex("#2A1010"),
            font_size=dp(12),
        )
        clear_all.bind(on_release=lambda *_: self._clear_all_history())
        hdr.add_widget(clear_all)
        self.sidebar.add_widget(hdr)

        # Scrollable history listesi
        self.hist_scroll = ScrollView(size_hint=(1, 1))
        self.hist_list   = BoxLayout(
            orientation="vertical",
            size_hint_y=None, spacing=dp(4)
        )
        self.hist_list.bind(minimum_height=self.hist_list.setter("height"))
        self.hist_scroll.add_widget(self.hist_list)
        self.sidebar.add_widget(self.hist_scroll)

        self.add_widget(self.sidebar)

        # ---- ANA ALAN ----
        main = BoxLayout(orientation="vertical",
                         padding=dp(16), spacing=dp(10))

        # Chat ekranı
        self.chat_scroll = ScrollView(size_hint=(1, 1))
        self.chat_label  = Label(
            text="",
            color=TEXT_WHITE,
            font_size=dp(14),
            markup=True,
            size_hint_y=None,
            halign="left", valign="top",
            text_size=(Window.width - dp(260), None),
            padding=(dp(8), dp(8)),
        )
        self.chat_label.bind(texture_size=self.chat_label.setter("size"))
        self.chat_scroll.add_widget(self.chat_label)
        main.add_widget(self.chat_scroll)

        # Input satırı
        input_row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))

        self.entry = TextInput(
            hint_text="Give Nexus a command...",
            multiline=False,
            font_size=dp(14),
            background_color=BTN_BG,
            foreground_color=TEXT_WHITE,
            hint_text_color=TEXT_GRAY,
            cursor_color=ACCENT_CYAN,
            padding=[dp(16), dp(14)],
        )
        self.entry.bind(on_text_validate=lambda *_: self._process_command())
        input_row.add_widget(self.entry)

        send_btn = RoundedButton(
            text="▶",
            size_hint_x=None, width=dp(52),
            bg_color=get_color_from_hex("#003A4A"),
            font_size=dp(18),
        )
        send_btn.bind(on_release=lambda *_: self._process_command())
        input_row.add_widget(send_btn)

        mic_btn = RoundedButton(
            text="🎤",
            size_hint_x=None, width=dp(52),
            bg_color=get_color_from_hex("#1A003A"),
            font_size=dp(18),
        )
        mic_btn.bind(on_release=lambda *_: self._start_voice())
        self.mic_btn = mic_btn
        input_row.add_widget(mic_btn)

        main.add_widget(input_row)
        self.add_widget(main)

    def _upd_sb(self, *_):
        self._sb_rect.pos  = self.sidebar.pos
        self._sb_rect.size = self.sidebar.size

    # ── Animasyonlu yazı ──────────────────────────────────

    def _animate_welcome(self):
        msg = "Nexus AI: Universal control interface active.\nType or speak a command."
        self._animate_text(msg)

    def _animate_text(self, full_text, idx=0, current=""):
        if idx == 0:
            self._anim_base = self.chat_label.text

        if idx < len(full_text):
            current += full_text[idx]
            self.chat_label.text = self._anim_base + current
            Clock.schedule_once(
                lambda dt: self._animate_text(full_text, idx + 1, current),
                0.01
            )
        else:
            self.chat_label.text += "\n\n"
            Clock.schedule_once(lambda dt: self._scroll_bottom(), 0.05)

    def _scroll_bottom(self):
        self.chat_scroll.scroll_y = 0

    # ── JSON ──────────────────────────────────────────────

    def _load_json(self, path):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_json(self, path, data):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"JSON error: {e}")

    def _load_history(self):
        for item in self._load_json(HISTORY_FILE):
            self._add_history_item(item.get("text", ""))

    def _append_history(self, text):
        h = self._load_json(HISTORY_FILE)
        h.append({"text": text})
        self._save_json(HISTORY_FILE, h)

    def _append_memory(self, user_text, response_text):
        m = self._load_json(MEMORY_FILE)
        m.append({"text": user_text,     "is_user": True})
        m.append({"text": response_text, "is_user": False})
        self._save_json(MEMORY_FILE, m)

    # ── History UI ────────────────────────────────────────

    def _add_history_item(self, text):
        item = HistoryItem(
            text=text,
            on_tap=self._replay,
            on_delete=self._delete_item,
        )
        self.hist_list.add_widget(item)

    def _replay(self, text):
        self.entry.text = text
        self.entry.focus = True

    def _delete_item(self, widget, text):
        self.hist_list.remove_widget(widget)
        h = self._load_json(HISTORY_FILE)
        for i, item in enumerate(h):
            if item.get("text") == text:
                h.pop(i)
                break
        self._save_json(HISTORY_FILE, h)

    def _clear_all_history(self):
        self.hist_list.clear_widgets()
        self._save_json(HISTORY_FILE, [])

    def _clear_chat(self):
        self.chat_label.text = ""
        self._animate_text("Nexus AI: Chat cleared. Awaiting new command...")

    # ── Sesli komut ───────────────────────────────────────

    def _start_voice(self):
        if not SR_AVAILABLE:
            self._append_chat("Nexus AI: speech_recognition not installed.")
            return
        if IS_ANDROID:
            request_permissions([Permission.RECORD_AUDIO])
        self.mic_btn.text = "⏳"
        threading.Thread(target=self._listen, daemon=True).start()

    def _listen(self):
        try:
            with sr.Microphone() as src:
                self.recognizer.adjust_for_ambient_noise(src, duration=0.5)
                audio = self.recognizer.listen(src, timeout=5, phrase_time_limit=7)
                text  = self.recognizer.recognize_google(audio, language="en-US")
                Clock.schedule_once(lambda dt: self._set_entry(text), 0)
        except sr.UnknownValueError:
            Clock.schedule_once(
                lambda dt: self._append_chat("Nexus AI: Could not understand audio."), 0)
        except Exception as e:
            Clock.schedule_once(
                lambda dt: self._append_chat(f"Nexus AI: Mic error → {e}"), 0)
        finally:
            Clock.schedule_once(lambda dt: setattr(self.mic_btn, "text", "🎤"), 0)

    def _set_entry(self, text):
        self.entry.text = text
        self._process_command()

    # ── Komut işleme ──────────────────────────────────────

    def _process_command(self):
        text = self.entry.text.strip()
        if not text:
            return
        self.entry.text = ""
        self._append_chat(f"[color=#00D2FF]You:[/color] {text}")
        threading.Thread(target=self._execute, args=(text,), daemon=True).start()

    def _execute(self, user_text):
        cmd      = user_text.lower().strip()
        response = "Nexus AI: Command not recognized."

        try:
            # ── Sistem durumu ──
            if cmd in ["status", "health", "cpu", "ram", "system status"]:
                response = self._system_health()

            # ── Ses kontrolü ──
            elif "volume" in cmd:
                response = self._set_volume(cmd)

            # ── Uygulama açma ──
            elif cmd.startswith("open "):
                app = user_text[5:].strip()
                response = self._open_app(app)

            # ── Shutdown / Lock ──
            elif cmd in ["shutdown", "close pc", "turn off"]:
                response = self._power_action("shutdown")

            elif cmd in ["restart", "reboot"]:
                response = self._power_action("restart")

            elif cmd in ["lock", "lock screen"]:
                response = self._power_action("lock")

        except Exception as e:
            response = f"Nexus AI: Error → {e}"

        Clock.schedule_once(
            lambda dt: self._finish_response(user_text, response), 0)

    def _finish_response(self, user_text, response):
        self._animate_text(response)
        self._append_history(user_text)
        self._append_memory(user_text, response)
        self._add_history_item(user_text)

    def _append_chat(self, text):
        self.chat_label.text += text + "\n\n"
        Clock.schedule_once(lambda dt: self._scroll_bottom(), 0.05)

    # ── Sistem durumu ─────────────────────────────────────

    def _system_health(self):
        cpu  = psutil.cpu_percent(interval=0.5)
        ram  = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        warn = ("⚠ Heavy load!" if cpu > 85 or ram.percent > 85
                else "✓ All systems normal.")
        return (f"Nexus AI:\n"
                f"CPU  : {cpu}%\n"
                f"RAM  : {ram.percent}%\n"
                f"Disk : {disk.percent}%\n"
                f"Status: {warn}")

    # ── Ses kontrolü ──────────────────────────────────────

    def _set_volume(self, cmd):
        if not IS_ANDROID:
            return "Nexus AI: Volume control only works on Android."
        try:
            AudioManager = autoclass("android.media.AudioManager")
            ctx          = autoclass(
                "org.kivy.android.PythonActivity").mActivity
            am = ctx.getSystemService(ctx.AUDIO_SERVICE)
            max_vol = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC)

            if "max" in cmd:
                level = 100
            elif "min" in cmd or "mute" in cmd:
                level = 0
            else:
                nums  = ''.join(filter(str.isdigit, cmd))
                level = int(nums) if nums else -1

            if 0 <= level <= 100:
                target = int(max_vol * level / 100)
                am.setStreamVolume(
                    AudioManager.STREAM_MUSIC, target,
                    AudioManager.FLAG_SHOW_UI)
                return f"Nexus AI: Volume set to {level}%."
            else:
                return "Nexus AI: Specify volume level (e.g. 'volume 50')."
        except Exception as e:
            return f"Nexus AI: Volume error → {e}"

    # ── Uygulama açma ─────────────────────────────────────

    def _open_app(self, app_name):
        if not IS_ANDROID:
            return f"Nexus AI: App launching only works on Android."
        try:
            Intent        = autoclass("android.content.Intent")
            Uri           = autoclass("android.net.Uri")
            activity      = autoclass(
                "org.kivy.android.PythonActivity").mActivity
            pm            = activity.getPackageManager()

            # Popüler uygulama paket isimleri
            KNOWN = {
                "whatsapp":  "com.whatsapp",
                "youtube":   "com.google.android.youtube",
                "chrome":    "com.android.chrome",
                "spotify":   "com.spotify.music",
                "instagram": "com.instagram.android",
                "twitter":   "com.twitter.android",
                "x":         "com.twitter.android",
                "tiktok":    "com.zhiliaoapp.musically",
                "gmail":     "com.google.android.gm",
                "maps":      "com.google.android.apps.maps",
                "settings":  "com.android.settings",
                "camera":    "android.media.action.IMAGE_CAPTURE",
                "gallery":   "com.android.gallery3d",
                "calculator":"com.android.calculator2",
            }

            pkg = KNOWN.get(app_name.lower())
            if pkg:
                intent = pm.getLaunchIntentForPackage(pkg)
                if intent:
                    activity.startActivity(intent)
                    return f"Nexus AI: Opening '{app_name}'..."
                else:
                    return f"Nexus AI: '{app_name}' is not installed."
            else:
                return f"Nexus AI: '{app_name}' not in known apps list."
        except Exception as e:
            return f"Nexus AI: App error → {e}"

    # ── Güç eylemleri ─────────────────────────────────────

    def _power_action(self, action):
        if not IS_ANDROID:
            return f"Nexus AI: '{action}' only works on Android."
        try:
            activity = autoclass(
                "org.kivy.android.PythonActivity").mActivity
            if action == "lock":
                DevicePolicyManager = autoclass(
                    "android.app.admin.DevicePolicyManager")
                dpm = activity.getSystemService(
                    activity.DEVICE_POLICY_SERVICE)
                dpm.lockNow()
                return "Nexus AI: Screen locked."
            else:
                return f"Nexus AI: '{action}' requires system-level permissions."
        except Exception as e:
            return f"Nexus AI: Power error → {e}"


# ══════════════════════════════════════════════════════════
#  App
# ══════════════════════════════════════════════════════════

class NexusApp(App):
    def build(self):
        self.title = "Nexus AI"
        Window.clearcolor = BG_DARK
        return NexusLayout()


if __name__ == "__main__":
    NexusApp().run()
