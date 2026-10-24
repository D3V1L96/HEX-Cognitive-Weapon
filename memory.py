_short_memory = []
_preferences = {}

def remember(text: str, emotion: str):
    _short_memory.append({"text": text, "emotion": emotion})
    if len(_short_memory) > 10:
        _short_memory.pop(0)

def remember_preference(key, value):
    _preferences[key] = value

def build_context() -> str:
    ctx = "Recent conversation:\n"
    for m in _short_memory:
        ctx += f"- ({m['emotion']}) {m['text']}\n"
    if _preferences:
        ctx += "\nUser preferences:\n"
        for k, v in _preferences.items():
            ctx += f"- {k}: {v}\n"
    return ctx
