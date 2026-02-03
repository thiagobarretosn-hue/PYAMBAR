# -*- coding: utf-8 -*-
__title__ = "Configurar Parâmetros"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "3.1"
__doc__ = """
Config Parameters v3.1 - FILTRO SIMPLIFICADO

_
Uso:
1. Execute o script
2. Selecione os parâmetros desejados no DataGrid
3. Use botões: Select All, Clear, Restore Defaults
4. Clique em Save para salvar configuração



"""

import clr
import os
import sys
import json
import codecs
from datetime import datetime

# Add lib path for Snippets
LIB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.append(LIB_PATH)

clr.AddReference("System")
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from System.Windows.Markup import XamlReader
from System.Windows.Data import CollectionViewSource, PropertyGroupDescription
from System.ComponentModel import SortDescription, ListSortDirection
from System.Collections.ObjectModel import ObservableCollection
from Autodesk.Revit.DB import FilteredElementCollector, LabelUtils, SharedParameterElement
from pyrevit import script, forms, revit

# Snippets
from Snippets.data._state_persistence import (
    save_state, load_state,
    save_window_state, restore_window_state
)

# Globals
doc = revit.doc
output = script.get_output()
PATH_SCRIPT = os.path.dirname(__file__)

# Parâmetros padrão (usado em "Restore Defaults")
PARAMETROS_PADRAO = [
    "Módulo Montagem",
    "WBS",
    "WBS Detail",
    "WBS Instance",
    "WBS Detail Instance",
    "Ambiente",
    "Tipologia UH",
    "Stage"
]

# Localização antiga do config (v1.5) - para migração
OLD_CONFIG_FILE = os.path.join(
    os.getenv('APPDATA'),
    'PYAMBAR',
    'CopyParameters',
    'user_parameters.json'
)


# ============================================================================
# CONFIGURATION MANAGEMENT
# ============================================================================

