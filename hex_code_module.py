import os
import subprocess
import time
import logging
import requests
import psutil
from code_language_module import lang_db

logging.basicConfig(level=logging.INFO, format='[CodeMod] %(message)s')
logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2"


class HexCodeModule:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized: return

        self.workspace = os.path.join(os.getcwd(), "HEX_CODE")
        # Ensure directory exists and is writable
        try:
            os.makedirs(self.workspace, exist_ok=True)
        except Exception as e:
            logger.error(f"Cannot create workspace: {e}")

        self.last_generated_file = None
        self.active_ide = self._detect_ide()
        self._initialized = True
        logger.info(f"Code Architect Module Ready. IDE: {self.active_ide} | Workspace: {self.workspace}")

    def _detect_ide(self):
        try:
            running = [p.name().lower() for p in psutil.process_iter(['name'])]
            if "code.exe" in running: return "vscode"
            if "pycharm64.exe" in running: return "pycharm"
        except:
            pass
        return "none"

    def generate_code(self, language, requirement):
        """Generate expert-level code."""
        lang_info = lang_db.get_language_info(language)
        ext = lang_info["ext"] if lang_info else f".{language.lower()}"
        lang_name = next((k for k, v in lang_db.languages.items() if v == lang_info),
                         language) if lang_info else language

        logger.info(f"Generating {lang_name} code for: {requirement}")

        prompt = f"""
        You are a Principal Software Engineer. Write production-grade code in {lang_name}.
        Task: {requirement}

        Rules:
        - Modular, efficient, and well-commented.
        - Handle edge cases.
        - NO markdown backticks. Raw code only.
        - Do not include explanations, just the code.
        """

        try:
            resp = requests.post(OLLAMA_URL, json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 2000, "temperature": 0.2}  # Increased limit
            }, timeout=180)  # Increased timeout

            if resp.status_code == 200:
                code = resp.json().get("response", "").strip()
                # Aggressive cleaning of markdown
                if "```" in code:
                    code = code.split("```")[-2] if len(code.split("```")) > 1 else code.replace("```", "")

                filename = f"hex_{lang_name}_{int(time.time())}{ext}"
                filepath = os.path.join(self.workspace, filename)

                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(code)

                self.last_generated_file = filepath
                logger.info(f"Code saved to: {filepath}")
                return filepath, code
            else:
                logger.error(f"LLM Status Code: {resp.status_code}")
                return None, f"LLM Error: Status {resp.status_code}, Sir."

        except requests.exceptions.Timeout:
            return None, "Coding took too long. Try a simpler task, Sir."
        except Exception as e:
            logger.error(f"Generation Exception: {e}")
            return None, f"Generation Error: {str(e)}, Sir."

    # ... (Baaki methods: explain, summarize, debug, deploy, open_in_ide same rahenge) ...
    def explain_code(self, filepath=None, detail_level="simple"):
        target = filepath or self.last_generated_file
        if not target or not os.path.exists(target): return "File not found, Sir."
        with open(target, "r", encoding="utf-8") as f:
            code_content = f.read()
        lang_name = os.path.splitext(target)[1].replace(".", "")
        level_prompt = "Explain like I'm a beginner." if detail_level == "simple" else "Provide a deep technical architectural breakdown."
        prompt = f"You are a Lead Developer. {level_prompt}\nLanguage: {lang_name}\nCode:\n{code_content[:3000]}"
        try:
            resp = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                                                   "options": {"num_predict": 1000}}, timeout=90)
            return resp.json().get("response",
                                   "Explanation unavailable, Sir.") if resp.status_code == 200 else "LLM Error, Sir."
        except:
            return "Connection error, Sir."

    def summarize_code(self, filepath=None):
        target = filepath or self.last_generated_file
        if not target or not os.path.exists(target): return "File not found, Sir."
        with open(target, "r", encoding="utf-8") as f:
            code_content = f.read()
        prompt = f"Analyze this code and provide a 3-bullet point summary:\n1. Purpose?\n2. Inputs/Outputs?\n3. Dependencies?\nCode:\n{code_content[:2000]}"
        try:
            resp = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                                                   "options": {"num_predict": 300}}, timeout=60)
            return resp.json().get("response",
                                   "Summary unavailable, Sir.") if resp.status_code == 200 else "LLM Error, Sir."
        except:
            return "Connection error, Sir."

    def debug_and_fix(self, filepath=None):
        target = filepath or self.last_generated_file
        if not target: return "No file specified, Sir."
        ext = os.path.splitext(target)[1].lower()
        lang_info = next((info for info in lang_db.languages.values() if info["ext"] == ext), None)
        error_msg = ""
        if ext == ".py":
            result = subprocess.run(["py", "-3.11", "-m", "py_compile", target], capture_output=True, text=True)
            if result.returncode != 0: error_msg = result.stderr.strip()
        if not error_msg: return "No obvious syntax errors found, Sir."
        with open(target, "r") as f:
            original = f.read()
        fix_prompt = f"Fix this error:\n{error_msg}\n\nCode:\n{original}\n\nReturn ONLY fixed code."
        try:
            resp = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": fix_prompt, "stream": False,
                                                   "options": {"num_predict": 1500}}, timeout=90)
            if resp.status_code == 200:
                fixed = resp.json().get("response", "").strip()
                if "```" in fixed: fixed = fixed.split("```")[-2] if len(fixed.split("```")) > 1 else fixed.replace(
                    "```", "")
                with open(target, "w") as f:
                    f.write(fixed)
                return "Error detected and automatically fixed, Sir. Check the file."
            return "Could not auto-fix, Sir."
        except:
            return "Debugging connection failed, Sir."

    def deploy_code(self, filepath=None):
        target = filepath or self.last_generated_file
        if not target: return "No file, Sir."
        ext = os.path.splitext(target)[1].lower()
        lang_info = next((info for info in lang_db.languages.values() if info["ext"] == ext), None)
        if not lang_info: return "Unknown type, Sir."
        if ext in [".html"]:
            os.startfile(target);
            return "Opened in browser, Sir."
        if "compiler" in lang_info:
            try:
                out = os.path.join(self.workspace, "output.exe") if ext in [".c", ".cpp"] else target
                cmd = lang_info["compiler"] + ([target, "-o", out] if ext in [".c", ".cpp"] else [target])
                subprocess.run(cmd, check=True, timeout=15)
                if ext in [".c", ".cpp"]: target = out
            except Exception as e:
                return f"Compilation failed: {e}, Sir."
        if "runtime" in lang_info:
            try:
                proc = subprocess.Popen(lang_info["runtime"] + [target], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True)
                out, err = proc.communicate(timeout=20)
                return f"Output:\n{out}" if not err else f"Error:\n{err}, Sir."
            except Exception as e:
                return f"Run failed: {e}, Sir."
        return "Deployed to IDE for manual run, Sir."

    def open_in_ide(self, filepath=None):
        target = filepath or self.last_generated_file
        if not target: return "No file, Sir."
        try:
            if self.active_ide == "vscode":
                subprocess.Popen(["code", target])
            elif self.active_ide == "pycharm":
                subprocess.Popen(["pycharm", target])
            else:
                os.startfile(target)
            return f"Opened in {self.active_ide.upper() if self.active_ide != 'none' else 'Editor'}, Sir."
        except Exception as e:
            return f"Failed to open IDE: {e}, Sir."


# Global Singleton
hex_code_module = HexCodeModule()