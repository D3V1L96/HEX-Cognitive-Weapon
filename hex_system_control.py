import logging
import time
import math
import os
import ctypes
import threading

logging.basicConfig(level=logging.INFO, format='[Screen] %(message)s')
logger = logging.getLogger(__name__)

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.03
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    logger.warning("pyautogui not installed. Run: pip install pyautogui")

try:
    import win32gui
    import win32con
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False
    logger.warning("pywin32 not installed. Run: pip install pywin32")


class HexScreenControl:
    """INSANE Screen Access. Mouse. Keyboard. Vision. Windows. Everything on screen."""

    def __init__(self):
        self.w = 0
        self.h = 0
        self._refresh()
        self._history = []
        self._lock = threading.Lock()
        logger.info(f"SCREEN CONTROL ONLINE | {self.w}x{self.h}")

    def _refresh(self):
        try:
            if PYAUTOGUI_AVAILABLE:
                self.w, self.h = pyautogui.size()
            else:
                u = ctypes.windll.user32
                self.w = u.GetSystemMetrics(0)
                self.h = u.GetSystemMetrics(1)
        except Exception:
            self.w, self.h = 1920, 1080

    def _log(self, action, detail=""):
        with self._lock:
            self._history.append({"t": time.time(), "a": action, "d": detail})
            if len(self._history) > 50:
                self._history = self._history[-25:]

    # ==================== GOD LEVEL AUTONOMOUS EXECUTOR ====================

    def execute(self, command):
        """Parse ANY screen-related command and execute autonomously."""
        cmd = command.lower().strip()
        self._log("CMD", cmd)

        # --- MOUSE ---
        if any(w in cmd for w in ["move mouse", "cursor move", "mouse jaao", "pointer"]):
            return self._smart_mouse_move(cmd)
        if any(w in cmd for w in ["click", "dabao", "tap"]):
            return self._smart_click(cmd)
        if any(w in cmd for w in ["double click", "double dabao"]):
            return self._smart_double_click(cmd)
        if any(w in cmd for w in ["right click", "right dabao"]):
            return self._smart_right_click(cmd)
        if any(w in cmd for w in ["drag", "kheench"]):
            return self._smart_drag(cmd)
        if any(w in cmd for w in ["scroll", "neeche", "upar", "page up", "page down"]):
            return self._smart_scroll(cmd)
        if any(w in cmd for w in ["mouse position", "cursor kahan", "where is mouse"]):
            return self.get_mouse_pos()

        # --- KEYBOARD ---
        if any(w in cmd for w in ["type ", "write ", "likho ", "input "]):
            return self._smart_type(cmd)
        if any(w in cmd for w in ["press key", "key press", "key dabao", "hit key"]):
            return self._smart_key(cmd)
        if any(w in cmd for w in ["shortcut", "hotkey", "ctrl+", "alt+", "win+", "shift+"]):
            return self._smart_hotkey(cmd)
        if any(w in cmd for w in ["select all", "sab select"]):
            return self.hotkey('ctrl', 'a')
        if any(w in cmd for w in ["copy", "copy karo"]):
            return self.hotkey('ctrl', 'c')
        if any(w in cmd for w in ["paste", "paste karo"]):
            return self.hotkey('ctrl', 'v')
        if any(w in cmd for w in ["cut", "cut karo"]):
            return self.hotkey('ctrl', 'x')
        if any(w in cmd for w in ["undo", "wapas"]):
            return self.hotkey('ctrl', 'z')
        if any(w in cmd for w in ["redo"]):
            return self.hotkey('ctrl', 'y')
        if any(w in cmd for w in ["save", "save karo"]):
            return self.hotkey('ctrl', 's')
        if any(w in cmd for w in ["enter", "return"]):
            return self.press('enter')
        if any(w in cmd for w in ["escape", "esc", "cancel"]):
            return self.press('escape')
        if any(w in cmd for w in ["tab"]):
            return self.press('tab')
        if any(w in cmd for w in ["backspace", "delete char"]):
            return self.press('backspace')
        if any(w in cmd for w in ["delete"]):
            return self.press('delete')

        # --- SCREENSHOT / VISION ---
        if any(w in cmd for w in ["screenshot", "capture", "screen le", "screen shot"]):
            return self.screenshot(cmd)
        if any(w in cmd for w in ["what do you see", "screen pe kya", "describe screen", "screen read"]):
            return self._describe_screen()

        # --- WINDOW MANAGEMENT ---
        if any(w in cmd for w in ["focus", "switch to", "ispe jaao", "activate"]):
            return self._smart_focus(cmd)
        if any(w in cmd for w in ["minimize", "chhota karo"]):
            return self._smart_minimize(cmd)
        if any(w in cmd for w in ["maximize", "bada karo", "full screen"]):
            return self._smart_maximize(cmd)
        if any(w in cmd for w in ["close window", "window band", "close this"]):
            return self._smart_close(cmd)
        if any(w in cmd for w in ["snap left", "left side", "baayi"]):
            return self._smart_snap(cmd, "left")
        if any(w in cmd for w in ["snap right", "right side", "daayi"]):
            return self._smart_snap(cmd, "right")
        if any(w in cmd for w in ["tile", "arrange", "split", "grid"]):
            return self._smart_tile()
        if any(w in cmd for w in ["resize", "size change"]):
            return self._smart_resize(cmd)
        if any(w in cmd for w in ["move window", "window move"]):
            return self._smart_move_window(cmd)
        if any(w in cmd for w in ["list windows", "open apps", "kaunsi window", "what's open"]):
            return self._list_visible_windows()
        if any(w in cmd for w in ["show desktop", "desktop dikhao"]):
            return self.hotkey('win', 'd')
        if any(w in cmd for w in ["alt tab", "switch app", "agla app"]):
            return self._smart_alt_tab(cmd)
        if any(w in cmd for w in ["always on top", "pin window", "upar rakho"]):
            return self._smart_pin(cmd)

        # --- ZOOM / DISPLAY ---
        if any(w in cmd for w in ["zoom in", "bada dikhao"]):
            return self.hotkey('ctrl', '+')
        if any(w in cmd for w in ["zoom out", "chhota dikhao"]):
            return self.hotkey('ctrl', '-')
        if any(w in cmd for w in ["zoom reset", "normal size"]):
            return self.hotkey('ctrl', '0')

        return f"No screen action matched. Be more specific, Sir."

    # ==================== SMART MOUSE ====================

    def _smart_mouse_move(self, cmd):
        import re
        nums = re.findall(r'\d+', cmd)
        if len(nums) >= 2:
            x, y = int(nums[0]), int(nums[1])
            return self.move_to(x, y)
        # Directional
        cx, cy = self.w // 2, self.h // 2
        step = 200
        if "left" in cmd or "baayein" in cmd:
            return self.move_to(cx - step, cy)
        if "right" in cmd or "daayein" in cmd:
            return self.move_to(cx + step, cy)
        if "up" in cmd or "upar" in cmd:
            return self.move_to(cx, cy - step)
        if "down" in cmd or "neeche" in cmd:
            return self.move_to(cx, cy + step)
        if "center" in cmd or "beech" in cmd:
            return self.move_to(cx, cy)
        if "top left" in cmd:
            return self.move_to(100, 100)
        if "top right" in cmd:
            return self.move_to(self.w - 100, 100)
        if "bottom left" in cmd:
            return self.move_to(100, self.h - 100)
        if "bottom right" in cmd:
            return self.move_to(self.w - 100, self.h - 100)
        return "Specify coordinates or direction, Sir."

    def _smart_click(self, cmd):
        import re
        nums = re.findall(r'\d+', cmd)
        if len(nums) >= 2:
            return self.click_at(int(nums[0]), int(nums[1]))
        return self.click_here()

    def _smart_double_click(self, cmd):
        import re
        nums = re.findall(r'\d+', cmd)
        if len(nums) >= 2:
            return self.double_click_at(int(nums[0]), int(nums[1]))
        return self.double_click_here()

    def _smart_right_click(self, cmd):
        import re
        nums = re.findall(r'\d+', cmd)
        if len(nums) >= 2:
            return self.right_click_at(int(nums[0]), int(nums[1]))
        return self.right_click_here()

    def _smart_drag(self, cmd):
        import re
        nums = re.findall(r'\d+', cmd)
        if len(nums) >= 4:
            return self.drag(int(nums[0]), int(nums[1]), int(nums[2]), int(nums[3]))
        return "Specify start and end coordinates for drag, Sir."

    def _smart_scroll(self, cmd):
        import re
        nums = re.findall(r'\d+', cmd)
        amount = int(nums[0]) if nums else 3
        if "down" in cmd or "neeche" in cmd:
            direction = -1
        elif "up" in cmd or "upar" in cmd:
            direction = 1
        else:
            direction = -1

        # Human-like glide scrolling with ease-in-out
        total_steps = abs(amount) * 3
        try:
            import pyautogui
            for i in range(total_steps):
                # Ease-in-out curve: slow start, fast middle, slow end
                progress = i / max(total_steps - 1, 1)
                # Sine ease-in-out: 0→1 smooth curve
                eased = 0.5 - 0.5 * math.cos(math.pi * progress)
                # Speed multiplier: 1x at edges, 3x at center
                speed = 1 + 2 * math.sin(math.pi * progress)
                step = max(1, round(speed))

                pyautogui.scroll(direction * step)
                # Delay also varies: longer at edges, shorter at center
                delay = 0.06 - 0.04 * math.sin(math.pi * progress)
                time.sleep(max(0.015, delay))

            return f"Scrolled {'down' if direction < 0 else 'up'}, Sir."
        except Exception as e:
            return f"Scroll failed: {e}, Sir."

    def _smart_type(self, cmd):
        """Extract and type text, return what was actually typed."""
        text = cmd
        for w in ["type ", "write ", "likho ", "input "]:
            text = text.replace(w, "", 1)
        text = text.strip()

        # Remove trailing command separators so they don't get typed
        for suffix in [" and then", " also", " plus", " then", " after that",
                       " aur ", " phir ", " uske baad"]:
            idx = text.lower().find(suffix)
            if idx > 0:
                text = text[:idx].strip()

        if not text:
            return "What should I type, Sir?"

        result = self.type_text(text)
        return result

    def _smart_key(self, cmd):
        text = cmd
        for w in ["press key", "key press", "key dabao", "hit key"]:
            text = text.replace(w, "")
        key = text.strip()
        if key:
            return self.press(key)
        return "Which key, Sir?"

    def _smart_hotkey(self, cmd):
        import re
        keys = re.findall(r'(ctrl|alt|shift|win|super)', cmd)
        remaining = cmd
        for k in keys:
            remaining = remaining.replace(k, "", 1)
        remaining = remaining.replace("+", " ").replace("-", " ").strip()
        extra = re.findall(r'[a-z0-9]+', remaining)
        all_keys = keys + extra
        if len(all_keys) >= 2:
            return self.hotkey(*all_keys)
        elif len(all_keys) == 1:
            return self.press(all_keys[0])
        return "Specify keys like 'ctrl shift escape', Sir."

    # ==================== SMART WINDOW ====================

    def _smart_focus(self, cmd):
        name = cmd
        for w in ["focus", "switch to", "ispe jaao", "activate"]:
            name = name.replace(w, "")
        name = name.strip()
        if name:
            return self.focus_window(name)
        return "Which window, Sir?"

    def _smart_minimize(self, cmd):
        name = cmd
        for w in ["minimize", "chhota karo"]:
            name = name.replace(w, "")
        name = name.strip()
        if name:
            return self.minimize_window(name)
        return self.hotkey('win', 'd')

    def _smart_maximize(self, cmd):
        name = cmd
        for w in ["maximize", "bada karo", "full screen"]:
            name = name.replace(w, "")
        name = name.strip()
        if name:
            return self.maximize_window(name)
        return "Which window to maximize, Sir?"

    def _smart_close(self, cmd):
        name = cmd
        for w in ["close window", "window band", "close this", "close"]:
            name = name.replace(w, "")
        name = name.strip()
        if name:
            return self.close_window(name)
        return self.hotkey('alt', 'F4')

    def _smart_snap(self, cmd, side):
        name = cmd
        for w in ["snap left", "snap right", "left side", "right side", "baayi", "daayi"]:
            name = name.replace(w, "")
        name = name.strip()
        if name:
            if side == "left":
                return self.snap_left(name)
            return self.snap_right(name)
        # Snap active window
        hwnd = self._get_foreground_hwnd()
        if hwnd:
            self._refresh()
            if side == "left":
                win32gui.MoveWindow(hwnd, 0, 0, self.w // 2, self.h, True)
                return "Snapped active window left, Sir."
            else:
                win32gui.MoveWindow(hwnd, self.w // 2, 0, self.w // 2, self.h, True)
                return "Snapped active window right, Sir."
        return "No active window found, Sir."

    def _smart_tile(self):
        wins = self._get_visible_windows()
        count = len(wins)
        if count == 0:
            return "No windows to tile, Sir."
        self._refresh()
        if count == 1:
            win32gui.ShowWindow(wins[0]["hwnd"], win32con.SW_MAXIMIZE)
            return "Maximized single window, Sir."
        elif count == 2:
            hw = self.w // 2
            win32gui.MoveWindow(wins[0]["hwnd"], 0, 0, hw, self.h, True)
            win32gui.MoveWindow(wins[1]["hwnd"], hw, 0, hw, self.h, True)
            return "Tiled 2 windows side by side, Sir."
        else:
            hw = self.w // 2
            hh = self.h // 2
            positions = [(0, 0), (hw, 0), (0, hh), (hw, hh)]
            for i in range(min(count, 4)):
                win32gui.MoveWindow(wins[i]["hwnd"], positions[i][0], positions[i][1], hw, hh, True)
            return f"Tiled {min(count, 4)} windows in grid, Sir."

    def _smart_resize(self, cmd):
        import re
        nums = re.findall(r'\d+', cmd)
        if len(nums) >= 2:
            hwnd = self._get_foreground_hwnd()
            if hwnd:
                rect = win32gui.GetWindowRect(hwnd)
                nw, nh = int(nums[0]), int(nums[1])
                win32gui.MoveWindow(hwnd, rect[0], rect[1], nw, nh, True)
                return f"Resized to {nw}x{nh}, Sir."
        return "Specify width and height, Sir."

    def _smart_move_window(self, cmd):
        import re
        nums = re.findall(r'\d+', cmd)
        if len(nums) >= 2:
            hwnd = self._get_foreground_hwnd()
            if hwnd:
                rect = win32gui.GetWindowRect(hwnd)
                nx, ny = int(nums[0]), int(nums[1])
                win32gui.MoveWindow(hwnd, nx, ny, rect[2]-rect[0], rect[3]-rect[1], True)
                return f"Moved to ({nx},{ny}), Sir."
        return "Specify x and y, Sir."

    def _smart_alt_tab(self, cmd):
        import re
        nums = re.findall(r'\d+', cmd)
        times = int(nums[0]) if nums else 1
        return self.alt_tab(times)

    def _smart_pin(self, cmd):
        if not WIN32_AVAILABLE:
            return "Unavailable, Sir."
        hwnd = self._get_foreground_hwnd()
        if hwnd:
            try:
                style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style | 0x00000008)
                return "Window pinned on top, Sir."
            except Exception as e:
                return f"Pin failed: {e}"
        return "No active window, Sir."

    def _list_visible_windows(self):
        wins = self._get_visible_windows()
        if wins:
            names = [w["title"][:25] for w in wins[:8]]
            extra = f" +{len(wins)-8} more" if len(wins) > 8 else ""
            return f"Open: {', '.join(names)}{extra}. Total {len(wins)}, Sir."
        return "No visible windows, Sir."

    def _describe_screen(self):
        path = self.screenshot(save_only=True)
        if path and os.path.exists(path):
            return f"Screenshot captured at {path}. Analyze it, Sir."
        return "Screenshot failed, Sir."

    # ==================== CORE PRIMITIVES ====================

    def move_to(self, x, y, duration=0.15):
        if not PYAUTOGUI_AVAILABLE:
            return "Mouse unavailable, Sir."
        try:
            pyautogui.moveTo(x, y, duration=duration)
            self._log("MOVE", f"({x},{y})")
            return f"Mouse at ({x},{y}), Sir."
        except Exception as e:
            return f"Move failed: {e}"

    def click_at(self, x, y):
        if not PYAUTOGUI_AVAILABLE:
            return "Mouse unavailable, Sir."
        try:
            pyautogui.click(x, y)
            self._log("CLICK", f"({x},{y})")
            return f"Clicked ({x},{y}), Sir."
        except Exception as e:
            return f"Click failed: {e}"

    def click_here(self):
        if not PYAUTOGUI_AVAILABLE:
            return "Mouse unavailable, Sir."
        try:
            pyautogui.click()
            self._log("CLICK", "current")
            return "Clicked, Sir."
        except Exception as e:
            return f"Click failed: {e}"

    def double_click_at(self, x, y):
        if not PYAUTOGUI_AVAILABLE:
            return "Mouse unavailable, Sir."
        try:
            pyautogui.doubleClick(x, y)
            self._log("DBLCLICK", f"({x},{y})")
            return f"Double clicked ({x},{y}), Sir."
        except Exception as e:
            return f"Double click failed: {e}"

    def double_click_here(self):
        if not PYAUTOGUI_AVAILABLE:
            return "Mouse unavailable, Sir."
        try:
            pyautogui.doubleClick()
            self._log("DBLCLICK", "current")
            return "Double clicked, Sir."
        except Exception as e:
            return f"Double click failed: {e}"

    def right_click_at(self, x, y):
        if not PYAUTOGUI_AVAILABLE:
            return "Mouse unavailable, Sir."
        try:
            pyautogui.rightClick(x, y)
            self._log("RCLICK", f"({x},{y})")
            return f"Right clicked ({x},{y}), Sir."
        except Exception as e:
            return f"Right click failed: {e}"

    def right_click_here(self):
        if not PYAUTOGUI_AVAILABLE:
            return "Mouse unavailable, Sir."
        try:
            pyautogui.rightClick()
            self._log("RCLICK", "current")
            return "Right clicked, Sir."
        except Exception as e:
            return f"Right click failed: {e}"

    def drag(self, sx, sy, ex, ey, duration=0.3):
        if not PYAUTOGUI_AVAILABLE:
            return "Drag unavailable, Sir."
        try:
            pyautogui.moveTo(sx, sy)
            pyautogui.drag(ex - sx, ey - sy, duration=duration)
            self._log("DRAG", f"({sx},{sy})->({ex},{ey})")
            return f"Dragged to ({ex},{ey}), Sir."
        except Exception as e:
            return f"Drag failed: {e}"

    def scroll(self, amount):
        if not PYAUTOGUI_AVAILABLE:
            return "Scroll unavailable, Sir."
        try:
            pyautogui.scroll(amount)
            d = "up" if amount > 0 else "down"
            self._log("SCROLL", f"{d} {abs(amount)}")
            return f"Scrolled {d} {abs(amount)}, Sir."
        except Exception as e:
            return f"Scroll failed: {e}"

    def get_mouse_pos(self):
        if not PYAUTOGUI_AVAILABLE:
            return "Unavailable, Sir."
        x, y = pyautogui.position()
        return f"Mouse at ({x}, {y}), Sir."

    def type_text(self, text, interval=0.02):
        """Type text and return exactly what was typed."""
        if not PYAUTOGUI_AVAILABLE:
            return "Keyboard unavailable, Sir."
        try:
            pyautogui.typewrite(text, interval=interval)
            self._log("TYPE", text[:50])
            # Return WHAT was typed, not just char count
            display = text if len(text) <= 80 else text[:80] + "..."
            return f"Typed: \"{display}\", Sir."
        except Exception as e:
            return f"Type failed: {e}"
    def press(self, key):
        if not PYAUTOGUI_AVAILABLE:
            return "Keyboard unavailable, Sir."
        try:
            pyautogui.press(key)
            self._log("KEY", key)
            return f"Pressed '{key}', Sir."
        except Exception as e:
            return f"Key failed: {e}"

    def hotkey(self, *keys):
        if not PYAUTOGUI_AVAILABLE:
            return "Keyboard unavailable, Sir."
        try:
            pyautogui.hotkey(*keys)
            self._log("HOTKEY", "+".join(keys))
            return f"Pressed {'+'.join(keys)}, Sir."
        except Exception as e:
            return f"Hotkey failed: {e}"

    def screenshot(self, cmd="", save_only=False):
        if not PYAUTOGUI_AVAILABLE:
            return "Screenshot unavailable, Sir."
        try:
            import re
            nums = re.findall(r'\d+', cmd)
            path = os.path.join(os.getcwd(), "hex_screenshot.png")
            if len(nums) >= 4:
                region = (int(nums[0]), int(nums[1]), int(nums[2]), int(nums[3]))
                pyautogui.screenshot(region=region).save(path)
                self._log("SS_REGION", str(region))
            else:
                pyautogui.screenshot().save(path)
                self._log("SS_FULL", path)
            if save_only:
                return path
            return f"Screenshot saved: {path}"
        except Exception as e:
            return f"Screenshot failed: {e}"

    # ==================== WINDOW PRIMITIVES ====================

    def _get_visible_windows(self):
        if not WIN32_AVAILABLE:
            return []
        wins = []
        def cb(hwnd, results):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title and len(title) > 1:
                    r = win32gui.GetWindowRect(hwnd)
                    results.append({"title": title, "hwnd": hwnd,
                                    "x": r[0], "y": r[1], "w": r[2]-r[0], "h": r[3]-r[1]})
            return True
        try:
            win32gui.EnumWindows(cb, wins)
        except Exception:
            pass
        return wins[:20]

    def _get_foreground_hwnd(self):
        if not WIN32_AVAILABLE:
            return None
        try:
            return win32gui.GetForegroundWindow()
        except Exception:
            return None

    def focus_window(self, keyword):
        if not WIN32_AVAILABLE:
            return "Unavailable, Sir."
        for w in self._get_visible_windows():
            if keyword.lower() in w["title"].lower():
                try:
                    win32gui.ShowWindow(w["hwnd"], win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(w["hwnd"])
                    self._log("FOCUS", w["title"])
                    return f"Focused '{w['title']}', Sir."
                except Exception as e:
                    return f"Focus failed: {e}"
        return f"'{keyword}' not found, Sir."

    def minimize_window(self, keyword):
        if not WIN32_AVAILABLE:
            return "Unavailable, Sir."
        for w in self._get_visible_windows():
            if keyword.lower() in w["title"].lower():
                win32gui.ShowWindow(w["hwnd"], win32con.SW_MINIMIZE)
                return f"Minimized '{w['title']}', Sir."
        return f"'{keyword}' not found, Sir."

    def maximize_window(self, keyword):
        if not WIN32_AVAILABLE:
            return "Unavailable, Sir."
        for w in self._get_visible_windows():
            if keyword.lower() in w["title"].lower():
                win32gui.ShowWindow(w["hwnd"], win32con.SW_MAXIMIZE)
                win32gui.SetForegroundWindow(w["hwnd"])
                return f"Maximized '{w['title']}', Sir."
        return f"'{keyword}' not found, Sir."

    def close_window(self, keyword):
        if not WIN32_AVAILABLE:
            return "Unavailable, Sir."
        for w in self._get_visible_windows():
            if keyword.lower() in w["title"].lower():
                win32gui.PostMessage(w["hwnd"], win32con.WM_CLOSE, 0, 0)
                return f"Closed '{w['title']}', Sir."
        return f"'{keyword}' not found, Sir."

    def snap_left(self, keyword):
        self._refresh()
        for w in self._get_visible_windows():
            if keyword.lower() in w["title"].lower():
                win32gui.MoveWindow(w["hwnd"], 0, 0, self.w // 2, self.h, True)
                return f"Snapped '{w['title']}' left, Sir."
        return f"'{keyword}' not found, Sir."

    def snap_right(self, keyword):
        self._refresh()
        for w in self._get_visible_windows():
            if keyword.lower() in w["title"].lower():
                win32gui.MoveWindow(w["hwnd"], self.w // 2, 0, self.w // 2, self.h, True)
                return f"Snapped '{w['title']}' right, Sir."
        return f"'{keyword}' not found, Sir."

    def alt_tab(self, times=1):
        if not PYAUTOGUI_AVAILABLE:
            return "Unavailable, Sir."
        for _ in range(max(1, times)):
            pyautogui.hotkey('alt', 'tab')
            time.sleep(0.08)
        return f"Switched {times}x, Sir."


# Global Singleton
screen_control = HexScreenControl()