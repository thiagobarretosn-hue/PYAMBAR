# -*- coding: utf-8 -*-
"""
PYAMBAR Installer
Instalador/Atualizador da extensao PYAMBAR para pyRevit

VERSAO: 1.0.0
AUTOR: Thiago Barreto Sobral Nunes
"""

import json
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# =============================================================================
# CONFIGURACAO
# =============================================================================

GITHUB_REPO = "thiagobarretosn-hue/PYAMBAR"
GITHUB_BRANCH = "main"
EXTENSION_NAME = "PYAMBAR.extension"
APP_VERSION = "1.0.0"
APP_TITLE = "PYAMBAR Installer"

# Caminhos padrao
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
    """Retorna URL para download do ZIP do repositorio"""
    return f"https://github.com/{GITHUB_REPO}/archive/refs/heads/{GITHUB_BRANCH}.zip"

def get_github_api_url():
    """Retorna URL da API do GitHub para info do repo"""
    return f"https://api.github.com/repos/{GITHUB_REPO}"

def get_latest_release_url():
    """Retorna URL da API para releases"""
    return f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

def find_pyrevit_cli():
    """Procura o executavel do pyRevit CLI"""
    for path in PYREVIT_CLI_PATHS:
        if os.path.exists(path):
            return path
    return None

def get_installed_version(install_path):
    """Le a versao instalada do extension.json"""
    ext_path = os.path.join(install_path, EXTENSION_NAME)
    json_path = os.path.join(ext_path, 'extension.json')

    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('version', 'Desconhecida')
        except:
            pass
    return None

def get_remote_version():
    """Busca versao mais recente do GitHub"""
    try:
        # Primeiro tenta releases
        req = Request(get_latest_release_url())
        req.add_header('User-Agent', 'PYAMBAR-Installer')
        with urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            return data.get('tag_name', 'v?.?.?').lstrip('v')
    except:
        pass

    # Fallback: le extension.json do repo
    try:
        raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/PYAMBAR.extension/extension.json"
        req = Request(raw_url)
        req.add_header('User-Agent', 'PYAMBAR-Installer')
        with urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            return data.get('version', '?.?.?')
    except:
        return "Erro ao verificar"

def is_pyrevit_installed():
    """Verifica se pyRevit esta instalado"""
    return find_pyrevit_cli() is not None or os.path.exists(PYREVIT_CONFIG_PATH)

def register_extension_pyrevit(extension_path):
    """Registra a extensao no pyRevit:
    1. Adiciona o diretorio pai ao userextensions
    2. Cria a secao [PYAMBAR.extension] no config
    """
    import re

    parent_path = os.path.dirname(extension_path)
    extension_section = "[{}.extension]".format(EXTENSION_NAME.replace('.extension', ''))

    # Tenta usar o CLI primeiro
    cli = find_pyrevit_cli()
    if cli:
        try:
            cmd = [cli, 'extensions', 'paths', 'add', parent_path]
            subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except Exception:
            pass

    # Edita o config.ini diretamente
    try:
        if not os.path.exists(PYREVIT_CONFIG_PATH):
            return False

        with open(PYREVIT_CONFIG_PATH, 'r', encoding='utf-8') as f:
            content = f.read()

        modified = False

        # 1. Adiciona ao userextensions se necessario
        pattern = r'(userextensions\s*=\s*)(\[.*?\])'
        match = re.search(pattern, content)

        if match:
            current_list_str = match.group(2)
            try:
                current_list = json.loads(current_list_str)
            except (json.JSONDecodeError, ValueError):
                current_list = []

            normalized_parent = os.path.normpath(parent_path).lower()
            normalized_existing = [os.path.normpath(p).lower() for p in current_list]

            if normalized_parent not in normalized_existing:
                current_list.append(parent_path)
                new_list_str = json.dumps(current_list)
                content = content[:match.start(2)] + new_list_str + content[match.end(2):]
                modified = True
        else:
            # userextensions nao existe, adiciona na secao [core]
            core_pattern = r'(\[core\])'
            core_match = re.search(core_pattern, content)
            if core_match:
                new_line = '\nuserextensions = ["{}"]'.format(parent_path.replace('\\', '\\\\'))
                insert_pos = core_match.end()
                content = content[:insert_pos] + new_line + content[insert_pos:]
                modified = True

        # 2. Cria a secao [PYAMBAR.extension] se nao existir
        if extension_section not in content:
            extension_config = """
{}
disabled = false
private_repo = false
username = ""
password = ""
""".format(extension_section)
            content += extension_config
            modified = True

        if modified:
            with open(PYREVIT_CONFIG_PATH, 'w', encoding='utf-8') as f:
                f.write(content)

        return True
    except Exception as e:
        print("Erro ao registrar: {}".format(e))
        return False

