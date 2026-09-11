# -*- coding: utf-8 -*-
"""
Paleta de Parametros v5.6.1 - MODELESS + forms.WPFWindow

CORRECOES v5.6.1 (11/09/2026):
- Fix: a janela passou a rodar como modulo (paleta_janela.py, disparado
  pelo script.py). Com `__persistentengine__` ela so funcionava se fosse
  a primeira ferramenta do lab depois do Reload; nas outras vezes o
  primeiro clique dava NameError.

FEATURES:
- Carregar CSV (DAT ou raiz)
- Adicionar parametros do projeto
- Remover parametros
- Salvar/Carregar templates
- Estado persistente (APPDATA)
- Clone: captura parametros do elemento selecionado (host e link)
- Hold: trava parametros para nao serem alterados pelo clone
- Singleton: se ja aberta, traz para frente ao clicar novamente

NOVIDADES v5.6.0:
- Projeto sem paleta agora PERGUNTA de qual base partir, em vez de presumir:
  Base NOVA (data_NEW.csv), Base ANTIGA (data_OLD.csv), copiar de outro
  projeto ou importar um CSV do disco
- Cada opcao mostra o resumo lido do proprio arquivo (nro de parametros +
  primeiros nomes), entao a lista nunca desatualiza
- data.csv saiu (era copia identica de data_OLD.csv)

NOVIDADES v5.5.0 (usabilidade):
- Barra de contexto: diz de qual projeto e a paleta, quantos parametros tem e
  onde ela esta salva
- "Copiar de outro projeto": traz a paleta de um projeto onde a ferramenta ja
  foi usada (indice em APPDATA)
- A paleta vira do projeto sozinha na primeira edicao (botao "Paleta do
  Projeto" saiu)
- Ordem A-Z (natural: Nivel 2 antes de Nivel 10) para parametros e valores
- Templates recolhido num Expander - pouco usado, nao ocupa mais a tela
- Preferencias de exibicao gravadas por projeto

CORRECOES v5.4.0:
- Fix CRITICO: botao CSV nao abria o seletor. forms.pick_file usa OpenFileDialog
  do WinForms SEM owner e a paleta era escondida antes: o dialogo nascia atras
  do Revit. Agora e o OpenFileDialog do WPF com ShowDialog(self).
- Fix: CSV vazio criado no DAT mascarava o data.csv de fabrica para sempre
  (paleta abria com zero parametros). Agora e semeado do padrao.
- Fix: nunca mais escrever na pasta do script (git, sobrescrita pelo updater)
- Fix: parser CSV RFC 4180 - 1/2" e valores com virgula pararam de corromper
- Fix: state por projeto - um projeto nao herda mais os valores do outro
- Fix: escrita de parametro respeita StorageType (Double/Integer/ElementId)
- Melhoria: modais nao escondem mais a paleta; debounce do state; excecoes
  silenciosas passaram a ser logadas

CORRECOES v5.1.0:
- Fix: Clone agora suporta elementos de Revit Link (PickObject via ExternalEvent)
- Fix: Singleton - segundo clique no botao traz a paleta para frente em vez de abrir nova
- Fix: on_closing limpa referencia do singleton para permitir reabertura

CORRECOES v5.0.0:
- Fix CRITICO: doc/uidoc agora sao dinamicos (resolvem a cada uso)
- Fix: except:pass removidos - erros agora sao logados
- Fix: load_new_csv com Hide/Show para modal funcionar
- Fix: file locking para CSV em ambiente multiusuario
- Fix: escrita atomica no state file
"""
__title__ = "Paleta de\nParametros"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "5.6.1"

# Janela modeless: este arquivo roda como MODULO, disparado pelo script.py
# (`Snippets._janela_modeless`). Ate a v5.6.0 a protecao era
# `__persistentengine__ = True`, que so valia quando esta era a primeira
# ferramenta do lab rodada depois do Reload — nas outras vezes o pyRevit
# apagava os globais e o primeiro clique dava NameError ([[api-pyrevit-motor]]).

import clr
import os
import sys
import json
import codecs
import hashlib
import shutil
import time
import traceback
from datetime import datetime

# Add lib path for Snippets
LIB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.append(LIB_PATH)

clr.AddReference("System")
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System import TimeSpan, Int64
from System.IO import File
from System.Windows import Thickness, VerticalAlignment, Visibility, FontWeights, TextAlignment
from System.Windows.Controls import (
    Label, ComboBox, StackPanel, CheckBox, Orientation, TextBlock, RadioButton
)
from System.Windows.Controls.Primitives import ToggleButton
from System.Windows.Markup import XamlReader
from System.Windows.Media import SolidColorBrush, Color, FontFamily
from System.Windows.Threading import DispatcherTimer

# OpenFileDialog do WPF (PresentationFramework) - aceita owner explicito.
# forms.pick_file usa System.Windows.Forms.OpenFileDialog SEM owner: numa paleta
# modeless com Topmost o dialogo nasce atras do Revit e parece que "nao abriu".
try:
    from Microsoft.Win32 import OpenFileDialog as _WpfOpenFileDialog
except ImportError:
    _WpfOpenFileDialog = None

from Autodesk.Revit.DB import (
    Transaction, SubTransaction, FilteredElementCollector,
    SharedParameterElement, Group, RevitLinkInstance, StorageType, ElementId
)
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI import IExternalEventHandler, ExternalEvent, TaskDialog
from Autodesk.Revit.UI.Selection import ObjectType

from pyrevit import forms, script, revit

from Snippets.data._csv_rfc import parse_csv_text, format_csv_text
from Snippets.data._ordenacao import chave_natural

# ============================================================================
# LOGGING - substituir except:pass
# ============================================================================

PATH_SCRIPT = os.path.dirname(__file__)

# Log file para debug (APPDATA)
APPDATA = os.getenv('APPDATA')
STATE_DIR = os.path.join(APPDATA, 'pyRevit', 'PYAMBAR', 'ParameterPalette')
if not os.path.exists(STATE_DIR):
    try:
        os.makedirs(STATE_DIR)
    except OSError:
        pass  # sem STATE_DIR nao ha nem log para registrar a falha
LOG_FILE = os.path.join(STATE_DIR, 'palette_debug.log')

# State: um arquivo POR PROJETO. O arquivo unico antigo fazia o projeto novo
# herdar os valores do anterior na troca de documento.
LEGACY_STATE_FILE = os.path.join(STATE_DIR, 'palette_state.json')

# Indice das paletas ja vistas — alimenta "Copiar de outro projeto"
INDEX_FILE = os.path.join(STATE_DIR, 'palettes_index.json')

# CSV de trabalho: DAT do projeto ou, sem projeto salvo, APPDATA.
_APPDATA_CSV = os.path.join(STATE_DIR, 'data.csv')

# SEMENTES de fabrica (somente leitura, na pasta do script). Projeto sem paleta
# pergunta qual usar — nao ha mais uma base unica presumida.
# A primeira linha de cada opcao no dialogo sai automatica do proprio CSV
# (numero de parametros + primeiros nomes); so a 'nota' abaixo e texto fixo.
BASES_SEMENTE = [
    {
        'chave': 'nova',
        'arquivo': 'data_NEW.csv',
        'titulo': 'Base NOVA',
        'nota': 'Padrao atual — ARN, Filter, Unit ID',
    },
    {
        'chave': 'antiga',
        'arquivo': 'data_OLD.csv',
        'titulo': 'Base ANTIGA',
        'nota': 'Projetos legados — WBS, Modulo Montagem',
    },
]


def caminho_semente(arquivo):
    return os.path.join(PATH_SCRIPT, arquivo)

# Singleton guard via sys.modules - sobrevive a re-execucoes do script
_SINGLETON_KEY = '__PYAMBAR_ParameterPalette_instance__'


def _get_singleton():
    return sys.modules.get(_SINGLETON_KEY)


def _set_singleton(instance):
    if instance is None:
        sys.modules.pop(_SINGLETON_KEY, None)
    else:
        sys.modules[_SINGLETON_KEY] = instance


