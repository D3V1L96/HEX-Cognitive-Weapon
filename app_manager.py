import subprocess
import os
import logging
import time
import json

logging.basicConfig(level=logging.INFO, format='[AppMgr] %(message)s')
logger = logging.getLogger(__name__)


class HexAppManager:
    """Jarvis-Level App Manager. Win+S Search Only + Registry Memory."""
    _instance = None
    CACHE_FILE = os.path.join(os.getcwd(), "hex_app_registry.json")
    LAUNCH_MEMORY_FILE = os.path.join(os.getcwd(), "hex_launch_memory.json")
    CACHE_TTL = 86400

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.winget_available = self._check_winget()
        self.app_registry = {}
        self.launch_memory = {}

        self._load_launch_memory()

        if not self._load_cache():
            logger.info("Cache miss or expired. Building fresh registry...")
            self._build_dynamic_registry()
            self._save_cache()
        else:
            logger.info(f"Registry loaded from cache: {len(self.app_registry)} apps indexed.")

        self._initialized = True
        logger.info(
            f"Dynamic App Manager Ready | Winget: {'Yes' if self.winget_available else 'No'} | "
            f"Aliases: {len(self.app_registry)} | Memory: {len(self.launch_memory)}"
        )

    # ==================== LAUNCH MEMORY ====================

    def _load_launch_memory(self):
        try:
            if os.path.exists(self.LAUNCH_MEMORY_FILE):
                with open(self.LAUNCH_MEMORY_FILE, "r", encoding="utf-8") as f:
                    self.launch_memory = json.load(f)
                logger.info(f"Launch memory loaded: {len(self.launch_memory)} remembered apps")
        except Exception:
            self.launch_memory = {}

    def _save_launch_memory(self):
        try:
            with open(self.LAUNCH_MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.launch_memory, f)
        except Exception:
            pass

    def _remember_launch(self, user_query, app_name, method):
        key = user_query.lower().strip()
        self.launch_memory[key] = {
            "app_name": app_name,
            "method": method,
            "last_used": time.time(),
            "count": self.launch_memory.get(key, {}).get("count", 0) + 1
        }
        self._save_launch_memory()

    # ==================== CACHE ====================

    def _load_cache(self):
        try:
            if os.path.exists(self.CACHE_FILE):
                with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if time.time() - data.get("timestamp", 0) < self.CACHE_TTL:
                    self.app_registry = data.get("registry", {})
                    return True
        except Exception:
            pass
        return False

    def _save_cache(self):
        try:
            with open(self.CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({"timestamp": time.time(), "count": len(self.app_registry), "registry": self.app_registry}, f)
        except Exception:
            pass

    # ==================== UTILS ====================

    @staticmethod
    def _check_winget():
        try:
            r = subprocess.run(["winget", "--version"], capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
            return r.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _run_cmd(cmd, timeout=30):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
            return r.stdout.strip(), r.stderr.strip(), r.returncode
        except subprocess.TimeoutExpired:
            return "", "Timeout", -1
        except Exception as e:
            return "", str(e), -1

    @staticmethod
    def _generate_aliases(name):
        aliases = set()
        cleaned = name.lower().strip()
        aliases.add(cleaned)
        compact = cleaned.replace(" ", "").replace("-", "").replace("_", "")
        if compact != cleaned:
            aliases.add(compact)
        first = cleaned.split()[0]
        if len(first) > 2 and first != cleaned:
            aliases.add(first)
        for suffix in [" app", " desktop", " player", " editor"]:
            if cleaned.endswith(suffix):
                base = cleaned[:-len(suffix)]
                if len(base) > 2:
                    aliases.add(base)
        return list(aliases)

    # ==================== REGISTRY BUILD ====================

    def _build_dynamic_registry(self):
        logger.info("Building dynamic application registry...")
        start = time.time()
        seen = set()

        # Source 1: Winget
        if self.winget_available:
            stdout, _, code = self._run_cmd(["winget", "list", "--accept-source-agreements"], timeout=30)
            if code == 0 and stdout:
                for line in stdout.strip().split("\n"):
                    line = line.strip()
                    if not line or line.startswith("-") or "Name" in line:
                        continue
                    parts = [p.strip() for p in line.split("  ") if p.strip()]
                    if len(parts) >= 2:
                        name = parts[0].lower()
                        for alias in self._generate_aliases(name):
                            if alias not in self.app_registry:
                                self.app_registry[alias] = {"name": parts[0], "id": parts[1], "source": "winget", "type": "package"}

        # Source 2: Start Menu
        for base in [os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
                      os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs")]:
            if not os.path.exists(base):
                continue
            try:
                for root, dirs, files in os.walk(base):
                    if root.replace(base, "").count(os.sep) > 2:
                        dirs.clear()
                        continue
                    for f in files:
                        if f.endswith(".lnk"):
                            clean = f.replace(".lnk", "").lower()
                            for alias in self._generate_aliases(clean):
                                if alias not in self.app_registry:
                                    self.app_registry[alias] = {"name": f.replace(".lnk", ""), "source": "start_menu", "type": "shortcut"}
            except Exception:
                continue

        # Source 3: Program Files
        skip = {"windows", "system32", "drivers", "winsxs", "microsoft.net", "common files", "temp", "installer"}
        for base in [os.path.expandvars(r"%ProgramFiles%"), os.path.expandvars(r"%ProgramFiles(x86)%"), os.path.expandvars(r"%LOCALAPPDATA%\Programs")]:
            if not os.path.exists(base):
                continue
            try:
                for root, dirs, files in os.walk(base):
                    if root.replace(base, "").count(os.sep) > 3:
                        dirs.clear()
                        continue
                    for fname in files:
                        if fname.lower().endswith(".exe"):
                            exe_lower = fname.lower()
                            if exe_lower in seen:
                                continue
                            seen.add(exe_lower)
                            base_name = fname.replace(".exe", "").lower()
                            for alias in self._generate_aliases(base_name):
                                if alias not in self.app_registry:
                                    self.app_registry[alias] = {"name": fname.replace(".exe", ""), "exe": fname, "source": "filesystem", "type": "executable"}
                    dirs[:] = [d for d in dirs if d.lower() not in skip]
            except Exception:
                continue

        # Source 4: PATH
        for p in os.environ.get("PATH", "").split(";"):
            if not p or not os.path.isdir(p):
                continue
            try:
                for f in os.listdir(p):
                    if f.lower().endswith(".exe"):
                        base_name = f.replace(".exe", "").lower()
                        for alias in self._generate_aliases(base_name):
                            if alias not in self.app_registry:
                                self.app_registry[alias] = {"name": f.replace(".exe", ""), "exe": f, "source": "PATH", "type": "cli_tool"}
            except Exception:
                continue

        logger.info(f"Registry built: {len(self.app_registry)} aliases in {time.time()-start:.1f}s")

    # ==================== OPEN APP (FIXED: self added) ====================

    def open_app(self, app_name):
        """Auto-detect and open any app using Win+S search."""
        query = app_name.strip()
        if not query:
            return "Which app should I open, Sir?"

        # Check launch memory first
        query_lower = query.lower()
        if query_lower in self.launch_memory:
            remembered = self.launch_memory[query_lower]["app_name"]
            logger.info(f"Launch memory hit: '{query}' -> '{remembered}'")
            result = self._win_search_launch(remembered)
            if result:
                self._remember_launch(query, remembered, "memory+winsearch")
                return result

        # Try Win+S search
        result = self._win_search_launch(query)
        if result:
            self._remember_launch(query, query, "winsearch")
            return result

        # Fallback: start command
        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "", query],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self._remember_launch(query, query, "start_cmd")
            return f"Opened {query}, Sir."
        except Exception:
            return f"Could not open '{query}'. Is it installed, Sir?"

    def _win_search_launch(self, query):
        """Launch app via Win+S search bar."""
        try:
            import pyautogui

            before = self._get_running_set()

            pyautogui.hotkey('win', 's')
            time.sleep(0.8)

            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.1)
            pyautogui.typewrite(query, interval=0.03)
            time.sleep(1.0)

            pyautogui.press('enter')
            time.sleep(2.0)

            after = self._get_running_set()
            new_apps = after - before

            if new_apps:
                launched = list(new_apps)[0]
                logger.info(f"Win+S SUCCESS: '{query}' -> {launched}")
                return f"Opened {query}, Sir."

            if self._is_running(query):
                logger.info(f"Win+S FOCUSED: '{query}'")
                return f"Opened {query}, Sir."

        except ImportError:
            logger.warning("pyautogui not installed. Win+S unavailable.")
        except Exception as e:
            logger.error(f"Win+S failed: {e}")

        return None

    def _get_running_set(self):
        try:
            stdout, _, code = self._run_cmd(["tasklist", "/FO", "CSV", "/NH"], timeout=5)
            if code == 0:
                apps = set()
                for line in stdout.strip().split("\n"):
                    parts = line.strip('"').split('","')
                    if parts:
                        apps.add(parts[0].lower())
                return apps
        except Exception:
            pass
        return set()

    def _is_running(self, name):
        try:
            base = name.lower().replace(".exe", "").replace(" ", "")
            stdout, _, code = self._run_cmd(["tasklist", "/FO", "CSV", "/NH"], timeout=5)
            if code == 0:
                return base in stdout.lower()
        except Exception:
            pass
        return False

    def _get_app_details(self, name):
        name_lower = name.lower().strip()
        if name_lower in self.app_registry:
            return self.app_registry[name_lower]
        for alias in self._generate_aliases(name_lower):
            if alias in self.app_registry:
                return self.app_registry[alias]
        return None

    # ==================== CLOSE APP (FIXED: self added) ====================

    def close_app(self, app_name):
        """Auto-detect and close any running app by fuzzy matching."""
        import psutil

        query = app_name.lower().strip()
        if not query:
            return "Which app should I close, Sir?"

        matched = []
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                pname = proc.info['name']
                if pname and len(pname) > 2:
                    pname_clean = pname.lower().replace(".exe", "")
                    if query == pname_clean or query in pname_clean or pname_clean in query:
                        matched.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not matched:
            try:
                result = subprocess.run(
                    ["taskkill", "/F", "/IM", f"{query}.exe"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                if result.returncode == 0:
                    return f"Closed {query}, Sir."
            except Exception:
                pass
            return f"No running app matching '{app_name}' found, Sir."

        closed = []
        for proc in matched:
            try:
                proc.kill()
                closed.append(proc.info['name'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(proc.pid)],
                        capture_output=True, timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    closed.append(proc.info['name'])
                except Exception:
                    pass

        if closed:
            return f"Closed {', '.join(set(closed))}, Sir."
        return f"Failed to close '{app_name}', Sir."

    # ==================== INSTALL / UNINSTALL ====================

    def install_app(self, name):
        if not self.winget_available:
            return "Winget not available, Sir."
        if self.is_installed(name):
            return f"{name} already installed, Sir."
        _, _, code = self._run_cmd(["winget", "install", name.strip(), "--accept-package-agreements", "--accept-source-agreements", "--silent"], timeout=120)
        if code == 0:
            self._build_dynamic_registry()
            self._save_cache()
            return f"Installed {name}, Sir."
        return f"Install failed for {name}, Sir."

    def uninstall_app(self, name):
        if not self.winget_available:
            return "Winget not available, Sir."
        _, _, code = self._run_cmd(["winget", "uninstall", name.strip(), "--accept-source-agreements", "--silent"], timeout=120)
        if code == 0:
            self._build_dynamic_registry()
            self._save_cache()
            return f"Uninstalled {name}, Sir."
        return f"Uninstall failed for {name}, Sir."

    def search_apps(self, query):
        if not self.winget_available:
            return "Winget not available, Sir."
        stdout, _, code = self._run_cmd(["winget", "search", query.strip(), "--accept-source-agreements"], timeout=15)
        if code != 0 or not stdout:
            return f"No apps found for '{query}', Sir."
        lines = [l.strip() for l in stdout.strip().split("\n") if l.strip() and not l.startswith("-") and "Name" not in l and "Id" not in l]
        results = []
        for line in lines[:5]:
            parts = [p.strip() for p in line.split("  ") if p.strip()]
            if len(parts) >= 2:
                results.append(f"{parts[0]} ({parts[1]})")
        return f"Found: {', '.join(results)}. Say 'install' + name, Sir." if results else f"No matches for '{query}', Sir."

    def list_running(self):
        stdout, _, code = self._run_cmd(["tasklist", "/FO", "CSV", "/NH"])
        if code != 0:
            return "Could not list running apps, Sir."
        skip = {"svchost", "csrss", "wininit", "services", "lsass", "system", "idle", "registry", "smss", "runtimebroker", "dwm", "fontdrvhost", "ctfmon", "sihost", "taskhostw", "explorer", "searchhost", "startmenuexperiencehost", "shellexperiencehost", "textinputhost", "securityhealthsystray"}
        apps = []
        seen = set()
        for line in stdout.strip().split("\n"):
            parts = line.strip('"').split('","')
            if parts:
                n = parts[0].replace(".exe", "").replace(".EXE", "").lower()
                if n not in seen and n not in skip and len(n) > 2:
                    seen.add(n)
                    apps.append(parts[0].replace(".exe", "").replace(".EXE", ""))
        return f"Running: {', '.join(apps[:10])}, Sir." if apps else "No user apps running, Sir."

    def app_status(self, name):
        name_lower = name.lower().strip()
        if self._is_running(name_lower):
            return f"{name} is running, Sir."
        if self.is_installed(name_lower):
            return f"{name} is installed but not running, Sir."
        return f"{name} not found, Sir."

    def is_installed(self, name):
        name_lower = name.lower().strip()
        if name_lower in self.app_registry:
            return True
        for alias in self._generate_aliases(name_lower):
            if alias in self.app_registry:
                return True
        return False


app_manager = HexAppManager()