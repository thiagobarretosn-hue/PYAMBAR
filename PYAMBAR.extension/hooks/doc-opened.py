# -*- coding: utf-8 -*-
"""
PYAMBAR Auto-Updater Hook - doc-opened
Verifica atualizacoes ao abrir documento (uma vez por sessao, max 1x/24h).
"""
from __future__ import print_function
import os
import sys
import json
import codecs
import threading
import datetime
import shutil
import zipfile
import tempfile


def main():
    try:
        import clr
        clr.AddReference('System')
        clr.AddReference('PresentationFramework')
        clr.AddReference('PresentationCore')
        clr.AddReference('WindowsBase')

        from System import Action
        from System.Net import WebRequest, WebClient
        from System.IO import StreamReader
        from System.Windows.Markup import XamlReader
        from System.Windows.Threading import Dispatcher
        from System.Windows import LogicalTreeHelper, SystemParameters
        import System.Windows

        from pyrevit import script

        # ── Guarda de sessao: rodar apenas 1x por sessao ──────────────────
        SESSION_KEY = 'PYAMBAR_UPDATE_CHECKED'
        if script.get_envvar(SESSION_KEY):
            return
        script.set_envvar(SESSION_KEY, '1')

    except Exception:
        return

    # ── Constantes ────────────────────────────────────────────────────────
    APPDATA     = os.environ.get('APPDATA', os.path.expanduser('~'))
    GITHUB_RAW  = "https://raw.githubusercontent.com/thiagobarretosn-hue/PYAMBAR/main/PYAMBAR.extension/extension.json"
    GITHUB_ZIP  = "https://github.com/thiagobarretosn-hue/PYAMBAR/archive/refs/heads/main.zip"
    STATE_DIR   = os.path.join(APPDATA, 'pyRevit', 'PYAMBAR', 'updater')
    STATE_FILE  = os.path.join(STATE_DIR, 'update_state.json')
    CHECK_HOURS = 24

    # ── State helpers ─────────────────────────────────────────────────────
    def load_state():
        try:
            if os.path.exists(STATE_FILE):
                with codecs.open(STATE_FILE, 'r', 'utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def save_state(st):
        try:
            if not os.path.exists(STATE_DIR):
                os.makedirs(STATE_DIR)
            tmp = STATE_FILE + '.tmp'
            with codecs.open(tmp, 'w', 'utf-8') as f:
                json.dump(st, f, indent=2)
            os.replace(tmp, STATE_FILE)
        except Exception:
            pass

    def parse_ver(v):
        try:
            return tuple(int(x) for x in str(v).split('.'))
        except Exception:
            return (0, 0, 0)

    def get_local_version():
        try:
            ext_json = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), 'extension.json')
            with codecs.open(ext_json, 'r', 'utf-8') as f:
                return json.load(f).get('version', '0.0.0')
        except Exception:
            return '0.0.0'

    # ── Throttle: max 1x por 24h ─────────────────────────────────────────
    state = load_state()
    last_str = state.get('last_check', '')
    if last_str:
        try:
            last = datetime.datetime.strptime(last_str[:19], '%Y-%m-%dT%H:%M:%S')
            elapsed = (datetime.datetime.now() - last).total_seconds()
            if elapsed < CHECK_HOURS * 3600:
                return
        except Exception:
            pass

    state['last_check'] = datetime.datetime.now().isoformat()
    save_state(state)

    local_ver = get_local_version()
    dispatcher = Dispatcher.CurrentDispatcher

    # ── XAML da janela de notificacao ─────────────────────────────────────
    XAML = (
        '<Window'
        ' xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"'
        ' xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"'
        ' Title="PYAMBAR Update" Width="340" SizeToContent="Height"'
        ' WindowStyle="ToolWindow" ResizeMode="NoResize"'
        ' Topmost="True" ShowInTaskbar="False">'
        '<Grid Margin="14">'
        '<Grid.RowDefinitions>'
        '<RowDefinition Height="Auto"/>'
        '<RowDefinition Height="Auto"/>'
        '<RowDefinition Height="Auto"/>'
        '<RowDefinition Height="Auto"/>'
        '</Grid.RowDefinitions>'
        '<TextBlock Grid.Row="0" Name="TxtTitle" FontSize="13" FontWeight="Bold"'
        ' Foreground="#1565C0" Margin="0,0,0,8" TextWrapping="Wrap"/>'
        '<TextBlock Grid.Row="1" Name="TxtChangelog" TextWrapping="Wrap"'
        ' FontSize="11" Margin="0,0,0,10"/>'
        '<StackPanel Grid.Row="2" Name="PnlProgress" Visibility="Collapsed"'
        ' Margin="0,0,0,10">'
        '<ProgressBar Height="8" IsIndeterminate="True"/>'
        '<TextBlock Name="TxtStatus" FontSize="10" Margin="0,4,0,0" Foreground="#555"/>'
        '</StackPanel>'
        '<StackPanel Grid.Row="3" Orientation="Horizontal"'
        ' HorizontalAlignment="Right" Margin="0,4,0,0">'
        '<Button Name="BtnUpdate" Content="Atualizar agora"'
        ' Padding="10,5" Margin="0,0,6,0"/>'
        '<Button Name="BtnLater" Content="Mais tarde"'
        ' Padding="10,5" Margin="0,0,6,0"/>'
        '<Button Name="BtnIgnore" Content="Ignorar versao"'
        ' Padding="10,5"/>'
        '</StackPanel>'
        '</Grid>'
        '</Window>'
    )

    # ── Funcao de copia sem remover diretorio (seguro em use) ─────────────
    def copy_update(src_root, dst_root):
        for root, dirs, files in os.walk(src_root):
            dirs[:] = [d for d in dirs
                       if not d.startswith('.') and d != '__pycache__']
            rel = os.path.relpath(root, src_root)
            dst_dir = os.path.join(dst_root, rel) if rel != '.' else dst_root
            if not os.path.exists(dst_dir):
                os.makedirs(dst_dir)
            for fname in files:
                if fname.endswith(('.pyc', '.pyo')):
                    continue
                shutil.copy2(os.path.join(root, fname),
                             os.path.join(dst_dir, fname))

    # ── Janela WPF de notificacao ─────────────────────────────────────────
    def show_notification(local_v, remote_v, whats_new, st):
        try:
            win = XamlReader.Parse(XAML)

            txt_title     = win.FindName('TxtTitle')
            txt_changelog = win.FindName('TxtChangelog')
            pnl_progress  = win.FindName('PnlProgress')
            txt_status    = win.FindName('TxtStatus')
            btn_update    = win.FindName('BtnUpdate')
            btn_later     = win.FindName('BtnLater')
            btn_ignore    = win.FindName('BtnIgnore')

            txt_title.Text = "PYAMBAR {} disponivel  (atual: {})".format(
                remote_v, local_v)
            txt_changelog.Text = (whats_new.strip()
                                  if whats_new else "Nova versao disponivel.")

            def on_loaded(s, e):
                area = SystemParameters.WorkArea
                win.Left = area.Right - win.ActualWidth - 20
                win.Top  = area.Bottom - win.ActualHeight - 20
            win.Loaded += on_loaded

            # ── Atualizar ─────────────────────────────────────────────────
            def do_update(s, e):
                btn_update.IsEnabled = False
                btn_later.IsEnabled  = False
                btn_ignore.IsEnabled = False
                pnl_progress.Visibility = System.Windows.Visibility.Visible

                def run():
                    try:
                        def set_st(msg):
                            m = msg
                            def inner():
                                txt_status.Text = m
                            win.Dispatcher.BeginInvoke(Action(inner))

                        set_st("Baixando atualizacao...")
                        tmp_zip = os.path.join(
                            tempfile.gettempdir(), 'pyambar_update.zip')
                        tmp_dir = os.path.join(
                            tempfile.gettempdir(), 'pyambar_update_ext')

                        wc = WebClient()
                        wc.DownloadFile(GITHUB_ZIP, tmp_zip)

                        set_st("Extraindo arquivos...")
                        if os.path.exists(tmp_dir):
                            shutil.rmtree(tmp_dir)
                        os.makedirs(tmp_dir)
                        with zipfile.ZipFile(tmp_zip, 'r') as zf:
                            zf.extractall(tmp_dir)

                        set_st("Instalando...")
                        repo_dirs = [d for d in os.listdir(tmp_dir)
                                     if os.path.isdir(
                                         os.path.join(tmp_dir, d))]
                        if not repo_dirs:
                            raise Exception("Pasta nao encontrada no ZIP.")

                        src = os.path.join(
                            tmp_dir, repo_dirs[0], 'PYAMBAR.extension')
                        dst = os.path.dirname(os.path.dirname(__file__))

                        if not os.path.exists(src):
                            raise Exception(
                                "PYAMBAR.extension nao encontrada no ZIP.")

                        copy_update(src, dst)

                        try:
                            os.remove(tmp_zip)
                        except Exception:
                            pass
                        try:
                            shutil.rmtree(tmp_dir)
                        except Exception:
                            pass

                        st_up = dict(st)
                        st_up['last_check'] = (
                            datetime.datetime.now().isoformat())
                        st_up.pop('ignored_version', None)
                        save_state(st_up)

                        def finish():
                            pnl_progress.Visibility = (
                                System.Windows.Visibility.Collapsed)
                            txt_title.Text = (
                                "PYAMBAR {} instalado com sucesso!"
                                .format(remote_v))
                            txt_changelog.Text = (
                                "Recarregue o pyRevit para aplicar "
                                "a atualizacao.")
                            btn_later.Content = "Fechar"
                            btn_later.IsEnabled = True
                        win.Dispatcher.BeginInvoke(Action(finish))

                    except Exception as ex:
                        err = str(ex)
                        def show_err():
                            pnl_progress.Visibility = (
                                System.Windows.Visibility.Collapsed)
                            txt_changelog.Text = (
                                "Erro: {}".format(err))
                            btn_update.Content = "Tentar novamente"
                            btn_update.IsEnabled = True
                            btn_later.IsEnabled = True
                        win.Dispatcher.BeginInvoke(Action(show_err))

                t = threading.Thread(target=run)
                t.daemon = True
                t.start()

            # ── Mais tarde ────────────────────────────────────────────────
            def do_later(s, e):
                win.Close()

            # ── Ignorar versao ────────────────────────────────────────────
            def do_ignore(s, e):
                st_up = dict(st)
                st_up['ignored_version'] = remote_v
                save_state(st_up)
                win.Close()

            btn_update.Click += do_update
            btn_later.Click  += do_later
            btn_ignore.Click += do_ignore

            win.Show()

        except Exception:
            pass

    # ── Background: busca versao remota ───────────────────────────────────
    def bg_check():
        try:
            req = WebRequest.Create(GITHUB_RAW)
            req.Timeout = 6000
            resp = req.GetResponse()
            reader = StreamReader(resp.GetResponseStream())
            raw_json = reader.ReadToEnd()
            resp.Close()

            data = json.loads(raw_json)
            remote_ver = data.get('version', '0.0.0')
            whats_new  = data.get('whats_new', '')

            if parse_ver(remote_ver) <= parse_ver(local_ver):
                return
            if state.get('ignored_version') == remote_ver:
                return

            rv = remote_ver
            lv = local_ver
            wn = whats_new
            st = dict(state)
            dispatcher.BeginInvoke(
                Action(lambda: show_notification(lv, rv, wn, st)))

        except Exception:
            pass  # Falha silenciosa (sem rede, GitHub indisponivel, etc.)

    t = threading.Thread(target=bg_check)
    t.daemon = True
    t.start()


try:
    main()
except Exception:
    pass  # Hook nunca deve travar o Revit