def _log(msg):
    """Log para arquivo de debug."""
    # Best-effort: uma falha aqui nunca pode derrubar a ferramenta.
    try:
        with codecs.open(LOG_FILE, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write("[{}] {}\n".format(timestamp, msg))
    except Exception as e:
        pass


def _log_error(context, exc=None):
    """Log de erro com traceback."""
    tb = traceback.format_exc()
    msg = "ERRO em {}: {}\n{}".format(context, str(exc) if exc else "?", tb)
    _log(msg)
    return msg


# ============================================================================
# DYNAMIC DOC/UIDOC - NUNCA usar globais stale
# ============================================================================

def _get_doc():
    """Retorna documento ATUAL (nao stale)."""
    return revit.doc


def _get_uidoc():
    """Retorna UIDocument ATUAL (nao stale)."""
    return revit.uidoc


# ============================================================================
# CSV HELPERS - com file locking
# ============================================================================

def substituir_arquivo(origem, destino):
    """Move `origem` sobre `destino`, sobrescrevendo. Retorna True/False.

    ATENCAO: `os.replace` NAO EXISTE no IronPython 3 do pyRevit — chama-lo
    lanca AttributeError("'module' object has no attribute 'replace'") e a
    escrita atomica falha inteira, em silencio, dentro do except.
    Verificado em 09/09/2026 (pyRevit 6.5.5 / IPY3).

    Caminho bom: File.Move(.., overwrite: True) do .NET, que e atomico de
    verdade. O fallback remove+move existe para o caso raro de a sobrecarga
    de 3 argumentos nao estar disponivel.
    """
    try:
        File.Move(origem, destino, True)
        return True
    except Exception as e:
        _log("File.Move falhou ({}) - usando remove+move".format(e))

    try:
        if os.path.exists(destino):
            os.remove(destino)
        shutil.move(origem, destino)
        return True
    except Exception as e:
        _log_error("substituir_arquivo", e)
        return False


def _read_file_safe(caminho, max_retries=3, wait_sec=0.2):
    """Le arquivo com retry para ambientes multiusuario.

    Se outro processo esta escrevendo (lock), tenta novamente apos wait_sec.
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            with codecs.open(caminho, 'r', encoding='utf-8-sig') as f:
                content = f.read()
            return content
        except IOError as e:
            last_error = e
            _log("Retry leitura {}/{}: {}".format(attempt + 1, max_retries, e))
            time.sleep(wait_sec * (attempt + 1))
        except Exception as e:
            _log_error("_read_file_safe", e)
            return None
    _log("Falha leitura apos {} tentativas: {}".format(max_retries, last_error))
    return None


def _pick_csv_file(owner, init_dir=None):
    """Abre seletor de CSV com owner EXPLICITO.

    Motivo: forms.pick_file() chama OpenFileDialog.ShowDialog() sem owner.
    Sem owner o WinForms usa GetActiveWindow() da thread — numa paleta modeless
    (ainda por cima Topmost) o dialogo nasce atras da janela do Revit ou preso a
    uma janela oculta, e o usuario ve "nada acontece" enquanto o Revit trava.
    O OpenFileDialog do WPF aceita ShowDialog(owner), garantindo que o dialogo
    nasce na frente da paleta.

    Retorna o caminho escolhido ou None (cancelado).
    """
    if _WpfOpenFileDialog is None:
        _log("OpenFileDialog WPF indisponivel - fallback forms.pick_file")
        return forms.pick_file(file_ext='csv', title='Selecionar CSV')

    dlg = _WpfOpenFileDialog()
    dlg.Title = 'Selecionar CSV'
    dlg.Filter = 'CSV (*.csv)|*.csv|Todos os arquivos (*.*)|*.*'
    dlg.Multiselect = False
    dlg.CheckFileExists = True
    if init_dir and os.path.isdir(init_dir):
        dlg.InitialDirectory = init_dir

    result = dlg.ShowDialog(owner) if owner is not None else dlg.ShowDialog()
    if result:
        return dlg.FileName
    return None


def ler_csv_utf8(caminho):
    """Le CSV (RFC 4180) com encoding UTF-8 e retry.

    Parser em Snippets/data/_csv_rfc.py: o split(',') antigo comia a aspa de
    polegada (1/2") e partia valores que continham virgula.
    """
    try:
        content = _read_file_safe(caminho)
        if content is None:
            return [], []
        return parse_csv_text(content)
    except Exception as e:
        _log_error("ler_csv_utf8", e)
        return [], []


def escrever_csv_utf8(caminho, headers, rows, max_retries=3):
    """Escreve CSV com encoding UTF-8 de forma atomica (temp + rename).

    Evita race condition em ambientes multiusuario: o arquivo original
    permanece integro ate que a escrita esteja 100% concluida no .tmp,
    entao a substituicao ocorre de uma vez via substituir_arquivo().
    """
    tmp_path = caminho + '.tmp.{}'.format(os.getpid())
    last_error = None
    pasta = os.path.dirname(caminho)
    if pasta and not os.path.exists(pasta):
        try:
            os.makedirs(pasta)
        except OSError as e:
            _log("Nao foi possivel criar {}: {}".format(pasta, e))
    for attempt in range(max_retries):
        try:
            with codecs.open(tmp_path, 'w', encoding='utf-8-sig') as f:
                f.write(format_csv_text(headers, rows))
                f.flush()
                os.fsync(f.fileno())
            if not substituir_arquivo(tmp_path, caminho):
                raise IOError('falha ao substituir {}'.format(caminho))
            return True
        except IOError as e:
            last_error = e
            _log("Retry escrita CSV {}/{}: {}".format(attempt + 1, max_retries, e))
            time.sleep(0.2 * (attempt + 1))
        except Exception as e:
            _log_error("escrever_csv_utf8", e)
            break
    try:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    except Exception as e:
        _log("Sobrou tmp de CSV nao removido: {}".format(e))
    _log("Falha escrita CSV apos retries: {}".format(last_error))
    return False


# ============================================================================
# DAT FOLDER
# ============================================================================

def get_dat_folder(document):
    """Obtem pasta DAT do projeto."""
    try:
        if document and document.PathName:
            project_folder = os.path.dirname(document.PathName)
            dat_folder = os.path.join(project_folder, 'DAT')
            if not os.path.exists(dat_folder):
                os.makedirs(dat_folder)
            return dat_folder
    except Exception as e:
        _log_error("get_dat_folder", e)
    return None


def get_project_name(document):
    """Obtem nome do projeto."""
    try:
        if document and document.PathName:
            return os.path.splitext(os.path.basename(document.PathName))[0]
    except Exception as e:
        _log_error("get_project_name", e)
    return "projeto"


def get_work_csv_path(document):
    """Caminho do CSV GRAVAVEL do projeto: (caminho, origem).

    DAT do projeto quando ele esta salvo; APPDATA quando nao esta. Nunca a
    pasta do script — ela vive no git e e sobrescrita pelo updater
    (CLAUDE.md, secao Config e State de Ferramentas).
    """
    dat = get_dat_folder(document)
    if dat:
        project_name = get_project_name(document)
        return os.path.join(dat, "{}_data.csv".format(project_name)), "DAT"
    return _APPDATA_CSV, "APPDATA"


def _mesmo_arquivo(a, b):
    """Compara dois caminhos ignorando caixa e forma (., .., barras)."""
    if not a or not b:
        return False
    try:
        return os.path.normcase(os.path.abspath(a)) == \
            os.path.normcase(os.path.abspath(b))
    except Exception as e:
        _log("_mesmo_arquivo falhou ({}) - assumindo diferentes".format(e))
        return False


def csv_tem_headers(caminho):
    """True se o CSV existe e tem ao menos uma coluna nomeada."""
    if not caminho or not os.path.exists(caminho):
        return False
    headers, _ = ler_csv_utf8(caminho)
    return any(h.strip() for h in headers)


def resumo_csv(caminho):
    """'11 parametros — Floor, PHASE, Room, Stage...' lido do proprio arquivo.

    Evita nota fixa que envelhece: se a base mudar de colunas, o texto muda junto.
    """
    headers, _ = ler_csv_utf8(caminho)
    nomes = [h.strip() for h in headers if h.strip()]
    if not nomes:
        return "arquivo vazio ou ilegivel"
    total = len(nomes)
    plural = "parametro" if total == 1 else "parametros"
    amostra = ", ".join(nomes[:4])
    if total > 4:
        amostra += "..."
    return u"{} {} — {}".format(total, plural, amostra)


def sementes_disponiveis():
    """Bases de fabrica que existem em disco e tem cabecalho."""
    achadas = []
    for base in BASES_SEMENTE:
        caminho = caminho_semente(base['arquivo'])
        if not csv_tem_headers(caminho):
            _log("Semente ausente ou sem headers: {}".format(caminho))
            continue
        item = dict(base)
        item['caminho'] = caminho
        item['resumo'] = resumo_csv(caminho)
        achadas.append(item)
    return achadas


def adotar_csv(document, origem_arquivo):
    """Copia `origem_arquivo` para o CSV de trabalho do projeto. Retorna o destino."""
    destino, _ = get_work_csv_path(document)
    pasta = os.path.dirname(destino)
    if pasta and not os.path.exists(pasta):
        os.makedirs(pasta)
    shutil.copy2(origem_arquivo, destino)
    _log("Paleta do projeto criada de {}: {}".format(origem_arquivo, destino))
    return destino


def create_backup(csv_path, document):
    """Cria backup do CSV."""
    try:
        dat = get_dat_folder(document)
        if not dat:
            return False, "Sem pasta DAT"
        backup_dir = os.path.join(dat, 'backup')
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = "data_backup_{}.csv".format(timestamp)
        backup_path = os.path.join(backup_dir, backup_name)
        shutil.copy2(csv_path, backup_path)
        return True, backup_path
    except Exception as e:
        _log_error("create_backup", e)
        return False, str(e)


# ============================================================================
# INDICE DE PALETAS CONHECIDAS
# ============================================================================
# Cada projeto guarda a propria paleta no seu DAT, entao nao ha lugar central
# de onde listar "as paletas que existem". Este indice em APPDATA anota cada
# projeto em que a ferramenta ja foi usada — e o que alimenta o botao
# "Copiar de outro projeto".

def _ler_indice():
    if not os.path.exists(INDEX_FILE):
        return {}
    try:
        content = _read_file_safe(INDEX_FILE)
        if not content:
            return {}
        dados = json.loads(content)
        return dados if isinstance(dados, dict) else {}
    except Exception as e:
        _log_error("_ler_indice", e)
        return {}


def registrar_paleta(doc_key, projeto, csv_path, total_params):
    """Anota que este projeto tem paleta, para outros projetos poderem copiar."""
    if not doc_key or not csv_path or not total_params:
        return
    try:
        indice = _ler_indice()
        indice[doc_key] = {
            'projeto': projeto,
            'csv': csv_path,
            'params': total_params,
            'visto': datetime.now().isoformat(),
        }
        tmp_path = INDEX_FILE + '.tmp.{}'.format(os.getpid())
        with codecs.open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(indice, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        substituir_arquivo(tmp_path, INDEX_FILE)
    except Exception as e:
        _log_error("registrar_paleta", e)


def paletas_conhecidas(excluir_key=None):
    """Paletas de outros projetos que ainda existem em disco.

    Ordenadas da mais recente para a mais antiga. Entradas cujo CSV sumiu sao
    descartadas silenciosamente — projeto arquivado, drive desconectado.
    """
    encontradas = []
    for doc_key, info in _ler_indice().items():
        if excluir_key and doc_key == excluir_key:
            continue
        caminho = info.get('csv')
        if not caminho or not os.path.exists(caminho):
            continue
        encontradas.append({
            'projeto': info.get('projeto') or os.path.basename(doc_key),
            'csv': caminho,
            'params': info.get('params') or 0,
            'visto': info.get('visto') or '',
        })
    encontradas.sort(key=lambda p: p['visto'], reverse=True)
    return encontradas


# ============================================================================
# TEMPLATES
# ============================================================================

def get_templates_path(document, script_path):
    """Obtem caminho do arquivo de templates."""
    dat = get_dat_folder(document)
    if dat:
        return os.path.join(dat, 'templates.csv')
    return os.path.join(script_path, 'templates.csv')


def load_templates(document, script_path):
    """Carrega templates salvos."""
    templates_path = get_templates_path(document, script_path)
    if not os.path.exists(templates_path):
        return []
    try:
        headers, rows = ler_csv_utf8(templates_path)
        templates = []
        for row in rows:
            if row and row[0].strip():
                name = row[0].strip()
                data = {}
                for i, h in enumerate(headers[1:], 1):
                    if i < len(row):
                        data[h] = row[i]
                templates.append({'name': name, 'data': data})
        return templates
    except Exception as e:
        _log_error("load_templates", e)
        return []


def save_template(document, script_path, template_name, param_values):
    """Salva um template."""
    try:
        templates_path = get_templates_path(document, script_path)
        if os.path.exists(templates_path):
            headers, rows = ler_csv_utf8(templates_path)
        else:
            headers = ['Template'] + sorted(param_values.keys())
            rows = []

        for p in param_values.keys():
            if p not in headers:
                headers.append(p)

        new_row = [template_name]
        for h in headers[1:]:
            new_row.append(param_values.get(h, ''))

        found = False
        for i, row in enumerate(rows):
            if row and row[0] == template_name:
                rows[i] = new_row
                found = True
                break
        if not found:
            rows.append(new_row)

        return escrever_csv_utf8(templates_path, headers, rows)
    except Exception as e:
        _log_error("save_template", e)
        return False


# ============================================================================
# STATE MANAGER - escrita atomica
# ============================================================================

def doc_state_file(doc_key):
    """Arquivo de state do projeto identificado por doc_key.

    Nome legivel + hash do caminho completo: dois projetos homonimos em pastas
    diferentes nao colidem.
    """
    if not doc_key:
        return os.path.join(STATE_DIR, 'state__sem_projeto.json')
    digest = hashlib.md5(doc_key.encode('utf-8')).hexdigest()[:8]
    base = os.path.splitext(os.path.basename(doc_key))[0]
    nome = ''.join(c for c in base if c.isalnum() or c in ' -_').strip()[:40]
    if not nome:
        nome = 'projeto'
    return os.path.join(STATE_DIR, 'state_{}_{}.json'.format(nome, digest))


def _migrar_state_legado(doc_key, destino, current_csv):
    """Copia o state global antigo para o do projeto - uma vez so.

    So migra se o CSV registrado no state antigo for o CSV deste projeto;
    caso contrario o state pertencia a outro projeto e seria lixo aqui.
    """
    if os.path.exists(destino) or not os.path.exists(LEGACY_STATE_FILE):
        return
    try:
        content = _read_file_safe(LEGACY_STATE_FILE)
        if not content:
            return
        legado = json.loads(content)
        antigo_csv = legado.get('csv_file') or ""
        if not antigo_csv or not current_csv:
            return
        if os.path.normcase(os.path.abspath(antigo_csv)) != \
                os.path.normcase(os.path.abspath(current_csv)):
            return
        shutil.copy2(LEGACY_STATE_FILE, destino)
        _log("State legado migrado para {}".format(destino))
    except Exception as e:
        _log_error("_migrar_state_legado", e)


def save_state(param_controls, current_csv, selected_template="", doc_key="",
               layout=None):
    """Salva estado dos controles (incluindo hold) - ATOMICO, por projeto."""
    state_file = doc_state_file(doc_key)
    try:
        state = {
            'parameters': {},
            'csv_file': current_csv,
            'selected_template': selected_template,
            'layout': layout or {},
            'timestamp': datetime.now().isoformat()
        }
        for param_name, controls in param_controls.items():
            combo = controls["combo"]
            toggle = controls["toggle"]
            hold = controls.get("hold")
            state['parameters'][param_name] = {
                'enabled': bool(toggle.IsChecked),
                'selected_value': str(combo.Text) if combo.Text else None,
                'held': bool(hold.IsChecked) if hold else False
            }

        # Escrita atomica: tmp + rename
        tmp_path = state_file + '.tmp.{}'.format(os.getpid())
        with codecs.open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        substituir_arquivo(tmp_path, state_file)

    except Exception as e:
        _log_error("save_state", e)
        try:
            tmp_path = state_file + '.tmp.{}'.format(os.getpid())
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception as e:
            _log("save_state: sobrou tmp nao removido ({})".format(e))


def load_state(doc_key="", current_csv=None):
    """Carrega o estado salvo DESTE projeto."""
    state_file = doc_state_file(doc_key)
    _migrar_state_legado(doc_key, state_file, current_csv)
    try:
        if os.path.exists(state_file):
            content = _read_file_safe(state_file)
            if content:
                return json.loads(content)
    except Exception as e:
        _log_error("load_state", e)
        # State corrompido - renomear e seguir
        try:
            corrupt_path = state_file + '.corrupt.{}'.format(
                datetime.now().strftime("%Y%m%d_%H%M%S"))
            os.rename(state_file, corrupt_path)
            _log("State corrompido movido para: {}".format(corrupt_path))
        except Exception as e:
            _log("load_state: falha ao isolar state corrompido ({})".format(e))
    return None


# ============================================================================
# ESCRITA DE PARAMETRO POR STORAGE TYPE
# ============================================================================

_TEXTO_VERDADEIRO = ('1', 'sim', 'yes', 'true', 'verdadeiro', 's', 'y')
_TEXTO_FALSO = ('0', 'nao', u'não', 'no', 'false', 'falso', 'n')


def _para_int(texto):
    try:
        return int(str(texto).strip())
    except (ValueError, TypeError):
        return None


def _para_float(texto):
    try:
        return float(str(texto).strip().replace(',', '.'))
    except (ValueError, TypeError):
        return None


def set_param_texto(param, texto):
    """Escreve `texto` em `param` respeitando o StorageType. Retorna bool.

    A paleta so tem texto para oferecer, mas param.Set(str) so vale para
    parametros String: em Double/Integer/ElementId ele lanca excecao e o
    resultado virava "erro" generico no relatorio. Double passa por
    SetValueString, que interpreta a unidade do projeto ("2 1/2\"", "150").
    """
    storage = param.StorageType

    if storage == StorageType.String:
        param.Set(texto)
        return True

    if storage == StorageType.Integer:
        valor = _para_int(texto)
        if valor is None:
            chave = texto.strip().lower()
            if chave in _TEXTO_VERDADEIRO:
                valor = 1
            elif chave in _TEXTO_FALSO:
                valor = 0
        if valor is not None:
            param.Set(valor)
            return True
        return bool(param.SetValueString(texto))

    if storage == StorageType.Double:
        # SetValueString respeita a unidade do projeto - tentar primeiro
        try:
            if param.SetValueString(texto):
                return True
        except Exception as e:
            _log("SetValueString falhou em '{}': {}".format(
                param.Definition.Name, e))
        valor = _para_float(texto)
        if valor is None:
            return False
        param.Set(valor)
        return True

    if storage == StorageType.ElementId:
        valor = _para_int(texto)
        if valor is None:
            return False
        param.Set(ElementId(Int64(valor)))
        return True

    return False


# ============================================================================
# EXTERNAL EVENT HANDLER
# ============================================================================

class ApplyParametersHandler(IExternalEventHandler):
    """Handler para aplicar parametros via ExternalEvent."""

    def __init__(self):
        self.param_values = None
        self.selected_ids = None
        self.palette_window = None
        self.apply_to_group_members = True

    def _collect_group_members(self, group, current_doc, acc):
        """Coleta membros de um grupo recursivamente (grupos aninhados).

        Desce em cada membro que tambem e um Group, alcancando os
        elementos de grupos dentro de grupos.
        """
        for mid in group.GetMemberIds():
            member = current_doc.GetElement(mid)
            if not member:
                continue
            acc.append(member)
            if isinstance(member, Group):
                self._collect_group_members(member, current_doc, acc)

    def _apply_to_elements(self, current_doc, elements, restrict_group=False):
        """Aplica parametros a uma lista de elementos.

        Args:
            restrict_group: Se True, so aplica params com VariesAcrossGroups.

        Retorna (success, errors, not_found, skipped, incompativeis).
        """
        success = 0
        errors = 0
        not_found = set()
        skipped = set()
        incompativeis = set()

        ilegiveis = 0
        ultimo_ilegivel = None

        for element in elements:
            elem_params = {}
            for param in element.Parameters:
                try:
                    elem_params[param.Definition.Name] = param
                except Exception as e:
                    # Contado e logado UMA vez no fim: um lote grande geraria
                    # milhares de linhas identicas.
                    ilegiveis += 1
                    ultimo_ilegivel = e
                    continue

            for param_name, param_value in self.param_values.items():
                if param_value is None:
                    continue
                try:
                    if param_name in elem_params:
                        param = elem_params[param_name]
                        if param.IsReadOnly:
                            continue
                        if restrict_group:
                            varies = getattr(
                                param.Definition,
                                'VariesAcrossGroups', False)
                            if not varies:
                                skipped.add(param_name)
                                continue
                        if set_param_texto(param, param_value):
                            success += 1
                        else:
                            incompativeis.add(param_name)
                    else:
                        not_found.add(param_name)
                except Exception as e:
                    errors += 1
                    _log("Erro set param '{}' = '{}': {}".format(
                        param_name, param_value, e))

        if ilegiveis:
            _log("{} parametro(s) sem Definition legivel ignorado(s). "
                 "Ultimo: {}".format(ilegiveis, ultimo_ilegivel))

        return success, errors, not_found, skipped, incompativeis

    def _apply_all(self, current_doc, elements, group_members, acumulado):
        """Aplica nos elementos e nos membros de grupo, somando em `acumulado`."""
        s, e, nf, sk, inc = self._apply_to_elements(
            current_doc, elements, restrict_group=False)
        acumulado['success'] += s
        acumulado['errors'] += e
        acumulado['not_found'].update(nf)
        acumulado['skipped'].update(sk)
        acumulado['incompativeis'].update(inc)

        if group_members:
            s, e, nf, sk, inc = self._apply_to_elements(
                current_doc, group_members, restrict_group=True)
            acumulado['success'] += s
            acumulado['errors'] += e
            acumulado['not_found'].update(nf)
            acumulado['skipped'].update(sk)
            acumulado['incompativeis'].update(inc)

    def _run_in_transaction(self, current_doc, elements, group_members):
        """Executa aplicacao dentro de Transaction adequada.

        Retorna dict com success, errors, not_found, skipped, incompativeis
        e group_count.
        """
        acumulado = {
            'success': 0,
            'errors': 0,
            'not_found': set(),
            'skipped': set(),
            'incompativeis': set(),
            'group_count': len(group_members),
        }

        is_modifiable = current_doc.IsModifiable
        _log("_run_in_transaction: IsModifiable={}".format(is_modifiable))

        if is_modifiable:
            # Doc ja tem transacao ativa - usar SubTransaction
            _log("Usando SubTransaction (doc modifiable)")
            sub = SubTransaction(current_doc)
            sub.Start()
            try:
                self._apply_all(
                    current_doc, elements, group_members, acumulado)
                sub.Commit()
                _log("SubTransaction committed OK")
            except Exception as ex:
                sub.RollBack()
                _log_error("SubTransaction", ex)
                raise
            finally:
                sub.Dispose()
        else:
            # Modo normal - Transaction padrao
            _log("Usando Transaction regular")
            t = Transaction(current_doc, "Aplicar Parametros")
            t.Start()
            try:
                self._apply_all(
                    current_doc, elements, group_members, acumulado)
                t.Commit()
                _log("Transaction committed OK")
            except Exception as ex:
                t.RollBack()
                _log_error("Transaction", ex)
                raise
            finally:
                t.Dispose()

        return acumulado

    def Execute(self, uiapp):
        start_time = time.time()

        try:
            current_doc = uiapp.ActiveUIDocument.Document

            if not self.selected_ids or len(self.selected_ids) == 0:
                TaskDialog.Show("Aviso", "Nenhum elemento selecionado!")
                return

            if not self.param_values:
                TaskDialog.Show("Aviso", "Nenhum parametro para aplicar!")
                return

            # Detectar estados do documento
            is_in_edit_mode = current_doc.IsInEditMode()
            is_modifiable = current_doc.IsModifiable
            edit_mode_type = "N/A"
            try:
                edit_mode_type = str(current_doc.GetActiveEditMode())
            except Exception as e:
                _log("GetActiveEditMode indisponivel: {}".format(e))
            _log("Execute: IsInEditMode={}, IsModifiable={}, EditMode={}".format(
                is_in_edit_mode, is_modifiable, edit_mode_type))
            _log("Execute: {} elementos, {} params".format(
                len(self.selected_ids), len(self.param_values)))

            # Coletar elementos
            normal_elements = []
            group_members = []
            null_count = 0
            for elem_id in self.selected_ids:
                element = current_doc.GetElement(elem_id)
                if not element:
                    null_count += 1
                    continue
                normal_elements.append(element)

                # Coletar membros de grupo (so fora do edit mode)
                # Recursivo: alcanca grupos aninhados (grupo dentro de grupo)
                if not is_in_edit_mode and self.apply_to_group_members:
                    if isinstance(element, Group):
                        self._collect_group_members(
                            element, current_doc, group_members)

            _log("Elementos: {} validos, {} null, {} group_members".format(
                len(normal_elements), null_count, len(group_members)))

            if not normal_elements:
                msg = "Nenhum elemento valido encontrado"
                if null_count:
                    msg += " ({} IDs nao resolvidos)".format(null_count)
                TaskDialog.Show("Aviso", msg)
                return

            # Aplicar parametros
            res = self._run_in_transaction(
                current_doc, normal_elements, group_members)

            elapsed = time.time() - start_time

            # Atualizar status
            if self.palette_window:
                mode_label = " (Group Edit)" if is_in_edit_mode else ""
                msg = "{} aplicacoes em {:.2f}s{}".format(
                    res['success'], elapsed, mode_label)
                if res['group_count']:
                    msg += " | {} membros de grupos".format(res['group_count'])
                if res['skipped']:
                    msg += " | {} ignorados (sem VariesAcrossGroups)".format(
                        len(res['skipped']))
                    _log("Params ignorados em grupos: {}".format(
                        ", ".join(res['skipped'])))
                if res['incompativeis']:
                    msg += " | {} valor incompativel".format(
                        len(res['incompativeis']))
                    _log("Valor incompativel com o tipo do parametro: {}".format(
                        ", ".join(res['incompativeis'])))
                if res['not_found']:
                    msg += " | {} nao encontrados".format(len(res['not_found']))
                if res['errors']:
                    msg += " | {} erros".format(res['errors'])
                self.palette_window.status_text.Text = msg
                self.palette_window.btn_apply.IsEnabled = True
                _log("Resultado: {}".format(msg))

        except Exception as e:
            _log_error("ApplyHandler.Execute", e)
            if self.palette_window:
                self.palette_window.btn_apply.IsEnabled = True
            TaskDialog.Show("Erro", str(e))

    def GetName(self):
        return "ApplyParametersHandler"


# ============================================================================
# PICK LINK ELEMENT HANDLER
# ============================================================================

class PickLinkElementHandler(IExternalEventHandler):
    """Handler para selecionar elemento de Revit Link via PickObject."""

    def __init__(self):
        self.palette_window = None

    def Execute(self, uiapp):
        try:
            uidoc = uiapp.ActiveUIDocument
            if not uidoc or not self.palette_window:
                return
            self.palette_window.Hide()
            try:
                ref = uidoc.Selection.PickObject(
                    ObjectType.LinkedElement,
                    "Selecione o elemento do link para clonar"
                )
                linked_id = ref.LinkedElementId
                host_element = _get_doc().GetElement(ref.ElementId)
                if isinstance(host_element, RevitLinkInstance):
                    link_doc = host_element.GetLinkDocument()
                    if link_doc:
                        linked_element = link_doc.GetElement(linked_id)
                        if linked_element:
                            self.palette_window._clone_from_element(linked_element)
            except OperationCanceledException:
                self.palette_window.status_text.Text = "Clone cancelado"
            finally:
                self.palette_window.Show()
        except Exception as e:
            _log_error("PickLinkElementHandler.Execute", e)
            try:
                self.palette_window.Show()
            except Exception:
                pass  # ultimo recurso: a janela ja pode ter sido fechada

    def GetName(self):
        return "PickLinkElementHandler"


# ============================================================================
# GUARDA DE JANELA MODAL
# ============================================================================

class ModalGuard(object):
    """Prepara a paleta para abrir uma janela modal por cima dela.

    Substitui o antigo Hide()/Show(): esconder a paleta fazia o dialogo sem
    owner (forms.pick_file) nascer atras do Revit, e ainda por cima o usuario
    perdia a janela de vista. Aqui a paleta continua na tela, so o Topmost sai
    de cena para nao cobrir a modal.

    O watcher de documento tambem para: ele reconstroi a UI e nao pode rodar
    dentro do message loop aninhado de um dialogo modal.
    """

    def __init__(self, window):
        self.window = window
        self._topmost = False
        self._watcher_ativo = False

    def __enter__(self):
        self._topmost = self.window.Topmost
        self.window.Topmost = False
        timer = self.window._doc_watcher_timer
        self._watcher_ativo = timer.IsEnabled
        timer.Stop()
        return self.window

    def __exit__(self, exc_type, exc_value, tb):
        self.window.Topmost = self._topmost
        if self._watcher_ativo:
            self.window._doc_watcher_timer.Start()
        try:
            self.window.Activate()
        except Exception as e:
            _log("Activate apos modal falhou: {}".format(e))
        return False


# ============================================================================
# ESCOLHA DA BASE - projeto que ainda nao tem paleta
# ============================================================================

class EscolherBaseWindow(forms.WPFWindow):
    """Pergunta de qual base partir num projeto sem paleta.

    Existem duas bases de fabrica com esquemas diferentes (a antiga em WBS e a
    nova em ARN/Filter), entao nao da para presumir uma. O usuario tambem pode
    trazer a paleta de outro projeto ou de um CSV solto.

    Ao fechar, `self.escolha` e None (cancelou) ou um dict com 'tipo'.
    """

    def __init__(self, projeto, sementes, total_outros):
        forms.WPFWindow.__init__(self, os.path.join(PATH_SCRIPT, 'seed_ui.xaml'))

        self.escolha = None
        self._radios = []

        self.txt_titulo.Text = \
            u'O projeto "{}" ainda nao tem paleta de parametros.'.format(projeto)

        for semente in sementes:
            radio = self._criar_opcao(
                semente['titulo'], semente['resumo'], semente['nota'])
            radio.Tag = {'tipo': 'semente',
                         'caminho': semente['caminho'],
                         'rotulo': semente['titulo']}

        if total_outros:
            plural = "projeto" if total_outros == 1 else "projetos"
            self._criar_opcao(
                "Copiar de outro projeto",
                u"{} {} com paleta disponivel".format(total_outros, plural),
                "Traz a paleta pronta de um modelo ja usado"
            ).Tag = {'tipo': 'projeto'}

        self._criar_opcao(
            "Importar CSV de uma pasta...",
            "Escolher um arquivo .csv no disco ou na rede",
            "Cada coluna vira um parametro; os valores viram as opcoes"
        ).Tag = {'tipo': 'arquivo'}

        if self._radios:
            self._radios[0].IsChecked = True
        else:
            self.btn_usar.IsEnabled = False

        if len(sementes) < len(BASES_SEMENTE):
            faltando = [b['arquivo'] for b in BASES_SEMENTE
                        if b['arquivo'] not in
                        [s['arquivo'] for s in sementes]]
            self.txt_aviso.Text = (
                "Base de fabrica ausente na pasta da ferramenta: {}. "
                "Reinstale a extensao para recupera-la.".format(
                    ", ".join(faltando)))
            self.borda_aviso.Visibility = Visibility.Visible

        self.btn_usar.Click += self.confirmar
        self.btn_cancelar.Click += self.cancelar

    def _criar_opcao(self, titulo, resumo, nota=None):
        """Monta uma opcao com titulo, resumo automatico e nota fixa."""
        radio = RadioButton()
        radio.GroupName = "base"
        radio.Style = self.FindResource("OpcaoStyle")

        conteudo = StackPanel()

        tb_titulo = TextBlock()
        tb_titulo.Text = titulo
        tb_titulo.Style = self.FindResource("TituloOpcao")
        conteudo.Children.Add(tb_titulo)

        tb_resumo = TextBlock()
        tb_resumo.Text = resumo
        tb_resumo.Style = self.FindResource("ResumoOpcao")
        conteudo.Children.Add(tb_resumo)

        if nota:
            tb_nota = TextBlock()
            tb_nota.Text = nota
            tb_nota.Style = self.FindResource("NotaOpcao")
            conteudo.Children.Add(tb_nota)

        radio.Content = conteudo
        self.painel_opcoes.Children.Add(radio)
        self._radios.append(radio)
        return radio

    def confirmar(self, sender, args):
        for radio in self._radios:
            if radio.IsChecked:
                self.escolha = radio.Tag
                break
        self.Close()

    def cancelar(self, sender, args):
        self.escolha = None
        self.Close()


# ============================================================================
# PALETA - forms.WPFWindow (PADRAO FUNCIONAL)
# ============================================================================

class ParameterPalette(forms.WPFWindow):
    """Paleta MODELESS usando forms.WPFWindow."""

    def __init__(self, external_event, event_handler, pick_link_event, pick_link_handler):
        xaml_file = os.path.join(PATH_SCRIPT, 'ui.xaml')
        forms.WPFWindow.__init__(self, xaml_file)

        self.Closing += self.on_closing

        self.external_event = external_event
        self.event_handler = event_handler
        self.event_handler.palette_window = self

        self._pick_link_event = pick_link_event
        self._pick_link_handler = pick_link_handler
        self._pick_link_handler.palette_window = self

        self.param_controls = {}
        self.csv_data = {}
        self.current_csv = None
        self.templates = []

        # Clone mode
        self._clone_timer = DispatcherTimer()
        self._clone_timer.Interval = TimeSpan.FromMilliseconds(500)
        self._clone_timer.Tick += self._on_clone_tick
        self._previous_clone_id = None
        self._cloned_values = {}

        # Document watcher — detecta troca de projeto ativo
        self._active_doc_key = self._doc_key(_get_doc())
        self._doc_watcher_timer = DispatcherTimer()
        self._doc_watcher_timer.Interval = TimeSpan.FromMilliseconds(1500)
        self._doc_watcher_timer.Tick += self._on_doc_watcher_tick
        self._doc_watcher_timer.Start()

        # Debounce do state: gravar em disco (com fsync) a cada clique era I/O
        # demais. Um unico save 400ms depois da ultima interacao basta.
        self._state_timer = DispatcherTimer()
        self._state_timer.Interval = TimeSpan.FromMilliseconds(400)
        self._state_timer.Tick += self._on_state_timer_tick

        _log("=== ParameterPalette v5.6.1 init ===")

        # Carregar templates
        self.load_templates()

        # Timer que dispara a pergunta da base DEPOIS que a janela aparece:
        # um modal antes do Show() nasce sem dono e some atras do Revit.
        self._seed_timer = DispatcherTimer()
        self._seed_timer.Interval = TimeSpan.FromMilliseconds(250)
        self._seed_timer.Tick += self._on_seed_timer_tick

        # Carregar CSV de trabalho (usa doc DINAMICO)
        current_doc = _get_doc()
        csv_path, csv_source = get_work_csv_path(current_doc)
        tem_paleta = csv_tem_headers(csv_path)
        self.current_csv = csv_path if tem_paleta else None

        # Preferencias de LAYOUT antes do load_csv: a ordenacao decide como a
        # lista e montada, entao nao adianta restaura-la depois.
        saved_state = load_state(self._active_doc_key, self.current_csv)
        if saved_state:
            self.restore_layout(saved_state)

        if tem_paleta:
            self.load_csv(csv_path)
            if self.param_controls:
                self.status_text.Text = "CSV {} carregado".format(csv_source)
            # Restaurar valores e toggles DESTE projeto
            if saved_state:
                self.restore_state(saved_state)
        else:
            self.param_panel.Children.Clear()
            self.status_text.Text = "Projeto sem paleta — escolha a base"
            self._atualizar_contexto()
            self._seed_timer.Start()

        # Eventos dos botoes
        self.btn_apply.Click += self.apply_parameters
        self.btn_import_csv.Click += self.load_new_csv
        self.btn_copy_project.Click += self.copiar_de_outro_projeto
        self.btn_add_param.Click += self.add_parameter_from_project
        self.btn_remove_param.Click += self.remove_parameter
        self.btn_save_template.Click += self.on_save_template
        self.combo_template.SelectionChanged += self.on_template_selected

        # Eventos das checkboxes
        self.chk_topmost.Checked += self.on_topmost_changed
        self.chk_topmost.Unchecked += self.on_topmost_changed
        self.chk_clone.Checked += self._on_clone_changed
        self.chk_clone.Unchecked += self._on_clone_changed
        self.chk_select_all.Checked += self.on_select_all_checked
        self.chk_select_all.Unchecked += self.on_select_all_unchecked
        self.chk_sort_az.Checked += self._on_sort_changed
        self.chk_sort_az.Unchecked += self._on_sort_changed

        _log("Init completo. CSV: {}".format(self.current_csv))

        # Mostrar janela MODELESS
        self.Show()

    # ========================================================================
    # DOCUMENT WATCHER — troca de projeto ativo
    # ========================================================================

    @staticmethod
    def _doc_key(doc):
        """Chave unica do documento (PathName ou Title como fallback)."""
        if not doc:
            return ""
        try:
            path = doc.PathName
            return path if path else doc.Title
        except Exception:
            return ""

    def _on_doc_watcher_tick(self, sender, args):
        """Timer: verifica se o projeto ativo mudou a cada 1.5s."""
        try:
            current_doc = _get_doc()
            key = self._doc_key(current_doc)
            if key and key != self._active_doc_key:
                _log("Documento trocado: {} -> {}".format(
                    self._active_doc_key, key))
                chave_anterior = self._active_doc_key
                self._active_doc_key = key
                self._on_document_switched(current_doc, chave_anterior)
        except Exception as e:
            _log_error("_on_doc_watcher_tick", e)

    def _on_document_switched(self, new_doc, chave_anterior):
        """Recarrega CSV e UI quando projeto ativo muda."""
        try:
            # Salvar estado do projeto ANTERIOR no arquivo DELE
            self._state_timer.Stop()
            self._save_state_now(chave_anterior)

            # Parar clone se ativo
            if self.chk_clone.IsChecked:
                self._clone_timer.Stop()
                self.chk_clone.IsChecked = False
                self._previous_clone_id = None
            self._cloned_values.clear()
            self._clear_all_clone_highlights()

            # Recarregar CSV do novo projeto
            csv_path, csv_source = get_work_csv_path(new_doc)
            tem_paleta = csv_tem_headers(csv_path)
            self.current_csv = csv_path if tem_paleta else None

            if tem_paleta:
                self.load_csv(csv_path)

                # Estado do NOVO projeto (nao herda os valores do anterior)
                saved_state = load_state(self._active_doc_key, self.current_csv)
                if saved_state:
                    self.restore_state(saved_state)

                if self.param_controls:
                    self.status_text.Text = "Projeto trocado — CSV {} carregado".format(
                        csv_source)
            else:
                # Projeto novo sem paleta: limpar a tela e perguntar a base
                self._limpar_parametros()
                self.status_text.Text = "Projeto trocado — sem paleta"
                self._atualizar_contexto()
                self._seed_timer.Stop()
                self._seed_timer.Start()

            self.load_templates()
            _log("Documento trocado OK: {}".format(self._doc_key(new_doc)))

        except Exception as e:
            _log_error("_on_document_switched", e)

    # ========================================================================
    # STATE
    # ========================================================================

    def _selected_template_name(self):
        if self.combo_template.SelectedItem:
            return str(self.combo_template.SelectedItem)
        return ""

    def _save_state_now(self, doc_key=None):
        """Grava o state imediatamente."""
        if doc_key is None:
            doc_key = self._active_doc_key
        layout = {}
        try:
            layout = {
                'sort_az': bool(self.chk_sort_az.IsChecked),
                'templates_abertos': bool(self.exp_templates.IsExpanded),
            }
        except Exception as e:
            _log_error("_save_state_now/layout", e)
        save_state(self.param_controls, self.current_csv,
                   self._selected_template_name(), doc_key, layout)

    def _schedule_save_state(self):
        """Adia a gravacao do state (debounce de 400ms)."""
        try:
            self._state_timer.Stop()
            self._state_timer.Start()
        except Exception as e:
            _log_error("_schedule_save_state", e)
            self._save_state_now()

    def _on_state_timer_tick(self, sender, args):
        self._state_timer.Stop()
        self._save_state_now()

    def on_closing(self, sender, args):
        """Salva estado ao fechar."""
        try:
            self._clone_timer.Stop()
            self._doc_watcher_timer.Stop()
            self._state_timer.Stop()
            self._seed_timer.Stop()

            self._save_state_now()

            # Deswire handlers estaticos
            self.btn_apply.Click -= self.apply_parameters
            self.btn_import_csv.Click -= self.load_new_csv
            self.btn_copy_project.Click -= self.copiar_de_outro_projeto
            self.btn_add_param.Click -= self.add_parameter_from_project
            self.btn_remove_param.Click -= self.remove_parameter
            self.btn_save_template.Click -= self.on_save_template
            self.combo_template.SelectionChanged -= self.on_template_selected
            self.chk_topmost.Checked -= self.on_topmost_changed
            self.chk_topmost.Unchecked -= self.on_topmost_changed
            self.chk_clone.Checked -= self._on_clone_changed
            self.chk_clone.Unchecked -= self._on_clone_changed
            self.chk_select_all.Checked -= self.on_select_all_checked
            self.chk_select_all.Unchecked -= self.on_select_all_unchecked
            self.chk_sort_az.Checked -= self._on_sort_changed
            self.chk_sort_az.Unchecked -= self._on_sort_changed

            # Deswire handlers dinamicos
            for controls in self.param_controls.values():
                controls['combo'].LostFocus -= self.on_combo_lost_focus
                controls['combo'].SelectionChanged -= self.on_selection_changed
                controls['toggle'].Checked -= self.on_toggle_changed
                controls['toggle'].Unchecked -= self.on_toggle_changed
                controls['hold'].Checked -= self._on_hold_changed
                controls['hold'].Unchecked -= self._on_hold_changed

            # Limpar referencias circulares e disposed external events
            if self.event_handler:
                self.event_handler.palette_window = None
            if self._pick_link_handler:
                self._pick_link_handler.palette_window = None
            if self._pick_link_event:
                self._pick_link_event.Dispose()
            if self.external_event:
                self.external_event.Dispose()

            _set_singleton(None)
            _log("Janela fechada.")
        except Exception as e:
            _log_error("on_closing", e)

    def on_topmost_changed(self, sender, args):
        """Altera Topmost da janela."""
        try:
            self.Topmost = bool(self.chk_topmost.IsChecked)
        except Exception as e:
            _log_error("on_topmost_changed", e)

    def on_select_all_checked(self, sender, args):
        """Marca todos os toggles."""
        for controls in self.param_controls.values():
            controls['toggle'].IsChecked = True
        self.status_text.Text = "Todos marcados"

    def on_select_all_unchecked(self, sender, args):
        """Desmarca todos os toggles."""
        for controls in self.param_controls.values():
            controls['toggle'].IsChecked = False
        self.status_text.Text = "Todos desmarcados"

    # ========================================================================
    # CLONE MODE
    # ========================================================================

    def _on_clone_changed(self, sender, args):
        """Liga/desliga monitoramento de selecao para clone."""
        if self.chk_clone.IsChecked:
            self._previous_clone_id = None
            self._clone_timer.Start()
            self.status_text.Text = "Clone ativo - selecione um elemento"
        else:
            self._clone_timer.Stop()
            self._cloned_values.clear()
            self._previous_clone_id = None
            self._clear_all_clone_highlights()
            self.status_text.Text = "Clone desativado"

    def _on_clone_tick(self, sender, args):
        """Timer callback - verifica mudanca de selecao."""
        try:
            current_uidoc = _get_uidoc()
            if not current_uidoc:
                return
            selected_ids = current_uidoc.Selection.GetElementIds()
            if not selected_ids or selected_ids.Count == 0:
                return

            first_id = list(selected_ids)[0]
            id_value = first_id.Value if hasattr(first_id, 'Value') else first_id.IntegerValue

            if id_value == self._previous_clone_id:
                return

            self._previous_clone_id = id_value
            current_doc = _get_doc()
            if current_doc:
                element = current_doc.GetElement(first_id)
                if element:
                    if isinstance(element, RevitLinkInstance):
                        self._clone_timer.Stop()
                        self.chk_clone.IsChecked = False
                        self._previous_clone_id = None
                        self.status_text.Text = "Link detectado - selecione o elemento"
                        self._pick_link_event.Raise()
                    else:
                        self._clone_from_element(element)
        except Exception as e:
            _log_error("_on_clone_tick", e)

    def _clone_from_element(self, element):
        """Le parametros do elemento e popula combos.
        - Parametros com Hold ativo sao ignorados
        - Parametros sem valor no elemento fonte: toggle desligado
        """
        self._cloned_values.clear()
        self._clear_all_clone_highlights()
        cloned_count = 0
        held_count = 0

        for param_name, controls in self.param_controls.items():
            # Respeitar Hold - nao tocar em parametros travados
            if controls['hold'].IsChecked:
                held_count += 1
                continue

            param = element.LookupParameter(param_name)
            has_value = False

            if param and param.HasValue:
                value = param.AsString()
                if not value:
                    value = param.AsValueString()
                if value and value.strip():
                    has_value = True
                    value = value.strip()
                    controls['combo'].Text = value
                    controls['toggle'].IsChecked = True
                    self._cloned_values[param_name] = value
                    self._set_clone_highlight(controls['combo'], True)
                    cloned_count += 1

            # Sem valor: desligar toggle
            if not has_value:
                controls['toggle'].IsChecked = False

        # Auto-desativar clone apos captura
        self._clone_timer.Stop()
        self.chk_clone.IsChecked = False

        msg = "{} clonados".format(cloned_count)
        if held_count:
            msg += " | {} travados".format(held_count)
        self.status_text.Text = msg

    def _set_clone_highlight(self, combo, highlighted):
        """Aplica/remove highlight visual de clone."""
        if highlighted:
            combo.Background = SolidColorBrush(Color.FromArgb(255, 255, 243, 224))
            combo.BorderBrush = SolidColorBrush(Color.FromArgb(255, 255, 152, 0))
        else:
            combo.Background = SolidColorBrush(Color.FromArgb(255, 255, 255, 255))
            combo.BorderBrush = SolidColorBrush(Color.FromArgb(255, 224, 224, 224))

    def _clear_all_clone_highlights(self):
        """Remove highlights de todos os combos."""
        for controls in self.param_controls.values():
            self._set_clone_highlight(controls['combo'], False)

    def load_templates(self):
        """Carrega templates no dropdown."""
        try:
            current_doc = _get_doc()
            self.templates = load_templates(current_doc, PATH_SCRIPT)
            self.combo_template.Items.Clear()
            self.combo_template.Items.Add("[ Nenhum Template ]")
            for t in self.templates:
                self.combo_template.Items.Add(t['name'])
            self.combo_template.SelectedIndex = 0
        except Exception as e:
            _log_error("load_templates_ui", e)

    def on_template_selected(self, sender, args):
        """Aplica template selecionado."""
        try:
            if self.combo_template.SelectedIndex <= 0:
                return
            name = str(self.combo_template.SelectedItem)
            for t in self.templates:
                if t['name'] == name:
                    for param, value in t['data'].items():
                        if param in self.param_controls:
                            self.param_controls[param]['combo'].Text = value
                    self.status_text.Text = "Template '{}' aplicado".format(name)
                    break
        except Exception as e:
            _log_error("on_template_selected", e)

    def on_save_template(self, sender, args):
        """Salva template atual."""
        try:
            values = self.get_selected_values()
            if not values:
                self.status_text.Text = "Nenhum parametro ativo para salvar"
                return

            with ModalGuard(self):
                name = forms.ask_for_string(
                    prompt="Nome do template:", title="Salvar Template")

            if not name:
                self.status_text.Text = "Operacao cancelada"
                return

            current_doc = _get_doc()
            if save_template(current_doc, PATH_SCRIPT, name, values):
                self.load_templates()
                self.status_text.Text = "Template '{}' salvo".format(name)
            else:
                self.status_text.Text = "Erro ao salvar template"

        except Exception as e:
            _log_error("on_save_template", e)
            TaskDialog.Show("Erro", str(e))

    def create_toggle_checkbox(self, param_name):
        """Cria checkbox toggle estilo iOS."""
        toggle = CheckBox()
        toggle.IsChecked = True
        toggle.Tag = param_name
        toggle.Style = self.FindResource("iOSToggleStyle")
        toggle.Margin = Thickness(0, 0, 8, 0)
        toggle.VerticalAlignment = VerticalAlignment.Center
        return toggle

    def _make_lock_text(self, locked=False):
        """Cria TextBlock com icone de cadeado usando Segoe UI Emoji."""
        tb = TextBlock()
        tb.Text = u"\U0001F512" if locked else u"\U0001F513"
        tb.FontFamily = FontFamily("Segoe UI Emoji")
        tb.FontSize = 14
        tb.TextAlignment = TextAlignment.Center
        return tb

    def create_hold_button(self, param_name):
        """Cria ToggleButton de hold (cadeado) por parametro."""
        btn = ToggleButton()
        btn.Content = self._make_lock_text(False)
        btn.Tag = param_name
        btn.Width = 26
        btn.Height = 24
        btn.FontSize = 14
        btn.Margin = Thickness(0, 0, 4, 0)
        btn.VerticalAlignment = VerticalAlignment.Center
        btn.Background = SolidColorBrush(Color.FromArgb(255, 245, 245, 245))
        btn.BorderBrush = SolidColorBrush(Color.FromArgb(255, 200, 200, 200))
        btn.BorderThickness = Thickness(1)
        btn.ToolTip = "Hold: travar parametro contra clone"
        btn.Checked += self._on_hold_changed
        btn.Unchecked += self._on_hold_changed
        return btn

    def _on_hold_changed(self, sender, args):
        """Altera visual do hold button."""
        try:
            param_name = str(sender.Tag)
            if sender.IsChecked:
                sender.Content = self._make_lock_text(True)
                sender.Background = SolidColorBrush(
                    Color.FromArgb(255, 255, 243, 224))
                sender.BorderBrush = SolidColorBrush(
                    Color.FromArgb(255, 255, 152, 0))
                self.status_text.Text = "{} travado".format(param_name)
            else:
                sender.Content = self._make_lock_text(False)
                sender.Background = SolidColorBrush(
                    Color.FromArgb(255, 245, 245, 245))
                sender.BorderBrush = SolidColorBrush(
                    Color.FromArgb(255, 200, 200, 200))
                self.status_text.Text = "{} destravado".format(param_name)
        except Exception as e:
            _log_error("_on_hold_changed", e)

    def create_editable_combobox(self, options, param_name):
        """Cria combobox editavel."""
        combo = ComboBox()
        combo.IsEditable = True
        combo.Height = 28
        combo.Margin = Thickness(0, 0, 5, 10)
        combo.Tag = param_name

        for option in options:
            if option and option.strip():
                combo.Items.Add(option.strip())

        combo.LostFocus += self.on_combo_lost_focus

        return combo

    def on_combo_lost_focus(self, sender, args):
        """Salva novo valor no CSV quando usuario digita texto novo."""
        try:
            combo = sender
            param_name = str(combo.Tag)
            new_value = combo.Text.strip() if combo.Text else ""

            if not new_value:
                return

            # Se valor foi alterado de um clone, limpar tracking
            if param_name in self._cloned_values:
                if new_value != self._cloned_values[param_name]:
                    del self._cloned_values[param_name]
                    self._set_clone_highlight(combo, False)
                else:
                    return

            # Verificar se valor ja existe no combo
            existing_values = [str(combo.Items[i]) for i in range(combo.Items.Count)]
            if new_value in existing_values:
                self._schedule_save_state()
                return

            # Adicionar ao combo (na posicao certa se A-Z estiver ligado)
            self._inserir_no_combo(combo, new_value)

            # Adicionar ao csv_data local
            if param_name in self.csv_data:
                self.csv_data[param_name].append(new_value)

            # Salvar no CSV
            if self.current_csv:
                self.add_value_to_csv(param_name, new_value)
                self.status_text.Text = "'{}' adicionado a {}".format(
                    new_value, param_name)
        except Exception as e:
            _log_error("on_combo_lost_focus", e)

    def _csv_gravavel(self):
        """Devolve o CSV deste projeto, materializando-o se preciso (ou None).

        Editar a paleta e o gesto que diz "esta paleta e deste projeto": na
        primeira edicao de um CSV que veio de fora (importado ou copiado de
        outro projeto), ele e gravado como <projeto>_data.csv no DAT e passa a
        ser o CSV de trabalho.

        Sem paleta nenhuma (o usuario dispensou a escolha da base), cria um CSV
        vazio para que dê para montar a paleta do zero pelo "+ Parametro".
        """
        destino, origem = get_work_csv_path(_get_doc())

        if not self.current_csv:
            try:
                if not csv_tem_headers(destino):
                    escrever_csv_utf8(destino, [], [])
                self.current_csv = destino
                _log("Paleta vazia criada para o projeto: {}".format(destino))
                self._atualizar_contexto()
                return destino
            except Exception as e:
                _log_error("_csv_gravavel/criar_vazio", e)
                return None

        if _mesmo_arquivo(self.current_csv, destino):
            return destino

        try:
            pasta = os.path.dirname(destino)
            if pasta and not os.path.exists(pasta):
                os.makedirs(pasta)
            shutil.copy2(self.current_csv, destino)
            _log("Paleta adotada pelo projeto ({}): {} -> {}".format(
                origem, self.current_csv, destino))
            self.current_csv = destino
            self.status_text.Text = "Paleta salva como {}".format(
                os.path.basename(destino))
            self._atualizar_contexto()
            return destino
        except Exception as e:
            _log_error("_csv_gravavel/copia", e)
            return None

    # ========================================================================
    # CONTEXTO E ORDENACAO
    # ========================================================================

    # ========================================================================
    # ESCOLHA DA BASE (projeto sem paleta)
    # ========================================================================

    def _on_seed_timer_tick(self, sender, args):
        self._seed_timer.Stop()
        self.escolher_base_inicial()

    def escolher_base_inicial(self):
        """Pergunta de qual base partir e cria a paleta do projeto."""
        try:
            doc = _get_doc()
            if doc is None:
                return

            sementes = sementes_disponiveis()
            outros = paletas_conhecidas(excluir_key=self._active_doc_key)

            escolha = None
            with ModalGuard(self):
                dialogo = EscolherBaseWindow(
                    get_project_name(doc), sementes, len(outros))
                try:
                    dialogo.Owner = self
                except Exception as e:
                    _log("Owner do dialogo de base nao pode ser definido: {}".format(e))
                dialogo.ShowDialog()
                escolha = dialogo.escolha

            if not escolha:
                self.status_text.Text = "Nenhuma base escolhida — paleta vazia"
                _log("Escolha de base cancelada pelo usuario")
                return

            self._aplicar_escolha_de_base(doc, escolha, outros)

        except Exception as e:
            _log_error("escolher_base_inicial", e)
            TaskDialog.Show("Erro", "Erro ao criar a paleta:\n{}".format(str(e)))

    def _aplicar_escolha_de_base(self, doc, escolha, outros):
        """Materializa a paleta do projeto a partir da opcao escolhida."""
        tipo = escolha.get('tipo')
        origem = None
        rotulo = ""

        if tipo == 'semente':
            origem = escolha.get('caminho')
            rotulo = escolha.get('rotulo') or "base padrao"

        elif tipo == 'projeto':
            if not outros:
                self.status_text.Text = "Nenhuma paleta de outro projeto disponivel"
                return
            rotulos = [u"{}  ({} parametros)".format(p['projeto'], p['params'])
                       for p in outros]
            with ModalGuard(self):
                escolhido = forms.SelectFromList.show(
                    rotulos,
                    title="Copiar a paleta de qual projeto?",
                    button_name="Copiar",
                    multiselect=False)
            if not escolhido:
                self.status_text.Text = "Copia cancelada — paleta vazia"
                return
            paleta = outros[rotulos.index(escolhido)]
            origem = paleta['csv']
            rotulo = u'projeto "{}"'.format(paleta['projeto'])

        elif tipo == 'arquivo':
            init_dir = get_dat_folder(doc)
            with ModalGuard(self):
                origem = _pick_csv_file(self, init_dir)
            if not origem:
                self.status_text.Text = "Importacao cancelada — paleta vazia"
                return
            rotulo = os.path.basename(origem)

        if not origem or not os.path.exists(origem):
            self.status_text.Text = "Origem da paleta nao encontrada"
            _log("Origem invalida para a base: {}".format(origem))
            return

        destino = adotar_csv(doc, origem)
        self.current_csv = destino
        self.load_csv(destino)
        self.restaurar_estado_atual()
        self.status_text.Text = u"Paleta criada de {} ({} parametros)".format(
            rotulo, len(self.param_controls))

    def _inserir_no_combo(self, combo, valor):
        """Insere um valor novo no combo, no lugar certo se A-Z estiver ligado."""
        try:
            if not self._ordenar_az():
                combo.Items.Add(valor)
                return
            chave = chave_natural(valor)
            for i in range(combo.Items.Count):
                if chave_natural(str(combo.Items[i])) > chave:
                    combo.Items.Insert(i, valor)
                    return
            combo.Items.Add(valor)
        except Exception as e:
            _log_error("_inserir_no_combo", e)
            combo.Items.Add(valor)

    def _ordenar_az(self):
        """True se a exibicao deve sair em ordem natural (A-Z)."""
        try:
            return bool(self.chk_sort_az.IsChecked)
        except Exception as e:
            _log_error("_ordenar_az", e)
            return True

    def _on_sort_changed(self, sender, args):
        """Reordena a lista sem perder o que esta preenchido."""
        if not self.current_csv:
            return
        self.load_csv(self.current_csv)
        self.restaurar_estado_atual()
        self.status_text.Text = ("Ordem alfabetica" if self._ordenar_az()
                                 else "Ordem do CSV")
        self._schedule_save_state()

    def _atualizar_contexto(self):
        """Escreve na faixa do topo de qual projeto e a paleta e onde ela esta.

        O usuario precisa saber, sem abrir nada, se esta editando a paleta
        deste projeto ou um CSV emprestado que ainda nao foi adotado.
        """
        try:
            projeto = get_project_name(_get_doc())
            total = len(self.param_controls)
            plural = "parametro" if total == 1 else "parametros"

            if not self.current_csv:
                self.ctx_text.Text = u"\U0001F4C4 {} · sem paleta".format(projeto)
                self.ctx_hint.Text = "Importe um CSV ou copie a paleta de outro projeto."
                return

            destino, origem = get_work_csv_path(_get_doc())
            e_do_projeto = _mesmo_arquivo(self.current_csv, destino)

            self.ctx_text.Text = u"\U0001F4C4 {} · {} {} · {}".format(
                projeto, total, plural,
                origem if e_do_projeto else "arquivo externo")

            if e_do_projeto:
                self.ctx_hint.Text = os.path.basename(self.current_csv)
            else:
                self.ctx_hint.Text = (
                    "{} — vira a paleta deste projeto assim que voce editar "
                    "algo.".format(os.path.basename(self.current_csv)))
        except Exception as e:
            _log_error("_atualizar_contexto", e)

    def copiar_de_outro_projeto(self, sender, args):
        """Traz a paleta de um projeto onde a ferramenta ja foi usada."""
        try:
            outras = paletas_conhecidas(excluir_key=self._active_doc_key)
            if not outras:
                forms.alert(
                    "Ainda nao ha outra paleta registrada.\n\n"
                    "Abra esta ferramenta em outro projeto uma vez e ela "
                    "aparecera aqui.",
                    title="Copiar de outro projeto")
                return

            rotulos = [u"{}  ({} parametros)".format(p['projeto'], p['params'])
                       for p in outras]
            with ModalGuard(self):
                escolhido = forms.SelectFromList.show(
                    rotulos,
                    title="Copiar a paleta de qual projeto?",
                    button_name="Copiar",
                    multiselect=False)

            if not escolhido:
                self.status_text.Text = "Copia cancelada"
                return

            origem = outras[rotulos.index(escolhido)]
            destino, rotulo_destino = get_work_csv_path(_get_doc())

            if csv_tem_headers(destino):
                with ModalGuard(self):
                    confirmar = forms.alert(
                        "Este projeto ja tem paleta com {} parametros.\n\n"
                        "Copiar de \"{}\" substitui a paleta atual. "
                        "Um backup e criado antes.".format(
                            len(self.param_controls), origem['projeto']),
                        title="Copiar de outro projeto",
                        options=["Substituir", "Cancelar"])
                if confirmar != "Substituir":
                    self.status_text.Text = "Copia cancelada"
                    return
                create_backup(destino, _get_doc())

            pasta = os.path.dirname(destino)
            if pasta and not os.path.exists(pasta):
                os.makedirs(pasta)
            shutil.copy2(origem['csv'], destino)
            _log("Paleta copiada de {} para {}".format(
                origem['projeto'], destino))

            self.current_csv = destino
            self.load_csv(destino)
            self.restaurar_estado_atual()
            self.status_text.Text = u"Paleta de \"{}\" copiada ({} parametros)".format(
                origem['projeto'], len(self.param_controls))

        except Exception as e:
            _log_error("copiar_de_outro_projeto", e)
            TaskDialog.Show("Erro", str(e))

    def add_value_to_csv(self, param_name, new_value):
        """Adiciona novo valor ao CSV."""
        try:
            destino = self._csv_gravavel()
            if not destino or not os.path.exists(destino):
                return

            headers, rows = ler_csv_utf8(destino)
            if param_name not in headers:
                return

            param_idx = headers.index(param_name)

            # Encontrar linha vazia ou criar nova
            added = False
            for row in rows:
                while len(row) < len(headers):
                    row.append('')
                if not row[param_idx].strip():
                    row[param_idx] = new_value
                    added = True
                    break

            if not added:
                new_row = [''] * len(headers)
                new_row[param_idx] = new_value
                rows.append(new_row)

            escrever_csv_utf8(destino, headers, rows)
        except Exception as e:
            _log_error("add_value_to_csv", e)

    def _limpar_parametros(self):
        """Desliga os handlers dos controles e esvazia a lista de parametros.

        Sem o deswire os controles antigos continuam presos aos eventos e
        vazam a cada recarga do CSV.
        """
        for controls in self.param_controls.values():
            controls['combo'].LostFocus -= self.on_combo_lost_focus
            controls['combo'].SelectionChanged -= self.on_selection_changed
            controls['toggle'].Checked -= self.on_toggle_changed
            controls['toggle'].Unchecked -= self.on_toggle_changed
            controls['hold'].Checked -= self._on_hold_changed
            controls['hold'].Unchecked -= self._on_hold_changed

        self.param_panel.Children.Clear()
        self.param_controls.clear()
        self.csv_data.clear()

    def load_csv(self, csv_path):
        """Carrega CSV e cria controles."""
        try:
            if not os.path.exists(csv_path):
                self.status_text.Text = "CSV nao encontrado"
                _log("CSV nao encontrado: {}".format(csv_path))
                return

            self._limpar_parametros()

            headers, rows = ler_csv_utf8(csv_path)

            if not headers:
                self.status_text.Text = "CSV vazio ou corrompido"
                _log("CSV sem headers: {}".format(csv_path))
                self._atualizar_contexto()
                return

            # Processar colunas
            columns = [[] for _ in headers]
            for row in rows:
                for i in range(len(headers)):
                    if i < len(row):
                        value = row[i].strip()
                        if value and value not in columns[i]:
                            columns[i].append(value)

            # Ordem de exibicao: alfabetica ou a ordem original do CSV
            ordem = list(range(len(headers)))
            if self._ordenar_az():
                ordem.sort(key=lambda i: chave_natural(headers[i]))

            # Criar controles
            for i in ordem:
                param_name = headers[i].strip()
                if not param_name:
                    continue

                options = columns[i]
                if self._ordenar_az():
                    options = sorted(options, key=chave_natural)
                self.csv_data[param_name] = options

                # Row: hold + toggle + label
                row_panel = StackPanel()
                row_panel.Orientation = Orientation.Horizontal
                row_panel.Margin = Thickness(0, 8, 0, 3)

                hold_btn = self.create_hold_button(param_name)
                row_panel.Children.Add(hold_btn)

                toggle = self.create_toggle_checkbox(param_name)
                toggle.Checked += self.on_toggle_changed
                toggle.Unchecked += self.on_toggle_changed
                row_panel.Children.Add(toggle)

                label = Label()
                label.Content = param_name
                label.FontSize = 13
                label.FontWeight = FontWeights.SemiBold
                label.Width = 150
                label.VerticalAlignment = VerticalAlignment.Center
                row_panel.Children.Add(label)

                self.param_panel.Children.Add(row_panel)

                # Row: combo
                combo_panel = StackPanel()
                combo_panel.Orientation = Orientation.Horizontal
                combo_panel.Margin = Thickness(85, 0, 0, 0)

                combo = self.create_editable_combobox(options, param_name)
                combo.SelectionChanged += self.on_selection_changed
                combo_panel.Children.Add(combo)

                self.param_panel.Children.Add(combo_panel)

                self.param_controls[param_name] = {
                    "combo": combo,
                    "toggle": toggle,
                    "hold": hold_btn
                }

            self.current_csv = csv_path
            self.status_text.Text = "{} parametros carregados".format(
                len(self.param_controls))
            _log("CSV carregado: {} params de {}".format(
                len(self.param_controls), csv_path))

            self._atualizar_contexto()
            # So entra no indice a paleta que E deste projeto: um CSV
            # emprestado nao pode aparecer como paleta dele em outro lugar.
            destino, _ = get_work_csv_path(_get_doc())
            if _mesmo_arquivo(csv_path, destino):
                registrar_paleta(self._active_doc_key,
                                 get_project_name(_get_doc()),
                                 csv_path, len(self.param_controls))

        except Exception as e:
            msg = _log_error("load_csv", e)
            self.status_text.Text = "Erro ao carregar CSV"
            TaskDialog.Show("Erro", "Erro ao carregar CSV:\n{}".format(str(e)))

    def restore_layout(self, state):
        """Restaura as preferencias de exibicao (ordem e Templates aberto).

        Roda ANTES de load_csv: a ordenacao decide como a lista e montada.
        """
        try:
            layout = state.get('layout') or {}
            if 'sort_az' in layout:
                self.chk_sort_az.IsChecked = bool(layout['sort_az'])
            if 'templates_abertos' in layout:
                self.exp_templates.IsExpanded = bool(layout['templates_abertos'])
        except Exception as e:
            _log_error("restore_layout", e)

    def restaurar_estado_atual(self):
        """Reaplica o state deste projeto apos um load_csv.

        load_csv reconstroi todos os controles do zero: sem isso, adicionar ou
        remover um parametro zerava os toggles e os valores digitados.
        """
        saved_state = load_state(self._active_doc_key, self.current_csv)
        if saved_state:
            self.restore_state(saved_state)

    def restore_state(self, state):
        """Restaura estado salvo (incluindo hold)."""
        try:
            if 'parameters' not in state:
                return
            for param_name, ps in state['parameters'].items():
                if param_name in self.param_controls:
                    self.param_controls[param_name]['toggle'].IsChecked = ps.get(
                        'enabled', True)
                    val = ps.get('selected_value')
                    if val:
                        self.param_controls[param_name]['combo'].Text = val
                    # Restaurar hold
                    hold = self.param_controls[param_name].get('hold')
                    if hold and ps.get('held', False):
                        hold.IsChecked = True
            if 'selected_template' in state and state['selected_template']:
                for i in range(self.combo_template.Items.Count):
                    if str(self.combo_template.Items[i]) == state['selected_template']:
                        self.combo_template.SelectedIndex = i
                        break
        except Exception as e:
            _log_error("restore_state", e)

    def on_toggle_changed(self, sender, args):
        """Toggle alterado."""
        try:
            param_name = sender.Tag
            is_checked = sender.IsChecked

            if param_name in self.param_controls:
                combo = self.param_controls[param_name]["combo"]
                combo.IsEnabled = is_checked

            self._schedule_save_state()
        except Exception as e:
            _log_error("on_toggle_changed", e)

    def on_selection_changed(self, sender, args):
        """Selecao alterada no combo."""
        try:
            param_name = str(sender.Tag) if sender.Tag else None
            if param_name and param_name in self._cloned_values:
                new_value = sender.Text.strip() if sender.Text else ""
                if new_value != self._cloned_values[param_name]:
                    del self._cloned_values[param_name]
                    self._set_clone_highlight(sender, False)

            self._schedule_save_state()
        except Exception as e:
            _log_error("on_selection_changed", e)

    def get_selected_values(self):
        """Obtem valores dos parametros ativos."""
        values = {}
        for param_name, controls in self.param_controls.items():
            if controls['toggle'].IsChecked and controls['combo'].Text:
                values[param_name] = controls['combo'].Text.strip()
        return values

    def apply_parameters(self, sender, args):
        """Dispara ExternalEvent para aplicar."""
        try:
            current_uidoc = _get_uidoc()
            if not current_uidoc:
                TaskDialog.Show("Erro", "Nenhum documento ativo.")
                return

            selection = current_uidoc.Selection
            selected_ids = selection.GetElementIds()

            if not selected_ids or selected_ids.Count == 0:
                TaskDialog.Show("Aviso", "Selecione elementos no Revit primeiro.")
                return

            param_values = self.get_selected_values()

            if not param_values:
                TaskDialog.Show("Aviso",
                    "Ative ao menos um parametro (toggle marcado).")
                return

            # Persistir valores clonados que estao sendo aplicados
            self._persist_used_clone_values(param_values)

            # PRE-CARREGAR selected_ids ANTES do Raise (CRITICO!)
            self.event_handler.param_values = param_values
            self.event_handler.selected_ids = list(selected_ids)
            self.event_handler.apply_to_group_members = self.chk_apply_group_members.IsChecked

            self.btn_apply.IsEnabled = False
            self.status_text.Text = "Aplicando {} elemento(s)...".format(
                selected_ids.Count)

            self.external_event.Raise()

        except Exception as e:
            _log_error("apply_parameters", e)
            TaskDialog.Show("Erro", "Erro ao aplicar: {}".format(str(e)))

    def _persist_used_clone_values(self, param_values):
        """Salva no CSV valores clonados que estao sendo aplicados."""
        try:
            to_remove = []
            for param_name, value in param_values.items():
                if param_name not in self._cloned_values:
                    continue
                if value != self._cloned_values[param_name]:
                    continue
                # Valor clonado sendo usado - verificar se ja existe no combo
                combo = self.param_controls[param_name]['combo']
                existing = [str(combo.Items[i]) for i in range(combo.Items.Count)]
                if value not in existing:
                    self._inserir_no_combo(combo, value)
                    if param_name in self.csv_data:
                        self.csv_data[param_name].append(value)
                    if self.current_csv:
                        self.add_value_to_csv(param_name, value)
                to_remove.append(param_name)
            for p in to_remove:
                del self._cloned_values[p]
        except Exception as e:
            _log_error("_persist_used_clone_values", e)

    def load_new_csv(self, sender, args):
        """Carrega CSV externo.

        A janela NAO e escondida: o dialogo recebe a paleta como owner e por
        isso nasce sempre na frente. Topmost e desligado durante o dialogo para
        a paleta nao cobrir o seletor.
        """
        _log("load_new_csv: abrindo seletor de CSV")
        csv_file = None

        try:
            init_dir = None
            if self.current_csv:
                init_dir = os.path.dirname(self.current_csv)
            if not init_dir:
                init_dir = get_dat_folder(_get_doc())

            with ModalGuard(self):
                csv_file = _pick_csv_file(self, init_dir)
        except Exception as e:
            _log_error("load_new_csv/dialogo", e)
            self.status_text.Text = "Erro ao abrir o seletor de CSV"
            return

        if not csv_file:
            _log("load_new_csv: cancelado pelo usuario")
            self.status_text.Text = "Selecao de CSV cancelada"
            return

        try:
            self.load_csv(csv_file)
            self.restaurar_estado_atual()
            _log("CSV externo carregado: {}".format(csv_file))
        except Exception as e:
            _log_error("load_new_csv/load_csv", e)
            self.status_text.Text = "Erro ao carregar CSV"

    def add_parameter_from_project(self, sender, args):
        """Adiciona parametro do projeto."""
        try:
            current_doc = _get_doc()
            current_uidoc = _get_uidoc()

            if not current_doc or not current_uidoc:
                TaskDialog.Show("Erro", "Nenhum documento ativo.")
                return

            param_names = set()

            # SharedParameters
            for sp in FilteredElementCollector(current_doc).OfClass(
                    SharedParameterElement):
                try:
                    param_names.add(sp.GetDefinition().Name)
                except Exception as e:
                    _log("SharedParameter sem definition legivel: {}".format(e))
                    continue

            # Parametros de elementos selecionados
            for eid in current_uidoc.Selection.GetElementIds():
                elem = current_doc.GetElement(eid)
                if elem:
                    for p in elem.Parameters:
                        try:
                            if not p.Definition.Name.startswith('-'):
                                param_names.add(p.Definition.Name)
                        except Exception as e:
                            _log("Parametro ilegivel ignorado: {}".format(e))
                            continue

            available = sorted(
                [p for p in param_names if p not in self.param_controls])
            if not available:
                self.status_text.Text = "Nenhum parametro novo disponivel"
                return

            with ModalGuard(self):
                selected = forms.SelectFromList.show(
                    available,
                    title="Adicionar Parametros",
                    button_name="Adicionar",
                    multiselect=True
                )

            if not selected:
                self.status_text.Text = "Nenhum parametro selecionado"
                return

            destino = self._csv_gravavel()
            if not destino:
                self.status_text.Text = "Nenhum CSV gravavel"
                return

            create_backup(destino, current_doc)
            headers, rows = ler_csv_utf8(destino)
            for p in selected:
                if p not in headers:
                    headers.append(p)
            for row in rows:
                while len(row) < len(headers):
                    row.append('')
            escrever_csv_utf8(destino, headers, rows)
            self.load_csv(destino)
            self.restaurar_estado_atual()
            self.status_text.Text = "{} adicionado(s)".format(len(selected))

        except Exception as e:
            _log_error("add_parameter_from_project", e)
            TaskDialog.Show("Erro", str(e))

    def remove_parameter(self, sender, args):
        """Remove parametro do CSV."""
        try:
            if not self.param_controls:
                self.status_text.Text = "Nenhum parametro para remover"
                return

            if not self.current_csv:
                self.status_text.Text = "Nenhum CSV carregado"
                return

            params = sorted(self.param_controls.keys())
            if not params:
                self.status_text.Text = "Lista de parametros vazia"
                return

            with ModalGuard(self):
                selected = forms.SelectFromList.show(
                    params,
                    title="Remover Parametros",
                    button_name="Remover",
                    multiselect=True
                )

            if not selected:
                self.status_text.Text = "Nenhum parametro selecionado"
                return

            # Backup (silencioso)
            current_doc = _get_doc()
            destino = self._csv_gravavel()
            if not destino:
                self.status_text.Text = "Nenhum CSV gravavel"
                return
            create_backup(destino, current_doc)

            # Ler CSV atual
            headers, rows = ler_csv_utf8(destino)
            if not headers:
                self.status_text.Text = "CSV vazio ou erro de leitura"
                return

            # Remover colunas (ordem reversa para manter indices)
            indices = sorted(
                [headers.index(p) for p in selected if p in headers],
                reverse=True)
            for idx in indices:
                del headers[idx]
                for row in rows:
                    if idx < len(row):
                        del row[idx]

            # Salvar
            if escrever_csv_utf8(destino, headers, rows):
                self.load_csv(destino)
                self.restaurar_estado_atual()
                self.status_text.Text = "{} removido(s)".format(len(selected))
            else:
                self.status_text.Text = "Erro ao salvar CSV"

        except Exception as e:
            _log_error("remove_parameter", e)
            TaskDialog.Show("Erro", str(e))


# ============================================================================
# MAIN
# ============================================================================

try:
    # Singleton: se ja aberta, trazer para frente
    _existing = _get_singleton()
    if _existing is not None:
        try:
            if _existing.IsVisible:
                _existing.Activate()
                _existing.Focus()
                _log("Paleta ja aberta - trazendo para frente")
            else:
                _set_singleton(None)
                _existing = None
        except Exception:
            _set_singleton(None)
            _existing = None

    if _get_singleton() is None:
        current_doc = _get_doc()
        if not current_doc:
            TaskDialog.Show("Erro", "Nenhum documento ativo")
        else:
            _log("=== Iniciando ParameterPalette v5.6.1 ===")
            apply_handler = ApplyParametersHandler()
            apply_event = ExternalEvent.Create(apply_handler)
            pick_link_handler = PickLinkElementHandler()
            pick_link_event = ExternalEvent.Create(pick_link_handler)
            _set_singleton(ParameterPalette(
                apply_event, apply_handler, pick_link_event, pick_link_handler
            ))

except Exception as e:
    _log_error("MAIN", e)
    TaskDialog.Show("Erro", str(e))