def load_parameter_config():
    """
    Carrega configuração de parâmetros com hierarquia:
    1. Config do projeto (NA PASTA DAT, se existir)
    2. Config padrão da raiz (user_parameters.json) - APENAS LEITURA
    3. Padrão hardcoded (PARAMETROS_PADRAO)
    """
    import hashlib

    # 1. Tentar carregar config específico do projeto (NA PASTA DAT)
    try:
        project_path = doc.PathName
        if project_path:
            # Obter diretório do projeto
            project_dir = os.path.dirname(project_path)
            dat_folder = os.path.join(project_dir, "DAT")

            # Criar hash do caminho do projeto para nome único
            project_hash = hashlib.md5(project_path.encode('utf-8')).hexdigest()[:8]
            config_filename = "pyambar_params_{}.json".format(project_hash)

            # Caminho completo: DAT/pyambar_params_{hash}.json
            config_path = os.path.join(dat_folder, config_filename)

            # Se existir, carregar
            if os.path.exists(config_path):
                with codecs.open(config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    if 'parameters' in config_data:
                        return config_data['parameters']
    except:
        pass

    # 2. Tentar carregar config padrão da raiz (APENAS LEITURA)
    state = load_state(
        script_path=PATH_SCRIPT,
        state_folder_name="config",
        state_file_name="user_parameters.json"
    )

    if state and 'parameters' in state:
        return state['parameters']

    # 3. MIGRAÇÃO: Se não encontrou, tentar localização antiga (v1.5)
    if os.path.exists(OLD_CONFIG_FILE):
        try:
            with codecs.open(OLD_CONFIG_FILE, 'r', encoding='utf-8') as f:
                old_data = json.load(f)
                params = old_data.get('parameters', PARAMETROS_PADRAO)
                return params
        except:
            pass

    # 4. Retornar padrão hardcoded
    return PARAMETROS_PADRAO


def save_parameter_config(parameters):
    """
    Salva configuração de parâmetros:
    - Se projeto salvo: salva JSON na pasta DAT do projeto
    - NÃO modifica Copy Parameters config.json (ele lê direto do projeto)
    - NÃO mexe no config da raiz (só usado como padrão inicial)
    """
    import hashlib

    try:
        project_path = doc.PathName
        if not project_path:
            forms.alert("Salve o projeto primeiro para criar configuracao especifica!")
            return False

        # Obter diretório do projeto e criar pasta DAT
        project_dir = os.path.dirname(project_path)
        project_name = os.path.splitext(os.path.basename(project_path))[0]

        # Criar pasta DAT se não existir
        dat_folder = os.path.join(project_dir, "DAT")
        if not os.path.exists(dat_folder):
            os.makedirs(dat_folder)

        # Criar nome do arquivo com hash
        project_hash = hashlib.md5(project_path.encode('utf-8')).hexdigest()[:8]
        config_filename = "pyambar_params_{}.json".format(project_hash)

        # Caminho completo: DAT/pyambar_params_{hash}.json
        config_path = os.path.join(dat_folder, config_filename)

        # Salvar
        config_data = {
            "parameters": parameters,
            "project_path": project_path,
            "project_name": project_name,
            "version": "3.1",
            "_last_update": datetime.now().isoformat()
        }

        with codecs.open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

        return True

    except Exception as e:
        forms.alert("Erro ao salvar config do projeto:\n\n{}".format(str(e)))
        return False


# ============================================================================
# PARAMETER DATA CLASSES
# ============================================================================

class ParameterItem(object):
    """Container de dados para parâmetros (WPF binding)"""

    def __init__(self, name, param_type, group, is_selected=False, callback=None):
        self._name = name
        self._type = param_type
        self._group = group
        self._is_selected = is_selected
        self._callback = callback  # Callback para notificar mudanças

    @property
    def Name(self):
        return self._name

    @property
    def Type(self):
        return self._type

    @property
    def Group(self):
        return self._group

    @property
    def IsSelected(self):
        return self._is_selected

    @IsSelected.setter
    def IsSelected(self, value):
        if self._is_selected != value:
            self._is_selected = value
            # Notificar mudança
            if self._callback:
                self._callback()


# ============================================================================
# PARAMETER COLLECTION
# ============================================================================

class ParameterCollector:
    """Coleta parâmetros do projeto"""

    @staticmethod
    def get_all_project_parameters():
        """
        Coleta parâmetros únicos do projeto.

        FILTRO SIMPLIFICADO (v3.1):
        - APENAS Parâmetros de Projeto (via ParameterBindings)
        - Sem parâmetros built-in do sistema
        - Sem parâmetros compartilhados
        """
        # Mapear parâmetros de projeto com grupos nativos
        project_param_groups = ParameterCollector._get_project_parameter_groups()

        # Construir lista filtrada - apenas parâmetros de projeto
        parameters_list = []

        for param_name, param_group in project_param_groups.items():
            param_type = "Projeto"
            parameters_list.append((param_name, param_type, param_group))

        # Ordenar por grupo e nome
        parameters_list.sort(key=lambda x: (x[2], x[0]))

        return parameters_list

    @staticmethod
    def _classify_by_name(param_name):
        """
        Classifica parâmetro por nome em categorias úteis.
        Para parâmetros built-in do sistema que não estão em ParameterBindings.
        """
        name_lower = param_name.lower()

        # IDENTIFICAÇÃO
        if any(word in name_lower for word in ['nome', 'name', 'marca', 'mark', 'comentario', 'comment', 'descri', 'description', 'codigo', 'code', 'número', 'number']):
            return "Identificação"

        # DIMENSÕES
        if any(word in name_lower for word in ['comprimento', 'length', 'largura', 'width', 'altura', 'height', 'area', 'volume', 'perimetro', 'perimeter', 'espessura', 'thickness', 'diametro', 'diameter', 'raio', 'radius']):
            return "Dimensões"

        # LOCALIZAÇÃO
        if any(word in name_lower for word in ['nivel', 'level', 'fase', 'phase', 'workset', 'offset', 'elevacao', 'elevation', 'piso', 'floor']):
            return "Localização"

        # MATERIAIS
        if any(word in name_lower for word in ['material', 'acabamento', 'finish', 'textura', 'texture', 'cor', 'color']):
            return "Materiais"

        # ESTRUTURAL
        if any(word in name_lower for word in ['estrutural', 'structural', 'armadura', 'rebar', 'concreto', 'concrete', 'aco', 'steel', 'carga', 'load']):
            return "Estrutural"

        # MEP / SISTEMAS
        if any(word in name_lower for word in ['fluxo', 'flow', 'pressao', 'pressure', 'temperatura', 'temperature', 'vazao', 'diametro', 'eletric', 'voltage', 'corrente', 'current', 'potencia', 'power']):
            return "Sistemas (MEP)"

        # GEOMETRIA
        if any(word in name_lower for word in ['coordenada', 'coordinate', 'ponto', 'point', 'rotacao', 'rotation', 'angulo', 'angle', 'orientacao', 'orientation']):
            return "Geometria"

        # CATEGORIA/TIPO
        if any(word in name_lower for word in ['categoria', 'category', 'familia', 'family', 'tipo', 'type', 'simbolo', 'symbol']):
            return "Categoria e Tipo"

        # VISIBILIDADE/GRÁFICOS
        if any(word in name_lower for word in ['visibilidade', 'visibility', 'grafico', 'graphic', 'linha', 'line', 'padrao', 'pattern', 'cor', 'color']):
            return "Visibilidade e Gráficos"

        # DADOS/INFORMAÇÕES
        if any(word in name_lower for word in ['data', 'date', 'autor', 'author', 'criado', 'created', 'modificado', 'modified', 'revisao', 'revision', 'versao', 'version']):
            return "Dados e Informações"

        # Se não se encaixa em nenhuma categoria
        return "Outros"

    @staticmethod
    def _get_project_parameter_groups():
        """
        Obtém mapeamento de nome do parâmetro -> grupo usando ParameterBindings.
        Esta é a fonte correta de informação de grupos no Revit.
        """
        param_group_map = {}

        try:
            # Acessar ParameterBindings do documento
            iterator = doc.ParameterBindings.ForwardIterator()
            iterator.Reset()

            while iterator.MoveNext():
                try:
                    definition = iterator.Key
                    param_name = definition.Name

                    # Aqui sim temos acesso ao ParameterGroup correto!
                    if hasattr(definition, 'ParameterGroup'):
                        param_group_enum = definition.ParameterGroup

                        # Traduzir com LabelUtils
                        try:
                            label = LabelUtils.GetLabelFor(param_group_enum)
                            if label and label.strip() and label != "INVALID":
                                param_group_map[param_name] = label
                                continue
                        except:
                            pass

                        # Fallback: dicionário de traduções
                        try:
                            group_name = param_group_enum.ToString()
                            if group_name and group_name != "INVALID":
                                translated = ParameterCollector._translate_parameter_group(group_name)
                                param_group_map[param_name] = translated
                                continue
                        except:
                            pass

                    # Se chegou aqui, não conseguiu obter grupo
                    param_group_map[param_name] = "Parâmetros de Projeto"

                except Exception:
                    continue

        except Exception as e:
            output.print_md("⚠️ Erro ao ler ParameterBindings: {}".format(str(e)))

        return param_group_map

    @staticmethod
    def _translate_parameter_group(group_enum_string):
        """Traduz nome do enum ParameterGroup para português"""
        translations = {
            "PG_CONSTRUCTION": "Construção",
            "PG_IDENTITY_DATA": "Dados de identidade",
            "PG_GEOMETRY": "Geometria",
            "PG_MATERIALS": "Materiais e acabamentos",
            "PG_STRUCTURAL": "Estrutural",
            "PG_MECHANICAL": "Mecânico",
            "PG_ELECTRICAL": "Elétrico",
            "PG_PLUMBING": "Hidráulico",
            "PG_ENERGY_ANALYSIS": "Análise de energia",
            "PG_TEXT": "Texto",
            "PG_CONSTRAINTS": "Restrições",
            "PG_PHASING": "Fase",
            "PG_GRAPHICS": "Gráficos",
            "PG_DIMENSIONS": "Cotas",
            "PG_VISIBILITY": "Visibilidade",
            "PG_ANALYTICAL_PROPERTIES": "Propriedades analíticas",
            "PG_ANALYTICAL_ALIGNMENT": "Alinhamento analítico",
            "PG_REFERENCE": "Referência",
            "PG_GENERAL": "Geral",
            "PG_DIVISION_GEOMETRY": "Geometria de divisão",
            "PG_SLAB_SHAPE_EDIT": "Edição de forma de laje",
            "PG_FLEXIBLE": "Flexível",
            "PG_RELEASES_MEMBER_FORCES": "Liberações/Forças de membros",
            "PG_IFC": "IFC",
            "PG_FIRE_PROTECTION": "Proteção contra incêndio",
            "PG_LIGHT_PHOTOMETRICS": "Fotometria de iluminação",
            "PG_PATTERN": "Padrão",
            "PG_TITLE": "Título",
            "PG_DATA": "Dados",
            "PG_OVERALL_LEGEND": "Legenda geral",
            "PG_ROTATION_ABOUT": "Rotação sobre",
            "PG_REBAR_SYSTEM_LAYERS": "Camadas de sistema de armadura",
            "PG_SUPPORT": "Suporte",
            "PG_SECONDARY_END": "Extremidade secundária",
            "PG_PRIMARY_END": "Extremidade primária",
            "PG_MOMENTS": "Momentos",
            "PG_FORCES": "Forças",
            "PG_LENGTH": "Comprimento",
            "PG_PROFILE_2": "Perfil 2",
            "PG_PROFILE_1": "Perfil 1",
            "PG_PROFILE": "Perfil"
        }

        if group_enum_string in translations:
            return translations[group_enum_string]

        # Se não tem tradução, limpar o nome
        return group_enum_string.replace("PG_", "").replace("_", " ").title()


# ============================================================================
# WPF WINDOW
# ============================================================================

class ConfigWindow:
    """Janela de configuração WPF"""

    def __init__(self, xaml_path):
        # Carregar XAML
        try:
            with open(xaml_path, 'r') as f:
                xaml_string = f.read()
            self.window = XamlReader.Parse(xaml_string)
        except Exception as e:
            forms.alert("Erro ao carregar UI: {}".format(str(e)), exitscript=True)

        # Obter controles
        self.parameters_listbox = self.window.FindName('parameters_listbox')
        self.scroll_viewer = self.window.FindName('scroll_viewer')
        self.search_box = self.window.FindName('search_box')
        self.btn_clear_search = self.window.FindName('btn_clear_search')
        self.btn_select_all = self.window.FindName('btn_select_all')
        self.btn_clear = self.window.FindName('btn_clear')
        self.btn_restore = self.window.FindName('btn_restore')
        self.btn_save = self.window.FindName('btn_save')
        self.btn_cancel = self.window.FindName('btn_cancel')
        self.selected_listbox = self.window.FindName('selected_listbox')
        self.selected_count = self.window.FindName('selected_count')

        # Carregar parâmetros
        self.Parameters = ObservableCollection[object]()
        self._load_parameters()

        # Configurar view com grouping e sorting
        self.view = CollectionViewSource.GetDefaultView(self.Parameters)
        self.view.GroupDescriptions.Add(PropertyGroupDescription("Group"))
        self.view.SortDescriptions.Add(SortDescription("Group", ListSortDirection.Ascending))
        self.view.SortDescriptions.Add(SortDescription("Name", ListSortDirection.Ascending))

        self.parameters_listbox.ItemsSource = self.view

        # Event handlers
        self.scroll_viewer.PreviewMouseWheel += self.on_mouse_wheel
        self.search_box.GotFocus += self.on_search_got_focus
        self.search_box.LostFocus += self.on_search_lost_focus
        self.search_box.TextChanged += self.on_search_changed
        self.btn_clear_search.Click += self.on_clear_search_click
        self.parameters_listbox.SelectionChanged += self.on_selection_changed
        self.btn_select_all.Click += self.select_all_click
        self.btn_clear.Click += self.clear_selection_click
        self.btn_restore.Click += self.restore_default_click
        self.btn_save.Click += self.save_click
        self.btn_cancel.Click += self.cancel_click
        self.window.Closing += self._on_closing

        # Restaurar estado da janela (posição/tamanho)
        restore_window_state(self.window, PATH_SCRIPT, "config", "window_state.json")

        # Restaurar seleção inicial
        self._restore_initial_selection()
        # Atualizar lista inicial de selecionados
        self.update_selected_list()

    def _restore_initial_selection(self):
        """Restaura seleção inicial dos parâmetros salvos"""
        saved_params = load_parameter_config()

        for item in self.Parameters:
            if item.Name in saved_params:
                self.parameters_listbox.SelectedItems.Add(item)

    def on_selection_changed(self, sender, e):
        """Handler quando seleção da ListBox muda"""
        self.update_selected_list()

    def update_selected_list(self):
        """Atualiza a lista da coluna direita com parâmetros selecionados"""
        self.selected_listbox.Items.Clear()

        selected_params = [item.Name for item in self.parameters_listbox.SelectedItems]
        selected_params.sort()  # Ordenar alfabeticamente

        for param_name in selected_params:
            self.selected_listbox.Items.Add(param_name)

        # Atualizar contador
        self.selected_count.Text = str(len(selected_params))

    def on_mouse_wheel(self, sender, e):
        """Melhora scroll com mouse wheel"""
        self.scroll_viewer.ScrollToVerticalOffset(
            self.scroll_viewer.VerticalOffset - e.Delta / 3
        )
        e.Handled = True

    def on_search_got_focus(self, sender, e):
        """Remove placeholder quando campo recebe foco"""
        from System.Windows.Media import SolidColorBrush, Colors
        if self.search_box.Text == "Digite para buscar parametros...":
            self.search_box.Text = ""
            self.search_box.Foreground = SolidColorBrush(Colors.Black)

    def on_search_lost_focus(self, sender, e):
        """Restaura placeholder se campo estiver vazio"""
        from System.Windows.Media import SolidColorBrush, Color
        if self.search_box.Text.strip() == "":
            self.search_box.Text = "Digite para buscar parametros..."
            # Cinza: #BDBDBD
            self.search_box.Foreground = SolidColorBrush(Color.FromRgb(189, 189, 189))

    def on_search_changed(self, sender, e):
        """Filtra parâmetros conforme busca"""
        search_text = self.search_box.Text.strip()

        # Ignorar se for o placeholder
        if search_text == "Digite para buscar parametros..." or not search_text:
            self.view.Filter = None
        else:
            # Filtrar por nome de parâmetro (case insensitive)
            search_lower = search_text.lower()
            self.view.Filter = lambda item: search_lower in item.Name.lower()

        self.view.Refresh()

    def on_clear_search_click(self, sender, args):
        """Limpa campo de busca"""
        from System.Windows.Media import SolidColorBrush, Color
        self.search_box.Text = "Digite para buscar parametros..."
        self.search_box.Foreground = SolidColorBrush(Color.FromRgb(189, 189, 189))
        self.view.Filter = None
        self.view.Refresh()

    def _load_parameters(self):
        """Carrega parâmetros do projeto"""
        all_params = ParameterCollector.get_all_project_parameters()

        if not all_params:
            forms.alert("Nenhum parâmetro encontrado no projeto!", exitscript=True)

        for param_name, param_type, param_group in all_params:
            # Não precisa IsSelected, controlado pela ListBox
            self.Parameters.Add(ParameterItem(
                param_name,
                param_type,
                param_group,
                is_selected=False,
                callback=None
            ))

    def select_all_click(self, sender, args):
        """Seleciona todos os parâmetros"""
        self.parameters_listbox.SelectAll()

    def clear_selection_click(self, sender, args):
        """Limpa seleção"""
        self.parameters_listbox.SelectedItems.Clear()

    def restore_default_click(self, sender, args):
        """Restaura seleção padrão"""
        self.parameters_listbox.SelectedItems.Clear()

        for item in self.Parameters:
            if item.Name in PARAMETROS_PADRAO:
                self.parameters_listbox.SelectedItems.Add(item)

    def save_click(self, sender, args):
        """Salva configuração"""
        selected = [item.Name for item in self.parameters_listbox.SelectedItems]

        if not selected:
            forms.alert("Selecione pelo menos um parâmetro!")
            return

        success = save_parameter_config(selected)

        if success:
            # Config salvo - fechar janela sem alert
            self.window.DialogResult = True
            self.window.Close()
        else:
            # Erro já foi exibido em save_parameter_config()
            pass

    def cancel_click(self, sender, args):
        """Cancela e fecha"""
        self.window.DialogResult = False
        self.window.Close()

    def _on_closing(self, sender, event):
        """Salva estado da janela ao fechar"""
        save_window_state(self.window, PATH_SCRIPT, "config", "window_state.json")

    def ShowDialog(self):
        """Exibe janela modal"""
        return self.window.ShowDialog()


# ============================================================================
# MAIN
# ============================================================================

def main():
    try:
        xaml_path = os.path.join(PATH_SCRIPT, 'config_ui.xaml')

        if not os.path.exists(xaml_path):
            forms.alert("Arquivo XAML nao encontrado!", exitscript=True)
            return

        window = ConfigWindow(xaml_path)
        window.window.ShowDialog()

    except Exception as e:
        forms.alert("Erro ao carregar interface:\n\n{}".format(str(e)), exitscript=True)


if __name__ == '__main__':
    main()
