import os
import re
import json
import shutil
import subprocess
import tempfile
import logging
import threading
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='[FileUpload] %(message)s')
logger = logging.getLogger(__name__)


def _ollama_analyze(prompt: str, max_tokens: int = 512) -> str:
    """Use local Ollama instead of Gemini - keeps HEX 100% offline."""
    import requests
    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.2",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.5,
                    "num_predict": max_tokens,
                    "num_ctx": 4096,
                }
            },
            timeout=60
        )
        if resp.status_code == 200:
            return resp.json().get("response", "").strip()
        return f"LLM error: HTTP {resp.status_code}"
    except Exception as e:
        return f"LLM unavailable: {e}"


class HexFileUpload:
    """
    Universal File Processor + Upload Manager for HEX.
    Supports: Image, PDF, DOCX, TXT, MD, CSV, XLSX, JSON, XML, Code, Audio, Video, Archive, PPTX
    All AI processing via LOCAL Ollama - zero cloud dependency.
    """
    _instance = None

    SUPPORTED_EXTENSIONS = {
        # Images
        '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', '.svg',
        # Documents
        '.pdf', '.docx', '.doc', '.txt', '.md', '.rst', '.log', '.pptx', '.ppt',
        # Data
        '.csv', '.tsv', '.xlsx', '.xls', '.json', '.xml', '.yaml', '.yml',
        # Code
        '.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css', '.java', '.c',
        '.cpp', '.cs', '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.sh',
        '.bash', '.ps1', '.lua', '.r', '.sql', '.toml',
        # Media
        '.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.mp4', '.avi',
        '.mov', '.mkv', '.wmv', '.webm',
        # Archives
        '.zip', '.tar', '.gz', '.7z', '.rar',
    }

    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
    UPLOAD_DIR = os.path.join(os.getcwd(), "hex_uploads")

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        os.makedirs(self.UPLOAD_DIR, exist_ok=True)
        self.uploaded_files = []
        self.file_contents_cache = {}
        self._initialized = True
        logger.info("Hex Universal File Processor Ready")

    # ==================== FILE TYPE DETECTION ====================
    @staticmethod
    def _detect_type(path: Path) -> str:
        ext = path.suffix.lower()
        image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', '.svg'}
        video_exts = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.webm'}
        audio_exts = {'.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac'}
        code_exts = {'.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css', '.java',
                     '.c', '.cpp', '.cs', '.go', '.rs', '.rb', '.php', '.swift',
                     '.kt', '.sh', '.bash', '.ps1', '.lua', '.r', '.sql', '.toml'}
        archive_exts = {'.zip', '.tar', '.gz', '.7z', '.rar'}

        if ext in image_exts: return "image"
        if ext in video_exts: return "video"
        if ext in audio_exts: return "audio"
        if ext in code_exts: return "code"
        if ext in archive_exts: return "archive"
        if ext == '.pdf': return "pdf"
        if ext in ('.docx', '.doc'): return "docx"
        if ext in ('.txt', '.md', '.rst', '.log'): return "text"
        if ext in ('.csv', '.tsv'): return "csv"
        if ext in ('.xlsx', '.xls'): return "excel"
        if ext == '.json': return "json"
        if ext == '.xml': return "xml"
        if ext in ('.pptx', '.ppt'): return "pptx"
        return "unknown"

    @staticmethod
    def _file_size_str(path: Path) -> str:
        size = path.stat().st_size
        if size < 1024: return f"{size} B"
        if size < 1024**2: return f"{size/1024:.1f} KB"
        if size < 1024**3: return f"{size/1024**2:.1f} MB"
        return f"{size/1024**3:.1f} GB"

    @staticmethod
    def _output_path(src: Path, suffix: str, new_ext: str = None) -> Path:
        ext = new_ext or src.suffix
        name = f"{src.stem}_{suffix}{ext}"
        return src.parent / name

    # ==================== MAIN PROCESS ENTRY POINT ====================
    def process_file(self, filepath: str, action: str = "", instruction: str = "") -> dict:
        """Process any uploaded file with specified action."""
        try:
            path = Path(filepath)
            if not path.exists():
                return {"success": False, "error": f"File not found: {filepath}"}
            if not path.is_file():
                return {"success": False, "error": f"Not a file: {filepath}"}

            ext = path.suffix.lower()
            if ext not in self.SUPPORTED_EXTENSIONS:
                return {"success": False, "error": f"Unsupported format: {ext}"}

            size = path.stat().st_size
            if size > self.MAX_FILE_SIZE:
                return {"success": False, "error": f"File too large ({size//1024//1024}MB). Max 50MB."}

            # Copy to uploads dir
            dest = os.path.join(self.UPLOAD_DIR, path.name)
            shutil.copy2(filepath, dest)
            dest_path = Path(dest)

            file_type = self._detect_type(dest_path)
            params = {"action": action, "instruction": instruction, "save": True}

            logger.info(f"Processing: {path.name} | type={file_type} | action={action or 'auto'}")

            # Dispatch to type-specific processor
            result_text = self._dispatch(dest_path, file_type, action, params)

            file_info = {
                "name": path.name,
                "path": str(dest_path),
                "extension": ext,
                "type": file_type,
                "size": size,
                "size_str": self._file_size_str(dest_path),
                "action": action or "auto",
                "result": result_text,
                "content_preview": result_text[:500] if result_text else "",
                "success": True
            }

            self.uploaded_files.append(file_info)
            if result_text:
                self.file_contents_cache[path.name] = result_text

            return file_info

        except Exception as e:
            logger.error(f"File processing error: {e}")
            return {"success": False, "error": str(e)}

    def _dispatch(self, path: Path, file_type: str, action: str, params: dict) -> str:
        """Route to correct processor based on file type."""
        processors = {
            "image": self._process_image,
            "pdf": self._process_pdf,
            "docx": lambda p, a, pm: self._process_text_doc(p, "docx", a, pm),
            "text": lambda p, a, pm: self._process_text_doc(p, "text", a, pm),
            "csv": lambda p, a, pm: self._process_data(p, "csv", a, pm),
            "excel": lambda p, a, pm: self._process_data(p, "excel", a, pm),
            "json": self._process_json,
            "xml": self._process_json,
            "code": self._process_code,
            "audio": self._process_audio,
            "video": self._process_video,
            "archive": self._process_archive,
            "pptx": self._process_pptx,
        }

        handler = processors.get(file_type)
        if not handler:
            return f"Unsupported file type: {file_type}"

        try:
            return handler(path, action, params)
        except Exception as e:
            logger.error(f"Processor error [{file_type}]: {e}")
            return f"Processing failed: {e}"

    # ==================== IMAGE PROCESSOR ====================
    def _process_image(self, path: Path, action: str, params: dict) -> str:
        action = action or "describe"

        if action in ("describe", "ocr", "analyze", "read"):
            try:
                from PIL import Image
                img = Image.open(path)
                prompt_map = {
                    "describe": f"Describe this image in detail. Size: {img.size[0]}x{img.size[1]}, Mode: {img.mode}",
                    "ocr": "Extract all text visible in this image. Return only the text.",
                    "analyze": f"Analyze this image thoroughly: objects, colors, composition, context. Size: {img.size[0]}x{img.size[1]}",
                    "read": "Read all text in this image, preserving structure.",
                }
                prompt = prompt_map.get(action, f"Describe this image.")
                if params.get("instruction"):
                    prompt = params["instruction"]
                # For images without vision model, provide metadata
                return (f"Image: {path.name}, {img.size[0]}x{img.size[1]}px, "
                        f"mode: {img.mode}, size: {self._file_size_str(path)}\n"
                        f"Note: Install MiniCPM-V for visual analysis. "
                        f"Say 'see screen' for vision capabilities.")
            except ImportError:
                return f"Image file: {path.name}, size: {self._file_size_str(path)}. Install Pillow for more."
            except Exception as e:
                return f"Image info failed: {e}"

        if action == "resize":
            try:
                from PIL import Image
                img = Image.open(path)
                w, h = img.size
                width = int(params.get("width", 0))
                height = int(params.get("height", 0))
                scale = float(params.get("scale", 0))
                if scale:
                    new_size = (int(w * scale), int(h * scale))
                elif width and height:
                    new_size = (width, height)
                elif width:
                    new_size = (width, int(h * width / w))
                elif height:
                    new_size = (int(w * height / h), height)
                else:
                    return "Specify width, height, or scale."
                out = self._output_path(path, f"resized_{new_size[0]}x{new_size[1]}")
                img.resize(new_size, Image.LANCZOS).save(out)
                return f"Resized {w}x{h} → {new_size[0]}x{new_size[1]}. Saved: {out.name}"
            except ImportError:
                return "Pillow not installed. Run: pip install Pillow"
            except Exception as e:
                return f"Resize failed: {e}"

        if action == "convert":
            try:
                from PIL import Image
                fmt = params.get("format", "png").lower().strip(".")
                fmt_map = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP", "bmp": "BMP"}
                pil_fmt = fmt_map.get(fmt, fmt.upper())
                img = Image.open(path).convert("RGB") if fmt == "jpg" else Image.open(path)
                out = self._output_path(path, "converted", f".{fmt}")
                img.save(out, pil_fmt)
                return f"Converted to {fmt.upper()}. Saved: {out.name}"
            except ImportError:
                return "Pillow not installed."
            except Exception as e:
                return f"Convert failed: {e}"

        if action == "compress":
            try:
                from PIL import Image
                quality = int(params.get("quality", 70))
                img = Image.open(path).convert("RGB")
                out = self._output_path(path, f"compressed_q{quality}", ".jpg")
                img.save(out, "JPEG", quality=quality, optimize=True)
                return f"Compressed: {self._file_size_str(path)} → {self._file_size_str(out)}. Saved: {out.name}"
            except ImportError:
                return "Pillow not installed."
            except Exception as e:
                return f"Compress failed: {e}"

        if action == "info":
            try:
                from PIL import Image
                img = Image.open(path)
                return (f"Image: {img.format}, {img.size[0]}x{img.size[1]}px, "
                        f"mode: {img.mode}, size: {self._file_size_str(path)}")
            except Exception as e:
                return f"Info failed: {e}"

        return f"Image action '{action}' done. Try: describe, resize, convert, compress, info"

    # ==================== PDF PROCESSOR ====================
    def _process_pdf(self, path: Path, action: str, params: dict) -> str:
        action = action or "summarize"

        def extract_text(max_chars=50000):
            text = ""
            try:
                import pdfplumber
                with pdfplumber.open(path) as pdf:
                    for page in pdf.pages:
                        text += (page.extract_text() or "") + "\n"
            except ImportError:
                try:
                    import PyPDF2
                    with open(path, "rb") as f:
                        reader = PyPDF2.PdfReader(f)
                        for page in reader.pages:
                            text += (page.extract_text() or "") + "\n"
                except ImportError:
                    return ""
            return text[:max_chars]

        if action == "extract_text":
            text = extract_text()
            if not text.strip():
                return "Could not extract text (may be scanned/image PDF)."
            out = self._output_path(path, "text", ".txt")
            out.write_text(text, encoding="utf-8")
            return f"Text extracted ({len(text)} chars). Saved: {out.name}"

        if action == "info":
            try:
                import pdfplumber
                with pdfplumber.open(path) as pdf:
                    pages = len(pdf.pages)
                return f"PDF: {pages} pages, size: {self._file_size_str(path)}"
            except Exception:
                return f"PDF: {self._file_size_str(path)}"

        if action == "to_word":
            text = extract_text()
            if not text:
                return "Could not extract text to convert."
            try:
                from docx import Document
                doc = Document()
                doc.add_heading(path.stem, 0)
                for para in text.split("\n\n"):
                    if para.strip():
                        doc.add_paragraph(para.strip())
                out = self._output_path(path, "converted", ".docx")
                doc.save(out)
                return f"Converted to Word. Saved: {out.name}"
            except ImportError:
                return "python-docx not installed."

        if action in ("summarize", "analyze", "reformat"):
            text = extract_text()
            if not text.strip():
                return "Could not extract text from PDF."
            prompt_map = {
                "summarize": f"Summarize this document concisely:\n\n{text[:30000]}",
                "analyze": f"Analyze this document thoroughly:\n\n{text[:30000]}",
                "reformat": f"Reformat this text with clean structure:\n\n{text[:30000]}",
            }
            result = _ollama_analyze(prompt_map.get(action, f"Analyze:\n\n{text[:30000]}"))
            if len(result) > 600 and params.get("save", True):
                out = self._output_path(path, action, ".txt")
                out.write_text(result, encoding="utf-8")
                return f"{result[:400]}...\n\nFull result saved: {out.name}"
            return result

        return f"PDF action '{action}'. Try: summarize, extract_text, info, to_word"

    # ==================== TEXT/DOCX PROCESSOR ====================
    def _process_text_doc(self, path: Path, file_type: str, action: str, params: dict) -> str:
        action = action or "summarize"

        def read_content():
            if file_type == "docx":
                try:
                    from docx import Document
                    doc = Document(path)
                    return "\n".join(p.text for p in doc.paragraphs)
                except ImportError:
                    return "python-docx not installed."
            else:
                return path.read_text(encoding="utf-8", errors="ignore")

        content = read_content()
        if not content.strip():
            return "File appears empty."

        if action == "word_count":
            words = len(content.split())
            chars = len(content)
            lines = content.count("\n")
            return f"{words} words, {chars} characters, {lines} lines."

        if action == "extract_text":
            if file_type != "txt":
                out = self._output_path(path, "extracted", ".txt")
                out.write_text(content, encoding="utf-8")
                return f"Text extracted. Saved: {out.name}"
            return content[:2000]

        prompt_map = {
            "summarize": f"Summarize concisely:\n\n{content[:30000]}",
            "analyze": f"Analyze this document:\n\n{content[:30000]}",
            "reformat": f"Reformat with clean structure:\n\n{content[:30000]}",
            "fix": f"Fix grammar and style:\n\n{content[:30000]}",
            "to_bullet": f"Convert to bullet-point summary:\n\n{content[:30000]}",
        }

        instruction = params.get("instruction", "")
        if action == "custom" or action not in prompt_map:
            prompt = f"{instruction or action}\n\n{content[:30000]}"
        else:
            prompt = prompt_map[action]

        result = _ollama_analyze(prompt)
        if len(result) > 600 and params.get("save", True):
            out = self._output_path(path, action, ".txt")
            out.write_text(result, encoding="utf-8")
            return f"{result[:400]}...\n\nSaved: {out.name}"
        return result

    # ==================== DATA PROCESSOR (CSV/EXCEL) ====================
    def _process_data(self, path: Path, file_type: str, action: str, params: dict) -> str:
        try:
            import pandas as pd
        except ImportError:
            return "pandas not installed. Run: pip install pandas openpyxl"

        action = action or "analyze"
        try:
            df = pd.read_csv(path) if file_type == "csv" else pd.read_excel(path)
        except Exception as e:
            return f"Could not read file: {e}"

        if action == "info":
            return (f"Rows: {len(df)}, Columns: {len(df.columns)}\n"
                    f"Columns: {', '.join(df.columns.tolist())}\nSize: {self._file_size_str(path)}")

        if action == "stats":
            try:
                return f"Statistics:\n{df.describe(include='all').to_string()[:2000]}"
            except Exception as e:
                return f"Stats failed: {e}"

        if action == "analyze":
            preview = df.head(50).to_string()
            prompt = (f"Analyze this dataset. Columns: {list(df.columns)}, Rows: {len(df)}\n"
                      f"Preview:\n{preview}\nGive insights and patterns.")
            return _ollama_analyze(prompt)

        if action in ("convert", "to_csv", "to_excel", "to_json"):
            fmt = {"to_csv": "csv", "to_excel": "xlsx", "to_json": "json",
                   "convert": params.get("format", "csv")}.get(action, "csv")
            try:
                out = self._output_path(path, "converted", f".{fmt}")
                if fmt == "csv": df.to_csv(out, index=False)
                elif fmt == "xlsx": df.to_excel(out, index=False)
                elif fmt == "json": df.to_json(out, orient="records", indent=2)
                return f"Converted to {fmt.upper()}. Saved: {out.name}"
            except Exception as e:
                return f"Convert failed: {e}"

        if action == "filter":
            col = params.get("column", "")
            value = params.get("value", "")
            cond = params.get("condition", "equals")
            if not col or col not in df.columns:
                return f"Column '{col}' not found. Available: {', '.join(df.columns)}"
            try:
                if cond == "contains": filtered = df[df[col].astype(str).str.contains(str(value), case=False)]
                elif cond == "gt": filtered = df[df[col] > float(value)]
                elif cond == "lt": filtered = df[df[col] < float(value)]
                else: filtered = df[df[col] == value]
                out = self._output_path(path, "filtered", ".csv")
                filtered.to_csv(out, index=False)
                return f"Filtered: {len(filtered)} rows. Saved: {out.name}"
            except Exception as e:
                return f"Filter failed: {e}"

        if action == "sort":
            col = params.get("column", df.columns[0])
            asc = params.get("ascending", True)
            try:
                sorted_df = df.sort_values(col, ascending=asc)
                out = self._output_path(path, "sorted", ".csv")
                sorted_df.to_csv(out, index=False)
                return f"Sorted by '{col}'. Saved: {out.name}"
            except Exception as e:
                return f"Sort failed: {e}"

        preview = df.head(30).to_string()
        return _ollama_analyze(f"Task: {action}\nDataset ({len(df)} rows):\n{preview}")

    # ==================== JSON PROCESSOR ====================
    def _process_json(self, path: Path, action: str, params: dict) -> str:
        action = action or "analyze"
        try:
            content = path.read_text(encoding="utf-8")
            data = json.loads(content)
        except Exception as e:
            return f"Invalid JSON: {e}"

        if action == "validate":
            return f"Valid JSON. Type: {type(data).__name__}, size: {self._file_size_str(path)}"

        if action == "format":
            out = self._output_path(path, "formatted", ".json")
            out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return f"Formatted JSON saved: {out.name}"

        preview = json.dumps(data, indent=2)[:8000]
        instruction = params.get("instruction", "")
        prompt = f"{instruction or action} this JSON:\n{preview}"
        result = _ollama_analyze(prompt)
        if len(result) > 600 and params.get("save", True):
            out = self._output_path(path, action, ".txt")
            out.write_text(result, encoding="utf-8")
            return f"{result[:400]}...\n\nSaved: {out.name}"
        return result

    # ==================== CODE PROCESSOR ====================
    def _process_code(self, path: Path, action: str, params: dict) -> str:
        action = action or "explain"
        content = path.read_text(encoding="utf-8", errors="ignore")
        ext = path.suffix.lstrip(".")

        if action == "run" and ext == "py":
            try:
                result = subprocess.run(["python", str(path)], capture_output=True, text=True, timeout=30)
                out = result.stdout or result.stderr
                return f"Output:\n{out[:2000]}" if out else "No output."
            except subprocess.TimeoutExpired:
                return "Execution timed out (30s)."
            except Exception as e:
                return f"Run failed: {e}"

        if action == "info":
            lines = content.count("\n")
            return f"Code: {lines} lines, {len(content.split())} words, {self._file_size_str(path)}"

        prompt_map = {
            "explain": f"Explain this {ext} code clearly:\n\n```{ext}\n{content[:25000]}\n```",
            "review": f"Review this {ext} code for bugs and improvements:\n\n```{ext}\n{content[:25000]}\n```",
            "fix": f"Fix bugs in this {ext} code. Return corrected version:\n\n```{ext}\n{content[:25000]}\n```",
            "optimize": f"Optimize this {ext} code:\n\n```{ext}\n{content[:25000]}\n```",
            "document": f"Add documentation to this {ext} code:\n\n```{ext}\n{content[:25000]}\n```",
            "summarize": f"Summarize what this {ext} code does:\n\n```{ext}\n{content[:25000]}\n```",
            "test": f"Write unit tests for this {ext} code:\n\n```{ext}\n{content[:25000]}\n```",
        }

        instruction = params.get("instruction", "")
        prompt = prompt_map.get(action, f"{instruction or action}\n\n```{ext}\n{content[:25000]}\n```")
        result = _ollama_analyze(prompt, max_tokens=1024)

        if action in ("fix", "optimize", "document") and params.get("save", True):
            out = self._output_path(path, action)
            code_match = re.search(r"```(?:\w+)?\n(.*?)```", result, re.DOTALL)
            code_to_save = code_match.group(1) if code_match else result
            out.write_text(code_to_save, encoding="utf-8")
            return f"{result[:400]}...\n\nSaved: {out.name}"
        return result

    # ==================== AUDIO PROCESSOR ====================
    def _process_audio(self, path: Path, action: str, params: dict) -> str:
        action = action or "info"

        if action == "info":
            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_file(path)
                duration = len(audio) / 1000
                mins, secs = divmod(int(duration), 60)
                return (f"Audio: {mins}m {secs}s, {audio.channels}ch, "
                        f"{audio.frame_rate}Hz, {self._file_size_str(path)}")
            except ImportError:
                return f"Audio: {self._file_size_str(path)}. Install pydub for details."
            except Exception as e:
                return f"Info failed: {e}"

        if action == "transcribe":
            return ("Audio transcription requires Whisper model. "
                    "Install: pip install openai-whisper\n"
                    f"File: {path.name}, size: {self._file_size_str(path)}")

        if action == "convert":
            fmt = params.get("format", "mp3").lstrip(".")
            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_file(path)
                out = self._output_path(path, "converted", f".{fmt}")
                audio.export(out, format=fmt)
                return f"Converted to {fmt.upper()}. Saved: {out.name}"
            except ImportError:
                return "pydub not installed."
            except Exception as e:
                return f"Convert failed: {e}"

        return f"Audio action '{action}'. Try: info, transcribe, convert"

    # ==================== VIDEO PROCESSOR ====================
    def _process_video(self, path: Path, action: str, params: dict) -> str:
        action = action or "info"

        def ffmpeg_ok():
            try:
                subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=3)
                return True
            except Exception:
                return False

        if action == "info":
            try:
                result = subprocess.run(
                    ["ffprobe", "-v", "quiet", "-print_format", "json",
                     "-show_format", "-show_streams", str(path)],
                    capture_output=True, text=True, timeout=10)
                data = json.loads(result.stdout)
                fmt = data.get("format", {})
                duration = float(fmt.get("duration", 0))
                mins, secs = divmod(int(duration), 60)
                vs = next((s for s in data.get("streams", []) if s["codec_type"] == "video"), {})
                return (f"Video: {mins}m {secs}s, {vs.get('width','?')}x{vs.get('height','?')}, "
                        f"{self._file_size_str(path)}")
            except Exception:
                return f"Video: {self._file_size_str(path)}"

        if action == "extract_audio":
            if not ffmpeg_ok(): return "ffmpeg not found."
            out = self._output_path(path, "audio", ".mp3")
            try:
                subprocess.run(["ffmpeg", "-i", str(path), "-q:a", "0", "-map", "a",
                                str(out), "-y"], capture_output=True, timeout=300)
                return f"Audio extracted. Saved: {out.name}"
            except Exception as e:
                return f"Failed: {e}"

        if action == "extract_frame":
            ts = params.get("timestamp", "00:00:01")
            if not ffmpeg_ok(): return "ffmpeg not found."
            out = self._output_path(path, f"frame", ".jpg")
            try:
                subprocess.run(["ffmpeg", "-i", str(path), "-ss", ts,
                                "-vframes", "1", str(out), "-y"], capture_output=True, timeout=30)
                return f"Frame at {ts}. Saved: {out.name}"
            except Exception as e:
                return f"Failed: {e}"

        if action == "compress":
            crf = int(params.get("quality", 28))
            if not ffmpeg_ok(): return "ffmpeg not found."
            out = self._output_path(path, f"compressed_crf{crf}", ".mp4")
            try:
                subprocess.run(["ffmpeg", "-i", str(path), "-c:v", "libx264", "-crf", str(crf),
                                "-preset", "medium", "-c:a", "copy", str(out), "-y"],
                               capture_output=True, timeout=1800)
                return f"Compressed: {self._file_size_str(path)} → {self._file_size_str(out)}. Saved: {out.name}"
            except Exception as e:
                return f"Failed: {e}"

        return f"Video action '{action}'. Try: info, extract_audio, extract_frame, compress"

    # ==================== ARCHIVE PROCESSOR ====================
    def _process_archive(self, path: Path, action: str, params: dict) -> str:
        action = action or "list"

        if action == "list":
            try:
                import zipfile, tarfile
                ext = path.suffix.lower()
                if ext == ".zip":
                    with zipfile.ZipFile(path) as z: names = z.namelist()
                elif ext in (".tar", ".gz", ".bz2"):
                    with tarfile.open(path) as t: names = t.getnames()
                else:
                    return f"Unsupported archive: {ext}"
                preview = "\n".join(names[:30])
                suffix = f"\n... and {len(names)-30} more" if len(names) > 30 else ""
                return f"{len(names)} files:\n{preview}{suffix}"
            except Exception as e:
                return f"List failed: {e}"

        if action == "extract":
            dest = Path(params.get("destination", str(path.parent / path.stem)))
            dest.mkdir(parents=True, exist_ok=True)
            try:
                shutil.unpack_archive(path, dest)
                return f"Extracted to: {dest}"
            except Exception as e:
                return f"Extract failed: {e}"

        return f"Archive action '{action}'. Try: list, extract"

    # ==================== PPTX PROCESSOR ====================
    def _process_pptx(self, path: Path, action: str, params: dict) -> str:
        action = action or "summarize"

        def read_pptx():
            try:
                from pptx import Presentation
                prs = Presentation(path)
                text = []
                for i, slide in enumerate(prs.slides, 1):
                    slide_text = f"\n--- Slide {i} ---\n"
                    for shape in slide.shapes:
                        if hasattr(shape, "text") and shape.text.strip():
                            slide_text += shape.text.strip() + "\n"
                    text.append(slide_text)
                return "\n".join(text)
            except ImportError:
                return "python-pptx not installed."

        if action == "extract_text":
            text = read_pptx()
            out = self._output_path(path, "text", ".txt")
            out.write_text(text, encoding="utf-8")
            return f"Text extracted. Saved: {out.name}"

        text = read_pptx()
        prompt = f"{'Summarize' if action == 'summarize' else 'Analyze'} this presentation:\n{text[:25000]}"
        result = _ollama_analyze(prompt)
        if len(result) > 600 and params.get("save", True):
            out = self._output_path(path, action, ".txt")
            out.write_text(result, encoding="utf-8")
            return f"{result[:400]}...\n\nSaved: {out.name}"
        return result

    # ==================== PUBLIC API ====================
    def get_file_context(self, filename: str = None) -> str:
        """Get file content for LLM context injection."""
        if filename and filename in self.file_contents_cache:
            content = self.file_contents_cache[filename]
            return f"\n\nUPLOADED FILE ({filename}):\n{content[:3000]}\n"
        if self.uploaded_files:
            contexts = []
            for f in self.uploaded_files[-3:]:
                preview = f.get("content_preview", "")
                if preview:
                    contexts.append(f"FILE: {f['name']} ({f['type']}, {f['size_str']})\n{preview}")
            if contexts:
                return "\n\nUPLOADED FILES:\n" + "\n\n---\n\n".join(contexts)
        return ""

    def list_uploaded_files(self) -> str:
        if not self.uploaded_files:
            return "No files uploaded yet, Sir."
        lines = [f"You have {len(self.uploaded_files)} file(s), Sir:"]
        for i, f in enumerate(self.uploaded_files[-10:], 1):
            lines.append(f"{i}. {f['name']} ({f['size_str']}, {f['type']})")
        return "\n".join(lines)

    def clear_files(self):
        count = len(self.uploaded_files)
        self.uploaded_files.clear()
        self.file_contents_cache.clear()
        return f"Cleared {count} file(s), Sir."


# Global Singleton
hex_file_upload = HexFileUpload()