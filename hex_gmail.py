import logging
import os
import re
import base64
import time
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

logging.basicConfig(level=logging.INFO, format='[Gmail] %(message)s')
logger = logging.getLogger(__name__)

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False
    logger.warning("Google API not installed. Run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
TOKEN_FILE = os.path.join(os.getcwd(), "gmail_token.json")
CREDS_FILE = os.path.join(os.getcwd(), "credentials.json")


class HexGmail:
    """
    Deep Gmail Integration.
    Read, Send, Reply, Search, Unread Count, Auto-Monitor.
    Voice-controlled email management.
    """

    def __init__(self):
        self._service = None
        self._authenticated = False
        self._monitor_thread = None
        self._monitoring = False
        self._last_check_ids = set()
        self._speak_callback = None
        if GMAIL_AVAILABLE:
            self._authenticate()
        logger.info(f"Gmail Engine Ready | Auth: {'OK' if self._authenticated else 'PENDING'}")

    # ==================== AUTH ====================

    def _authenticate(self):
        creds = None
        try:
            if os.path.exists(TOKEN_FILE):
                creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not os.path.exists(CREDS_FILE):
                        logger.warning("credentials.json missing. Download from Google Cloud Console.")
                        return
                    flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
                    creds = flow.run_local_server(port=0)
                with open(TOKEN_FILE, "w") as token:
                    token.write(creds.to_json())
            self._service = build("gmail", "v1", credentials=creds)
            self._authenticated = True
            logger.info("Gmail authenticated successfully")
        except Exception as e:
            logger.error(f"Gmail auth failed: {e}")
            self._authenticated = False

    def _check_auth(self):
        if not self._authenticated:
            return "Gmail not authenticated, Sir. Place credentials.json in project folder and restart."
        return None

    # ==================== READ INBOX ====================

    def get_inbox(self, max_results=5, unread_only=False):
        err = self._check_auth()
        if err:
            return err
        try:
            label_ids = ["INBOX", "UNREAD"] if unread_only else ["INBOX"]
            results = self._service.users().messages().list(
                userId="me", labelIds=label_ids, maxResults=max_results
            ).execute()
            messages = results.get("messages", [])
            if not messages:
                return "No emails found, Sir." if not unread_only else "No unread emails, Sir."

            emails = []
            for msg in messages[:max_results]:
                data = self._service.users().messages().get(userId="me", id=msg["id"]).execute()
                headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
                subject = headers.get("Subject", "(No Subject)")
                sender = headers.get("From", "Unknown")
                date = headers.get("Date", "")
                snippet = data.get("snippet", "")
                emails.append({
                    "id": msg["id"],
                    "from": sender,
                    "subject": subject,
                    "date": date,
                    "snippet": snippet,
                })

            response_parts = []
            for i, e in enumerate(emails, 1):
                response_parts.append(f"Email {i}: From {e['from']}, Subject: {e['subject']}. {e['snippet'][:120]}")

            return f"{len(emails)} emails:\n" + "\n\n".join(response_parts)
        except Exception as e:
            return f"Inbox error: {e}, Sir."

    # ==================== READ SPECIFIC EMAIL ====================

    def read_email(self, index=1, unread_only=False):
        """Read full body of email by position (1 = newest)."""
        err = self._check_auth()
        if err:
            return err
        try:
            label_ids = ["INBOX", "UNREAD"] if unread_only else ["INBOX"]
            results = self._service.users().messages().list(
                userId="me", labelIds=label_ids, maxResults=index
            ).execute()
            messages = results.get("messages", [])
            if len(messages) < index:
                return f"Only {len(messages)} emails available, Sir."

            msg_id = messages[index - 1]["id"]
            data = self._service.users().messages().get(userId="me", id=msg_id, format="full").execute()
            headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}

            # Extract body
            body = ""
            payload = data.get("payload", {})
            if "body" in payload and payload["body"].get("data"):
                body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
            elif "parts" in payload:
                for part in payload["parts"]:
                    mime = part.get("mimeType", "")
                    if mime == "text/plain" and part.get("body", {}).get("data"):
                        body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                        break

            subject = headers.get("Subject", "(No Subject)")
            sender = headers.get("From", "Unknown")

            # Truncate for TTS
            if len(body) > 800:
                body = body[:800] + "... Email truncated for speech, Sir."

            return f"From: {sender}\nSubject: {subject}\n\n{body}"
        except Exception as e:
            return f"Read email error: {e}, Sir."

    # ==================== SEND EMAIL ====================

    def send_email(self, to_addr, subject, body, attachment_path=None):
        err = self._check_auth()
        if err:
            return err
        try:
            msg = MIMEMultipart()
            msg["to"] = to_addr
            msg["subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            if attachment_path and os.path.exists(attachment_path):
                with open(attachment_path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(attachment_path)}")
                    msg.attach(part)

            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            self._service.users().messages().send(userId="me", body={"raw": raw}).execute()
            att_msg = f" with attachment {os.path.basename(attachment_path)}" if attachment_path else ""
            logger.info(f"Email sent to {to_addr}: {subject}")
            return f"Email sent to {to_addr}: {subject}{att_msg}, Sir."
        except Exception as e:
            return f"Send failed: {e}, Sir."

    # ==================== REPLY TO EMAIL ====================

    def reply_to_email(self, reply_body, index=1, unread_only=False):
        """Reply to an existing email thread."""
        err = self._check_auth()
        if err:
            return err
        try:
            label_ids = ["INBOX", "UNREAD"] if unread_only else ["INBOX"]
            results = self._service.users().messages().list(
                userId="me", labelIds=label_ids, maxResults=index
            ).execute()
            messages = results.get("messages", [])
            if len(messages) < index:
                return f"Only {len(messages)} emails available, Sir."

            msg_id = messages[index - 1]["id"]
            original = self._service.users().messages().get(userId="me", id=msg_id).execute()
            headers = {h["name"]: h["value"] for h in original.get("payload", {}).get("headers", [])}

            thread_id = original.get("threadId", msg_id)
            original_subject = headers.get("Subject", "")
            reply_subject = f"Re: {original_subject}" if not original_subject.lower().startswith("re:") else original_subject
            original_from = headers.get("From", "")
            message_id = headers.get("Message-ID", "")

            msg = MIMEText(reply_body)
            msg["to"] = original_from
            msg["subject"] = reply_subject
            msg["In-Reply-To"] = message_id
            msg["References"] = message_id

            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            self._service.users().messages().send(
                userId="me", body={"raw": raw, "threadId": thread_id}
            ).execute()

            logger.info(f"Replied to: {original_subject}")
            return f"Reply sent to {original_from}: {reply_subject}, Sir."
        except Exception as e:
            return f"Reply failed: {e}, Sir."

    # ==================== SEARCH ====================

    def search_emails(self, query, max_results=5):
        err = self._check_auth()
        if err:
            return err
        try:
            results = self._service.users().messages().list(
                userId="me", q=query, maxResults=max_results
            ).execute()
            messages = results.get("messages", [])
            if not messages:
                return f"No emails found for '{query}', Sir."

            emails = []
            for msg in messages[:max_results]:
                data = self._service.users().messages().get(userId="me", id=msg["id"]).execute()
                headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
                emails.append(f"From: {headers.get('From', '?')} | Subject: {headers.get('Subject', '?')}")

            return f"Found {len(emails)} emails:\n" + "\n".join(emails)
        except Exception as e:
            return f"Search failed: {e}, Sir."

    # ==================== UNREAD COUNT ====================

    def unread_count(self):
        err = self._check_auth()
        if err:
            return err
        try:
            results = self._service.users().labels().get(userId="me", id="UNREAD").execute()
            count = results.get("messagesUnread", 0)
            return f"You have {count} unread emails, Sir."
        except Exception as e:
            return f"Unread count failed: {e}, Sir."

    # ==================== AUTO MONITOR ====================

    def set_speak_callback(self, callback):
        self._speak_callback = callback

    def start_monitor(self, interval=300):
        """Background thread checks for new emails every N seconds."""
        if self._monitoring or not self._authenticated:
            return
        self._monitoring = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, args=(interval,), daemon=True)
        self._monitor_thread.start()
        logger.info(f"Gmail monitor started (every {interval}s)")

    def stop_monitor(self):
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("Gmail monitor stopped")

    def _monitor_loop(self, interval):
        while self._monitoring:
            try:
                results = self._service.users().messages().list(
                    userId="me", labelIds=["INBOX", "UNREAD"], maxResults=5
                ).execute()
                messages = results.get("messages", [])
                current_ids = {m["id"] for m in messages}
                new_ids = current_ids - self._last_check_ids

                if new_ids and self._last_check_ids:
                    for nid in list(new_ids)[:3]:
                        data = self._service.users().messages().get(userId="me", id=nid).execute()
                        headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
                        sender = headers.get("From", "Unknown")
                        subject = headers.get("Subject", "(No Subject)")
                        if self._speak_callback:
                            self._speak_callback(f"New email from {sender}: {subject}, Sir.")

                self._last_check_ids = current_ids
            except Exception as e:
                logger.debug(f"Monitor error: {e}")
            time.sleep(interval)

    # ==================== VOICE COMMAND PARSER ====================

    @staticmethod
    def parse_command(text):
        t = text.lower().strip()
        if not any(w in t for w in ["email", "gmail", "mail", "inbox", "unread"]):
            return None

        if any(w in t for w in ["send email", "mail bhejo", "send mail"]):
            return ("send", t)
        if any(w in t for w in ["reply", "jawab", "reply karo"]):
            return ("reply", t)
        if any(w in t for w in ["read email", "email padho", "read latest", "read newest"]):
            return ("read", t)
        if any(w in t for w in ["check inbox", "inbox check", "inbox dikhao", "new emails"]):
            return ("inbox", t)
        if any(w in t for w in ["unread", "kitne mail", "how many", "count"]):
            return ("unread", t)
        if any(w in t for w in ["search email", "find email", "dhundho email"]):
            return ("search", t)
        return ("inbox", t)

    def handle(self, voice_text):
        parsed = self.parse_command(voice_text)
        if not parsed:
            return None
        action, data = parsed

        if action == "inbox":
            return self.get_inbox(max_results=3)
        elif action == "unread":
            return self.unread_count()
        elif action == "read":
            return self.read_email(index=1)
        elif action == "search":
            query = data
            for w in ["search email", "find email", "dhundho email", "search", "for", "about"]:
                query = query.replace(w, "")
            query = query.strip()
            return self.search_emails(query) if query else "Search what in emails, Sir?"
        elif action == "reply":
            reply_text = data
            for w in ["reply", "jawab", "reply karo", "to last email", "to latest"]:
                reply_text = reply_text.replace(w, "")
            reply_text = reply_text.strip()
            if reply_text:
                return self.reply_to_email(reply_text)
            return "What should I reply, Sir?"
        elif action == "send":
            return self._parse_send_command(data)
        return None

    def _parse_send_command(self, text):
        """Parse: send email to X subject Y body Z"""
        to_addr = ""
        subject = ""
        body = ""

        # Extract email address
        email_match = re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', text)
        if email_match:
            to_addr = email_match[0]

        # Extract subject
        if "subject" in text.lower():
            parts = text.lower().split("subject")
            if len(parts) >= 2:
                sub_part = parts[1]
                if "body" in sub_part.lower():
                    subject = sub_part.split("body")[0].strip()
                    body = sub_part.split("body", 1)[1].strip()
                else:
                    subject = sub_part.strip()

        if not to_addr:
            return "Which email address, Sir? Say: send email to address@gmail.com subject hello"
        if not subject:
            subject = "Message from HEX"
        if not body:
            body = "Sent via HEX voice command."

        return self.send_email(to_addr, subject, body)


hex_gmail = HexGmail()