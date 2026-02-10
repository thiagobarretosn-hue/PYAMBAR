# -*- coding: utf-8 -*-
"""
PYAMBAR Installer
Instalador/Atualizador/Desinstalador da extensao PYAMBAR para pyRevit

VERSAO: 1.1.0
AUTOR: Thiago Barreto Sobral Nunes
"""

import json
import os
import re
import shutil
import subprocess
import threading
import tkinter as tk
import zipfile
from tkinter import filedialog, messagebox, ttk
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# =============================================================================
# CONFIGURACAO
# =============================================================================

GITHUB_REPO = "thiagobarretosn-hue/PYAMBAR"
GITHUB_BRANCH = "main"
EXTENSION_NAME = "PYAMBAR.extension"
APP_VERSION = "1.1.0"
APP_TITLE = "PYAMBAR Installer"

DEFAULT_EXTENSIONS_PATH = os.path.join(os.environ.get('APPDATA', ''), 'pyRevit-Master', 'Extensions')
PYREVIT_CONFIG_PATH = os.path.join(os.environ.get('APPDATA', ''), 'pyRevit', 'pyRevit_config.ini')
PYREVIT_CLI_PATHS = [
    r"C:\Program Files\pyRevit-Master\bin\pyrevit.exe",
    r"C:\Program Files\pyRevit\bin\pyrevit.exe",
    os.path.join(os.environ.get('APPDATA', ''), 'pyRevit-Master', 'bin', 'pyrevit.exe'),
]

# =============================================================================
# FUNCOES AUXILIARES
# =============================================================================

def get_github_download_url():
    return "https://github.com/{}/archive/refs/heads/{}.zip".format(GITHUB_REPO, GITHUB_BRANCH)

def find_pyrevit_cli():
    for path in PYREVIT_CLI_PATHS:
        if os.path.exists(path):
            return path
    return None

def get_installed_version(install_path):
    json_path = os.path.join(install_path, EXTENSION_NAME, 'extension.json')
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f).get('version', 'Desconhecida')
        except:
            pass
    return None

def get_remote_version():
    try:
        req = Request("https://api.github.com/repos/{}/releases/latest".format(GITHUB_REPO))
        req.add_header('User-Agent', 'PYAMBAR-Installer')
        with urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode()).get('tag_name', 'v?.?.?').lstrip('v')
    except:
        pass
    try:
        raw_url = "https://raw.githubusercontent.com/{}/{}/PYAMBAR.extension/extension.json".format(GITHUB_REPO, GITHUB_BRANCH)
        req = Request(raw_url)
        req.add_header('User-Agent', 'PYAMBAR-Installer')
        with urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode()).get('version', '?.?.?')
    except:
        return "Erro ao verificar"

def is_pyrevit_installed():
    return find_pyrevit_cli() is not None or os.path.exists(PYREVIT_CONFIG_PATH)

def register_extension_pyrevit(extension_path):
    parent_path = os.path.dirname(extension_path)
    extension_section = "[PYAMBAR.extension]"

    cli = find_pyrevit_cli()
    if cli:
        try:
            subprocess.run([cli, 'extensions', 'paths', 'add', parent_path],
                           capture_output=True, text=True, timeout=30)
        except Exception:
            pass

    try:
        if not os.path.exists(PYREVIT_CONFIG_PATH):
            return False

        with open(PYREVIT_CONFIG_PATH, 'r', encoding='utf-8') as f:
            content = f.read()

        modified = False

        match = re.search(r'(userextensions\s*=\s*)(\[.*?\])', content)
        if match:
            try:
                current_list = json.loads(match.group(2))
            except (json.JSONDecodeError, ValueError):
                current_list = []

            norm = os.path.normpath(parent_path).lower()
            if norm not in [os.path.normpath(p).lower() for p in current_list]:
                current_list.append(parent_path)
                content = content[:match.start(2)] + json.dumps(current_list) + content[match.end(2):]
                modified = True
        else:
            core_match = re.search(r'(\[core\])', content)
            if core_match:
                content = content[:core_match.end()] + \
                    '\nuserextensions = ["{}"]'.format(parent_path.replace('\\', '\\\\')) + \
                    content[core_match.end():]
                modified = True

        if extension_section not in content:
            content += '\n{}\ndisabled = false\nprivate_repo = false\nusername = ""\npassword = ""\n'.format(extension_section)
            modified = True

        if modified:
            with open(PYREVIT_CONFIG_PATH, 'w', encoding='utf-8') as f:
                f.write(content)
        return True
    except Exception:
        return False

