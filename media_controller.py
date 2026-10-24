import subprocess
import webbrowser
import urllib.parse
import time
import logging
import os
import re
import glob
import json
import threading
import tempfile
import win32gui
import win32con

logging.basicConfig(level=logging.INFO, format='[Media] %(message)s')
logger = logging.getLogger(__name__)

# Safe Pycaw Import for Volume
try:
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False
    logger.warning("pycaw not installed. Volume control limited.")

DEFAULT_PLATFORM = "bitchord"


class MediaSessionManager:
    """Hybrid Media Session Tracker: Uses PowerShell for SMTC (Lock Screen Data) then Window Titles."""

    def __init__(self):
        self._manager_class = None
        self._smtc_available = False
        self._init_smtc()

    def _init_smtc(self):
        # Try winsdk (Best for Python 3.10)
        try:
            from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
            self._manager_class = GlobalSystemMediaTransportControlsSessionManager
            self._smtc_available = True
            logger.info("✅ Windows SMTC API available (winsdk).")
            return
        except ImportError:
            pass

        # Fallback for Python 3.11+ if pywinrt is installed
        try:
            from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager
            self._manager_class = MediaManager
            self._smtc_available = True
            logger.info("✅ Windows SMTC API available (pywinrt).")
            return
        except ImportError:
            pass

        # Final Fallback: PowerShell Bridge (Works on all Python versions)
        self._smtc_available = True
        logger.info("✅ Using PowerShell SMTC Bridge for Real-Time Media Data.")

    def get_metadata(self):
        # --- METHOD 1: Native SMTC (if library exists) ---
        if self._manager_class:
            try:
                manager = self._manager_class.request_async().get_results()
                session = manager.get_current_session()
                if session:
                    props = session.try_get_media_properties_async().get_results()
                    title = props.title or ""
                    artist = props.artist or ""
                    if title and len(title) > 2:
                        return {
                            "title": title,
                            "artist": artist if artist else "Unknown Artist",
                            "album": props.album_title or "",
                            "thumbnail": self._get_thumbnail(session),
                            "source": "smtc"
                        }
            except Exception as e:
                logger.debug(f"Native SMTC failed: {e}")

        # --- METHOD 2: PowerShell SMTC Bridge (The Fix for BitChord + Progress) ---
        ps_data = self._get_via_powershell()
        if ps_data:
            return ps_data

        # --- METHOD 3: Advanced Window Title Fallback ---
        return self._get_from_window_title()

    def _get_via_powershell(self):
        """Fetches media info AND progress using PowerShell."""
        try:
            # This script gets Title, Artist, Duration, and Position
            ps_script = """
            Add-Type -AssemblyName System.Runtime.WindowsRuntime
            $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | ? { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
            Function Await($WinRtTask, $ResultType) {
                $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
                $netTask = $asTask.Invoke($null, @($WinRtTask))
                $netTask.Wait(-1) | Out-Null
                $netTask.Result
            }
            [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType = WindowsRuntime] | Out-Null
            $manager = Await ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
            $session = $manager.GetCurrentSession()
            if ($session) {
                $props = Await ($session.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
                $timeline = $session.GetTimelineProperties()

                $info = @{
                    Title = $props.Title
                    Artist = $props.Artist
                    Album = $props.AlbumTitle
                    # Convert TimeSpan to Seconds
                    Duration = [math]::Round($timeline.EndTime.TotalSeconds, 0)
                    Position = [math]::Round($timeline.Position.TotalSeconds, 0)
                    Status = $timeline.PlaybackStatus
                }
                ConvertTo-Json $info
            } else {
                ConvertTo-Json @{Title=""; Artist=""}
            }
            """
            result = subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True, text=True, timeout=5
            )

            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout.strip())
                title = data.get("Title", "")

                if title and len(title) > 2:
                    duration = int(data.get("Duration", 0))
                    position = int(data.get("Position", 0))

                    # Calculate Percent
                    percent = 0
                    if duration > 0:
                        percent = min(100, int((position / duration) * 100))

                    logger.debug(f"PS-SMTC: {title} | {position}s/{duration}s")

                    return {
                        "title": title.strip(),
                        "artist": data.get("Artist", "Unknown Artist").strip(),
                        "album": data.get("Album", "").strip(),
                        "thumbnail": None,
                        "source": "smtc_ps",
                        "progress": {
                            "position": position,
                            "duration": duration,
                            "percent": percent,
                            "is_playing": data.get("Status") == 4  # 4 is Playing
                        }
                    }
        except Exception as e:
            logger.debug(f"PowerShell SMTC failed: {e}")

        return None

    def _get_thumbnail(self, session):
        try:
            props = session.try_get_media_properties_async().get_results()
            thumb = props.thumbnail
            if thumb:
                stream = thumb.open_read_async().get_results()
                size = stream.size
                if size > 0:
                    temp_path = os.path.join(tempfile.gettempdir(), "hex_album_art.jpg")
                    with open(temp_path, "wb") as f:
                        buffer_size = 8192
                        while True:
                            buf = stream.read_async(buffer_size).get_results()
                            if not buf or len(buf) == 0:
                                break
                            f.write(bytes(buf))
                    return temp_path
        except Exception:
            pass
        return None

    def _get_from_window_title(self):
        """Ultra-Advanced Window Title Parser with Regex and Noise Filtering."""
        try:
            found_titles = []
            media_keywords = ["bitchord", "bit chord", "youtube music", "spotify", "vlc", "edge", "chrome"]

            def enum_callback(hwnd, results):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title and len(title) > 5:
                        title_lower = title.lower()
                        if any(kw in title_lower for kw in media_keywords):
                            ignore_terms = ["new tab", "google search", "start page", "home", "dashboard"]
                            if not any(term in title_lower for term in ignore_terms):
                                results.append(title)
                return True

            win32gui.EnumWindows(enum_callback, found_titles)

            if found_titles:
                raw = found_titles[0]

                # 1. Aggressive Cleaning of Platform Names
                platforms = ["bitchord", "spotify", "youtube", "vlc", "edge", "chrome", "opera", "firefox"]
                clean_raw = raw
                for p in platforms:
                    clean_raw = re.sub(rf'\s*[-|•]\s*{p}', '', clean_raw, flags=re.IGNORECASE)
                    clean_raw = re.sub(rf'{p}\s*[-|•]', '', clean_raw, flags=re.IGNORECASE)

                if clean_raw.strip().lower() in platforms or len(clean_raw.strip()) < 3:
                    return None

                # 2. Smart Splitting Logic
                parts = []
                if "|" in clean_raw:
                    parts = [p.strip() for p in clean_raw.split("|") if p.strip()]
                elif "•" in clean_raw:
                    parts = [p.strip() for p in clean_raw.split("•") if p.strip()]
                elif "~" in clean_raw:
                    parts = [p.strip() for p in clean_raw.split("~") if p.strip()]
                elif " - " in clean_raw:
                    parts = [p.strip() for p in clean_raw.split(" - ") if p.strip()]
                elif " – " in clean_raw:
                    parts = [p.strip() for p in clean_raw.split(" – ") if p.strip()]

                song = ""
                artist = ""

                if len(parts) >= 2:
                    song = parts[0]
                    artist = parts[1]
                    if "more pages" in song.lower() or "tab" in song.lower():
                        song = parts[0].split(" ")[0]
                elif len(parts) == 1:
                    song = parts[0]
                    artist = "Unknown Artist"
                else:
                    song = clean_raw
                    artist = ""

                for p in platforms:
                    song = re.sub(rf'\b{p}\b', '', song, flags=re.IGNORECASE).strip()
                    artist = re.sub(rf'\b{p}\b', '', artist, flags=re.IGNORECASE).strip()

                song = song.strip("-|•~ ()[]")
                artist = artist.strip("-|•~ ()[]")

                # Filter out common tab names if no artist is found
                common_tab_names = ["qwen", "resumly", "github", "stackoverflow"]
                if song.lower() in common_tab_names and len(parts) < 2:
                    return None

                if song and len(song) > 2:
                    return {
                        "title": song,
                        "artist": artist if artist else "Unknown Artist",
                        "album": "",
                        "thumbnail": None,
                        "source": "window"
                    }

        except Exception as e:
            logger.debug(f"Window title error: {e}")

        return None

    def get_playback_info(self):
        """Returns progress info. If using PS-SMTC, it's already in metadata."""
        meta = self.get_metadata()
        if meta and meta.get("source") == "smtc_ps":
            return meta.get("progress", {"is_playing": False})

        if meta and meta.get("title"):
            return {"position": 0, "duration": 0, "percent": 0, "is_playing": True}

        return {"position": 0, "duration": 0, "percent": 0, "is_playing": False}

    def send_command(self, command):
        try:
            import pyautogui
            key_map = {
                "play_pause": "playpause",
                "next": "nexttrack",
                "previous": "prevtrack",
                "stop": "stop"
            }
            if command in key_map:
                pyautogui.press(key_map[command])
                return True
        except:
            pass
        return False


