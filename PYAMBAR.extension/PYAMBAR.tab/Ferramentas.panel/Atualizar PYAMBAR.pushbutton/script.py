# -*- coding: utf-8 -*-
__title__ = "Atualizar\nPYAMBAR"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "1.0"
__doc__ = """Verifica atualizacoes do PYAMBAR no GitHub.
Se houver nova versao, baixa, instala e recarrega o pyRevit."""

import os
import json
import shutil
import zipfile
import tempfile
import codecs
from distutils.dir_util import copy_tree

import clr
clr.AddReference('System')
from System.Net import WebClient, WebRequest
from System.IO import StreamReader

from pyrevit import forms
from pyrevit.loader import sessionmgr

# ── Constantes ────────────────────────────────────────────────────────────────
GITHUB_RAW = "https://raw.githubusercontent.com/thiagobarretosn-hue/PYAMBAR/main/PYAMBAR.extension/extension.json"
GITHUB_ZIP = "https://github.com/thiagobarretosn-hue/PYAMBAR/archive/refs/heads/main.zip"
# script.py: PYAMBAR.extension/PYAMBAR.tab/Ferramentas.panel/Atualizar PYAMBAR.pushbutton/script.py
EXT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def parse_ver(v):
    try:
        return tuple(int(x) for x in str(v).split('.'))
    except Exception:
        return (0, 0, 0)


def get_local_version():
    try:
        with codecs.open(os.path.join(EXT_ROOT, 'extension.json'), 'r', 'utf-8') as f:
            return json.load(f).get('version', '0.0.0')
    except Exception:
        return '0.0.0'


def get_remote_data():
    req = WebRequest.Create(GITHUB_RAW)
    req.Timeout = 8000
    resp = req.GetResponse()
    reader = StreamReader(resp.GetResponseStream())
    raw = reader.ReadToEnd()
    resp.Close()
    return json.loads(raw)


def full_replace_update(src_root, dst_root):
    # copy_tree sobrescreve arquivos existentes sem deletar dst_root,
    # evitando erro de file-lock quando o script roda de dentro de dst_root
    copy_tree(src_root, dst_root, update=0)


def main():
    local_ver = get_local_version()

    # ── Verificar versao remota ───────────────────────────────────────────────
    try:
        data       = get_remote_data()
        remote_ver = data.get('version', '0.0.0')
        whats_new  = data.get('whats_new', '').strip()
    except Exception as e:
        forms.alert(
            "Nao foi possivel conectar ao GitHub.\n\n{}".format(str(e)),
            title="PYAMBAR Updater", warn_icon=True
        )
        return

    # ── Ja esta atualizado ────────────────────────────────────────────────────
    if parse_ver(remote_ver) <= parse_ver(local_ver):
        forms.alert(
            "PYAMBAR esta atualizado!\n\nVersao instalada: {}".format(local_ver),
            title="PYAMBAR Updater"
        )
        return

    # ── Oferecer atualizacao ──────────────────────────────────────────────────
    msg = "Nova versao disponivel!\n\nInstalada: {}\nDisponivel: {}\n\n{}".format(
        local_ver, remote_ver,
        whats_new if whats_new else "Clique OK para atualizar e recarregar o pyRevit."
    )

    resultado = forms.alert(msg, title="PYAMBAR Updater",
                            options=["Atualizar", "Cancelar"], warn_icon=False)
    if resultado != "Atualizar":
        return

    # ── Download ──────────────────────────────────────────────────────────────
    tmp_zip = os.path.join(tempfile.gettempdir(), 'pyambar_update.zip')
    tmp_dir = os.path.join(tempfile.gettempdir(), 'pyambar_update_ext')

    try:
        wc = WebClient()
        wc.DownloadFile(GITHUB_ZIP, tmp_zip)

        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)
        os.makedirs(tmp_dir)

        with zipfile.ZipFile(tmp_zip, 'r') as zf:
            zf.extractall(tmp_dir)

        repo_dirs = [d for d in os.listdir(tmp_dir)
                     if os.path.isdir(os.path.join(tmp_dir, d))]
        if not repo_dirs:
            raise Exception("Estrutura do ZIP inesperada.")

        src = os.path.join(tmp_dir, repo_dirs[0], 'PYAMBAR.extension')
        if not os.path.exists(src):
            raise Exception("PYAMBAR.extension nao encontrada no ZIP.")

        full_replace_update(src, EXT_ROOT)

    except Exception as e:
        forms.alert(
            "Erro durante o download/instalacao:\n\n{}".format(str(e)),
            title="PYAMBAR Updater", warn_icon=True
        )
        return
    finally:
        try:
            os.remove(tmp_zip)
        except Exception:
            pass
        try:
            shutil.rmtree(tmp_dir)
        except Exception:
            pass

    # ── Recarregar pyRevit ────────────────────────────────────────────────────
    forms.alert(
        "PYAMBAR {} instalado com sucesso!\n\nO pyRevit sera recarregado agora.".format(remote_ver),
        title="PYAMBAR Updater"
    )
    sessionmgr.reload_pyrevit()


main()
