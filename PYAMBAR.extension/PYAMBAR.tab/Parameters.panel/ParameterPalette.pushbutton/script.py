# -*- coding: utf-8 -*-
"""
Paleta de Parametros v5.1.0 - MODELESS + forms.WPFWindow

FEATURES:
- Carregar CSV (DAT ou raiz)
- Adicionar parametros do projeto
- Remover parametros
- Salvar/Carregar templates
- Estado persistente (APPDATA)
- Clone: captura parametros do elemento selecionado (host e link)
- Hold: trava parametros para nao serem alterados pelo clone
- Singleton: se ja aberta, traz para frente ao clicar novamente

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
__version__ = "5.3.0"

# CRITICO: Necessario para MODELESS
__persistentengine__ = True

import clr
import os
import sys
import json
import codecs
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

from System import TimeSpan
from System.Windows import Thickness, VerticalAlignment, Visibility, FontWeights, TextAlignment
from System.Windows.Controls import Label, ComboBox, StackPanel, CheckBox, Orientation, TextBlock
from System.Windows.Controls.Primitives import ToggleButton
from System.Windows.Markup import XamlReader
from System.Windows.Media import SolidColorBrush, Color, FontFamily
from System.Windows.Threading import DispatcherTimer

from Autodesk.Revit.DB import Transaction, SubTransaction, FilteredElementCollector, SharedParameterElement, Group, RevitLinkInstance
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI import IExternalEventHandler, ExternalEvent, TaskDialog
from Autodesk.Revit.UI.Selection import ObjectType

from pyrevit import forms, script, revit

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
        pass
STATE_FILE = os.path.join(STATE_DIR, 'palette_state.json')
LOG_FILE = os.path.join(STATE_DIR, 'palette_debug.log')

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


def ler_csv_utf8(caminho):
    """Le CSV com encoding UTF-8 e retry."""
    try:
        content = _read_file_safe(caminho)
        if content is None:
            return [], []
        linhas = []
        for linha in content.splitlines():
            linha = linha.strip()
            if linha:
                valores = [v.strip().strip('"').strip("'") for v in linha.split(',')]
                linhas.append(valores)
        if not linhas:
            return [], []
        return linhas[0], linhas[1:]
    except Exception as e:
        _log_error("ler_csv_utf8", e)
        return [], []


def escrever_csv_utf8(caminho, headers, rows, max_retries=3):
    """Escreve CSV com encoding UTF-8 de forma atomica (temp + rename).

    Evita race condition em ambientes multiusuario: o arquivo original
    permanece integro ate que a escrita esteja 100% concluida no .tmp,
    entao a substituicao ocorre instantaneamente via os.replace().
    """
    tmp_path = caminho + '.tmp.{}'.format(os.getpid())
    last_error = None
    for attempt in range(max_retries):
        try:
            with codecs.open(tmp_path, 'w', encoding='utf-8-sig') as f:
                f.write(u','.join([u'"{}"'.format(h) for h in headers]) + u'\n')
                for row in rows:
                    while len(row) < len(headers):
                        row.append(u'')
                    f.write(u','.join([u'"{}"'.format(v) for v in row]) + u'\n')
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, caminho)
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
        pass
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


def get_csv_path(document, script_path):
    """Obtem caminho do CSV (DAT ou raiz)."""
    dat = get_dat_folder(document)
    if dat:
        project_name = get_project_name(document)
        dat_csv = os.path.join(dat, "{}_data.csv".format(project_name))
        if os.path.exists(dat_csv):
            return dat_csv, "DAT"

    root_csv = os.path.join(script_path, 'data.csv')
    if os.path.exists(root_csv):
        return root_csv, "raiz"

    return None, None


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

def save_state(param_controls, current_csv, selected_template=""):
    """Salva estado dos controles (incluindo hold) - ATOMICO."""
    try:
        state = {
            'parameters': {},
            'csv_file': current_csv,
            'selected_template': selected_template,
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
        tmp_path = STATE_FILE + '.tmp.{}'.format(os.getpid())
        with codecs.open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        # IronPython 3 nao tem os.replace - usar shutil.move
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        shutil.move(tmp_path, STATE_FILE)

    except Exception as e:
        _log_error("save_state", e)
        try:
            tmp_path = STATE_FILE + '.tmp.{}'.format(os.getpid())
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception as e:
            pass


def load_state():
    """Carrega estado salvo."""
    try:
        if os.path.exists(STATE_FILE):
            content = _read_file_safe(STATE_FILE)
            if content:
                return json.loads(content)
    except Exception as e:
        _log_error("load_state", e)
        # State corrompido - renomear e seguir
        try:
            corrupt_path = STATE_FILE + '.corrupt.{}'.format(
                datetime.now().strftime("%Y%m%d_%H%M%S"))
            os.rename(STATE_FILE, corrupt_path)
            _log("State corrompido movido para: {}".format(corrupt_path))
        except Exception as e:
            pass
    return None


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
        """
        success = 0
        errors = 0
        not_found = set()
        skipped = set()

        for element in elements:
            elem_params = {}
            for param in element.Parameters:
                try:
                    elem_params[param.Definition.Name] = param
                except Exception as e:
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
                        param.Set(param_value)
                        success += 1
                    else:
                        not_found.add(param_name)
                except Exception as e:
                    errors += 1
                    _log("Erro set param '{}': {}".format(param_name, e))

        return success, errors, not_found, skipped

    def _run_in_transaction(self, current_doc, elements, group_members):
        """Executa aplicacao dentro de Transaction adequada.

        Retorna (success, errors, not_found, skipped_group, group_count).
        """
        success_count = 0
        error_count = 0
        not_found_params = set()
        skipped_group_params = set()
        group_member_count = len(group_members)

        is_modifiable = current_doc.IsModifiable
        _log("_run_in_transaction: IsModifiable={}".format(is_modifiable))

        if is_modifiable:
            # Doc ja tem transacao ativa - usar SubTransaction
            _log("Usando SubTransaction (doc modifiable)")
            sub = SubTransaction(current_doc)
            sub.Start()
            try:
                s, e, nf, sk = self._apply_to_elements(
                    current_doc, elements, restrict_group=False)
                success_count += s
                error_count += e
                not_found_params.update(nf)

                if group_members:
                    s, e, nf, sk = self._apply_to_elements(
                        current_doc, group_members, restrict_group=True)
                    success_count += s
                    error_count += e
                    not_found_params.update(nf)
                    skipped_group_params.update(sk)

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
                s, e, nf, sk = self._apply_to_elements(
                    current_doc, elements, restrict_group=False)
                success_count += s
                error_count += e
                not_found_params.update(nf)
                skipped_group_params.update(sk)

                if group_members:
                    s, e, nf, sk = self._apply_to_elements(
                        current_doc, group_members, restrict_group=True)
                    success_count += s
                    error_count += e
                    not_found_params.update(nf)
                    skipped_group_params.update(sk)

                t.Commit()
                _log("Transaction committed OK")
            except Exception as ex:
                t.RollBack()
                _log_error("Transaction", ex)
                raise
            finally:
                t.Dispose()

        return (success_count, error_count, not_found_params,
                skipped_group_params, group_member_count)

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
                pass
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
            success_count, error_count, not_found_params, \
                skipped_group_params, group_member_count = \
                self._run_in_transaction(
                    current_doc, normal_elements, group_members)

            elapsed = time.time() - start_time

            # Atualizar status
            if self.palette_window:
                mode_label = ""
                if is_in_edit_mode:
                    mode_label = " (Group Edit)"
                msg = "{} aplicacoes em {:.2f}s{}".format(
                    success_count, elapsed, mode_label)
                if group_member_count:
                    msg += " | {} membros de grupos".format(group_member_count)
                if skipped_group_params:
                    msg += " | {} ignorados (sem VariesAcrossGroups)".format(
                        len(skipped_group_params))
                    _log("Params ignorados em grupos: {}".format(
                        ", ".join(skipped_group_params)))
                if not_found_params:
                    msg += " | {} nao encontrados".format(len(not_found_params))
                if error_count:
                    msg += " | {} erros".format(error_count)
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
                pass

    def GetName(self):
        return "PickLinkElementHandler"


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

        _log("=== ParameterPalette v5.0.0 init ===")

        # Carregar templates
        self.load_templates()

        # Carregar CSV (usa doc DINAMICO)
        current_doc = _get_doc()
        csv_path, csv_source = get_csv_path(current_doc, PATH_SCRIPT)
        if csv_path:
            self.current_csv = csv_path
            self.load_csv(csv_path)
            self.status_text.Text = "CSV {} carregado".format(csv_source)
        else:
            dat = get_dat_folder(current_doc)
            if dat:
                project_name = get_project_name(current_doc)
                self.current_csv = os.path.join(
                    dat, "{}_data.csv".format(project_name))
                escrever_csv_utf8(self.current_csv, [], [])
                self.status_text.Text = "CSV DAT criado (vazio)"
            else:
                self.status_text.Text = "Projeto nao salvo"

        # Restaurar estado
        saved_state = load_state()
        if saved_state:
            self.restore_state(saved_state)

        # Eventos dos botoes
        self.btn_apply.Click += self.apply_parameters
        self.btn_load_csv.Click += self.load_new_csv
        self.btn_save_csv.Click += self.save_csv_to_dat
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
                self._active_doc_key = key
                self._on_document_switched(current_doc)
        except Exception as e:
            _log_error("_on_doc_watcher_tick", e)

    def _on_document_switched(self, new_doc):
        """Recarrega CSV e UI quando projeto ativo muda."""
        try:
            # Salvar estado do projeto anterior
            selected_template = ""
            if self.combo_template.SelectedItem:
                selected_template = str(self.combo_template.SelectedItem)
            save_state(self.param_controls, self.current_csv, selected_template)

            # Parar clone se ativo
            if self.chk_clone.IsChecked:
                self._clone_timer.Stop()
                self.chk_clone.IsChecked = False
                self._previous_clone_id = None
            self._cloned_values.clear()
            self._clear_all_clone_highlights()

            # Recarregar CSV do novo projeto
            csv_path, csv_source = get_csv_path(new_doc, PATH_SCRIPT)
            if csv_path:
                self.current_csv = csv_path
                self.load_csv(csv_path)
                saved_state = load_state()
                if saved_state:
                    self.restore_state(saved_state)
                self.status_text.Text = "Projeto trocado — CSV {} carregado".format(
                    csv_source)
            else:
                # Limpar UI — novo projeto sem CSV
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
                self.current_csv = None
                self.status_text.Text = "Projeto trocado — sem CSV"

            self.load_templates()
            _log("Documento trocado OK: {}".format(self._doc_key(new_doc)))

        except Exception as e:
            _log_error("_on_document_switched", e)

    def on_closing(self, sender, args):
        """Salva estado ao fechar."""
        try:
            self._clone_timer.Stop()
            self._doc_watcher_timer.Stop()

            selected_template = ""
            if self.combo_template.SelectedItem:
                selected_template = str(self.combo_template.SelectedItem)
            save_state(self.param_controls, self.current_csv, selected_template)

            # Deswire handlers estaticos
            self.btn_apply.Click -= self.apply_parameters
            self.btn_load_csv.Click -= self.load_new_csv
            self.btn_save_csv.Click -= self.save_csv_to_dat
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

            # Esconder janela temporariamente para modal funcionar
            self.Hide()
            try:
                name = forms.ask_for_string(
                    prompt="Nome do template:", title="Salvar Template")
            finally:
                self.Show()

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
                selected_template = ""
                if self.combo_template.SelectedItem:
                    selected_template = str(self.combo_template.SelectedItem)
                save_state(self.param_controls, self.current_csv, selected_template)
                return

            # Adicionar ao combo
            combo.Items.Add(new_value)

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

    def add_value_to_csv(self, param_name, new_value):
        """Adiciona novo valor ao CSV."""
        try:
            if not self.current_csv or not os.path.exists(self.current_csv):
                return

            headers, rows = ler_csv_utf8(self.current_csv)
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

            escrever_csv_utf8(self.current_csv, headers, rows)
        except Exception as e:
            _log_error("add_value_to_csv", e)

    def load_csv(self, csv_path):
        """Carrega CSV e cria controles."""
        try:
            if not os.path.exists(csv_path):
                self.status_text.Text = "CSV nao encontrado"
                _log("CSV nao encontrado: {}".format(csv_path))
                return

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

            headers, rows = ler_csv_utf8(csv_path)

            if not headers:
                self.status_text.Text = "CSV vazio ou corrompido"
                _log("CSV sem headers: {}".format(csv_path))
                return

            # Processar colunas
            columns = [[] for _ in headers]
            for row in rows:
                for i in range(len(headers)):
                    if i < len(row):
                        value = row[i].strip()
                        if value and value not in columns[i]:
                            columns[i].append(value)

            # Criar controles
            for i, param_name in enumerate(headers):
                param_name = param_name.strip()
                if not param_name:
                    continue

                options = columns[i]
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

        except Exception as e:
            msg = _log_error("load_csv", e)
            self.status_text.Text = "Erro ao carregar CSV"
            TaskDialog.Show("Erro", "Erro ao carregar CSV:\n{}".format(str(e)))

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

            selected_template = ""
            if self.combo_template.SelectedItem:
                selected_template = str(self.combo_template.SelectedItem)
            save_state(self.param_controls, self.current_csv, selected_template)
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

            selected_template = ""
            if self.combo_template.SelectedItem:
                selected_template = str(self.combo_template.SelectedItem)
            save_state(self.param_controls, self.current_csv, selected_template)
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
                    combo.Items.Add(value)
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
        """Carrega CSV externo - Hide/Show para modal funcionar."""
        try:
            self.Hide()
            try:
                csv_file = forms.pick_file(
                    file_ext='csv', title='Selecionar CSV')
            finally:
                self.Show()

            if csv_file:
                self.load_csv(csv_file)
                _log("CSV externo carregado: {}".format(csv_file))
        except Exception as e:
            _log_error("load_new_csv", e)
            self.status_text.Text = "Erro ao carregar CSV"

    def save_csv_to_dat(self, sender, args):
        """Salva CSV na pasta DAT."""
        try:
            current_doc = _get_doc()
            dat = get_dat_folder(current_doc)
            if not dat:
                self.status_text.Text = "Projeto nao salvo"
                return
            project_name = get_project_name(current_doc)
            dat_csv = os.path.join(
                dat, "{}_data.csv".format(project_name))
            if self.current_csv and self.current_csv != dat_csv:
                shutil.copy2(self.current_csv, dat_csv)
            self.current_csv = dat_csv
            self.status_text.Text = "CSV salvo em DAT"
            _log("CSV salvo em DAT: {}".format(dat_csv))
        except Exception as e:
            _log_error("save_csv_to_dat", e)
            self.status_text.Text = "Erro: {}".format(str(e))

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
                            continue

            available = sorted(
                [p for p in param_names if p not in self.param_controls])
            if not available:
                self.status_text.Text = "Nenhum parametro novo disponivel"
                return

            # Esconder janela temporariamente para modal funcionar
            self.Hide()
            try:
                selected = forms.SelectFromList.show(
                    available,
                    title="Adicionar Parametros",
                    button_name="Adicionar",
                    multiselect=True
                )
            finally:
                self.Show()

            if not selected:
                self.status_text.Text = "Nenhum parametro selecionado"
                return

            if not self.current_csv:
                self.status_text.Text = "Nenhum CSV carregado"
                return

            create_backup(self.current_csv, current_doc)
            headers, rows = ler_csv_utf8(self.current_csv)
            for p in selected:
                if p not in headers:
                    headers.append(p)
            for row in rows:
                while len(row) < len(headers):
                    row.append('')
            escrever_csv_utf8(self.current_csv, headers, rows)
            self.load_csv(self.current_csv)
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

            # Esconder janela temporariamente para modal funcionar
            self.Hide()
            try:
                selected = forms.SelectFromList.show(
                    params,
                    title="Remover Parametros",
                    button_name="Remover",
                    multiselect=True
                )
            finally:
                self.Show()

            if not selected:
                self.status_text.Text = "Nenhum parametro selecionado"
                return

            # Backup (silencioso)
            current_doc = _get_doc()
            create_backup(self.current_csv, current_doc)

            # Ler CSV atual
            headers, rows = ler_csv_utf8(self.current_csv)
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
            if escrever_csv_utf8(self.current_csv, headers, rows):
                self.load_csv(self.current_csv)
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
            _log("=== Iniciando ParameterPalette v5.1.0 ===")
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