# =============================================================================
# CLASSE PRINCIPAL - GUI
# =============================================================================

class InstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("550x550")
        self.root.resizable(False, False)

        # Centralizar janela
        self.center_window()

        # Variaveis
        self.install_path = tk.StringVar(value=DEFAULT_EXTENSIONS_PATH)
        self.register_pyrevit = tk.BooleanVar(value=True)
        self.installed_version = tk.StringVar(value="Verificando...")
        self.remote_version = tk.StringVar(value="Verificando...")
        self.status_text = tk.StringVar(value="Pronto")
        self.progress_value = tk.DoubleVar(value=0)

        # Criar interface
        self.create_widgets()

        # Verificar versoes em thread separada
        threading.Thread(target=self.check_versions, daemon=True).start()

    def center_window(self):
        """Centraliza a janela na tela"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'+{x}+{y}')

    def create_widgets(self):
        """Cria todos os widgets da interface"""

        # Frame principal
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # === TITULO ===
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 20))

        ttk.Label(
            title_frame,
            text="PYAMBAR Installer",
            font=('Segoe UI', 18, 'bold')
        ).pack()

        ttk.Label(
            title_frame,
            text="Extensao pyRevit para workflows BIM e MEP",
            font=('Segoe UI', 9)
        ).pack()

        # === STATUS ===
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding="10")
        status_frame.pack(fill=tk.X, pady=(0, 15))

        # Grid para versoes
        ttk.Label(status_frame, text="Versao instalada:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Label(status_frame, textvariable=self.installed_version, font=('Segoe UI', 9, 'bold')).grid(row=0, column=1, sticky=tk.W, padx=10)

        ttk.Label(status_frame, text="Versao disponivel:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Label(status_frame, textvariable=self.remote_version, font=('Segoe UI', 9, 'bold'), foreground='green').grid(row=1, column=1, sticky=tk.W, padx=10)

        ttk.Label(status_frame, text="pyRevit:").grid(row=2, column=0, sticky=tk.W, pady=2)
        pyrevit_status = "Instalado" if is_pyrevit_installed() else "Nao encontrado"
        pyrevit_color = 'green' if is_pyrevit_installed() else 'red'
        ttk.Label(status_frame, text=pyrevit_status, font=('Segoe UI', 9, 'bold'), foreground=pyrevit_color).grid(row=2, column=1, sticky=tk.W, padx=10)

        # === PASTA DE INSTALACAO ===
        path_frame = ttk.LabelFrame(main_frame, text="Pasta de Instalacao", padding="10")
        path_frame.pack(fill=tk.X, pady=(0, 15))

        path_entry = ttk.Entry(path_frame, textvariable=self.install_path, width=50)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        browse_btn = ttk.Button(path_frame, text="Procurar...", command=self.browse_folder)
        browse_btn.pack(side=tk.RIGHT)

        # === OPCOES ===
        options_frame = ttk.LabelFrame(main_frame, text="Opcoes", padding="10")
        options_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Checkbutton(
            options_frame,
            text="Registrar extensao no pyRevit automaticamente",
            variable=self.register_pyrevit
        ).pack(anchor=tk.W)

        # === PROGRESSO ===
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 15))

        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_value,
            maximum=100,
            mode='determinate'
        )
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(progress_frame, textvariable=self.status_text).pack(anchor=tk.W)

        # === BOTOES ===
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        self.install_btn = ttk.Button(
            btn_frame,
            text="Instalar / Atualizar",
            command=self.start_installation,
            style='Accent.TButton'
        )
        self.install_btn.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            btn_frame,
            text="Fechar",
            command=self.root.quit
        ).pack(side=tk.RIGHT)

        # === RODAPE ===
        footer_frame = ttk.Frame(main_frame)
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(20, 0))

        ttk.Label(
            footer_frame,
            text=f"Installer v{APP_VERSION} | github.com/{GITHUB_REPO}",
            font=('Segoe UI', 8),
            foreground='gray'
        ).pack()

    def browse_folder(self):
        """Abre dialogo para selecionar pasta"""
        folder = filedialog.askdirectory(
            title="Selecione a pasta de instalacao",
            initialdir=self.install_path.get()
        )
        if folder:
            self.install_path.set(folder)
            # Atualiza versao instalada
            threading.Thread(target=self.check_versions, daemon=True).start()

    def check_versions(self):
        """Verifica versoes instalada e remota"""
        # Versao instalada
        installed = get_installed_version(self.install_path.get())
        self.installed_version.set(installed if installed else "Nao instalado")

        # Versao remota
        remote = get_remote_version()
        self.remote_version.set(remote)

    def update_progress(self, value, status):
        """Atualiza barra de progresso e status"""
        self.progress_value.set(value)
        self.status_text.set(status)
        self.root.update_idletasks()

    def start_installation(self):
        """Inicia instalacao em thread separada"""
        self.install_btn.config(state='disabled')
        threading.Thread(target=self.run_installation, daemon=True).start()

    def run_installation(self):
        """Executa o processo de instalacao"""
        try:
            install_path = self.install_path.get()
            extension_path = os.path.join(install_path, EXTENSION_NAME)
            is_update = os.path.exists(extension_path)

            # 1. Criar pasta se nao existe
            self.update_progress(5, "Preparando pasta de instalacao...")
            os.makedirs(install_path, exist_ok=True)

            # 2. Backup se atualizacao
            if is_update:
                self.update_progress(10, "Criando backup da versao anterior...")
                backup_path = extension_path + "_backup"
                if os.path.exists(backup_path):
                    shutil.rmtree(backup_path)
                shutil.copytree(extension_path, backup_path)

            # 3. Download
            self.update_progress(20, "Baixando do GitHub...")
            zip_url = get_github_download_url()
            zip_path = os.path.join(install_path, "pyambar_download.zip")

            req = Request(zip_url)
            req.add_header('User-Agent', 'PYAMBAR-Installer')

            with urlopen(req, timeout=60) as response:
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                chunk_size = 8192

                with open(zip_path, 'wb') as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            percent = 20 + (downloaded / total_size * 40)
                            self.update_progress(percent, f"Baixando... {downloaded // 1024} KB")

            # 4. Extrair
            self.update_progress(65, "Extraindo arquivos...")
            extract_path = os.path.join(install_path, "pyambar_extract")

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)

            # 5. Mover para pasta final
            self.update_progress(80, "Instalando extensao...")

            # Encontrar pasta extraida (PYAMBAR-main/PYAMBAR.extension)
            extracted_folders = os.listdir(extract_path)
            if extracted_folders:
                repo_folder = os.path.join(extract_path, extracted_folders[0])
                source_extension = os.path.join(repo_folder, EXTENSION_NAME)

                if os.path.exists(source_extension):
                    # Remover versao antiga
                    if os.path.exists(extension_path):
                        shutil.rmtree(extension_path)

                    # Copiar nova versao
                    shutil.copytree(source_extension, extension_path)

            # 6. Limpar arquivos temporarios
            self.update_progress(90, "Limpando arquivos temporarios...")
            os.remove(zip_path)
            shutil.rmtree(extract_path)

            # 7. Registrar no pyRevit (sempre, pois a funcao ja verifica duplicatas)
            if self.register_pyrevit.get():
                self.update_progress(95, "Registrando no pyRevit...")
                register_extension_pyrevit(extension_path)

            # 8. Concluido
            self.update_progress(100, "Instalacao concluida!")

            # Atualizar versao mostrada
            self.check_versions()

            # Mensagem de sucesso
            action = "atualizado" if is_update else "instalado"
            self.root.after(0, lambda: messagebox.showinfo(
                "Sucesso",
                f"PYAMBAR foi {action} com sucesso!\n\n"
                f"Pasta: {extension_path}\n\n"
                "Reinicie o Revit para carregar a extensao."
            ))

        except HTTPError as e:
            self.update_progress(0, f"Erro HTTP: {e.code}")
            self.root.after(0, lambda: messagebox.showerror(
                "Erro de Download",
                f"Nao foi possivel baixar do GitHub.\n\nErro: {e}\n\n"
                "Verifique sua conexao com a internet."
            ))
        except URLError as e:
            self.update_progress(0, "Erro de conexao")
            self.root.after(0, lambda: messagebox.showerror(
                "Erro de Conexao",
                f"Nao foi possivel conectar ao GitHub.\n\nErro: {e}\n\n"
                "Verifique sua conexao com a internet."
            ))
        except Exception as e:
            self.update_progress(0, f"Erro: {str(e)}")
            self.root.after(0, lambda: messagebox.showerror(
                "Erro",
                f"Ocorreu um erro durante a instalacao:\n\n{str(e)}"
            ))
        finally:
            self.root.after(0, lambda: self.install_btn.config(state='normal'))

# =============================================================================
# MAIN
# =============================================================================

def main():
    root = tk.Tk()

    # Estilo
    style = ttk.Style()
    style.theme_use('clam')  # Tema mais moderno

    # Criar aplicacao
    app = InstallerApp(root)

    # Executar
    root.mainloop()

if __name__ == "__main__":
    main()
