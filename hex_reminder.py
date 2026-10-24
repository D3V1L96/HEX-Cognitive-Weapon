import os
import json
import time
import logging
import threading
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='[Reminder] %(message)s')
logger = logging.getLogger(__name__)


class HexReminder:
    """
    Smart Reminder & Time Awareness Module.
    Features: Exact-time reminders, Persistent storage, Contextual greetings, Auto-scheduler.
    """
    _instance = None
    REMINDERS_FILE = os.path.join(os.getcwd(), "hex_reminders.json")

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.reminders = self._load_reminders()
        self.scheduler_thread = None
        self.running = False
        self.speak_callback = None  # Will be set by main app

        self._initialized = True
        logger.info(f"Hex Reminder Ready. Active reminders: {len(self.reminders)}")

    def _load_reminders(self):
        if os.path.exists(self.REMINDERS_FILE):
            try:
                with open(self.REMINDERS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return []

    def _save_reminders(self):
        try:
            with open(self.REMINDERS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.reminders, f, indent=4)
        except OSError as e:
            logger.error(f"Save failed: {e}")

    def set_speak_callback(self, callback):
        """Set the speak function from main app."""
        self.speak_callback = callback

    # ==================== TIME AWARENESS ====================

    def get_current_time(self):
        """Get formatted current time."""
        now = datetime.now()
        return now.strftime("%I:%M %p")  # 02:30 PM format

    def get_current_date(self):
        """Get formatted current date."""
        now = datetime.now()
        return now.strftime("%A, %B %d, %Y")  # Monday, January 15, 2024

    def get_greeting(self):
        """Context-aware greeting based on time of day."""
        hour = datetime.now().hour

        if 5 <= hour < 12:
            period = "morning"
            greeting = "Good morning"
        elif 12 <= hour < 17:
            period = "afternoon"
            greeting = "Good afternoon"
        elif 17 <= hour < 21:
            period = "evening"
            greeting = "Good evening"
        else:
            period = "night"
            greeting = "Good evening"  # Polite even at night

        return greeting, period

    def get_time_response(self):
        """Natural language time response."""
        now = datetime.now()
        time_str = now.strftime("%I:%M %p")
        date_str = now.strftime("%A, %B %d")
        greeting, _ = self.get_greeting()

        return f"{greeting}, Sir. It's currently {time_str} on {date_str}."

    # ==================== REMINDER MANAGEMENT ====================

    def add_reminder(self, task, reminder_time, repeat=False):
        """
        Add a new reminder.

        Args:
            task: What to remind (string)
            reminder_time: When to remind (datetime object or "HH:MM" string)
            repeat: Daily repeat (bool)
        """
        # Parse time if string
        if isinstance(reminder_time, str):
            try:
                today = datetime.now().date()
                parsed_time = datetime.strptime(reminder_time, "%H:%M").time()
                reminder_dt = datetime.combine(today, parsed_time)

                # If time already passed today, schedule for tomorrow
                if reminder_dt <= datetime.now():
                    reminder_dt += timedelta(days=1)

            except ValueError:
                return f"Invalid time format '{reminder_time}'. Use HH:MM format, Sir."
        else:
            reminder_dt = reminder_time

        reminder_entry = {
            "id": int(time.time()),
            "task": task,
            "time": reminder_dt.isoformat(),
            "repeat": repeat,
            "active": True,
            "created": datetime.now().isoformat()
        }

        self.reminders.append(reminder_entry)
        self._save_reminders()

        time_str = reminder_dt.strftime("%I:%M %p")
        date_str = reminder_dt.strftime("%b %d")
        repeat_text = "daily" if repeat else f"on {date_str}"

        logger.info(f"Reminder added: '{task}' at {time_str} ({repeat_text})")
        return f"Reminder set, Sir. I'll remind you to '{task}' at {time_str} {repeat_text}."

    def remove_reminder(self, task_keyword=None, reminder_id=None):
        """Remove a reminder by keyword or ID."""
        original_count = len(self.reminders)

        if reminder_id:
            self.reminders = [r for r in self.reminders if r["id"] != reminder_id]
        elif task_keyword:
            keyword = task_keyword.lower()
            self.reminders = [r for r in self.reminders
                              if keyword not in r["task"].lower()]

        removed = original_count - len(self.reminders)
        self._save_reminders()

        if removed > 0:
            return f"Removed {removed} reminder(s), Sir."
        return "No matching reminder found, Sir."

    def list_reminders(self):
        """List all active reminders."""
        active = [r for r in self.reminders if r["active"]]

        if not active:
            return "You have no active reminders, Sir."

        lines = [f"You have {len(active)} active reminder(s), Sir:"]
        for i, r in enumerate(active, 1):
            dt = datetime.fromisoformat(r["time"])
            time_str = dt.strftime("%I:%M %p")
            date_str = dt.strftime("%b %d")
            repeat = " (Daily)" if r["repeat"] else ""
            lines.append(f"{i}. {r['task']} - {time_str} {date_str}{repeat}")

        return "\n".join(lines)

    def clear_all_reminders(self):
        """Clear all reminders."""
        count = len(self.reminders)
        self.reminders = []
        self._save_reminders()
        return f"Cleared all {count} reminders, Sir."

    # ==================== SCHEDULER ENGINE ====================

    def start_scheduler(self):
        """Start background scheduler thread."""
        if self.running:
            return

        self.running = True
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()
        logger.info("Reminder Scheduler Started")

    def stop_scheduler(self):
        """Stop background scheduler."""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        logger.info("Reminder Scheduler Stopped")

    def _scheduler_loop(self):
        """Background loop checking reminders every second."""
        while self.running:
            try:
                now = datetime.now()
                now_str = now.isoformat()

                for reminder in self.reminders:
                    if not reminder["active"]:
                        continue

                    reminder_time = datetime.fromisoformat(reminder["time"])

                    # Check if it's time (within 60 second window)
                    diff = abs((now - reminder_time).total_seconds())

                    if diff <= 60 and reminder.get("last_triggered", "") != now.strftime("%Y-%m-%d %H:%M"):
                        # Trigger reminder
                        task = reminder["task"]

                        if self.speak_callback:
                            self.speak_callback(f"Sir, this is your reminder: {task}")

                        logger.info(f"REMINDER TRIGGERED: {task}")

                        # Mark as triggered
                        reminder["last_triggered"] = now.strftime("%Y-%m-%d %H:%M")

                        # Handle repeat
                        if reminder["repeat"]:
                            # Schedule next occurrence (next day same time)
                            next_time = reminder_time + timedelta(days=1)
                            reminder["time"] = next_time.isoformat()
                            reminder["last_triggered"] = ""
                        else:
                            # One-time reminder: deactivate
                            reminder["active"] = False

                        self._save_reminders()

            except Exception as e:
                logger.error(f"Scheduler error: {e}")

            time.sleep(10)  # Check every 10 seconds

    # ==================== SMART PARSING ====================

    @staticmethod
    def parse_reminder_command(text):
        """
        Parse natural language reminder commands.
        Returns: (task, time_string, repeat) or None
        """
        text_lower = text.lower()

        # Extract time patterns
        import re

        # Pattern: "at HH:MM" or "at H AM/PM"
        time_match = re.search(r'at\s+(\d{1,2}:\d{2}\s*(?:am|pm)?)', text_lower)
        if not time_match:
            # Pattern: "in X minutes/hours"
            relative_match = re.search(r'in\s+(\d+)\s+(minute|hour|min|hr)', text_lower)
            if relative_match:
                value = int(relative_match.group(1))
                unit = relative_match.group(2)
                if "hour" in unit or "hr" in unit:
                    future = datetime.now() + timedelta(hours=value)
                else:
                    future = datetime.now() + timedelta(minutes=value)
                time_str = future.strftime("%H:%M")
            else:
                return None
        else:
            raw_time = time_match.group(1).strip()
            # Convert "2:30 pm" to "14:30"
            try:
                if "am" in raw_time or "pm" in raw_time:
                    parsed = datetime.strptime(raw_time, "%I:%M %p")
                else:
                    parsed = datetime.strptime(raw_time, "%H:%M")
                time_str = parsed.strftime("%H:%M")
            except ValueError:
                return None

        # Extract task (everything before "at" or "in")
        if " at " in text_lower:
            task_part = text_lower.split(" at ")[0]
        elif " in " in text_lower:
            task_part = text_lower.split(" in ")[0]
        else:
            task_part = text_lower

        # Clean task
        for prefix in ["remind me to", "remind me", "set reminder for", "remind", "add reminder"]:
            task_part = task_part.replace(prefix, "").strip()

        if not task_part:
            return None

        # Check for daily/repeat
        repeat = any(w in text_lower for w in ["daily", "every day", "everyday", "roz"])

        return (task_part, time_str, repeat)


# Global Singleton
hex_reminder = HexReminder()