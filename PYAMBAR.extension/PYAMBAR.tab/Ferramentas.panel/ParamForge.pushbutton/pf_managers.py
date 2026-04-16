# -*- coding: utf-8 -*-
"""
ParamForge - State e Preset managers.
"""
import codecs
import json
import os
from datetime import datetime

APPDATA = os.getenv('APPDATA')
STATE_DIR = os.path.join(APPDATA, "ParamForge")
if not os.path.exists(STATE_DIR):
    try:
        os.makedirs(STATE_DIR)
    except Exception as e:
        pass

STATE_FILE = os.path.join(STATE_DIR, "user_state.json")

PRESETS_DIR = os.path.join(STATE_DIR, "presets")
if not os.path.exists(PRESETS_DIR):
    try:
        os.makedirs(PRESETS_DIR)
    except Exception as e:
        pass


class StateManager(object):
    @staticmethod
    def load():
        if os.path.exists(STATE_FILE):
            try:
                with codecs.open(STATE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                pass
        return {}

    @staticmethod
    def save(data):
        try:
            with codecs.open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            pass


class PresetManager(object):
    @staticmethod
    def list_presets():
        try:
            if not os.path.exists(PRESETS_DIR):
                return []
            presets = []
            for filename in os.listdir(PRESETS_DIR):
                if filename.endswith('.json'):
                    presets.append(filename[:-5])
            return sorted(presets)
        except Exception as e:
            return []

    @staticmethod
    def save_preset(name, colors_data):
        try:
            filename = os.path.join(PRESETS_DIR, "{}.json".format(name))
            preset = {
                "name": name,
                "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "colors": colors_data
            }
            with codecs.open(filename, 'w', encoding='utf-8') as f:
                json.dump(preset, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            return False

    @staticmethod
    def load_preset(name):
        try:
            filename = os.path.join(PRESETS_DIR, "{}.json".format(name))
            if os.path.exists(filename):
                with codecs.open(filename, 'r', encoding='utf-8') as f:
                    preset = json.load(f)
                return preset.get("colors", {})
            return None
        except Exception as e:
            return None

    @staticmethod
    def delete_preset(name):
        try:
            filename = os.path.join(PRESETS_DIR, "{}.json".format(name))
            if os.path.exists(filename):
                os.remove(filename)
                return True
            return False
        except Exception as e:
            return False
