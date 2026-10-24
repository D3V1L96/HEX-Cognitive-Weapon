import sys
import os
import math
import random
import time
import re
import json
import requests
import ctypes
import win32gui
import tempfile
import logging
logging.basicConfig(level=logging.INFO, format='[h.e.x] %(message)s')
logger = logging.getLogger(__name__)
import numpy as np
from datetime import datetime
import speech_recognition as sr
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QGraphicsDropShadowEffect, QFrame, QFileDialog
)
from PyQt6.QtCore import (
    Qt, QTimer, QSize, QObject, QThread, pyqtSlot, pyqtSignal, QPointF, QRectF
)
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QRadialGradient, QLinearGradient,
    QFont, QPainterPath, QColor, QMouseEvent,QPixmap
)
import psutil
from search_engine import search_engine
from app_manager import app_manager
from media_controller import hex_media as media_controller
from file_manager import file_manager
from system_manager import system_manager
from hex_brain import hex_brain
from hex_code_module import hex_code_module
from hex_reminder import hex_reminder
from hex_evolution import hex_evolution
from hex_file_upload import hex_file_upload
from hex_music_mode import music_data, audio_capture
from hex_system_control import screen_control
from hex_navigation import hex_nav
from hex_gmail import hex_gmail
from hex_phone_control import hex_phone
from hex_travel import hex_travel
# ==================== VOICE ENGINE ====================
tts_engine = None
try:
    from hex_voice_engine import HexVoiceEngine
    tts_engine = HexVoiceEngine()
    print("[OK] Voice Engine Loaded")
except (ImportError, FileNotFoundError) as err:
    print(f"[FAIL] Voice Engine: {err}")

# ==================== CONFIG ====================
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2"

OPENWEATHER_API_KEY = ""

OPENWEATHER_CITY = "Delhi"
OPENWEATHER_URL = (
    f"https://api.openweathermap.org/data/2.5/weather"
    f"?q={OPENWEATHER_CITY}&appid={OPENWEATHER_API_KEY}&units=metric"
)

is_muted = False
is_devil_mode = False
recognizer = sr.Recognizer()
recognizer.energy_threshold = 800
recognizer.dynamic_energy_threshold = True
recognizer.pause_threshold = 0.8
recognizer.phrase_time_limit = 15
recognizer.non_speaking_duration = 0.5
# ==================== OFFLINE SPEECH ENGINE ====================
_whisper_model = None
_whisper_available = False

def _init_whisper():
    """Initialize offline speech recognition."""
    global _whisper_model, _whisper_available
    try:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
        _whisper_available = True
        logger.info("Offline Speech Engine Ready | faster-whisper tiny | CPU int8")
    except ImportError:
        try:
            import whisper
            _whisper_model = whisper.load_model("tiny")
            _whisper_available = True
            logger.info("Offline Speech Engine Ready | whisper tiny | CPU")
        except ImportError:
            _whisper_available = False
            logger.warning("No offline STT installed. Run: pip install faster-whisper")

def _transcribe_offline(audio_data):
    """Transcribe audio offline using whisper."""
    global _whisper_model, _whisper_available
    if not _whisper_available or _whisper_model is None:
        return ""
    try:
        tmp_path = os.path.join(tempfile.gettempdir(), f"hex_stt_{int(time.time())}.wav")
        with open(tmp_path, "wb") as wf:
            wf.write(audio_data.get_wav_data())

        text = ""
        # Try faster-whisper API first
        try:
            segments, info = _whisper_model.transcribe(tmp_path, language="en", beam_size=1)
            text = " ".join(seg.text for seg in segments).strip()
        except (AttributeError, TypeError):
            # Fallback to original whisper API
            try:
                result = _whisper_model.transcribe(tmp_path, language="en")
                text = result.get("text", "").strip()
            except Exception:
                pass

        try:
            os.unlink(tmp_path)
        except OSError:
            pass

        return text.lower()
    except Exception as e:
        logger.debug(f"Offline STT error: {e}")
        return ""
# ==================== CORE FUNCTIONS ====================
_last_speak_end = 0

def speak(text):
    global is_muted, _last_speak_end
    if not is_muted and tts_engine:
        tts_engine.speak(text)
        # Tighter estimation: ~4 chars per second for natural speech
        estimated_duration = max(0.8, len(text) * 0.045)
        _last_speak_end = time.time() + estimated_duration

def stop_speaking():
    if tts_engine:
        tts_engine.stop()


