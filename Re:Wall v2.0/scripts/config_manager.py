import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "pause_fullscreen": True,
    "autostart": False,
    "volume": 0.0,
    "playback_rate": 1.0,
    "target_fps": 0,
    "manual_paused": False,
    "theme": "neon",
    "wallpaper_folder": os.path.expanduser("~/Vídeos/Hidamari"),
}


def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG.copy())
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        config = DEFAULT_CONFIG.copy()
        if isinstance(data, dict):
            config.update(data)
        return config
    except Exception as exc:
        print(f"[Config Manager] Falha ao ler JSON: {exc}")
        return DEFAULT_CONFIG.copy()


def save_config(config_data):
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
        return True
    except Exception as exc:
        print(f"[Config Manager] Falha ao gravar JSON: {exc}")
        return False
