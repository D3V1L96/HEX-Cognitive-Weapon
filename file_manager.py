import os
import shutil
import logging
import chardet
import PyPDF2
import docx
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='[FileMgr] %(message)s')
logger = logging.getLogger(__name__)


class HexFileManager:
    """
    Advanced File Management System.
    Features: CRUD, Smart Search, Content Extraction, Summarization.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        logger.info("Advanced File Manager Ready")

    # ==================== BASIC OPERATIONS ====================

    def create_item(self, path, item_type="file"):
        """Create a new file or folder."""
        try:
            full_path = os.path.abspath(path)
            if item_type == "folder":
                os.makedirs(full_path, exist_ok=True)
                return f"Folder '{os.path.basename(full_path)}' created, Sir."
            else:
                # Create empty file if not exists
                if not os.path.exists(full_path):
                    with open(full_path, 'w') as f:
                        pass
                return f"File '{os.path.basename(full_path)}' created, Sir."
        except Exception as err:
            return f"Error creating item: {err}, Sir."

    def delete_item(self, path):
        """Delete a file or folder safely."""
        try:
            full_path = os.path.abspath(path)
            if not os.path.exists(full_path):
                return f"{path} does not exist, Sir."

            if os.path.isdir(full_path):
                shutil.rmtree(full_path)
                return f"Folder '{os.path.basename(full_path)}' and its contents deleted, Sir."
            else:
                os.remove(full_path)
                return f"File '{os.path.basename(full_path)}' deleted, Sir."
        except Exception as err:
            return f"Error deleting item: {err}, Sir."

    def rename_item(self, old_path, new_name):
        """Rename a file or folder."""
        try:
            full_old = os.path.abspath(old_path)
            if not os.path.exists(full_old):
                return f"{old_path} not found, Sir."

            parent_dir = os.path.dirname(full_old)
            new_full_path = os.path.join(parent_dir, new_name)

            os.rename(full_old, new_full_path)
            return f"Renamed to '{new_name}', Sir."
        except Exception as err:
            return f"Error renaming: {err}, Sir."

    def move_item(self, source_path, dest_folder):
        """Move a file or folder to a new location."""
        try:
            full_source = os.path.abspath(source_path)
            full_dest = os.path.abspath(dest_folder)

            if not os.path.exists(full_source):
                return f"Source {source_path} not found, Sir."
            if not os.path.isdir(full_dest):
                return f"Destination {dest_folder} is not a valid folder, Sir."

            shutil.move(full_source, full_dest)
            return f"Moved '{os.path.basename(full_source)}' to '{os.path.basename(full_dest)}', Sir."
        except Exception as err:
            return f"Error moving item: {err}, Sir."

    # ==================== SMART SEARCH ====================

    def find_files(self, query, search_path=None, file_type=None):
        """Smart search for files by name or extension."""
        if search_path is None:
            search_path = os.getcwd()  # Default to current project

        results = []
        query_lower = query.lower()

        try:
            for root, dirs, files in os.walk(search_path):
                # Skip hidden/system folders
                dirs[:] = [d for d in dirs if not d.startswith('.')]

                for file in files:
                    file_lower = file.lower()

                    # Match name or extension
                    if query_lower in file_lower:
                        results.append(os.path.join(root, file))

                    # If specific type requested (e.g., "pdf", "py")
                    if file_type and file_lower.endswith(f".{file_type}"):
                        if os.path.join(root, file) not in results:
                            results.append(os.path.join(root, file))

                # Limit results for speed
                if len(results) > 10:
                    break

        except Exception as err:
            return f"Search error: {err}, Sir."

        if not results:
            return f"No files found matching '{query}', Sir."

        # Return top 5 results
        display = "\n".join([f"- {os.path.basename(r)}" for r in results[:5]])
        return f"Found {len(results)} files:\n{display}"

    # ==================== DATA EXTRACTION & SUMMARY ====================

    def extract_content(self, file_path):
        """Extract text from PDF, DOCX, or TXT files."""
        full_path = os.path.abspath(file_path)
        if not os.path.exists(full_path):
            return "File not found, Sir."

        ext = os.path.splitext(full_path)[1].lower()

        try:
            if ext == ".pdf":
                return self._read_pdf(full_path)
            elif ext == ".docx":
                return self._read_docx(full_path)
            elif ext in [".txt", ".py", ".js", ".html", ".css", ".json", ".md"]:
                return self._read_text(full_path)
            else:
                return "Unsupported file format for extraction, Sir."
        except Exception as err:
            return f"Extraction failed: {err}, Sir."

    def _read_pdf(self, path):
        text = ""
        with open(path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        return text.strip()

    def _read_docx(self, path):
        doc = docx.Document(path)
        return "\n".join([para.text for para in doc.paragraphs])

    def _read_text(self, path):
        # Detect encoding automatically
        with open(path, 'rb') as f:
            raw = f.read()
            result = chardet.detect(raw)
            encoding = result['encoding']

        with open(path, 'r', encoding=encoding) as f:
            return f.read()

    def get_file_summary(self, file_path):
        """Get a summary of the file content using LLM."""
        content = self.extract_content(file_path)

        if not content:
            return "Could not extract content, Sir."

        # Truncate for LLM limit (keep first 2000 chars)
        truncated = content[:2000]

        prompt = (
            f"Summarize the following file content in 3 bullet points. "
            f"Focus on key information. Content:\n\n{truncated}"
        )

        # Call LLM (Assuming hex_voice_assistance has access to get_llm_response)
        # We will inject this logic in the main assistant
        return prompt  # Returning prompt so main assistant can process it

    def list_directory(self, path=None):
        """List files in a directory."""
        target = os.path.abspath(path) if path else os.getcwd()
        if not os.path.isdir(target):
            return f"{path} is not a valid directory, Sir."

        items = os.listdir(target)
        files = [i for i in items if os.path.isfile(os.path.join(target, i))]
        folders = [i for i in items if os.path.isdir(os.path.join(target, i))]

        response = f"Directory: {os.path.basename(target)}\n"
        if folders:
            response += f"Folders: {', '.join(folders[:5])}\n"
        if files:
            response += f"Files: {', '.join(files[:5])}"

        return response


# Global Singleton
file_manager = HexFileManager()