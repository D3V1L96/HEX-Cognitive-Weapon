import asyncio
import os
import re
import time
import logging
import tempfile
import threading
import hashlib
import queue

logging.basicConfig(level=logging.INFO, format='[Voice] %(message)s')
logger = logging.getLogger(__name__)


class HexVoiceEngine:
    """
    Optimized Voice Engine. Queue-Based Playback. Zero Stutter.
    Uses Edge-TTS (Christopher) with Safe Fallbacks.
    """
    _instance = None
    _lock = threading.Lock()

    VOICE = "en-US-ChristopherNeural"
    RATE = "+6%"
    PITCH = "-8Hz"
    VOLUME = "+12%"

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.is_playing = False
        self._stop_flag = False
        self._active_temp_files = set()
        self._temp_lock = threading.Lock()

        # Queue for smooth sequential playback
        self._audio_queue = queue.Queue()
        self._worker_thread = None

        self._initialized = True

        # Pre-init pygame mixer
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=24000, size=-16, channels=1, buffer=2048)  # Increased buffer for stability
            logger.info(f"HEX Voice Engine Initialized | {self.VOICE} | Dark Mode")
        except Exception as e:
            logger.error(f"Pygame init failed: {e}")

    # ==================== TEXT CLEANING ====================

    @staticmethod
    def _clean_text(text):
        if not isinstance(text, str):
            return ""

        # Remove Markdown
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`[^`]+`', '', text)
        text = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', text)
        text = re.sub(r'#{1,6}\s*', '', text)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

        # Technical Acronyms
        replacements = {
            "C++": "C plus plus", "C#": "C sharp",
            ".py": " dot py", ".js": " dot js", ".html": " dot html",
            ".json": " dot json", ".cpp": " dot cpp",
            "API": "A P I", "URL": "U R L", "JSON": "Jason",
            "SQL": "S Q L", "HTML": "H T M L", "CSS": "C S S",
            "IDE": "I D E", "CPU": "C P U", "RAM": "R A M",
            "GPU": "G P U", "AI": "A I", "LLM": "L L M",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)

        # Humanize Contractions
        humanize = {
            "I have": "I've", "I am": "I'm", "do not": "don't",
            "cannot": "can't", "will not": "won't", "it is": "it's",
        }
        for old, new in humanize.items():
            text = text.replace(old, new)

        # Cleanup Punctuation
        text = re.sub(r'[!]{2,}', '!', text)
        text = re.sub(r'[?]{2,}', '?', text)
        text = re.sub(r'\.{4,}', '.', text)
        text = re.sub(r'\n{2,}', '. ', text)
        text = re.sub(r'\n', ' ', text)
        text = ''.join(char for char in text if char.isprintable())
        text = re.sub(r'\s+', ' ', text).strip()

        # Truncate for speed
        if len(text) > 500:
            sentences = re.split(r'(?<=[.!?])\s+', text)
            trimmed = ""
            for s in sentences:
                if len(trimmed) + len(s) < 480:
                    trimmed += s + " "
                else:
                    break
            text = trimmed.strip()
            if text and text[-1] not in '.!?':
                text += '.'

        return text[:600]

    # ==================== SAFE CLEANUP ====================

    def _safe_cleanup(self, filepath):
        with self._temp_lock:
            self._active_temp_files.discard(filepath)
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except OSError:
            pass

    # ==================== QUEUE WORKER ====================

    def _start_worker(self):
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
            self._worker_thread.start()

    def _process_queue(self):
        while True:
            try:
                text, temp_file = self._audio_queue.get(timeout=1)
                if text is None:  # Shutdown signal
                    break
                self._play_audio_sync(text, temp_file)
                self._audio_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Queue worker error: {e}")

    def _play_audio_sync(self, text, temp_file):
        """Plays audio in the worker thread."""
        import pygame

        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=24000, size=-16, channels=1, buffer=2048)

            pygame.mixer.music.load(temp_file)
            pygame.mixer.music.play()
            self.is_playing = True

            while pygame.mixer.music.get_busy():
                if self._stop_flag:
                    pygame.mixer.music.stop()
                    break
                time.sleep(0.05)  # Slightly higher sleep to reduce CPU load

            self.is_playing = False
            self._safe_cleanup(temp_file)

        except Exception as e:
            logger.error(f"Playback failed: {e}")
            self.is_playing = False
            self._safe_cleanup(temp_file)

    # ==================== CORE SPEAK ====================

    def speak(self, text):
        cleaned = self._clean_text(text)
        if not cleaned:
            return

        # If we are currently speaking, we don't stop immediately unless it's a critical command.
        # For streaming, we let the queue handle sequence.
        # But for HEX responsiveness, we usually want to interrupt.
        if self._stop_flag:
            self._stop_flag = False

        unique_id = hashlib.md5(f"{time.time()}{threading.current_thread().ident}".encode()).hexdigest()[:8]
        temp_file = os.path.join(tempfile.gettempdir(), f"hex_{unique_id}.mp3")

        with self._temp_lock:
            self._active_temp_files.add(temp_file)

        # Start worker if not running
        self._start_worker()

        # Generate audio in a separate thread to avoid blocking the main app
        gen_thread = threading.Thread(
            target=self._generate_and_enqueue,
            args=(cleaned, temp_file),
            daemon=True
        )
        gen_thread.start()

    def _generate_and_enqueue(self, text, temp_file):
        """Generates audio using edge-tts and puts it in the queue."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._async_generate(text, temp_file))
        except Exception as e:
            logger.error(f"Generation error: {e}")
            self._safe_cleanup(temp_file)
        finally:
            loop.close()

    async def _async_generate(self, text, temp_file):
        import edge_tts

        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=self.VOICE,
                rate=self.RATE,
                pitch=self.PITCH,
                volume=self.VOLUME,
            )

            with open(temp_file, "wb") as f:
                async for chunk in communicate.stream():
                    if self._stop_flag:
                        return
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])

            if os.path.exists(temp_file) and os.path.getsize(temp_file) > 100:
                self._audio_queue.put((text, temp_file))
            else:
                self._safe_cleanup(temp_file)

        except Exception as e:
            logger.error(f"TTS Generation failed: {e}")
            self._safe_cleanup(temp_file)

    # ==================== STOP ====================

    def stop(self):
        self._stop_flag = True
        # Clear queue to stop pending speeches
        while not self._audio_queue.empty():
            try:
                _, f = self._audio_queue.get_nowait()
                self._safe_cleanup(f)
            except queue.Empty:
                break

        try:
            import pygame
            if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
        except Exception:
            pass
        self.is_playing = False
        self._stop_flag = False  # Reset for next speech

    # ==================== SHUTDOWN ====================

    def shutdown(self):
        self.stop()
        self._audio_queue.put((None, None))  # Signal worker to stop
        with self._temp_lock:
            for f in list(self._active_temp_files):
                try:
                    if os.path.exists(f):
                        os.remove(f)
                except OSError:
                    pass
            self._active_temp_files.clear()
        logger.info("Voice Engine Shutdown Complete")