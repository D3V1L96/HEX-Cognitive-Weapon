import logging

logging.basicConfig(level=logging.INFO, format='[LangMod] %(message)s')
logger = logging.getLogger(__name__)


class CodeLanguageDatabase:
    """
    Comprehensive Database of Programming Languages.
    Contains extensions, runtimes, and compilation commands for 50+ languages.
    """

    def __init__(self):
        # Structure: { "language_name": { "ext": ".xyz", "runtime": ["cmd"], "compiler": ["cmd"] } }
        self.languages = {
            # --- Scripting & Automation (High Priority) ---
            "python": {"ext": ".py", "runtime": ["py", "-3.11"], "alias": ["py", "python3"]},
            "bash": {"ext": ".sh", "runtime": ["bash"], "alias": ["shell", "sh", "script"]},
            "powershell": {"ext": ".ps1", "runtime": ["powershell", "-File"], "alias": ["ps", "pwsh"]},
            "perl": {"ext": ".pl", "runtime": ["perl"], "alias": []},
            "ruby": {"ext": ".rb", "runtime": ["ruby"], "alias": ["rb"]},
            "lua": {"ext": ".lua", "runtime": ["lua"], "alias": []},
            "php": {"ext": ".php", "runtime": ["php"], "alias": []},

            # --- Web Development ---
            "javascript": {"ext": ".js", "runtime": ["node"], "alias": ["js", "node"]},
            "typescript": {"ext": ".ts", "runtime": ["npx", "ts-node"], "alias": ["ts"]},
            "html": {"ext": ".html", "runtime": ["start"], "alias": ["web"]},  # 'start' opens in browser
            "css": {"ext": ".css", "runtime": None, "alias": []},
            "react": {"ext": ".jsx", "runtime": ["npm", "start"], "alias": ["jsx"]},
            "vue": {"ext": ".vue", "runtime": ["npm", "run", "serve"], "alias": []},

            # --- System & Low Level ---
            "c": {"ext": ".c", "compiler": ["gcc"], "runtime": ["./a.out"], "alias": []},
            "cpp": {"ext": ".cpp", "compiler": ["g++"], "runtime": ["./a.out"], "alias": ["c++", "cxx"]},
            "rust": {"ext": ".rs", "compiler": ["cargo", "build"], "runtime": ["cargo", "run"], "alias": ["rs"]},
            "go": {"ext": ".go", "runtime": ["go", "run"], "alias": ["golang"]},
            "assembly": {"ext": ".asm", "compiler": ["nasm"], "alias": ["asm", "nasm"]},

            # --- Enterprise & JVM ---
            "java": {"ext": ".java", "compiler": ["javac"], "runtime": ["java"], "alias": []},
            "kotlin": {"ext": ".kt", "compiler": ["kotlinc"], "runtime": ["kotlin"], "alias": []},
            "scala": {"ext": ".scala", "runtime": ["scala"], "alias": []},
            "groovy": {"ext": ".groovy", "runtime": ["groovy"], "alias": []},

            # --- Microsoft Ecosystem ---
            "csharp": {"ext": ".cs", "compiler": ["csc"], "runtime": ["dotnet", "run"], "alias": ["c#", "cs"]},
            "fsharp": {"ext": ".fs", "runtime": ["dotnet", "fsi"], "alias": ["f#"]},
            "vb": {"ext": ".vb", "compiler": ["vbc"], "alias": ["visual basic"]},

            # --- Data Science & Math ---
            "r": {"ext": ".r", "runtime": ["Rscript"], "alias": ["rlang"]},
            "julia": {"ext": ".jl", "runtime": ["julia"], "alias": []},
            "matlab": {"ext": ".m", "runtime": ["matlab", "-batch"], "alias": ["m"]},
            "fortran": {"ext": ".f90", "compiler": ["gfortran"], "alias": ["f90"]},

            # --- Mobile & Cross Platform ---
            "swift": {"ext": ".swift", "runtime": ["swift"], "alias": []},
            "dart": {"ext": ".dart", "runtime": ["dart"], "alias": ["flutter"]},
            "kotlin_android": {"ext": ".kt", "runtime": ["gradle", "run"], "alias": []},

            # --- Functional & Niche ---
            "haskell": {"ext": ".hs", "runtime": ["ghc"], "alias": []},
            "elixir": {"ext": ".ex", "runtime": ["elixir"], "alias": []},
            "erlang": {"ext": ".erl", "runtime": ["erl"], "alias": []},
            "clojure": {"ext": ".clj", "runtime": ["clojure"], "alias": []},
            "lisp": {"ext": ".lisp", "runtime": ["sbcl"], "alias": []},
            "scheme": {"ext": ".scm", "runtime": ["guile"], "alias": []},

            # --- Config & Markup ---
            "json": {"ext": ".json", "runtime": None, "alias": []},
            "xml": {"ext": ".xml", "runtime": None, "alias": []},
            "yaml": {"ext": ".yaml", "runtime": None, "alias": ["yml"]},
            "markdown": {"ext": ".md", "runtime": None, "alias": ["md"]},
            "sql": {"ext": ".sql", "runtime": ["sqlite3"], "alias": ["database"]},
            "graphql": {"ext": ".graphql", "runtime": None, "alias": []},

            # --- Legacy & Mainframe ---
            "cobol": {"ext": ".cob", "compiler": ["cobc"], "alias": []},
            "pascal": {"ext": ".pas", "compiler": ["fpc"], "alias": []},
            "ada": {"ext": ".adb", "compiler": ["gnatmake"], "alias": []},
        }

        logger.info(f"Language Database Loaded: {len(self.languages)} languages ready.")

    def get_language_info(self, lang_name):
        """Get details for a specific language."""
        lang_lower = lang_name.lower().strip()

        # Direct match
        if lang_lower in self.languages:
            return self.languages[lang_lower]

        # Alias match
        for name, info in self.languages.items():
            if lang_lower in info.get("alias", []):
                return info

        # Partial match (e.g., "py" matches "python")
        for name, info in self.languages.items():
            if lang_lower in name or name in lang_lower:
                return info

        return None

    def get_all_languages(self):
        """Return list of all supported languages."""
        return list(self.languages.keys())


# Global Singleton
lang_db = CodeLanguageDatabase()