class HexMediaController:
    """Next Level Multimedia Controller. BitChord Default. Volume Fixed. Direct Controls."""
    _instance = None
    MEDIA_CACHE_FILE = os.path.join(os.getcwd(), "hex_media_cache.json")
    CONTEXT_FILE = os.path.join(os.getcwd(), "media_context.json")

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # ==================== VOLUME CONTROL (FIXED) ====================
        self.volume_interface = None
        self.can_control_volume = False

        if PYCAW_AVAILABLE:
            try:
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                vol = interface.QueryInterface(IAudioEndpointVolume)
                test_vol = vol.GetMasterVolumeLevelScalar(None)
                if 0.0 <= test_vol <= 1.0:
                    self.volume_interface = vol
                    self.can_control_volume = True
                    logger.info(f"Volume control OK (Master: {int(test_vol * 100)}%)")
                else:
                    raise ValueError("Invalid volume value")
            except Exception as e1:
                logger.debug(f"Master volume failed: {e1}")
                try:
                    all_sessions = AudioUtilities.GetAllSessions()
                    for sess in all_sessions:
                        if sess.Process and sess.Process.name().lower() == "hex.exe":
                            sv = sess.SimpleAudioVolume
                            test = sv.GetMasterVolume()
                            if 0.0 <= test <= 1.0:
                                self.volume_interface = sv
                                self.can_control_volume = True
                                logger.info("Volume control via Session fallback OK")
                                break
                except Exception as e2:
                    logger.debug(f"Session volume failed: {e2}")

            if not self.can_control_volume:
                logger.warning("Pycaw failed. Using PyAutoGUI fallback for volume.")

        # ==================== MEDIA SESSION MANAGER ====================
        self.session_manager = MediaSessionManager()

        # ==================== PROGRESS TRACKING ====================
        self._progress_thread = None
        self._tracking = False
        self.current_progress = {"position": 0, "duration": 0, "percent": 0, "is_playing": False}
        self.current_metadata = {"title": "", "artist": "", "album": "", "thumbnail": None}
        self._progress_callback = None

        # ==================== LOCAL MEDIA ====================
        self.local_paths = [
            os.path.expanduser("~/Music"),
            os.path.expanduser("~/Downloads"),
            os.path.expanduser("~/Desktop"),
        ]

        self.local_files_cache = self._load_media_cache()
        if not self.local_files_cache:
            logger.info("Media cache miss. Scanning local storage...")
            self._scan_local_media()
            self._save_media_cache()
        else:
            logger.info(f"Loaded {len(self.local_files_cache)} media files from cache.")

        self.user_context = self._load_context()

        self._initialized = True
        logger.info(
            f"Media Controller Ready | Vol: {'OK' if self.can_control_volume else 'OFF'} | "
            f"Local: {len(self.local_files_cache)} | Pref: {self.user_context.get('last_platform', DEFAULT_PLATFORM)}"
        )

    # ==================== PROGRESS TRACKING ====================

    def set_progress_callback(self, callback):
        self._progress_callback = callback

    def start_tracking(self):
        if self._tracking:
            return
        self._tracking = True
        self._progress_thread = threading.Thread(target=self._track_loop, daemon=True)
        self._progress_thread.start()
        logger.info("Progress tracking started")

    def stop_tracking(self):
        self._tracking = False
        if self._progress_thread:
            self._progress_thread.join(timeout=3)
        logger.info("Progress tracking stopped")

    def _track_loop(self):
        last_title = ""
        last_duration = 0
        last_position = 0
        last_sync_time = 0

        while self._tracking:
            try:
                current_time = time.time()
                meta = self.session_manager.get_metadata()

                if meta and meta.get("title"):
                    title = meta.get("title", "")

                    # 1. CHECK IF SONG CHANGED
                    if title != last_title:
                        last_title = title
                        self.current_metadata = meta
                        logger.info(f"Now Playing: {title} by {meta.get('artist', 'Unknown')}")

                        # Force Sync: Get real duration and position
                        info = self.session_manager.get_playback_info()

                        # Safe extraction of duration/position
                        try:
                            dur = float(info.get("duration", 0))
                            pos = float(info.get("position", 0))

                            if dur > 0:
                                last_duration = int(dur)
                                last_position = int(pos)
                                last_sync_time = current_time
                                self.current_progress = info

                                if self._progress_callback:
                                    self._progress_callback(self.current_metadata, self.current_progress)
                        except (ValueError, TypeError):
                            logger.debug("Invalid duration/position received from SMTC")
                        continue

                    # 2. REAL-TIME SIMULATION (The Smart Move)
                    if last_duration > 0:
                        time_passed = current_time - last_sync_time
                        estimated_position = last_position + time_passed

                        # Safety Check: Don't exceed duration
                        if estimated_position >= last_duration:
                            estimated_position = last_duration

                        percent = min(100, int((estimated_position / last_duration) * 100))

                        self.current_progress = {
                            "position": estimated_position,
                            "duration": last_duration,
                            "percent": percent,
                            "is_playing": True
                        }

                        if self._progress_callback:
                            try:
                                self._progress_callback(self.current_metadata, self.current_progress)
                            except Exception:
                                pass

                    # 3. BACKGROUND SYNC (Every 10 seconds)
                    if (current_time - last_sync_time) > 10:
                        info = self.session_manager.get_playback_info()
                        try:
                            dur = float(info.get("duration", 0))
                            pos = float(info.get("position", 0))

                            if dur > 0:
                                last_position = int(pos)
                                last_duration = int(dur)
                                last_sync_time = current_time
                                self.current_progress = info

                                if self._progress_callback:
                                    self._progress_callback(self.current_metadata, self.current_progress)
                        except (ValueError, TypeError):
                            pass

                else:
                    # NO MEDIA FOUND
                    if last_title:
                        last_title = ""
                        last_duration = 0
                        self.current_metadata = {"title": "", "artist": "", "album": "", "thumbnail": None}
                        self.current_progress = {"is_playing": False, "percent": 0, "position": 0, "duration": 0}
                        if self._progress_callback:
                            self._progress_callback(self.current_metadata, self.current_progress)

            except Exception as e:
                logger.debug(f"Track loop error: {e}")

            time.sleep(1)

    def get_current_state(self):
        return {
            "metadata": self.current_metadata,
            "progress": self.current_progress,
        }

    @staticmethod
    def format_time(seconds):
        if not seconds or seconds <= 0:
            return "0:00"
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}:{secs:02d}"

    # ==================== CACHE MANAGEMENT ====================

    def _load_media_cache(self):
        if os.path.exists(self.MEDIA_CACHE_FILE):
            try:
                with open(self.MEDIA_CACHE_FILE, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_media_cache(self):
        try:
            with open(self.MEDIA_CACHE_FILE, "w", encoding="utf-8") as fh:
                json.dump(self.local_files_cache, fh)
        except OSError:
            pass

    def _load_context(self):
        if os.path.exists(self.CONTEXT_FILE):
            try:
                with open(self.CONTEXT_FILE, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            except (json.JSONDecodeError, OSError):
                pass
        return {"last_platform": DEFAULT_PLATFORM}

    def _save_context(self):
        try:
            with open(self.CONTEXT_FILE, "w", encoding="utf-8") as fh:
                json.dump(self.user_context, fh)
        except OSError:
            pass

    # ==================== LOCAL MEDIA SCAN ====================

    def _scan_local_media(self):
        extensions = ("*.mp3", "*.wav", "*.flac", "*.m4a", "*.ogg", "*.wma", "*.aac")
        for path in self.local_paths:
            if not os.path.exists(path):
                continue
            try:
                for ext in extensions:
                    pattern = os.path.join(path, "**", ext)
                    for file_path in glob.glob(pattern, recursive=True):
                        name = os.path.splitext(os.path.basename(file_path))[0].lower()
                        self.local_files_cache[name] = file_path
                        compact = name.replace(" ", "").replace("-", "")
                        if compact != name and compact not in self.local_files_cache:
                            self.local_files_cache[compact] = file_path
            except OSError:
                continue

    # ==================== QUERY CLEANING ====================

    @staticmethod
    def _clean_query(query):
        clean = query.lower()
        remove_words = [
            "on bitchord", "on spotify", "on youtube", "in bitchord",
            "in spotify", "in youtube", "on bit chord", "in bit chord",
            "play", "song", "music", "track",
        ]
        for word in remove_words:
            clean = clean.replace(word, "")
        return clean.strip()

    # ==================== VOLUME CONTROL ====================

    def set_volume(self, level):
        target = max(0, min(100, int(level)))

        if self.can_control_volume and self.volume_interface is not None:
            try:
                scalar = target / 100.0
                self.volume_interface.SetMasterVolumeLevelScalar(scalar, None)
                self._trigger_volume_osd()
                return f"Volume set to {target} percent, Sir."
            except (OSError, AttributeError):
                pass

        if PYCAW_AVAILABLE:
            try:
                sessions = AudioUtilities.GetAllSessions()
                for sess in sessions:
                    if sess.Process:
                        try:
                            sess.SimpleAudioVolume.SetMasterVolume(target / 100.0, None)
                            self._trigger_volume_osd()
                            return f"Volume set to {target} percent, Sir."
                        except Exception:
                            continue
            except Exception:
                pass

        try:
            import pyautogui
            current = self.get_volume()
            diff = target - current
            key = "volumeup" if diff > 0 else "volumedown"
            presses = abs(diff) // 2
            for _ in range(min(presses, 50)):
                pyautogui.press(key)
                time.sleep(0.02)
            return f"Volume adjusted to approximately {target} percent, Sir."
        except Exception:
            return "Volume control unavailable, Sir."

    def _trigger_volume_osd(self):
        try:
            import ctypes
            user32 = ctypes.windll.user32
            current = self.get_volume()
            if current < 100:
                user32.keybd_event(0xAF, 0, 0, 0)
                user32.keybd_event(0xAF, 0, 2, 0)
                time.sleep(0.05)
                user32.keybd_event(0xAE, 0, 0, 0)
                user32.keybd_event(0xAE, 0, 2, 0)
            else:
                user32.keybd_event(0xAE, 0, 0, 0)
                user32.keybd_event(0xAE, 0, 2, 0)
                time.sleep(0.05)
                user32.keybd_event(0xAF, 0, 0, 0)
                user32.keybd_event(0xAF, 0, 2, 0)
            time.sleep(0.1)
            if self.can_control_volume and self.volume_interface is not None:
                scalar = current / 100.0
                self.volume_interface.SetMasterVolumeLevelScalar(scalar, None)
        except Exception:
            pass

    def change_volume(self, amount):
        current = self.get_volume()
        new_level = max(0, min(100, current + amount))
        return self.set_volume(new_level)

    def get_volume(self):
        if self.can_control_volume and self.volume_interface is not None:
            try:
                return int(self.volume_interface.GetMasterVolumeLevelScalar(None) * 100)
            except (OSError, AttributeError):
                pass

        if PYCAW_AVAILABLE:
            try:
                sessions = AudioUtilities.GetAllSessions()
                for sess in sessions:
                    if sess.Process:
                        try:
                            return int(sess.SimpleAudioVolume.GetMasterVolume() * 100)
                        except Exception:
                            continue
            except Exception:
                pass

        return 50

    # ==================== SMART PLAY DECISION ====================

    def play_media(self, query, explicit_platform=None):
        if not query:
            return "Please specify a song name, Sir."

        clean_query = self._clean_query(query)

        # Priority 1: Local Files
        if clean_query in self.local_files_cache:
            path = self.local_files_cache[clean_query]
            try:
                os.startfile(path)
                self.start_tracking()
                return f"Playing {clean_query} from local storage, Sir."
            except OSError:
                pass

        compact_query = clean_query.replace(" ", "").replace("-", "")
        if compact_query in self.local_files_cache:
            path = self.local_files_cache[compact_query]
            try:
                os.startfile(path)
                self.start_tracking()
                return f"Playing {clean_query} from local storage, Sir."
            except OSError:
                pass

        # Priority 2: Determine Platform
        target = explicit_platform

        if target is None:
            lower_q = query.lower()
            if "youtube" in lower_q:
                target = "youtube"
            elif "bitchord" in lower_q or "bit chord" in lower_q:
                target = "bitchord"

        if target is None:
            pref = self.user_context.get("last_platform", DEFAULT_PLATFORM)
            if pref != "auto":
                target = pref

        if target is None:
            target = DEFAULT_PLATFORM

        self.user_context["last_platform"] = target
        self._save_context()

        if target == "bitchord":
            return self._play_bitchord(clean_query)
        return self._play_youtube(clean_query)

    def _play_bitchord(self, query):
        """Play music on BitChord using its native search interface."""
        try:
            import pyautogui

            if not self._is_bitchord_running():
                pyautogui.hotkey('win', 's')
                time.sleep(0.8)
                pyautogui.typewrite("bitchord", interval=0.03)
                time.sleep(1.2)
                pyautogui.press('enter')
                time.sleep(3.0)
                pyautogui.press('escape')

            self._focus_bitchord()
            time.sleep(0.5)

            pyautogui.hotkey('ctrl', 'f')
            time.sleep(0.3)

            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.1)
            pyautogui.typewrite(query, interval=0.03)
            time.sleep(0.8)

            pyautogui.press('enter')
            time.sleep(1.5)

            pyautogui.press('enter')
            time.sleep(0.5)

            self.start_tracking()
            return f"Playing {query} on BitChord, Sir."

        except ImportError:
            return "pyautogui not installed. Run: pip install pyautogui, Sir."
        except Exception as e:
            logger.error(f"BitChord playback failed: {e}")
            try:
                subprocess.Popen(
                    ["cmd", "/c", "start", "", "bitchord"],
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                self.start_tracking()
                return f"Opened BitChord. Search '{query}' manually, Sir."
            except Exception:
                return f"Could not open BitChord, Sir."

    def _focus_bitchord(self):
        """Bring BitChord window to foreground."""
        try:
            def enum_handler(hwnd, results):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd).lower()
                    if "bitchord" in title or "bit chord" in title:
                        results.append(hwnd)
                return True

            windows = []
            win32gui.EnumWindows(enum_handler, windows)

            if windows:
                hwnd = windows[0]
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
                return True
        except Exception:
            pass

        try:
            import pyautogui
            pyautogui.hotkey('alt', 'tab')
            time.sleep(0.3)
        except Exception:
            pass
        return False

    @staticmethod
    def _is_bitchord_running():
        """Check if BitChord process is running."""
        try:
            result = subprocess.run(
                ["tasklist", "/NH"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            stdout_lower = result.stdout.lower()
            return "bitchord" in stdout_lower or "bit chord" in stdout_lower or "bitchord.exe" in stdout_lower
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _play_youtube(self, query):
        encoded = urllib.parse.quote(query)
        url = f"https://www.youtube.com/results?search_query={encoded}"
        try:
            webbrowser.open(url)
            self.start_tracking()
            return f"Searching {query} on YouTube, Sir."
        except OSError:
            return "Could not open YouTube, Sir."

    # ==================== PLAYBACK CONTROLS ====================

    def control_playback(self, action):
        key_map = {
            "play_pause": "play_pause",
            "next": "next",
            "previous": "previous",
            "stop": "stop",
        }
        cmd = key_map.get(action)
        if not cmd:
            return "Unknown playback command, Sir."

        if self.session_manager.send_command(cmd):
            labels = {
                "play_pause": "Play/Pause toggled",
                "next": "Skipped to next track",
                "previous": "Returned to previous track",
                "stop": "Playback stopped",
            }
            return f"{labels.get(cmd, cmd)}, Sir."

        try:
            import pyautogui
            fallback_keys = {
                "play_pause": "playpause",
                "next": "nexttrack",
                "previous": "prevtrack",
                "stop": "stop",
            }
            pyautogui.press(fallback_keys.get(cmd, ""))
            return f"{action.replace('_', ' ').title()} executed, Sir."
        except (ImportError, OSError):
            return "Playback control failed. No media session active, Sir."

    # ==================== SONG SUMMARY ====================

    def get_song_summary(self, song_name):
        if not song_name:
            return "Which song, Sir?"
        try:
            from search_engine import search_engine
            result = search_engine.search(f"{song_name} song meaning artist album")
            return result
        except Exception as e:
            logger.debug(f"Song summary error: {e}")
            return f"Could not fetch details for {song_name}, Sir."


hex_media = HexMediaController()