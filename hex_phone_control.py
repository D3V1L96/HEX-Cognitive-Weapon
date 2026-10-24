import requests
import logging
import time
import threading

logging.basicConfig(level=logging.INFO, format='[Phone] %(message)s')
logger = logging.getLogger(__name__)


class HexPhoneControl:
    """
    Remote HEX Control via Phone using Pushbullet.
    Send commands FROM phone TO HEX.
    Receive notifications FROM HEX ON phone.
    Two-way communication bridge.
    """

    PUSHBULLET_API_KEY = ""  # ← Paste your key here
    PUSHBULLET_URL = "https://api.pushbullet.com/v2"

    def __init__(self):
        self.session = requests.Session()
        self._has_key = bool(self.PUSHBULLET_API_KEY)
        if self._has_key:
            self.session.headers.update({"Access-Token": self.PUSHBULLET_API_KEY})
        self._listener_thread = None
        self._listening = False
        self._command_callback = None
        self._speak_callback = None
        self._last_modified = 0
        logger.info(f"Phone Control Ready | Key: {'SET' if self._has_key else 'MISSING'}")

    # ==================== OUTGOING: HEX → PHONE ====================

    def notify(self, title, body):
        """Send notification from HEX to phone."""
        if not self._has_key:
            return "Pushbullet key not set, Sir."
        try:
            payload = {"type": "note", "title": title, "body": body}
            resp = self.session.post(f"{self.PUSHBULLET_URL}/pushes", json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info(f"Notified phone: {title}")
                return f"Sent to phone: {title}, Sir."
            return f"Notification failed: HTTP {resp.status_code}, Sir."
        except Exception as e:
            return f"Notification failed: {e}, Sir."

    def find_phone(self):
        """Ring phone remotely."""
        return self.notify("🔍 HEX Find Phone", "Your phone is ringing! Locate it now.")

    def send_clipboard(self, text):
        """Push text to phone."""
        return self.notify("📋 HEX Clipboard", text)

    # ==================== INCOMING: PHONE → HEX ====================

    def set_command_callback(self, callback):
        """Set function to execute when command received from phone."""
        self._command_callback = callback

    def set_speak_callback(self, callback):
        self._speak_callback = callback

    def start_listener(self, poll_interval=10):
        """Start listening for commands from phone via Pushbullet."""
        if self._listening or not self._has_key:
            return
        self._listening = True
        # Get initial timestamp to avoid old pushes
        try:
            resp = self.session.get(f"{self.PUSHBULLET_URL}/pushes", params={"limit": 1}, timeout=10)
            if resp.status_code == 200:
                pushes = resp.json().get("pushes", [])
                if pushes:
                    self._last_modified = pushes[0].get("modified", 0)
        except Exception:
            pass

        self._listener_thread = threading.Thread(target=self._listen_loop, args=(poll_interval,), daemon=True)
        self._listener_thread.start()
        logger.info(f"Phone listener started (polling every {poll_interval}s)")

    def stop_listener(self):
        self._listening = False
        if self._listener_thread:
            self._listener_thread.join(timeout=5)
        logger.info("Phone listener stopped")

    def _listen_loop(self, interval):
        """Poll Pushbullet for new pushes with strict deduplication."""
        import os, json

        # Load processed IDs from persistent file (survives restarts)
        dedup_file = os.path.join(os.getcwd(), "hex_phone_dedup.json")
        try:
            with open(dedup_file, "r") as f:
                _processed_ids = set(json.load(f))
        except:
            _processed_ids = set()

        while self._listening:
            try:
                resp = self.session.get(
                    f"{self.PUSHBULLET_URL}/pushes",
                    params={"modified_after": self._last_modified, "limit": 10},
                    timeout=10
                )
                if resp.status_code != 200:
                    continue

                pushes = resp.json().get("pushes", [])
                new_commands_processed = False

                for push in reversed(pushes):
                    push_id = push.get("iden", "")
                    created = push.get("created", 0)

                    # Skip if already processed OR older than 60 seconds (stale sync)
                    current_time = time.time()
                    if push_id in _processed_ids or (current_time - created > 60):
                        continue

                    # Only process notes sent TO us
                    if push.get("direction") == "outgoing" or push.get("type") != "note":
                        _processed_ids.add(push_id)
                        continue

                    body = push.get("body", "").strip()
                    title = push.get("title", "").strip()
                    command = body if body else title

                    if command and self._command_callback:
                        logger.info(f"New phone command: {command}")
                        self._command_callback(command)
                        new_commands_processed = True

                    _processed_ids.add(push_id)
                    self._last_modified = max(self._last_modified, push.get("modified", 0))

                # Save dedup state to disk after processing
                if new_commands_processed or len(_processed_ids) > 50:
                    # Keep only last 100 IDs to prevent file bloat
                    recent_ids = list(_processed_ids)[-100:]
                    with open(dedup_file, "w") as f:
                        json.dump(recent_ids, f)
                    _processed_ids = set(recent_ids)

            except Exception as e:
                logger.debug(f"Listener error: {e}")

            time.sleep(interval)
    # ==================== VOICE COMMANDS ====================

    @staticmethod
    def parse_command(text):
        t = text.lower().strip()
        if any(w in t for w in ["notify phone", "send to phone", "phone pe bhejo", "send notification"]):
            msg = t
            for w in ["notify phone", "send to phone", "phone pe bhejo", "send notification"]:
                msg = msg.replace(w, "")
            return ("notify", msg.strip())
        if any(w in t for w in ["find phone", "where is my phone", "phone kahan hai"]):
            return ("find", "")
        if any(w in t for w in ["start phone listener", "phone control on", "remote on"]):
            return ("listen_on", "")
        if any(w in t for w in ["stop phone listener", "phone control off", "remote off"]):
            return ("listen_off", "")
        return None

    def handle(self, voice_text):
        parsed = self.parse_command(voice_text)
        if not parsed:
            return None
        action, data = parsed
        if action == "notify":
            return self.notify("HEX", data if data else "Alert from HEX")
        elif action == "find":
            return self.find_phone()
        elif action == "listen_on":
            self.start_listener()
            return "Phone remote control activated. Send commands from Pushbullet app, Sir."
        elif action == "listen_off":
            self.stop_listener()
            return "Phone remote control deactivated, Sir."
        return None


hex_phone = HexPhoneControl()