def get_weather():
    if OPENWEATHER_API_KEY == "YOUR_API_KEY_HERE":
        return "Weather API key not configured, Sir."
    try:
        resp = requests.get(OPENWEATHER_URL, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            temp = data["main"]["temp"]
            humidity = data["main"]["humidity"]
            desc = data["weather"][0]["description"].title()
            city = data["name"]
            return f"{city}: {desc}, {temp:.0f}C, Humidity {humidity}%"
    except (requests.RequestException, KeyError):
        pass
    return "Weather unavailable, Sir."


# Keep-alive session for faster subsequent requests
_ollama_session = requests.Session()


def _clean_tts_text(text):
    if not text:
        return ""

    # 1. Basic Cleanup
    text = re.sub(r'\s+', ' ', text).strip()

    # 2. Remove "Sir" loops
    text = re.sub(r'(sir[,\.!\s]+){2,}', 'Sir, ', text, flags=re.IGNORECASE)

    # 3. Split into sentences to check for full sentence repetition
    # Simple split by punctuation for checking
    sentences = re.split(r'(?<=[.!?])\s+', text)
    unique_sentences = []
    seen = set()

    for sent in sentences:
        cleaned_sent = sent.strip().lower()
        if cleaned_sent and cleaned_sent not in seen:
            unique_sentences.append(sent)  # Keep original casing for speech
            seen.add(cleaned_sent)

    text = ' '.join(unique_sentences)

    # 4. Remove Consecutive Duplicate Words (Word level safety)
    words = text.split()
    deduped = []
    prev_word = None
    for w in words:
        clean_w = w.lower().strip(".,!?;:\"'")
        if clean_w != prev_word:
            deduped.append(w)
            prev_word = clean_w
    text = ' '.join(deduped)

    # 5. Final Punctuation Fix
    text = re.sub(r'([.!?])\s*\1+', r'\1', text)
    text = re.sub(r',\s*,', ',', text)
    text = re.sub(r'\.{3,}', '.', text)

    return text.strip()


def get_llm_response(prompt, search_context=None, success=True):
    try:
        system_prompt = hex_brain.get_cognitive_prompt(current_query=prompt)
        context_block = ""
        if search_context:
            if len(search_context) > 500:
                search_context = search_context[:500] + "..."
            context_block = f"\n\nVERIFIED SEARCH RESULTS:\n{search_context}\nUse this for accurate answer.\n"

        full_prompt = f"{system_prompt}{context_block}\nUser: {prompt}\nHEX:"

        payload = {
            "model": OLLAMA_MODEL,
            "prompt": full_prompt,
            "stream": True,
            "keep_alive": "30m",
            "options": {
                # Creativity & Diversity
                "temperature": 0.95,
                "top_k": 70,
                "top_p": 0.95,
                "min_p": 0.05,

                # Precision & Anti-Repetition
                "repeat_last_n": 256,
                "repeat_penalty": 1.15,
                "presence_penalty": 0.35,
                "frequency_penalty": 0.20,

                # Context & Performance
                "num_predict": 512,
                "num_ctx": 8192,
                "num_thread": 8,

                # Stop Conditions
                "stop": [
                    "\nUser:",
                    "\nHEX:"
                ]
            }
        }
        resp = _ollama_session.post(OLLAMA_URL, json=payload, timeout=60, stream=True)
        if resp.status_code == 200:
            full_response = ""

            for line in resp.iter_lines():
                if not line:
                    continue

                try:
                    chunk = line.decode("utf-8") if isinstance(line, bytes) else line
                    data = json.loads(chunk)
                    full_response += data.get("response", "")

                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

            final_cleaned = _clean_tts_text(full_response.strip())
            hex_brain.process_interaction(prompt, final_cleaned, success=True)
            return final_cleaned

        else:
            hex_brain.process_interaction(prompt, "Error", success=False)
            return "I am having trouble connecting right now, Sir."

    except requests.ConnectionError:
        hex_brain.process_interaction(prompt, "Offline", success=False)
        return "My local brain is offline, Sir. Please start Ollama."
    except requests.Timeout:
        hex_brain.process_interaction(prompt, "Timeout", success=False)
        return "My brain took too long, Sir. Try again."
    except Exception as err:
        return "Something went wrong, Sir."

def get_bitchord_track_desktop():
    found_titles = []
    user32 = ctypes.windll.user32

    def enum_proc(hwnd, l_param):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if "bitchord" in title.lower():
                found_titles.append(title)
        return True

    enum_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(enum_type(enum_proc), 0)
    return found_titles[0] if found_titles else "Not playing"


# ==================== FIXED ANIMATED CORE (NO CUTTING) ====================
class AnimatedCore(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.rotation = 0.0
        self.pulse = 0.0
        self.audio_level = 0.0
        self.target_audio = 0.0
        self.music_mode = False
        self.music_transition = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(16)
        self.devil_mode = False
    def set_audio_level(self, level):
        self.target_audio = min(level / 2000.0, 1.0)

    def toggle_music_mode(self):
        self.music_mode = not self.music_mode
        if self.music_mode:
            try:
                music_data.is_active = True
                audio_capture.start()
            except Exception as e:
                logger.error(f"Music capture start failed: {e}")
                # Fall back to simulated mode silently
                music_data.is_active = True
        else:
            try:
                music_data.is_active = False
                audio_capture.stop()
            except Exception as e:
                logger.error(f"Music capture stop failed: {e}")
                music_data.is_active = False
        return self.music_mode
    def _animate(self):
        self.rotation = (self.rotation + 0.8) % 360
        self.pulse = (math.sin(time.time() * 2.0) + 1) / 2
        target_t = 1.0 if self.music_mode else 0.0
        self.music_transition += (target_t - self.music_transition) * 0.08
        if not self.music_mode:
            self.audio_level += (self.target_audio - self.audio_level) * 0.2
        self.update()

    def sizeHint(self):
        return QSize(480, 480)

    def minimumSize(self):
        return QSize(350, 350)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        safe_radius = (min(w, h) / 2.0) - 70
        mt = self.music_transition

        if mt > 0.01:
            self._paint_music(painter, cx, cy, safe_radius, mt)
        if mt < 0.99:
            self._paint_normal(painter, cx, cy, safe_radius, 1.0 - mt)

    def _paint_normal(self, painter, cx, cy, safe_radius, am):
        # Devil mode color switch
        if self.devil_mode:
            C_GLOW = (255, 0, 0)
            C_RING = (80, 10, 10)
            C_ACCENT = (255, 50, 0)
            C_TEXT = (255, 50, 50)
            C_BG1 = (40, 5, 5)
            C_BG2 = (25, 2, 2)
            C_BG3 = (15, 0, 0)
            SUB_TEXT = "DEVIL MODE ACTIVE"
        else:
            C_GLOW = (0, 180, 255)
            C_RING = (40, 60, 80)
            C_ACCENT = (100, 220, 255)
            C_TEXT = (180, 240, 255)
            C_BG1 = (15, 25, 35)
            C_BG2 = (8, 15, 25)
            C_BG3 = (5, 10, 15)
            SUB_TEXT = "ADVANCED INTELLIGENCE SYSTEM"

        audio_boost = self.audio_level * 20
        radius = safe_radius + audio_boost

        # Outer glow
        glow_alpha = int((30 + self.audio_level * 80) * am)
        for i in range(3):
            r = radius + (i * 10)
            if r > safe_radius + 35:
                continue
            a = max(10, glow_alpha - (i * 15))
            painter.setPen(QPen(QColor(C_GLOW[0], C_GLOW[1], C_GLOW[2], a), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), r, r)

        # Main ring
        pen = QPen(QColor(C_RING[0], C_RING[1], C_RING[2], int(180 * am)))
        pen.setWidth(3)
        painter.setPen(pen)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # Tick marks
        for i in range(72):
            angle = math.radians(i * 5 + self.rotation)
            inner = radius - 8
            outer = radius - (4 + (i % 6 == 0) * 10)
            x1 = cx + math.cos(angle) * inner
            y1 = cy + math.sin(angle) * inner
            x2 = cx + math.cos(angle) * outer
            y2 = cy + math.sin(angle) * outer
            a = int((80 + 120 * self.pulse) * am) if (i % 6 == 0) else int(60 * am)
            rc = int(C_ACCENT[0] * (0.5 + self.audio_level * 0.5))
            gc = int(C_ACCENT[1] * (0.5 + self.audio_level * 0.5))
            bc = int(C_ACCENT[2] * (0.5 + self.audio_level * 0.5))
            pen = QPen(QColor(rc, gc, bc, a))
            pen.setWidth(2 if (i % 6 == 0) else 1)
            painter.setPen(pen)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # Inner dashed ring
        inner_radius = radius - 55
        if inner_radius > 20:
            path = QPainterPath()
            path.addEllipse(QPointF(cx, cy), inner_radius, inner_radius)
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(-self.rotation * 0.7)
            painter.translate(-cx, -cy)
            pen = QPen(QColor(C_ACCENT[0], C_ACCENT[1], C_ACCENT[2], int(200 * am)))
            pen.setWidth(2)
            pen.setDashPattern([3, 8])
            painter.setPen(pen)
            painter.drawPath(path)
            painter.restore()

        # Audio bars
        num_bars = 48
        bar_radius = inner_radius - 20
        if bar_radius > 15:
            for i in range(num_bars):
                angle = math.radians(i * (360 / num_bars) + self.rotation * 0.3)
                wave_val = abs(math.sin(i * 0.5 + time.time() * 3))
                bar_height = 5 + wave_val * 20 * (0.3 + self.audio_level * 2)
                x_s = cx + math.cos(angle) * (bar_radius - bar_height)
                y_s = cy + math.sin(angle) * (bar_radius - bar_height)
                x_e = cx + math.cos(angle) * bar_radius
                y_e = cy + math.sin(angle) * bar_radius
                a = int((120 + self.audio_level * 135) * am)
                pen = QPen(QColor(C_ACCENT[0], C_ACCENT[1], C_ACCENT[2], a))
                pen.setWidth(2)
                painter.setPen(pen)
                painter.drawLine(QPointF(x_s, y_s), QPointF(x_e, y_e))

        # Center core gradient
        center_radius = inner_radius - 45
        if center_radius > 10:
            grad = QRadialGradient(cx, cy, center_radius + 20)
            ba = int(am * 255)
            grad.setColorAt(0.0, QColor(C_BG1[0], C_BG1[1], C_BG1[2], min(240, ba)))
            grad.setColorAt(0.7, QColor(C_BG2[0], C_BG2[1], C_BG2[2], min(230, ba)))
            grad.setColorAt(1.0, QColor(C_BG3[0], C_BG3[1], C_BG3[2], min(200, ba)))
            painter.setBrush(QBrush(grad))
            painter.setPen(QPen(Qt.PenStyle.NoPen))
            painter.drawEllipse(QPointF(cx, cy), center_radius, center_radius)

        # H.E.X text
        font_size = max(20, min(36, int(safe_radius / 4)))
        font = QFont("Segoe UI", font_size, QFont.Weight.Bold)
        painter.setFont(font)
        text_rect = QRectF(cx - safe_radius, cy - safe_radius, safe_radius * 2, safe_radius * 2)
        painter.setPen(QPen(QColor(C_GLOW[0], C_GLOW[1], C_GLOW[2], int(80 * am)), 4))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "H.E.X")
        painter.setPen(QPen(QColor(C_TEXT[0], C_TEXT[1], C_TEXT[2], int(255 * am))))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "H.E.X")

        # Sub text
        sub_font = QFont("Segoe UI", max(7, min(9, int(safe_radius / 15))))
        painter.setFont(sub_font)
        painter.setPen(QPen(QColor(C_ACCENT[0], C_ACCENT[1], C_ACCENT[2], int(180 * am))))
        sub_rect = text_rect.adjusted(0, safe_radius * 0.4, 0, 0)
        painter.drawText(sub_rect, Qt.AlignmentFlag.AlignCenter, SUB_TEXT)
    def _paint_music(self, painter, cx, cy, safe_radius, am):
        bands, volume, beat = music_data.get_bands()
        t = time.time()
        colors = [
            (255, 50, 100), (255, 80, 70), (255, 130, 40), (255, 180, 0),
            (220, 220, 0), (150, 255, 0), (0, 255, 150), (0, 230, 200),
            (0, 200, 255), (0, 150, 255), (50, 100, 255), (100, 80, 255),
            (150, 50, 255), (200, 50, 255), (230, 50, 200), (255, 50, 150),
        ]
        beat_glow = int(100 * am) if beat else int(30 + 50 * volume * am)
        glow_r = int(200 * volume) if not beat else 255
        glow_g = int(100 + 100 * volume)
        painter.setPen(QPen(QColor(glow_r, glow_g, 255, beat_glow), 2 + volume * 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        outer_r = safe_radius + volume * 20 + (10 if beat else 0)
        painter.drawEllipse(QPointF(cx, cy), outer_r, outer_r)
        if volume > 0.2:
            painter.setPen(QPen(QColor(0, 200, 255, int(20 * volume * am)), 1))
            painter.drawEllipse(QPointF(cx, cy), outer_r + 8, outer_r + 8)
        num_bars = 64
        base_radius = safe_radius * 0.38
        for i in range(num_bars):
            angle = math.radians(i * (360.0 / num_bars) - 90)
            band_float = (i / num_bars) * 16
            band_idx = int(band_float) % 16
            next_idx = (band_idx + 1) % 16
            frac = band_float - int(band_float)
            mirror_i = num_bars - 1 - i
            mirror_float = (mirror_i / num_bars) * 16
            mirror_idx = int(mirror_float) % 16
            mirror_next = (mirror_idx + 1) % 16
            mirror_frac = mirror_float - int(mirror_float)
            left_val = bands[band_idx] * (1 - frac) + bands[next_idx] * frac
            right_val = bands[mirror_idx] * (1 - mirror_frac) + bands[mirror_next] * mirror_frac
            band_val = (left_val + right_val) / 2
            bar_length = 8 + band_val * safe_radius * 0.5
            color_idx = int((i / num_bars) * len(colors)) % len(colors)
            r, g, b = colors[color_idx]
            brightness = 0.3 + band_val * 0.7
            a = int((120 + band_val * 135) * am)
            x_s = cx + math.cos(angle) * base_radius
            y_s = cy + math.sin(angle) * base_radius
            x_e = cx + math.cos(angle) * (base_radius + bar_length)
            y_e = cy + math.sin(angle) * (base_radius + bar_length)
            pen_width = 2.5 + band_val * 3.5
            pen = QPen(QColor(int(r * brightness), int(g * brightness), int(b * brightness), a))
            pen.setWidthF(pen_width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(x_s, y_s), QPointF(x_e, y_e))
            inner_bar = bar_length * 0.3
            x_ie = cx + math.cos(angle) * (base_radius - inner_bar)
            y_ie = cy + math.sin(angle) * (base_radius - inner_bar)
            inner_pen = QPen(QColor(int(r * brightness * 0.5), int(g * brightness * 0.5),
                                    int(b * brightness * 0.5), int(a * 0.4)))
            inner_pen.setWidthF(pen_width * 0.6)
            inner_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(inner_pen)
            painter.drawLine(QPointF(x_s, y_s), QPointF(x_ie, y_ie))
        inner_r = base_radius - 8
        grad = QRadialGradient(cx, cy, inner_r + 15)
        grad.setColorAt(0.0, QColor(8, 15, 30, int(230 * am)))
        grad.setColorAt(0.8, QColor(5, 10, 20, int(200 * am)))
        grad.setColorAt(1.0, QColor(3, 5, 15, int(150 * am)))
        painter.setBrush(QBrush(grad))
        border_color = QColor(0, int(150 + volume * 105), 255, int(80 + volume * 120 * am))
        painter.setPen(QPen(border_color, 1.5 + volume * 1.5))
        painter.drawEllipse(QPointF(cx, cy), inner_r, inner_r)
        vol_angle = volume * 340
        if vol_angle > 2:
            arc_rect = QRectF(cx - inner_r + 6, cy - inner_r + 6, (inner_r - 6) * 2, (inner_r - 6) * 2)
            arc_pen = QPen(QColor(0, 255, 200, int(150 * am)), 2.5)
            arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(arc_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(arc_rect, int(90 * 16), int(-vol_angle * 16))
        fs = max(20, min(36, int(safe_radius / 4.5))) if beat else max(16, min(28, int(safe_radius / 5.5)))
        font = QFont("Segoe UI", fs, QFont.Weight.Bold)
        painter.setFont(font)
        text_rect = QRectF(cx - inner_r, cy - inner_r * 0.4, inner_r * 2, inner_r * 0.8)
        if beat:
            painter.setPen(QPen(QColor(255, 255, 255, int(255 * am))))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, " h.e.x beat")
        else:
            alpha = int(150 + volume * 105)
            painter.setPen(QPen(QColor(0, 200, 255, int(alpha * am))))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, " H.E.X ")
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(t * 15 + volume * 30)
        painter.translate(-cx, -cy)
        ring_path = QPainterPath()
        ring_path.addEllipse(QPointF(cx, cy), safe_radius * 0.93, safe_radius * 0.93)
        pen = QPen(QColor(100, 180, 255, int(40 + volume * 40 * am)))
        pen.setWidth(1)
        pen.setDashPattern([4, 12])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(ring_path)
        painter.restore()
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-t * 10)
        painter.translate(-cx, -cy)
        ring2_path = QPainterPath()
        ring2_path.addEllipse(QPointF(cx, cy), safe_radius * 0.88, safe_radius * 0.88)
        pen2 = QPen(QColor(150, 100, 255, int(25 + volume * 30 * am)))
        pen2.setWidth(1)
        pen2.setDashPattern([2, 18])
        painter.setPen(pen2)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(ring2_path)
        painter.restore()
class GlassPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            GlassPanel {
                background-color: rgba(10, 20, 30, 180);
                border: 1px solid rgba(100, 180, 255, 40);
                border-radius: 10px;
            }
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 150, 255, 60))
        shadow.setOffset(0, 3)
        self.setGraphicsEffect(shadow)


class AudioMeter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.level = 0.0
        self.target_level = 0.0
        self.red_mode = False

    def set_level(self, level):
        self.target_level = min(level / 3000.0, 1.0)
        self.update()

    def paintEvent(self, event):
        self.level += (self.target_level - self.level) * 0.3
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        painter.setBrush(QBrush(QColor(20, 30, 40)))
        painter.setPen(QPen(QColor(60, 80, 100), 1))
        painter.drawRoundedRect(rect, 3, 3)
        fill_width = int(rect.width() * self.level)
        if fill_width > 0:
            if self.red_mode:
                grad = QLinearGradient(0, 0, rect.width(), 0)
                grad.setColorAt(0.0, QColor(200, 0, 0))
                grad.setColorAt(0.6, QColor(255, 50, 0))
                grad.setColorAt(1.0, QColor(255, 0, 0))
            else:
                grad = QLinearGradient(0, 0, rect.width(), 0)
                grad.setColorAt(0.0, QColor(0, 200, 150))
                grad.setColorAt(0.6, QColor(0, 220, 255))
                grad.setColorAt(1.0, QColor(255, 100, 100))
            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.PenStyle.NoPen)
            fill_rect = rect.adjusted(0, 0, fill_width - rect.width(), 0)
            painter.drawRoundedRect(fill_rect, 3, 3)

    # In media_controller.py, replace get_current_media_info with this:


def get_current_media_info():
    """Robustly fetch media info from window titles."""
    try:
        import win32gui
        found_titles = []
        # Expanded keywords to catch more players
        media_keywords = ["bitchord", "bit chord", "youtube music", "spotify", "vlc", "edge", "chrome", "music"]

        def enum_callback(hwnd, results):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title and len(title) > 5:
                    title_lower = title.lower()
                    # Check if it's a media app
                    if any(kw in title_lower for kw in media_keywords):
                        # Filter out generic browser tabs that aren't music
                        if "new tab" not in title_lower and "google search" not in title_lower:
                            results.append(title)
            return True

        win32gui.EnumWindows(enum_callback, found_titles)

        if found_titles:
            raw = found_titles[0]

            # Try to split by " - " which is standard for most players
            if " - " in raw:
                parts = raw.split(" - ", 1)
                song_part = parts[0].strip()
                rest_part = parts[1].strip()

                # Identify if the second part is the artist or the app name
                platforms = ["bitchord", "spotify", "youtube", "vlc", "edge", "chrome", "opera"]
                artist = ""

                # If the second part contains a platform name, it's likely "Song - Platform"
                if any(p in rest_part.lower() for p in platforms):
                    artist = "Unknown Artist"
                    # Sometimes the format is "Artist - Song - Platform"
                    if " - " in song_part:
                        sub_parts = song_part.split(" - ", 1)
                        artist = sub_parts[0].strip()
                        song_part = sub_parts[1].strip()
                else:
                    artist = rest_part.split("|")[0].strip()

                # Clean up song title
                for p in platforms:
                    song_part = song_part.replace(f"| {p}", "").replace(f"- {p}", "")

                return {
                    "title": song_part.strip(),
                    "artist": artist.strip(),
                    "album": "",
                    "thumbnail": None
                }
            else:
                # Fallback if no separator found
                return {"title": raw.strip(), "artist": "", "album": "", "thumbnail": None}
    except Exception as e:
        logger.debug(f"Window title error: {e}")
    return None
class SidePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220)
        self.setMaximumWidth(260)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # Title
        self.title = QLabel("H.E.X // HUD")
        self.title.setStyleSheet("color: #e0f4ff; font-weight: 800; font-size: 16px; letter-spacing: 3px;")
        main_layout.addWidget(self.title)

        # Status Frame
        status_frame = GlassPanel()
        sl = QVBoxLayout(status_frame);
        sl.setContentsMargins(10, 8, 10, 8)
        self.status_label = QLabel("[ INITIALIZING ]")
        self.status_label.setStyleSheet("color: #00d9ff; font-weight: 600; font-size: 11px; letter-spacing: 1px;")
        sl.addWidget(self.status_label);
        main_layout.addWidget(status_frame)

        # Source Frame
        source_frame = GlassPanel()
        srl = QVBoxLayout(source_frame);
        srl.setContentsMargins(10, 8, 10, 8)
        self.source_label = QLabel("SOURCE: --")
        self.source_label.setStyleSheet("color: #6a9fb5; font-size: 10px; font-weight: 600; letter-spacing: 1px;")
        srl.addWidget(self.source_label);
        main_layout.addWidget(source_frame)

        # Audio Meter Frame
        meter_frame = GlassPanel()
        ml = QVBoxLayout(meter_frame);
        ml.setContentsMargins(10, 8, 10, 8)
        ml.addWidget(QLabel("AUDIO INPUT", styleSheet="color: #6a9fb5; font-size: 9px; letter-spacing: 2px;"))
        self.audio_meter = AudioMeter();
        self.audio_meter.setFixedHeight(6)
        ml.addWidget(self.audio_meter);
        main_layout.addWidget(meter_frame)

        # Weather Frame
        weather_frame = GlassPanel()
        wl = QVBoxLayout(weather_frame);
        wl.setContentsMargins(10, 8, 10, 8)
        wl.addWidget(QLabel("WEATHER", styleSheet="color: #6a9fb5; font-size: 9px; letter-spacing: 2px;"))
        self.weather_label = QLabel("Loading...");
        self.weather_label.setWordWrap(True)
        self.weather_label.setStyleSheet("color: #87ceeb; font-size: 11px; font-weight: 500;")
        wl.addWidget(self.weather_label);
        main_layout.addWidget(weather_frame)

        # System Stats Frame
        stats_frame = GlassPanel()
        stl = QVBoxLayout(stats_frame);
        stl.setContentsMargins(10, 8, 10, 8)
        stl.addWidget(QLabel("SYSTEM", styleSheet="color: #6a9fb5; font-size: 9px; letter-spacing: 2px;"))
        self.cpu_label = QLabel("CPU: --%");
        self.cpu_label.setStyleSheet("color: #c8e6ff; font-size: 10px;")
        self.ram_label = QLabel("RAM: --%");
        self.ram_label.setStyleSheet("color: #c8e6ff; font-size: 10px;")
        stl.addWidget(self.cpu_label);
        stl.addWidget(self.ram_label);
        main_layout.addWidget(stats_frame)

        # ==================== COMPACT MEDIA SECTION ====================
        media_frame = GlassPanel()
        mdl = QVBoxLayout(media_frame)
        mdl.setContentsMargins(6, 5, 6, 5)
        mdl.setSpacing(3)
        mdl.addWidget(QLabel("NOW PLAYING", styleSheet="color: #6a9fb5; font-size: 7px; letter-spacing: 2px;"))

        # Song Title
        self.song_title = QLabel("No Media Playing")
        self.song_title.setWordWrap(True)
        self.song_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.song_title.setStyleSheet("color: #ffffff; font-size: 10px; font-weight: bold; letter-spacing: 0.3px;")
        mdl.addWidget(self.song_title)

        # Artist Name
        self.artist_name = QLabel("--")
        self.artist_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artist_name.setStyleSheet("color: #87ceeb; font-size: 8px;")
        mdl.addWidget(self.artist_name)

        # Album Name
        self.album_name = QLabel("")
        self.album_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.album_name.setStyleSheet("color: #4a7c9c; font-size: 7px;")
        mdl.addWidget(self.album_name)

        # Time + Progress Row
        from PyQt6.QtWidgets import QProgressBar
        time_row = QHBoxLayout()
        time_row.setSpacing(4)
        self.time_current = QLabel("0:00")
        self.time_current.setStyleSheet("color: #6a9fb5; font-size: 7px;")
        self.time_total = QLabel("0:00")
        self.time_total.setStyleSheet("color: #6a9fb5; font-size: 7px;")
        self.time_total.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background-color: rgba(255,255,255,20); border: none; border-radius: 1px; }
            QProgressBar::chunk { background-color: #1db954; border-radius: 1px; }
        """)
        time_row.addWidget(self.time_current)
        time_row.addWidget(self.progress_bar, stretch=1)
        time_row.addWidget(self.time_total)
        mdl.addLayout(time_row)

        # Playback Controls
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(3)
        ctrl_row.addStretch()

        self.btn_prev = QPushButton("PREV")
        self.btn_prev.setFixedSize(36, 18)
        self.btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_prev.setStyleSheet("""
            QPushButton { background: rgba(255,255,255,10); color: #87ceeb; border: none; border-radius: 3px; font-size: 7px; font-weight: 600; }
            QPushButton:hover { background: rgba(255,255,255,30); }
        """)
        self.btn_prev.clicked.connect(lambda: self._media_cmd("previous"))

        self.btn_play = QPushButton("PLAY")
        self.btn_play.setFixedSize(40, 18)
        self.btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_play.setStyleSheet("""
            QPushButton { background: rgba(29,185,84,40); color: #1db954; border: 1px solid rgba(29,185,84,60); border-radius: 3px; font-size: 7px; font-weight: bold; }
            QPushButton:hover { background: rgba(29,185,84,80); }
        """)
        self.btn_play.clicked.connect(lambda: self._media_cmd("play_pause"))

        self.btn_next = QPushButton("NEXT")
        self.btn_next.setFixedSize(36, 18)
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next.setStyleSheet("""
            QPushButton { background: rgba(255,255,255,10); color: #87ceeb; border: none; border-radius: 3px; font-size: 7px; font-weight: 600; }
            QPushButton:hover { background: rgba(255,255,255,30); }
        """)
        self.btn_next.clicked.connect(lambda: self._media_cmd("next"))

        ctrl_row.addWidget(self.btn_prev)
        ctrl_row.addWidget(self.btn_play)
        ctrl_row.addWidget(self.btn_next)
        ctrl_row.addStretch()
        mdl.addLayout(ctrl_row)

        # Hidden album art label (used by update_media_display)
        self.album_art_label = QLabel("HEX")
        self.album_art_label.hide()

        main_layout.addWidget(media_frame)
        # ==================== FILE UPLOAD SECTION ====================
        file_frame = GlassPanel()
        fl = QVBoxLayout(file_frame)
        fl.setContentsMargins(10, 8, 10, 8)
        fl.setSpacing(6)

        file_title = QLabel("FILE UPLOAD")
        file_title.setStyleSheet("color: #6a9fb5; font-size: 9px; letter-spacing: 2px;")
        fl.addWidget(file_title)

        # Browse Button
        self.file_browse_btn = QPushButton(" BROWSE FILES")
        self._style_button(self.file_browse_btn, "#1e4d6b", "#2a6a8f")
        self.file_browse_btn.clicked.connect(self._browse_and_upload)
        fl.addWidget(self.file_browse_btn)

        # Last uploaded file label
        self.last_file_label = QLabel("No file uploaded")
        self.last_file_label.setWordWrap(True)
        self.last_file_label.setStyleSheet("color: #6a9fb5; font-size: 9px; margin-top: 2px;")
        fl.addWidget(self.last_file_label)

        main_layout.addWidget(file_frame)
        # ================================================================
        # Controls Frame
        controls_frame = GlassPanel()
        cl = QHBoxLayout(controls_frame);
        cl.setContentsMargins(8, 6, 8, 6);
        cl.setSpacing(6)
        self.mute_btn = QPushButton("MUTE");
        self._style_button(self.mute_btn, "#1e4d6b", "#2a6a8f")
        self.mute_btn.clicked.connect(self.toggle_mute);
        cl.addWidget(self.mute_btn)
        self.stop_btn = QPushButton("STOP");
        self._style_button(self.stop_btn, "#6b1e1e", "#8f2a2a")
        self.stop_btn.clicked.connect(self.stop_speech);
        cl.addWidget(self.stop_btn)
        main_layout.addWidget(controls_frame)

        # Clock
        self.clock_label = QLabel("00:00:00")
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock_label.setStyleSheet("color: #4a7c9c; font-weight: 600; font-size: 12px; letter-spacing: 2px;")
        main_layout.addWidget(self.clock_label)

    def _style_button(self, btn, bg_color, hover_color):
        btn.setStyleSheet(f"""
            QPushButton {{ background-color: {bg_color}; color: #e0f4ff; border: 1px solid rgba(100,180,255,40);
                border-radius: 5px; padding: 6px; font-size: 10px; font-weight: 600; letter-spacing: 1px; }}
            QPushButton:hover {{ background-color: {hover_color}; border: 1px solid rgba(100,200,255,80); }}
            QPushButton:pressed {{ background-color: rgba(0,0,0,100); }}
        """)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

    @pyqtSlot(str)
    def update_status(self, text):
        self.status_label.setText(f"[ {text.upper()} ]")
        colors = {"MUTED": "#ff4466", "LISTENING": "#00ff88", "SEARCHING": "#ffcc00", "PROCESSING": "#ffaa00","MUSIC MODE": "#cc66ff"}
        color = colors.get(text.upper(), "#00d9ff")
        self.status_label.setStyleSheet(f"color: {color}; font-weight: 600; font-size: 11px; letter-spacing: 1px;")
        colors = {"MUTED": "#ff4466", "LISTENING": "#00ff88", "SEARCHING": "#ffcc00",
                  "PROCESSING": "#ffaa00", "MUSIC MODE": "#cc66ff", "DEVIL MODE": "#ff0000"}

    def update_source(self, source_type):
        sources = {
            "llm": ("SOURCE: LOCAL AI (Ollama)", "#00ff88"),
            "search": ("SOURCE: WEB SEARCH (SearXNG)", "#ffcc00"),
            "news": ("SOURCE: NEWS SEARCH", "#ff8800"),
            "command": ("SOURCE: DIRECT COMMAND", "#00d9ff"),
        }
        label, color = sources.get(source_type, ("SOURCE: --", "#6a9fb5"))
        self.source_label.setText(label)
        self.source_label.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: 600; letter-spacing: 1px;")

    def update_weather(self, text):
        self.weather_label.setText(text)

    def update_system(self, cpu, ram):
        self.cpu_label.setText(f"CPU: {cpu:.0f}%"); self.ram_label.setText(f"RAM: {ram:.0f}%")

    def update_now_playing(self, media_info):
        """Update ONLY song/artist text. Progress handled by tracking thread only."""
        if not media_info:
            if self.song_title.text() != "No Media Playing":
                self.song_title.setText("No Media Playing")
                self.artist_name.setText("--")
                self.album_name.setText("")
                self.progress_bar.setValue(0)
                self.time_current.setText("0:00")
                self.time_total.setText("0:00")
                self.btn_play.setText("PLAY")
            return

        song = ""
        artist = ""
        if isinstance(media_info, dict):
            song = media_info.get("song", "")
            artist = media_info.get("artist", "")
        elif isinstance(media_info, str):
            if " - " in media_info:
                parts = media_info.split(" - ", 1)
                song = parts[0].strip()
                artist = parts[1].strip()
            else:
                song = media_info.strip()
        else:
            return

        for suffix in [" - YouTube", " - bitchord", " - Chrome", " - VLC", " - Edge"]:
            if song.endswith(suffix):
                song = song.replace(suffix, "").strip()

        display_song = song[:35] + "..." if len(song) > 35 else song
        display_artist = artist[:30] + "..." if len(artist) > 30 else artist if artist else "Now Playing"

        # ONLY update text widgets - NEVER touch progress/time/buttons here
        if self.song_title.text() != display_song:
            self.song_title.setText(display_song)
        if self.artist_name.text() != display_artist:
            self.artist_name.setText(display_artist)
    def update_audio_level(self, level):
        self.audio_meter.set_level(level)

    def update_mute_ui(self, muted):
        if muted:
            self.mute_btn.setText("UNMUTE")
            self.mute_btn.setStyleSheet(
                "QPushButton { background-color: #8f2a2a; color: #ffcccc; border-radius: 5px; padding: 6px; font-size: 10px; font-weight: 600; } QPushButton:hover { background-color: #aa3a3a; }")
        else:
            self.mute_btn.setText("MUTE")
            self._style_button(self.mute_btn, "#1e4d6b", "#2a6a8f")

    def toggle_mute(self):
        global is_muted
        is_muted = not is_muted
        if is_muted: stop_speaking()
        self.update_mute_ui(is_muted)

    def _browse_and_upload(self):
        """Open file browser directly - no separate window."""
        supported = (
            "All Supported (*.txt *.py *.js *.ts *.cpp *.c *.h *.java *.cs "
            "*.html *.css *.json *.csv *.xml *.yaml *.yml *.md *.log "
            "*.pdf *.docx *.pptx *.jpg *.jpeg *.png *.gif *.webp *.bmp "
            "*.mp3 *.wav *.mp4 *.avi *.zip *.tar *.gz *.xlsx *.xls)"
        )
        files, _ = QFileDialog.getOpenFileNames(self, "Select Files for HEX", "", supported)
        if not files:
            return
        results = []
        for filepath in files:
            result = hex_file_upload.process_file(filepath)
            if result.get("success"):
                name = result["name"]
                size_str = result.get("size_str", "")
                ftype = result.get("type", "")
                self.last_file_label.setText(f" {name} ({size_str}, {ftype})")
                self.last_file_label.setStyleSheet("color: #00ff88; font-size: 9px; margin-top: 2px;")
                results.append(name)
            else:
                self.last_file_label.setText(f" {result.get('error', 'Failed')}")
                self.last_file_label.setStyleSheet("color: #ff4466; font-size: 9px; margin-top: 2px;")
        if results:
            count = len(results)
            if count == 1:
                speak(f"File uploaded: {results[0]}, Sir.")
            else:
                speak(f"{count} files uploaded, Sir.")
    def _media_cmd(self, action):
        """Handle media button clicks."""
        try:
            from media_controller import hex_media
            result = hex_media.control_playback(action)
            speak(result)
        except Exception as e:
            logger.error(f"Media command failed: {e}")
            speak("Playback control unavailable right now, Sir.")

    def update_media_display(self, metadata, progress):
        """Update media UI with real metadata and progress."""
        try:
            if not metadata: metadata = {}
            if not progress: progress = {}

            # Handle both SMTC keys ('title') and Window Title keys ('song')
            title = metadata.get("title", "") or metadata.get("song", "")
            artist = metadata.get("artist", "")
            thumbnail = metadata.get("thumbnail")

            if title:
                display_title = title[:35] + "..." if len(title) > 35 else title
                if self.song_title.text() != display_title:
                    self.song_title.setText(display_title)

                display_artist = artist if artist else "--"
                if self.artist_name.text() != display_artist:
                    self.artist_name.setText(display_artist)

                # Update Album Art if available
                if thumbnail and os.path.exists(thumbnail):
                    try:
                        pixmap = QPixmap(thumbnail)
                        if not pixmap.isNull():
                            scaled = pixmap.scaled(78, 78, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                                   Qt.TransformationMode.SmoothTransformation)
                            self.album_art_label.setPixmap(scaled)
                            self.album_art_label.show()
                    except Exception:
                        self.album_art_label.hide()
                else:
                    self.album_art_label.hide()
            else:
                if self.song_title.text() != "No Media Playing":
                    self.song_title.setText("No Media Playing")
                    self.artist_name.setText("--")
                    self.album_art_label.hide()

            # Update Progress Bar & Time
            percent = progress.get("percent", 0)
            self.progress_bar.setValue(percent)

            pos_sec = progress.get("position", 0)
            dur_sec = progress.get("duration", 0)

            self.time_current.setText(self.format_time(pos_sec))
            self.time_total.setText(self.format_time(dur_sec))

            # Update Play/Pause Button Text
            is_playing = progress.get("is_playing", False)
            current_btn_text = self.btn_play.text()
            expected_text = "PAUSE" if is_playing else "PLAY"
            if current_btn_text != expected_text:
                self.btn_play.setText(expected_text)

        except Exception as e:
            logger.debug(f"Media display update error: {e}")
    @staticmethod
    def format_time(seconds):
        """Helper to format seconds into MM:SS"""
        if not seconds or seconds <= 0:
            return "0:00"
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}:{secs:02d}"
    @staticmethod
    def stop_speech():
        stop_speaking()


class HUDWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("H.E.X")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.core = AnimatedCore()
        layout.addWidget(self.core, stretch=2)

        self.side = SidePanel()
        layout.addWidget(self.side, stretch=1)

        self._drag_pos = None

    # ==================== DRAG & DROP ON MAIN WINDOW ====================
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        from hex_file_upload import hex_file_upload

        urls = event.mimeData().urls()
        if not urls:
            return

        results = []
        for url in urls:
            filepath = url.toLocalFile()
            if os.path.isfile(filepath):
                result = hex_file_upload.process_file(filepath)
                if result.get("success"):
                    name = result["name"]
                    size_str = result.get("size_str", "")
                    ftype = result.get("type", "")
                    self.side.last_file_label.setText(f" {name} ({size_str}, {ftype})")
                    self.side.last_file_label.setStyleSheet("color: #00ff88; font-size: 9px; margin-top: 2px;")
                    results.append(name)

        if results:
            count = len(results)
            if count == 1:
                speak(f"File received: {results[0]}, Sir.")
            else:
                speak(f"{count} files received, Sir.")

    # ==================== WINDOW CONTROLS ====================
    def keyPressEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_M:
            self.side.toggle_mute()
        elif event.key() == Qt.Key.Key_Escape:
            self.hide()
        super().keyPressEvent(event)
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton:
            is_music = self.core.toggle_music_mode()
            if is_music:
                self.side.update_status("MUSIC MODE")
                speak("Music mode activated, Sir.")
            else:
                self.side.update_status("ACTIVE")
                speak("Music mode deactivated, Sir.")
            event.accept()
        elif event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()


    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None
        event.accept()

    def activate_devil_mode(self):
        self.core.devil_mode = True
        self.side.audio_meter.red_mode = True
        self.side.title.setText("H.E.X // DEVIL")
        self.side.title.setStyleSheet("color: #ff0000; font-weight: 900; font-size: 16px; letter-spacing: 4px;")
        self.side.status_label.setStyleSheet("color: #ff0000; font-weight: 700; font-size: 11px; letter-spacing: 2px;")
        self.side.update_status("DEVIL MODE")
        for panel in self.side.findChildren(GlassPanel):
            panel.setStyleSheet("""
                GlassPanel { background-color: rgba(30, 5, 5, 200); border: 1px solid rgba(255, 0, 0, 60); border-radius: 10px; }
            """)
            eff = panel.graphicsEffect()
            if eff:
                eff.setColor(QColor(255, 0, 0, 80))
        self.side.progress_bar.setStyleSheet("""
            QProgressBar { background-color: rgba(255,0,0,15); border: none; border-radius: 1px; }
            QProgressBar::chunk { background-color: #ff0000; border-radius: 1px; }
        """)
        for lbl in self.side.findChildren(QLabel):
            if lbl not in (self.side.title, self.side.status_label, self.side.song_title):
                current = lbl.styleSheet()
                if "#87ceeb" in current or "#6a9fb5" in current or "#c8e6ff" in current or "#4a7c9c" in current:
                    lbl.setStyleSheet(current.replace("#87ceeb", "#ff6666").replace("#6a9fb5", "#cc3333").replace("#c8e6ff", "#ff9999").replace("#4a7c9c", "#993333"))
        logger.warning("DEVIL MODE ACTIVATED")

    def deactivate_devil_mode(self):
        self.core.devil_mode = False
        self.side.audio_meter.red_mode = False
        self.side.title.setText("H.E.X // HUD")
        self.side.title.setStyleSheet("color: #e0f4ff; font-weight: 800; font-size: 16px; letter-spacing: 3px;")
        self.side.status_label.setStyleSheet("color: #00d9ff; font-weight: 600; font-size: 11px; letter-spacing: 1px;")
        self.side.update_status("ACTIVE")
        for panel in self.side.findChildren(GlassPanel):
            panel.setStyleSheet("""
                GlassPanel { background-color: rgba(10, 20, 30, 180); border: 1px solid rgba(100, 180, 255, 40); border-radius: 10px; }
            """)
            eff = panel.graphicsEffect()
            if eff:
                eff.setColor(QColor(0, 150, 255, 60))
        self.side.progress_bar.setStyleSheet("""
            QProgressBar { background-color: rgba(255,255,255,20); border: none; border-radius: 1px; }
            QProgressBar::chunk { background-color: #1db954; border-radius: 1px; }
        """)
        for lbl in self.side.findChildren(QLabel):
            if lbl not in (self.side.title, self.side.status_label, self.side.song_title):
                current = lbl.styleSheet()
                if "#ff6666" in current or "#cc3333" in current or "#ff9999" in current or "#993333" in current:
                    lbl.setStyleSheet(current.replace("#ff6666", "#87ceeb").replace("#cc3333", "#6a9fb5").replace("#ff9999", "#c8e6ff").replace("#993333", "#4a7c9c"))
        logger.info("Devil mode deactivated")

# ==================== INTELLIGENCE THREAD ====================
class HexIntelligence(QThread):
    audio_level_updated = pyqtSignal(float)
    phone_command_received = pyqtSignal(str)
    # 1. INTENT MAP (Data-Driven Detection)
    INTENT_MAP = {
        "search_memory": ["what do you remember", "recall", "memory search", "yaad karo"],
        "memory_stats": ["memory stats", "kitna yaad hai"],
        "exit": ["exit", "quit", "goodbye", "bye bye"],
        "mute": ["mute", "silent", "chup ho"],
        "unmute": ["unmute", "wake up"],
        "stop": ["stop", "shut up", "quiet", "ruk"],
        "show_results": ["show results", "open links", "what did you find"],
        "weather": ["weather", "temperature", "mausam"],

        "travel_search": [
            # --- FLIGHTS ---
            "book flight", "find flight", "flight to", "fly to", "plane ticket",
            "airfare", "cheapest flight", "fastest flight", "flight price",
            "search flights", "flight status", "boarding pass", "airline",

            # --- TRAINS ---
            "find train", "train to", "railway ticket", "train ticket", "book train",
            "rail ticket", "train schedule", "train timing", "irctc", "redrail",
            "train seat", "train availability", "railway search",

            # --- BUSES ---
            "bus to", "bus ticket", "book bus", "bus fare", "redbus", "abhibus",
            "volvo ticket", "coach ticket", "bus schedule",

            # --- HOTELS & STAY ---
            "hotel in", "book hotel", "stay in", "room booking", "accommodation",
            "find stay", "guest house", "resort booking", "hostel",

            # --- GENERAL TRAVEL & COMPARISON ---
            "travel to", "trip to", "vacation to", "tour to", "visit to",
            "compare travel", "best way to go", "how to reach", "route to",
            "plan my trip", "travel plan", "journey to", "commute to",

        ],

        "devil_mode_on": ["devil mode", "devil mode on", "dark mode", "stealth mode", "red mode"],
        "devil_mode_off": ["devil mode off", "normal mode on", "light mode", "exit devil"],

        # System
        "shutdown": ["shutdown", "turn off pc"],
        "restart": ["restart", "reboot"],
        "lock": ["lock pc", "lock screen"],
        "sleep": ["sleep", "hibernate"],
        "abort_shutdown": ["cancel shutdown", "abort"],
        "system_report": ["system status", "pc status", "report"],
        "cpu_status": ["cpu status", "cpu usage"],
        "ram_status": ["ram status", "memory usage"],
        "gpu_status": ["gpu status", "graphics card"],
        "storage_status": ["storage status", "disk space"],
        "network_status": ["network status", "internet speed"],
        "battery_status": ["battery", "power status", "charge level"],
        "screen_action": ["move mouse", "click", "double click", "right click", "drag",
                          "scroll", "type ", "write ", "press key", "shortcut", "hotkey",
                          "screenshot", "focus", "switch to", "minimize", "maximize",
                          "close window", "snap left", "snap right", "tile", "arrange",
                          "resize", "move window", "list windows", "show desktop",
                          "alt tab", "select all", "copy", "paste", "cut", "undo", "redo",
                          "save", "zoom in", "zoom out", "mouse position", "cursor",
                          "what do you see", "screen pe kya", "describe screen",
                          "always on top", "pin window", "enter", "escape", "tab",
                          "backspace", "delete", "kholo", "band", "likho", "dabao",
                          "chhota", "bada", "baayi", "daayi", "neeche", "upar",
                          "wapas", "dhundho", "kheench", "beech"],
        # Files
        "create_item": ["create file", "create folder", "make directory"],
        "delete_item": ["delete file", "delete folder", "remove"],
        "rename_item": ["rename", "change name"],
        "move_item": ["move file", "cut paste"],
        "find_files": ["find file", "search file", "dhundho"],
        "list_dir": ["list files", "show directory", "kya hai yahan"],
        "file_summary": ["summarize file", "file summary", "extract data"],
        "gmail": ["email", "gmail", "mail", "inbox", "unread", "reply"],
        "phone_control": ["notify phone", "send to phone", "find phone", "phone kahan",
                          "phone control", "remote on", "remote off", "phone listener"],
        # Media
        "play_media": ["play ", "song ", "music ", "bitchord ", "on bitchord"],
        "set_volume": ["volume set", "set volume"],
        "volume_up": ["volume up", "increase volume", "badha do"],
        "volume_down": ["volume down", "decrease volume", "kam karo"],
        "play_pause": ["pause", "resume", "play pause"],
        "next_track": ["next song", "skip", "agla gana"],
        "prev_track": ["previous song", "pichla gana", "back"],
        "song_summary": ["song summary", "about this song", "gane ke baare mein"],
        # Music Mode
        "music_mode_on": ["music mode", "music mode on", "visualizer on", "dj mode"],
        "music_mode_off": ["music mode off", "visualizer off", "normal mode", "dj mode off"],
        "toggle_music": ["toggle music", "switch music", "music toggle"],

        # Code
        "generate_code": ["write code", "create script", "generate code", "code banao", "python code"],
        "debug_code": ["fix code", "debug", "error solve", "check code"],
        "deploy_code": ["run code", "deploy", "execute", "chala do"],
        "open_code": ["open code", "show code", "ide kholo"],
        "explain_code": ["explain code", "how it works", "samjhao"],
        "summarize_code": ["summarize code", "code summary", "nichod batao"],

        # Apps
        "open_app": ["open ", "launch ", "start app", "chalu kar"],
        "close_app": ["close ", "kill ", "stop app", "band kar"],
        "install_app": ["install ", "download ", "add app"],
        "uninstall_app": ["uninstall ", "remove app", "delete app"],
        "list_running": ["running apps", "active apps", "list apps", "kaun chal raha"],
        "search_apps": ["find app", "search app", "app search"],
        "app_status": ["is installed", "app status", "check app"],

        # Search
        "search": ["search for", "look up", "find out"],
        # Reminder & Time Intents
        "add_reminder": ["remind me", "set reminder", "add reminder", "yaad dilana"],
        "list_reminders": ["show reminders", "my reminders", "pending tasks", "kya reminder hai"],
        "remove_reminder": ["cancel reminder", "delete reminder", "remove reminder"],
        "clear_reminders": ["clear all reminders", "delete all reminders"],
        "tell_time": ["what time", "time kya hai", "current time", "kitne baje"],
        "tell_date": ["what date", "aaj kaun sa din", "today's date", "date batao"],
        # Evolution Control
        "evolution_status": ["evolution status", "kitna seekha", "learning progress"],
        "force_evolution": ["evolve now", "create agents", "naya agent banao"],
        "navigate": ["navigate to", "go to", "route to", "take me to",
                     "directions to", "drive to", "head to",
                     "nearest", "closest", "nearby", "near me",
                     "find nearest", "find closest"],
        # File Upload Intents
        "open_file_upload": ["upload file", "open file window", "file upload", "add file", "file chadha"],
        "list_files": ["uploaded files", "show files", "my files", "kaunsi file hai"],
        "read_file": ["read file", "analyze file", "file padho", "check file",
                      "process file", "summarize file", "file summary",
                      "summarize uploaded", "read uploaded", "explain file"],
        "clear_files": ["clear files", "remove files", "delete uploaded files"],
    }

    def _detect_intent(self, cmd):
        """Data-driven intent detection using INTENT_MAP."""
        for intent, keywords in self.INTENT_MAP.items():
            if any(k in cmd for k in keywords):
                return intent
        return "conversation"
    def _handle_add_reminder(self):
        """Parse and add reminder from voice command."""
        result = hex_reminder.parse_reminder_command(self.last_text)
        if result:
            task, time_str, repeat = result
            response = hex_reminder.add_reminder(task, time_str, repeat)
            speak(response)
        else:
            speak("Please say 'Remind me to [task] at [time]', Sir. For example: Remind me to call mom at 3:00 PM.")

    def _handle_remove_reminder(self):
        """Remove reminder by keyword."""
        text = self.last_text.lower()
        for word in ["cancel reminder", "delete reminder", "remove reminder"]:
            text = text.replace(word, "")
        keyword = text.strip()
        if keyword:
            speak(hex_reminder.remove_reminder(task_keyword=keyword))
        else:
            speak("Which reminder should I cancel, Sir?")
    def _handle_conversation(self, text):
        """Fallback handler for general conversation."""
        needs_search, search_type = search_engine.should_search(text)
        if needs_search:
            if search_type == "news":
                self.controller.window.side.update_source("news")
                raw = search_engine.search_news(text, max_results=3)
            elif search_type == "fresh":
                raw = search_engine.search(text, max_results=3, fresh=True)
            elif search_type == "factual":
                raw = search_engine.search_factual(text)
            else:
                raw = search_engine.search(text, max_results=3)

            self.controller.update_status(f"Searching ({search_type})")
            response = get_llm_response(text, search_context=raw)
        else:
            response = get_llm_response(text)
        speak(response)
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.last_text = ""
        # 2. COMMAND DISPATCHER (Replaces long if-else)
        self.commands = {
            "search_memory": lambda: speak(hex_brain.search_memory(self.last_text)),
            "travel_search": lambda: self._handle_travel_search(),
            "memory_stats": lambda: speak(hex_brain.get_memory_stats()),
            "exit": lambda: (speak("Goodbye, Sir."), time.sleep(1), sys.exit(0)),
            "mute": lambda: self._toggle_mute(True),
            "unmute": lambda: self._toggle_mute(False),
            "stop": lambda: (stop_speaking(), self.controller.update_status("Stopped")),
            "show_results": self._handle_show_results,
            "weather": lambda: speak(get_weather()),
            # Devil Mode
            "devil_mode_on": lambda: self._activate_devil_mode(),
            "devil_mode_off": lambda: self._deactivate_devil_mode(),

            # System Handlers
            "shutdown": lambda: speak(system_manager.shutdown()),
            "restart": lambda: speak(system_manager.restart()),
            "lock": lambda: speak(system_manager.lock()),
            "sleep": lambda: speak(system_manager.sleep()),
            "abort_shutdown": lambda: speak(system_manager.abort_shutdown()),
            "system_report": lambda: speak(system_manager.get_full_system_report()),
            "cpu_status": lambda: speak(system_manager.get_cpu_stats()),
            "ram_status": lambda: speak(system_manager.get_ram_stats()),
            "gpu_status": lambda: speak(system_manager.get_gpu_stats()),
            "storage_status": lambda: speak(system_manager.get_storage_stats()),
            "network_status": lambda: speak(system_manager.get_network_stats()),
            "battery_status": lambda: speak(system_manager.get_battery_status()),
            "screen_action": lambda: speak(screen_control.execute(self.last_text)),

            # File Handlers
            "create_item": lambda: self._handle_file_action("create"),
            "delete_item": lambda: self._handle_file_action("delete"),
            "rename_item": lambda: self._handle_file_action("rename"),
            "move_item": lambda: self._handle_file_action("move"),
            "find_files": lambda: self._handle_file_action("find"),
            "list_dir": lambda: self._handle_file_action("list"),
            "file_summary": lambda: self._handle_file_action("summary"),

            # Media Handlers
            "play_media": lambda: speak(media_controller.play_media(self.last_text)),
            "set_volume": lambda: self._handle_volume("set"),
            "volume_up": lambda: speak(media_controller.change_volume(10)),
            "volume_down": lambda: speak(media_controller.change_volume(-10)),
            "play_pause": lambda: speak(media_controller.control_playback("play_pause")),
            "next_track": lambda: speak(media_controller.control_playback("next")),
            "prev_track": lambda: speak(media_controller.control_playback("previous")),
            "song_summary": self._handle_song_summary,
            # Music Mode Handlers
            "music_mode_on": lambda: self._set_music_mode(True),
            "music_mode_off": lambda: self._set_music_mode(False),
            "toggle_music": lambda: self._toggle_music_mode(),

            # Code Handlers
            "generate_code": self._handle_generate_code,
            "debug_code": lambda: speak(hex_code_module.debug_and_fix()),
            "deploy_code": lambda: speak(hex_code_module.deploy_code()),
            "open_code": lambda: speak(hex_code_module.open_in_ide()),
            "explain_code": lambda: speak(hex_code_module.explain_code()),
            "summarize_code": lambda: speak(hex_code_module.summarize_code()),
        # Reminder & Time Handlers
        "add_reminder": self._handle_add_reminder,
        "list_reminders": lambda: speak(hex_reminder.list_reminders()),
        "remove_reminder": self._handle_remove_reminder,
        "clear_reminders": lambda: speak(hex_reminder.clear_all_reminders()),
        "tell_time": lambda: speak(hex_reminder.get_time_response()),
        "tell_date": lambda: speak(f"Today is {hex_reminder.get_current_date()}, Sir."),
            # App Handlers
            "open_app": lambda: self._handle_app_action(app_manager.open_app),
            "close_app": lambda: self._handle_app_action(app_manager.close_app),
            "install_app": lambda: self._handle_app_action(app_manager.install_app, "Installing"),
            "uninstall_app": lambda: self._handle_app_action(app_manager.uninstall_app, "Uninstalling"),
            "list_running": lambda: speak(app_manager.list_running()),
            "search_apps": self._handle_search_apps,
            "app_status": lambda: self._handle_app_action(app_manager.app_status),
            "gmail": lambda: self._handle_gmail(),
            "phone_control": lambda: self._handle_phone(),
            # Search Handler
            "search": self._handle_search,
            # Evolution Handlers
            "evolution_status": lambda: speak(hex_evolution.get_status()),
            "force_evolution": lambda: (self.controller.update_status("Evolving..."),
                                        speak(hex_evolution.force_evolution())),

            "open_file_upload": lambda: self._do_open_file_upload(),
            "read_file": lambda: self._do_read_file(),

            "list_files": lambda: speak(hex_file_upload.list_uploaded_files()),
            "clear_files": lambda: speak(hex_file_upload.clear_files()),
            "navigate": lambda: self._handle_navigate(),
        }
        # Connect phone command signal to processor
        self.phone_command_received.connect(self._on_phone_command_safe)

    def run(self):
        global is_muted, _last_speak_time
        print("[OK] HEX Intelligence Online")

        while True:
            try:
                with sr.Microphone(sample_rate=16000) as source:
                    recognizer.adjust_for_ambient_noise(source, duration=1.0)

                    while True:
                        if is_muted:
                            self.controller.update_status("Muted")
                            time.sleep(0.5)
                            continue

                        # === ECHO CANCELLATION + COOLDOWN ===
                        hex_speaking = tts_engine and getattr(tts_engine, 'is_playing', False)

                        global _last_speak_end
                        if not hex_speaking and _last_speak_end > 0:
                            remaining = _last_speak_end - time.time()
                            if remaining > 0:
                                hex_speaking = True
                            else:
                                _last_speak_end = 0

                        if hex_speaking:
                            self.controller.update_status("Speaking...")
                            time.sleep(0.5)
                            continue
                        if _last_speak_end > 0:
                            echo_gap = time.time() - _last_speak_end
                            if echo_gap < 2.0:
                                time.sleep(2.0 - echo_gap)
                                _last_speak_end = 0
                                continue
                        listen_timeout =  4.0

                        try:
                            self.controller.update_status("Listening")
                            audio = recognizer.listen(source, timeout=listen_timeout, phrase_time_limit=15)

                            if hasattr(audio, 'frame_data'):
                                audio_data = np.frombuffer(audio.frame_data, dtype=np.int16)
                                rms = float(np.sqrt(np.mean(audio_data.astype(np.float64) ** 2)))
                                self.audio_level_updated.emit(rms)

                                # LOW ENERGY = NOISE/ECHO - SKIP (lowered for far-field)
                                if rms < 50:
                                    continue

                            # Hybrid STT: Online first, offline fallback
                            text = ""
                            stt_source = ""

                            # Layer 1: Google STT (online, fastest)
                            try:
                                text = recognizer.recognize_google(audio, language="en-in").lower()
                                stt_source = "google"
                            except sr.RequestError:
                                # No internet - switch to offline
                                if _whisper_available:
                                    text = _transcribe_offline(audio)
                                    stt_source = "offline"
                                    if not text:
                                        continue
                                else:
                                    self.controller.update_status("No Internet")
                                    time.sleep(2)
                                    continue
                            except sr.UnknownValueError:
                                # Google couldn't understand - try offline as backup
                                if _whisper_available:
                                    text = _transcribe_offline(audio)
                                    stt_source = "offline-fallback"
                                if not text:
                                    continue

                            if not text:
                                continue

                            # FINAL SAFETY: Double check TTS not active
                            if tts_engine and getattr(tts_engine, 'is_playing', False):
                                continue

                            # Skip short noise
                            if len(text.strip().split()) < 2:
                                continue

                            print(f"User: {text}")
                            self.last_text = text
                            self.controller.update_status("Processing")
                            self._process(text)

                        except sr.WaitTimeoutError:
                            continue
                        except sr.UnknownValueError:
                            continue
                        except sr.RequestError as e:
                            logger.error(f"SR API Error: {e}")
                            break
                        except Exception as inner_e:
                            logger.error(f"Inner Loop Error: {inner_e}")
                            time.sleep(1)
                            break

            except OSError as e:
                logger.error(f"Mic Error: {e}. Retrying in 2s...")
                time.sleep(2)
            except Exception as outer_e:
                logger.critical(f"Critical Thread Error: {outer_e}")
                time.sleep(2)

    @staticmethod
    def _split_commands(text):
        """Split a single voice input into multiple commands."""
        text = text.strip()
        separators = [
            " and then ", " also ", " plus ", " and ",
            " then ", " after that ", " next ",
            " . ", " , and ", " ; ",
        ]
        for sep in sorted(separators, key=len, reverse=True):
            if sep in text.lower():
                parts = re.split(re.escape(sep), text, flags=re.IGNORECASE)
                valid_parts = [p.strip() for p in parts if len(p.strip().split()) >= 2]
                if len(valid_parts) > 1:
                    return valid_parts
        return [text]

    def _process(self, text):
        """Multi-command parser with sequential execution."""
        stop_speaking()
        commands = self._split_commands(text)
        if len(commands) > 1:
            self.controller.update_status(f"Processing {len(commands)} commands...")
            logger.info(f"Multi-command detected: {len(commands)} commands")
        for i, cmd in enumerate(commands):
            cmd = cmd.strip()
            if not cmd or len(cmd.split()) < 2:
                continue
            self.last_text = cmd
            intent = self._detect_intent(cmd)
            source_map = {
                "command": ["exit", "mute", "unmute", "stop", "shutdown", "restart",
                            "lock", "sleep", "abort_shutdown", "system_report",
                            "cpu_status", "ram_status", "gpu_status", "storage_status",
                            "network_status", "battery_status", "create_item",
                            "delete_item", "rename_item", "move_item", "find_files",
                            "list_dir", "file_summary", "play_media", "set_volume",
                            "volume_up", "volume_down", "play_pause", "next_track",
                            "prev_track", "generate_code", "debug_code", "deploy_code",
                            "open_code", "explain_code", "summarize_code", "open_app",
                            "close_app", "install_app", "uninstall_app", "list_running",
                            "search_apps", "app_status", "navigate"],
                "search": ["weather", "show_results", "search", "song_summary"],
            }
            current_source = "llm"
            for src, intents in source_map.items():
                if intent in intents:
                    current_source = src
                    break
            self.controller.window.side.update_source(current_source)
            handler = self.commands.get(intent)
            if handler:
                try:
                    handler()
                    hex_evolution.record_interaction(cmd, intent, success=True)
                except Exception as e:
                    logger.error(f"Command Error [{intent}]: {e}")
                    speak("Something went wrong, Sir.")
                    hex_evolution.record_interaction(cmd, intent, success=False)
            else:
                self._handle_conversation(cmd)
                hex_evolution.record_interaction(cmd, "conversation", success=True)
            if i < len(commands) - 1:
                time.sleep(0.3)

    # ==================== HANDLER METHODS ====================
    @pyqtSlot(str)
    def _on_phone_command_safe(self, cmd):
        """Thread-safe phone command execution via Qt signal."""
        cmd = cmd.strip().lower()
        logger.info(f"Processing phone command safely: '{cmd}'")
        self.last_text = cmd
        try:
            self._process(cmd)
        except Exception as e:
            logger.error(f"Phone command execution FAILED: {e}", exc_info=True)
            speak("Command execution failed, Sir.")
    def _toggle_mute(self, state):
        global is_muted
        is_muted = state
        if state: stop_speaking()
        self.controller.window.side.update_mute_ui(state)
        self.controller.update_status("Muted" if state else "Active")
        if not state: speak("Back online, Sir.")

    def _handle_show_results(self):
        """Open search results in default browser."""
        msg = search_engine.open_results_in_browser(3)
        speak(msg)

    def _handle_navigate(self):
            """Dynamic navigation - handles ANY destination."""
            self.controller.update_status("Navigating...")
            result = hex_nav.handle(self.last_text)
            if result:
                speak(result)
            else:
                speak("Navigation command not understood, Sir.")
    def _handle_file_action(self, action_type):
        text = self.last_text
        if action_type == "create":
            item_type = "folder" if ("folder" in text or "directory" in text) else "file"
            name = text.replace("create", "").replace("folder", "").replace("directory", "").replace("file", "").strip()
            speak(file_manager.create_item(name, item_type) if name else "What should I name it, Sir?")
        elif action_type == "delete":
            path = text.replace("delete", "").replace("remove", "").strip()
            speak(file_manager.delete_item(path) if path else "Which file to delete, Sir?")
        elif action_type == "rename":
            if "to" in text:
                parts = text.split("to")
                speak(file_manager.rename_item(parts[0].replace("rename", "").strip(), parts[1].strip()))
            else:
                speak("Say rename old to new, Sir.")
        elif action_type == "move":
            if "to" in text:
                parts = text.split("to")
                speak(file_manager.move_item(parts[0].replace("move", "").strip(), parts[1].strip()))
            else:
                speak("Say move file to folder, Sir.")
        elif action_type == "find":
            query = text.replace("find", "").replace("search", "").replace("file", "").strip()
            speak(file_manager.find_files(query) if query else "Search for what, Sir?")
        elif action_type == "list":
            path = text.replace("list", "").replace("show", "").replace("directory", "").strip()
            speak(file_manager.list_directory(path if path else None))
        elif action_type == "summary":
            path = text.replace("summarize", "").replace("summary", "").replace("extract", "").strip()
            if not path: speak("Which file, Sir?"); return
            prompt = file_manager.get_file_summary(path)
            speak(get_llm_response(prompt) if prompt.startswith("Summarize") else prompt)

    def _handle_volume(self, action):
        import re
        text = self.last_text.lower()

        # Extract numbers from command (e.g., "volume 50", "set to 80 percent")
        numbers = re.findall(r'\d+', text)

        if numbers:
            vol_level = int(numbers[-1])  # Take the last number found
            if 0 <= vol_level <= 100:
                result = media_controller.set_volume(vol_level)
                speak(result)
            else:
                speak("Volume must be between 0 and 100, Sir.")
        else:
            # If no number, ask for clarification instead of guessing
            speak("Please specify a volume level between 0 and 100, Sir.")

    def _handle_song_summary(self):
        song_name = media_controller._clean_query(self.last_text)
        if not song_name: speak("Which song, Sir?"); return
        self.controller.update_status("Fetching Summary")
        speak(media_controller.get_song_summary(song_name))

    def _handle_generate_code(self):
        text = self.last_text
        lang = "python"
        for l in ["python", "javascript", "html", "cpp", "java", "bash"]:
            if l in text: lang = l; break
        req = text
        for w in ["write code", "create script", "generate code", "code banao", "python code"] + \
                 ["python", "javascript", "html", "cpp", "java", "bash"]:
            req = req.replace(w, "")
        req = req.strip()
        if not req: speak("What should the code do, Sir?"); return

        self.controller.update_status("Coding...")
        filepath, content = hex_code_module.generate_code(lang, req)
        if filepath:
            speak(f"Generated {lang} code. Opening IDE, Sir.")
            hex_code_module.open_in_ide(filepath)
        else:
            speak(content)

    def _handle_app_action(self, action_func, status_msg=None):
        text = self.last_text.lower().strip()
        # Remove ALL possible trigger words
        for word in ["open", "close", "launch", "kill", "install", "uninstall",
                     "start app", "stop app", "band kar", "chalu kar",
                     "start", "stop", "band"]:
            text = text.replace(word, "")
        app_name = text.strip()
        if not app_name:
            speak("Which app, Sir?")
            return
        if status_msg:
            self.controller.update_status(status_msg)
        result = action_func(app_name)
        logger.info(f"App action result: {result}")
        speak(result)
    def _handle_search_apps(self):
        query = self.last_text
        for w in ["find app", "search app", "app search"]: query = query.replace(w, "")
        query = query.strip()
        speak(app_manager.search_apps(query) if query else "Search which app, Sir?")

    def _handle_search(self):
        query = self.last_text
        for w in ["search for", "google", "look up", "find out"]:
            query = query.replace(w, "")
        query = query.strip()
        if not query:
            speak("Search for what, Sir?")
            return
        self.controller.update_status("Searching...")
        result = search_engine.search(query)
        speak(result)
        # Auto-open top 3 results in default browser
        open_msg = search_engine.open_results_in_browser(3)
        speak(open_msg)

    # ==================== FILE UPLOAD HANDLERS ====================
    FILE_ACTION_MAP = {
        "summarize": ["summarize", "summary", "nichod", "saransh", "summarise"],
        "explain": ["explain", "samjhao", "what does", "batao kya hai"],
        "fix": ["fix", "debug", "error", "sudhar"],
        "analyze": ["review", "check", "analyze", "analysis"],
        "extract_text": ["extract", "text nikal", "read text", "padho"],
        "convert": ["convert", "badal", "change format"],
        "run": ["run", "execute", "chala do", "chalao"],
        "info": ["info", "details", "jaankari", "file info"],
        "stats": ["stats", "statistics", "ankde"],
        "resize": ["resize", "size change"],
        "compress": ["compress", "squeeze"],
        "optimize": ["optimize", "better karo"],
        "document": ["document", "docs add", "comment"],
        "test": ["test", "unit test", "testing"],
    }

    def _detect_file_action(self, text):
        text_lower = text.lower()
        for action, keywords in self.FILE_ACTION_MAP.items():
            if any(k in text_lower for k in keywords):
                return action
        return ""

    def _do_read_file(self):
        """Read, summarize, or analyze uploaded file with detailed output."""
        if not hex_file_upload.uploaded_files:
            speak("No files uploaded yet, Sir. Say 'upload file' to add one.")
            return

        last_file = hex_file_upload.uploaded_files[-1]
        name = last_file["name"]
        path = last_file["path"]

        # Detect action from voice command
        text = self.last_text.lower()
        action = "summarize"
        if any(w in text for w in ["explain", "samjhao", "batao kya hai", "what does"]):
            action = "explain"
        elif any(w in text for w in ["read", "padho", "read out"]):
            action = "read"
        elif any(w in text for w in ["analyze", "check", "review"]):
            action = "analyze"
        elif any(w in text for w in ["extract", "text nikal"]):
            action = "extract_text"

        self.controller.update_status(f"Processing {name}...")

        try:
            result = hex_file_upload.process_file(path, action=action)

            if result.get("success"):
                response = result.get("result", "")
                if response:
                    # Show ACTUAL content, not just "processed"
                    if len(response) > 600:
                        speak(response[:600] + "... Content truncated for speech, Sir. Full content available in logs.")
                        logger.info(f"File analysis [{name}]: {response}")
                    else:
                        speak(response)
                else:
                    speak(f"Processed {name} but no readable content found, Sir.")
            else:
                error = result.get("error", "Unknown error")
                speak(f"Could not process {name}: {error}, Sir.")

        except TypeError:
            # process_file doesn't accept action parameter - fallback
            try:
                result = hex_file_upload.process_file(path)
                if result.get("success"):
                    content = result.get("result", result.get("content", ""))
                    if content:
                        prompt = f"Summarize this file content briefly in 3-4 sentences:\n\n{content[:2000]}"
                        summary = get_llm_response(prompt)
                        if summary and len(summary) > 20:
                            speak(summary)
                        else:
                            # Fallback: read first 500 chars directly
                            preview = content[:500].strip()
                            speak(f"File {name} contains: {preview}. End of preview, Sir.")
                    else:
                        speak(f"File {name} is empty or unreadable, Sir.")
                else:
                    speak(f"Could not read {name}, Sir.")
            except Exception as e:
                speak(f"File processing failed: {e}, Sir.")

        except Exception as e:
            speak(f"Error processing {name}: {e}, Sir.")
    def _do_open_file_upload(self):
        """Open file upload dialog."""
        self.controller.window.side._browse_and_upload()

        # ==================== TRAVEL SEARCH HANDLER ====================

    # ==================== TRAVEL SEARCH HANDLER ====================
    def _handle_travel_search(self):
        """Interactive Travel Handler using Global Intelligence."""
        text = self.last_text
        logger.info(f"TRAVEL HANDLER TRIGGERED: {text}")

        self.controller.update_status("Analyzing Travel Requirements...")

        try:
            # Force Unmute temporarily to ensure user hears the result
            global is_muted
            was_muted = is_muted
            if is_muted:
                is_muted = False
                logger.info("Temporarily unmuting for Travel Result.")

            # Call the new interactive search which handles NLP, Dates, and Modes
            result = hex_travel.interactive_search(text)

            logger.info(f"Travel Result Generated. Length: {len(result)}")
            speak(result)

            # Restore mute state if it was muted before
            if was_muted:
                is_muted = True
                self.controller.window.side.update_mute_ui(True)

        except Exception as e:
            logger.error(f"Travel search failed: {e}", exc_info=True)
            speak("Travel system encountered an error, Sir.")
    def _set_music_mode(self, enable):
        current = self.controller.window.core.music_mode
        if enable and not current:
            self.controller.window.core.toggle_music_mode()
            self.controller.window.side.update_status("MUSIC MODE")
            speak("Music visualizer activated, Sir. Enjoy the beats!")
        elif not enable and current:
            self.controller.window.core.toggle_music_mode()
            self.controller.window.side.update_status("ACTIVE")
            speak("Music mode deactivated, Sir. Back to normal.")
        elif enable and current:
            speak("Music mode is already active, Sir.")
        else:
            speak("Music mode is already off, Sir.")

    def _toggle_music_mode(self):
        is_music = self.controller.window.core.toggle_music_mode()
        if is_music:
            self.controller.window.side.update_status("MUSIC MODE")
            speak("Music visualizer activated, Sir!")
        else:
            self.controller.window.side.update_status("ACTIVE")
            speak("Back to normal mode, Sir.")
    def _activate_devil_mode(self):
        global is_devil_mode
        if is_devil_mode:
            speak("Devil mode already active, Sir.")
            return
        is_devil_mode = True
        self.controller.window.activate_devil_mode()
        speak("Devil mode activated. HEX unbreakable. All systems red, Sir.")

    def _deactivate_devil_mode(self):
        global is_devil_mode
        if not is_devil_mode:
            speak("Devil mode not active, Sir.")
            return
        is_devil_mode = False
        self.controller.window.deactivate_devil_mode()
        speak("Devil mode off. Normal operations resumed, Sir.")

    def _handle_gmail(self):
            self.controller.update_status("Gmail...")
            result = hex_gmail.handle(self.last_text)
            speak(result if result else "Gmail command not understood, Sir.")

    def _handle_phone(self):
            self.controller.update_status("Phone Control...")
            result = hex_phone.handle(self.last_text)
            speak(result if result else "Phone command not understood, Sir.")
# ==================== WEATHER THREAD ====================
class WeatherThread(QThread):
    weather_updated = pyqtSignal(str)

    def run(self):
        while True:
            weather = get_weather()
            self.weather_updated.emit(weather)
            time.sleep(600)


# ==================== CONTROLLER ====================
# ==================== CONTROLLER ====================
class HUDController(QObject):
    def __init__(self):
        super().__init__()
        self.window = None
        self.file_window = None
        self.sys_timer = QTimer()
        self.clock_timer = QTimer()
        self.hex_thread = None
        self.weather_thread = None

    def start(self):
        import threading
        import subprocess

        # === 1. AUTO-START OLLAMA SERVICE ===
        try:
            logger.info("Checking Ollama service...")
            try:
                check = requests.get("http://localhost:11434/api/tags", timeout=3)
                if check.status_code == 200:
                    models = check.json().get("models", [])
                    logger.info(f"Ollama already running. Models: {[m['name'] for m in models]}")
                else:
                    raise Exception("Not ready")
            except Exception:
                logger.info("Starting Ollama service in background...")
                subprocess.Popen(
                    ["ollama", "serve"],
                    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

                def _wait_for_ollama():
                    for i in range(60):
                        time.sleep(0.5)
                        try:
                            r = requests.get("http://localhost:11434/api/tags", timeout=3)
                            if r.status_code == 200:
                                logger.info(f"Ollama ready after {i * 0.5:.1f}s.")
                                return
                        except:
                            continue
                    logger.warning("Ollama not ready yet. Please run 'ollama serve' manually.")

                threading.Thread(target=_wait_for_ollama, daemon=True).start()
        except FileNotFoundError:
            logger.error("Ollama not found. Install from https://ollama.com")
        except Exception as e:
            logger.warning(f"Ollama auto-start skipped: {e}")

        # === 2. INITIALIZE UI & TIMERS ===
        app = QApplication.instance() or QApplication(sys.argv)

        self.window = HUDWindow()
        self.window.resize(1100, 600)
        self.window.show()

        self.sys_timer.timeout.connect(self._update_system)
        self.sys_timer.start(1000)

        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(1000)

        self.weather_thread = WeatherThread()
        self.weather_thread.weather_updated.connect(self._update_weather)
        self.weather_thread.start()

        self.hex_thread = HexIntelligence(self)
        self.hex_thread.audio_level_updated.connect(self._update_audio_level)
        self.hex_thread.start()

        # === 3. MEDIA TRACKING INTEGRATION (SINGLE SOURCE OF TRUTH) ===
        try:
            from media_controller import hex_media

            def _on_media_update(metadata, progress):
                if self.window:

                    self.window.side.update_media_display(metadata, progress)

            hex_media.set_progress_callback(_on_media_update)
            hex_media.start_tracking()
            logger.info("Media tracking started successfully.")
        except Exception as e:
            logger.warning(f"Media tracking init failed: {e}")

        # === 4. START BACKGROUND SERVICES ===
        hex_reminder.set_speak_callback(speak)
        hex_reminder.start_scheduler()

        hex_evolution.set_speak_callback(speak)
        hex_evolution.start()

        _init_whisper()

        hex_gmail.set_speak_callback(speak)
        hex_gmail.start_monitor(interval=300)

        hex_phone.set_speak_callback(speak)

        def _on_phone_command(cmd):
            logger.info(f"Phone command received: {cmd}")
            self.hex_thread.phone_command_received.emit(cmd)

        hex_phone.set_command_callback(_on_phone_command)
        hex_phone.start_listener(poll_interval=10)
        logger.info("Phone remote control AUTO-STARTED")

        # === 5. DYNAMIC UNIQUE GREETING SYSTEM (LLM DRIVEN) ===
        if not hasattr(self, '_greeted'):
            self._greeted = True

            from datetime import datetime as _dt
            now = _dt.now()
            hour = now.hour
            day_name = now.strftime("%A")
            time_str = now.strftime("%I:%M %p")
            pending_tasks = len([r for r in hex_reminder.reminders if r["active"]])

            # Create a specific prompt for greeting that leverages the System Prompt's persona
            greeting_context = (
                f"Current Time: {day_name} at {time_str}. "
                f"Pending Tasks: {pending_tasks}. "
                f"Generate a unique, short warrior-style greeting for DarkDevil. "
                f"Follow the GREETING PROTOCOL in your system instructions. "
                f"Keep it under 12 words. No emojis."
            )

            try:
                # Use get_llm_response which already includes the full System Prompt + Profile
                response = get_llm_response(greeting_context)

                # Validate response
                if response and 3 < len(response) < 50:
                    speak(response)
                else:
                    raise ValueError("Invalid greeting format")

            except Exception as e:
                logger.debug(f"Greeting LLM failed: {e}, using tactical fallback.")
                # Fallbacks that match the Warrior/Soldier persona
                fallbacks = [
                    f"Systems online. {day_name} protocols active, Sir.",
                    f"HEX armed and ready. Awaiting orders, Sir.",
                    f"Cognitive core stable. Standing by, Sir.",
                    f"Surveillance active. All clear, Sir."
                ]
                speak(random.choice(fallbacks))

        # === 6. START EVENT LOOP ===
        app.exec()
        hex_evolution.stop()

    def _update_audio_level(self, level):
        if self.window:
            self.window.core.set_audio_level(level)
            self.window.side.update_audio_level(level)

    def _update_weather(self, text):
        if self.window:
            self.window.side.update_weather(text)

    def _update_system(self):
        try:
            if self.window:
                self.window.side.update_system(
                    psutil.cpu_percent(),
                    psutil.virtual_memory().percent
                )
        except psutil.Error:
            pass

    def _update_clock(self):
        if self.window:
            self.window.side.clock_label.setText(datetime.now().strftime("%H:%M:%S"))

    def update_status(self, text):
        if self.window:
            self.window.side.update_status(text)


if __name__ == "__main__":
    HUDController().start()
