# -*- coding: utf-8 -*-
"""Gerencia config APPDATA por projeto e presets de agrupamento."""

import os
import json
import hashlib

_APPDATA_ROOT = os.path.join(
    os.getenv('APPDATA', os.path.expanduser('~')),
    'pyRevit', 'PYAMBAR', 'ExportPro'
)

_SEED_CONFIG = {
    'default_folder': '',
    'default_format': 'csv',
    'include_headers': True,
    'filename_template': '{projeto}_{schedule}',
    'gas_url': '',
}


def get_project_id(doc):
    path = getattr(doc, 'PathName', '') or getattr(doc, 'Title', 'unknown')
    return hashlib.md5(path.encode('utf-8')).hexdigest()[:8]


def _project_dir(doc):
    return os.path.join(_APPDATA_ROOT, get_project_id(doc))


def _ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)


def load_config(doc):
    cfg = dict(_SEED_CONFIG)
    path = os.path.join(_project_dir(doc), 'config.json')
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save_config(doc, data):
    d = _project_dir(doc)
    _ensure_dir(d)
    path = os.path.join(d, 'config.json')
    existing = load_config(doc)
    existing.update(data)
    with open(path, 'w') as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)


# -- PRESET DE PROJETO (todas as schedules) ------------------------------------

def _project_preset_path(doc):
    return os.path.join(_project_dir(doc), 'project_preset.json')


def load_project_preset(doc):
    """Retorna dict {schedule_name: [rules]} ou {} se nao existir."""
    path = _project_preset_path(doc)
    if not os.path.exists(path):
        # Compat: tentar carregar presets antigos por schedule
        return {}
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        return data.get('schedules', {})
    except Exception:
        return {}


def save_project_preset(doc, schedules_dict):
    """Salva dict {schedule_name: [rules]} como preset do projeto."""
    d = _project_dir(doc)
    _ensure_dir(d)
    with open(_project_preset_path(doc), 'w') as f:
        json.dump({'version': 2, 'schedules': schedules_dict}, f,
                  indent=2, ensure_ascii=False)


def load_preset(doc, schedule_name):
    """Retorna regras de um schedule (do projeto preset) ou None."""
    project = load_project_preset(doc)
    if schedule_name in project:
        return project[schedule_name]
    # Compat: preset antigo por schedule (arquivo individual)
    old_path = os.path.join(_project_dir(doc), 'presets',
                            _safe_filename(schedule_name) + '.json')
    if os.path.exists(old_path):
        try:
            with open(old_path, 'r') as f:
                data = json.load(f)
            return data.get('columns', data) if isinstance(data, dict) else data
        except Exception:
            pass
    return None


def export_preset_to_file(schedules_dict, path):
    with open(path, 'w') as f:
        json.dump({'version': 2, 'schedules': schedules_dict}, f,
                  indent=2, ensure_ascii=False)


def import_preset_from_file(path):
    """Retorna dict {schedule_name: [rules]}."""
    try:
        with open(path, 'r') as f:
            data = json.load(f)
    except Exception as e:
        raise ValueError('Arquivo de preset invalido: {}'.format(str(e)))
    if isinstance(data, dict):
        # Formato v2
        if 'schedules' in data:
            return data['schedules']
        # Formato v1 (regras de uma unica schedule)
        cols = data.get('columns', [])
        name = data.get('schedule_name', 'imported')
        return {name: cols}
    raise ValueError('Formato de preset nao reconhecido.')


def _safe_filename(name):
    invalid = set('/\\:*?"<>|')
    safe = ''.join(c for c in name if c not in invalid).lstrip('.')
    return safe[:100] or 'preset'
