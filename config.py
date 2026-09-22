import json
import os

def get_config_path():
    appdata = os.getenv('APPDATA')
    if appdata:
        cfg_dir = os.path.join(appdata, "LensCapture")
        os.makedirs(cfg_dir, exist_ok=True)
        return os.path.join(cfg_dir, "config.json")
    return "config.json"

CONFIG_FILE = get_config_path()

DEFAULT_CONFIG = {
    "mode": "analysis",  # "translation" or "analysis"
    "target_language": "Spanish",
    "hotkey": "print screen",
    "drawing_color": "#ff0000"
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Merge with defaults to ensure all keys exist
            config = DEFAULT_CONFIG.copy()
            config.update(data)
            return config
    except Exception as e:
        print(f"Error loading config: {e}")
        return DEFAULT_CONFIG.copy()

def save_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error saving config: {e}")