def unregister_extension_pyrevit(install_path):
    parent_path = install_path
    extension_section = "[PYAMBAR.extension]"

    cli = find_pyrevit_cli()
    if cli:
        try:
            subprocess.run([cli, 'extensions', 'paths', 'remove', parent_path],
                           capture_output=True, text=True, timeout=30)
        except Exception:
            pass

    try:
        if not os.path.exists(PYREVIT_CONFIG_PATH):
            return

        with open(PYREVIT_CONFIG_PATH, 'r', encoding='utf-8') as f:
            content = f.read()

        modified = False

        match = re.search(r'(userextensions\s*=\s*)(\[.*?\])', content)
        if match:
            try:
                current_list = json.loads(match.group(2))
                norm = os.path.normpath(parent_path).lower()
                new_list = [p for p in current_list if os.path.normpath(p).lower() != norm]
                if len(new_list) != len(current_list):
                    content = content[:match.start(2)] + json.dumps(new_list) + content[match.end(2):]
                    modified = True
            except (json.JSONDecodeError, ValueError):
                pass

        if extension_section in content:
            content = re.sub(r'\[PYAMBAR\.extension\][^\[]*', '', content)
            modified = True

        if modified:
            with open(PYREVIT_CONFIG_PATH, 'w', encoding='utf-8') as f:
                f.write(content)
    except Exception:
        pass

# =============================================================================
# CLASSE PRINCIPAL - GUI
# =============================================================================

class InstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("550x580")
        self.root.resizable(False, False)
        self.center_window()

        self.install_path = tk.StringVar(value=DEFAULT_EXTENSIONS_PATH)
        self.register_pyrevit = tk.BooleanVar(value=True)
        self.installed_version = tk.StringVar(value="Verificando...")
        self.remote_version = tk.StringVar(value="Verificando...")
        self.status_text = tk.StringVar(value="Pronto")
        self.progress_value = tk.DoubleVar(value=0)

        self.create_widgets()
        threading.Thread(target=self.check_versions, daemon=True).start()

    def center_window(self):
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (550 // 2)
        y = (self.root.winfo_screenheight() // 2) - (580 // 2)
        self.root.geometry('+{}+{}'.format(x, y))

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Titulo
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 20))

        ttk.Label(title_frame, text="PYAMBAR Installer",
                  font=('Segoe UI', 18, 'bold')).pack()
        ttk.Label(title_frame, text="Extensao pyRevit para workflows BIM e MEP",
                  font=('Segoe UI', 9)).pack()

        # Status
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding="10")
        status_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(status_frame, text="Versao instalada:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.installed_label = ttk.Label(status_frame, textvariable=self.installed_version,
                                          font=('Segoe UI', 9, 'bold'))
        self.installed_label.grid(row=0, column=1, sticky=tk.W, padx=10)

        ttk.Label(status_frame, text="Versao disponivel:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Label(status_frame, textvariable=self.remote_version,
                  font=('Segoe UI', 9, 'bold'), foreground='green').grid(row=1, column=1, sticky=tk.W, padx=10)

        ttk.Label(status_frame, text="pyRevit:").grid(row=2, column=0, sticky=tk.W, pady=2)
        pyrevit_ok = is_pyrevit_installed()
        ttk.Label(status_frame,
                  text="Instalado" if pyrevit_ok else "Nao encontrado",
                  font=('Segoe UI', 9, 'bold'),
                  foreground='green' if pyrevit_ok else 'red').grid(row=2, column=1, sticky=tk.W, padx=10)

        # Pasta
        path_frame = ttk.LabelFrame(main_frame, text="Pasta de Instalacao", padding="10")
        path_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Entry(path_frame, textvariable=self.install_path, width=50).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(path_frame, text="Procurar...", command=self.browse_folder).pack(side=tk.RIGHT)

        # Opcoes
        options_frame = ttk.LabelFrame(main_frame, text="Opcoes", padding="10")
        options_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Checkbutton(options_frame,
                        text="Registrar extensao no pyRevit automaticamente",
                        variable=self.register_pyrevit).pack(anchor=tk.W)

        # Progresso
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 15))

        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_value,
                                             maximum=100, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(progress_frame, textvariable=self.status_text).pack(anchor=tk.W)

        # Botoes
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        self.install_btn = ttk.Button(btn_frame, text="Instalar / Atualizar",
                                       command=self.start_installation)
        self.install_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.uninstall_btn = ttk.Button(btn_frame, text="Desinstalar",
                                         command=self.start_uninstallation)
        self.uninstall_btn.pack(side=tk.LEFT)

        ttk.Button(btn_frame, text="Fechar", command=self.root.quit).pack(side=tk.RIGHT)

        # Rodape
        footer_frame = ttk.Frame(main_frame)
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(20, 0))

        ttk.Label(footer_frame,
                  text="Installer v{} | github.com/{}".format(APP_VERSION, GITHUB_REPO),
                  font=('Segoe UI', 8), foreground='gray').pack()

        # Estado inicial dos botoes
        self._refresh_buttons()

    def _refresh_buttons(self):
        extension_path = os.path.join(self.install_path.get(), EXTENSION_NAME)
        installed = os.path.exists(extension_path)
        self.uninstall_btn.config(state='normal' if installed else 'disabled')

    def browse_folder(self):
        folder = filedialog.askdirectory(title="Selecione a pasta de instalacao",
                                          initialdir=self.install_path.get())
        if folder:
            self.install_path.set(folder)
            threading.Thread(target=self.check_versions, daemon=True).start()

    def check_versions(self):
        installed = get_installed_version(self.install_path.get())
        self.installed_version.set(installed if installed else "Nao instalado")
        self.installed_label.config(foreground='black' if installed else 'gray')
        self.remote_version.set(get_remote_version())
        self.root.after(0, self._refresh_buttons)

    def update_progress(self, value, status):
        self.progress_value.set(value)
        self.status_text.set(status)
        self.root.update_idletasks()

    def _set_buttons_state(self, state):
        self.install_btn.config(state=state)
        self.uninstall_btn.config(state=state)

    # ------------------------------------------------------------------
    # INSTALACAO
    # ------------------------------------------------------------------

    def start_installation(self):
        self._set_buttons_state('disabled')
        threading.Thread(target=self.run_installation, daemon=True).start()

    def run_installation(self):
        try:
            install_path = self.install_path.get()
            extension_path = os.path.join(install_path, EXTENSION_NAME)
            is_update = os.path.exists(extension_path)

            self.update_progress(5, "Preparando pasta de instalacao...")
            os.makedirs(install_path, exist_ok=True)

            if is_update:
                self.update_progress(10, "Criando backup da versao anterior...")
                backup_path = extension_path + "_backup"
                if os.path.exists(backup_path):
                    shutil.rmtree(backup_path)
                shutil.copytree(extension_path, backup_path)

            self.update_progress(20, "Baixando do GitHub...")
            zip_path = os.path.join(install_path, "pyambar_download.zip")

            req = Request(get_github_download_url())
            req.add_header('User-Agent', 'PYAMBAR-Installer')

            with urlopen(req, timeout=60) as response:
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0

                with open(zip_path, 'wb') as f:
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            self.update_progress(20 + (downloaded / total_size * 40),
                                                  "Baixando... {} KB".format(downloaded // 1024))

            self.update_progress(65, "Extraindo arquivos...")
            extract_path = os.path.join(install_path, "pyambar_extract")

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)

            self.update_progress(80, "Instalando extensao...")
            extracted_folders = os.listdir(extract_path)
            if extracted_folders:
                source_extension = os.path.join(extract_path, extracted_folders[0], EXTENSION_NAME)
                if os.path.exists(source_extension):
                    if os.path.exists(extension_path):
                        shutil.rmtree(extension_path)
                    shutil.copytree(source_extension, extension_path)

            self.update_progress(90, "Limpando arquivos temporarios...")
            os.remove(zip_path)
            shutil.rmtree(extract_path)

            if self.register_pyrevit.get():
                self.update_progress(95, "Registrando no pyRevit...")
                register_extension_pyrevit(extension_path)

            self.update_progress(100, "Instalacao concluida!")
            self.check_versions()

            action = "atualizado" if is_update else "instalado"
            self.root.after(0, lambda: messagebox.showinfo(
                "Sucesso",
                "PYAMBAR foi {} com sucesso!\n\nPasta: {}\n\nReinicie o Revit para carregar a extensao.".format(
                    action, extension_path)
            ))

        except HTTPError as e:
            self.update_progress(0, "Erro HTTP: {}".format(e.code))
            self.root.after(0, lambda: messagebox.showerror(
                "Erro de Download",
                "Nao foi possivel baixar do GitHub.\n\nErro: {}\n\nVerifique sua conexao com a internet.".format(e)
            ))
        except URLError as e:
            self.update_progress(0, "Erro de conexao")
            self.root.after(0, lambda: messagebox.showerror(
                "Erro de Conexao",
                "Nao foi possivel conectar ao GitHub.\n\nErro: {}\n\nVerifique sua conexao.".format(e)
            ))
        except Exception as e:
            self.update_progress(0, "Erro: {}".format(str(e)))
            self.root.after(0, lambda: messagebox.showerror(
                "Erro",
                "Ocorreu um erro durante a instalacao:\n\n{}".format(str(e))
            ))
        finally:
            self.root.after(0, lambda: self._set_buttons_state('normal'))
            self.root.after(0, self._refresh_buttons)

    # ------------------------------------------------------------------
    # DESINSTALACAO
    # ------------------------------------------------------------------

    def start_uninstallation(self):
        extension_path = os.path.join(self.install_path.get(), EXTENSION_NAME)
        if not os.path.exists(extension_path):
            messagebox.showinfo("Informacao", "PYAMBAR nao esta instalado neste computador.")
            return

        confirm = messagebox.askyesno(
            "Confirmar Desinstalacao",
            "Tem certeza que deseja remover o PYAMBAR?\n\n"
            "Pasta: {}\n\n"
            "Esta acao nao pode ser desfeita.".format(extension_path),
            icon='warning'
        )
        if not confirm:
            return

        self._set_buttons_state('disabled')
        threading.Thread(target=self.run_uninstallation, daemon=True).start()

    def run_uninstallation(self):
        try:
            install_path = self.install_path.get()
            extension_path = os.path.join(install_path, EXTENSION_NAME)

            self.update_progress(30, "Removendo arquivos...")
            shutil.rmtree(extension_path)

            self.update_progress(70, "Desregistrando do pyRevit...")
            unregister_extension_pyrevit(install_path)

            self.update_progress(100, "Desinstalacao concluida.")
            self.check_versions()

            self.root.after(0, lambda: messagebox.showinfo(
                "Concluido",
                "PYAMBAR foi removido com sucesso.\n\nReinicie o Revit para aplicar a remocao."
            ))

        except PermissionError:
            self.update_progress(0, "Erro: sem permissao")
            self.root.after(0, lambda: messagebox.showerror(
                "Erro de Permissao",
                "Nao foi possivel remover os arquivos.\n\n"
                "Feche o Revit e tente novamente."
            ))
        except Exception as e:
            self.update_progress(0, "Erro: {}".format(str(e)))
            self.root.after(0, lambda: messagebox.showerror(
                "Erro",
                "Ocorreu um erro durante a desinstalacao:\n\n{}".format(str(e))
            ))
        finally:
            self.root.after(0, lambda: self._set_buttons_state('normal'))
            self.root.after(0, self._refresh_buttons)

# =============================================================================
# MAIN
# =============================================================================

def main():
    root = tk.Tk()
    style = ttk.Style()
    style.theme_use('clam')
    InstallerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
