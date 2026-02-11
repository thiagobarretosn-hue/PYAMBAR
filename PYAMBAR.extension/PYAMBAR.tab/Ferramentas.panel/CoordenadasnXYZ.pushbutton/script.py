# -*- coding: utf-8 -*-
"""
Coordenadas XYZ - Ferramenta Unificada v9.11

Fluxo simplificado em UMA UNICA TELA:
1. Selecionar elementos (filtro MEP automatico)
2. Escolher ponto de referencia (origem ou customizado)
3. Escolher prefixo para numeracao
4. Marcar opcoes de saida
5. Executar - faz tudo de uma vez

VERSAO: 9.11
AUTOR: Thiago Barreto Sobral Nunes
DATA: 09/02/2026

MUDANCAS v9.11:
- ADD: Ponto de Referencia customizado - permite selecionar ponto no modelo como origem
- ADD: Coordenadas calculadas RELATIVAS ao ponto de referencia (nao mais absolutas)
- ADD: Ordenacao por distancia relativa ao ponto de referencia
- ADD: Validacao impede executar sem ponto selecionado quando modo customizado ativo

MUDANCAS v9.10:
- FIX: Stage duplicado - agora detecta campos duplicados e escolhe SHARED PARAMETER
- FIX: Stage de "Multiplas Categorias" (shared param) preferido sobre "Informacoes do Projeto"
- ADD: is_shared_parameter_field() para identificar shared params vs built-in

MUDANCAS v9.9:
- FIX: Schedule volta a ser Multi-Category (como versao original que funcionava)
- FIX: Stage agora aparece corretamente (Multi-Category inclui todos shared params)

MUDANCAS v9.7:
- ADD: MIGRACAO AUTOMATICA de GUIDs - parametros antigos sao substituidos pelos oficiais
- ADD: GUIDs oficiais definidos em GUIDS_OFICIAIS para consistencia entre projetos
- FIX: Verifica GUID do parametro existente antes de decidir criar/usar

MUDANCAS v9.6:
- FIX: Parametros NAO sao criados se ja existirem no projeto (evita duplicacao GUID)
- FIX: Schedule busca campos por aliases (Mark/Marca, Comments/Comentarios)
- ADD: Debug mostra campos disponiveis no schedule para diagnostico

MUDANCAS v9.5:
- ADD: Filtro de selecao MEP (exclui linhas, eixos, grids, etc.)
- FIX: Performance - encontrar_maior_numero otimizado (filtra por categorias MEP)
- FIX: Parametros adicionados SOMENTE as categorias dos elementos selecionados
- FIX: Schedule criado para categoria especifica (nao Multi-Category)
- FIX: CSV com BOM UTF-8 para Excel reconhecer acentos
- FIX: Logging melhorado em vez de except:pass
- FIX: ActiveView fora de transaction
- FIX: Regex pattern cacheado

MUDANCAS v9.4:
- ADD: Opcao "Somente Coordenadas" - gera coordenadas sem alterar marcas existentes
- ADD: CSV com nome unico - adiciona sufixo _1, _2, etc se arquivo ja existir
- ADD: Schedule reutiliza existente em vez de recriar (evita erros)
"""
__title__ = "Coord\nXYZ"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "9.11"

# ============================================================================
# IMPORTS
# ============================================================================

import codecs
import json
import os
import re
from datetime import datetime

import clr

clr.AddReference("System")
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    CategoryType,
    ElementCategoryFilter,
    ElementFilter,
    ElementId,
    FilteredElementCollector,
    LogicalOrFilter,
    ScheduleFilter,
    ScheduleFilterType,
    ViewSchedule,
)
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from pyrevit import HOST_APP, forms, revit, script
from System.Collections.Generic import List
from System.IO import MemoryStream
from System.Text import Encoding
from System.Windows import Visibility
from System.Windows.Markup import XamlReader

# Imports condicionais para compatibilidade Revit 2021-2026
try:
    from Autodesk.Revit.DB import ParameterType
except ImportError:
    ParameterType = None

try:
    from Autodesk.Revit.DB import BuiltInParameterGroup
except ImportError:
    BuiltInParameterGroup = None

try:
    from Autodesk.Revit.DB import GroupTypeId, SpecTypeId, UnitTypeId
except ImportError:
    SpecTypeId = None
    GroupTypeId = None
    UnitTypeId = None

# IMPORTS DE SNIPPETS
from Snippets._transaction import ef_Transaction
from Snippets.core._revit_version_helpers import get_revit_year
from Snippets.geometry._geometry_center import obter_centro_elemento
from Snippets.views._schedule_utilities import buscar_schedule_por_nome

# ============================================================================
# GLOBALS
# ============================================================================

doc = revit.doc
uidoc = revit.uidoc
app = HOST_APP.app
rvt_year = get_revit_year()
PATH_SCRIPT = os.path.dirname(__file__)
output = script.get_output()

PARAM_COORD_X = "Coord_X"
PARAM_COORD_Y = "Coord_Y"
PARAM_COORD_Z = "Coord_Z"
PARAM_DATA = "Coord_DataGeracao"
PARAM_QTY = "QTY"
PARAM_SCHEDULE_CATEGORY = "Schedule Category"

# Arquivo de parametros compartilhados FIXO (GUIDs constantes)
LIB_PATH = os.path.join(PATH_SCRIPT, '..', '..', '..', 'lib')
SHARED_PARAMS_FILE = os.path.join(LIB_PATH, 'shared_parameters', 'PYAMBAR_CoordXYZ.txt')

STATE_FOLDER = os.path.join(PATH_SCRIPT, "state")
STATE_FILE = os.path.join(STATE_FOLDER, "coordenadasxyz_state.json")

# ============================================================================
# CATEGORIAS MEP PERMITIDAS
# ============================================================================

# Categorias MEP validas para selecao (hidrossanitario, eletrico, mecanico)
MEP_CATEGORIES = [
    # HIDROSSANITARIO / PLUMBING
    BuiltInCategory.OST_PipeCurves,           # Tubos
    BuiltInCategory.OST_PipeFitting,          # Conexoes de tubo
    BuiltInCategory.OST_PipeAccessory,        # Acessorios de tubo
    BuiltInCategory.OST_FlexPipeCurves,       # Tubos flexiveis
    BuiltInCategory.OST_PlumbingFixtures,     # Aparelhos sanitarios
    BuiltInCategory.OST_Sprinklers,           # Sprinklers

    # ELETRICO / ELECTRICAL
    BuiltInCategory.OST_ElectricalEquipment,  # Equipamentos eletricos
    BuiltInCategory.OST_ElectricalFixtures,   # Dispositivos eletricos
    BuiltInCategory.OST_LightingFixtures,     # Luminarias
    BuiltInCategory.OST_LightingDevices,      # Dispositivos de iluminacao
    BuiltInCategory.OST_CableTray,            # Eletrocalhas
    BuiltInCategory.OST_CableTrayFitting,     # Conexoes eletrocalha
    BuiltInCategory.OST_Conduit,              # Eletrodutos
    BuiltInCategory.OST_ConduitFitting,       # Conexoes eletroduto
    BuiltInCategory.OST_CommunicationDevices, # Dispositivos comunicacao
    BuiltInCategory.OST_DataDevices,          # Dispositivos dados
    BuiltInCategory.OST_FireAlarmDevices,     # Alarme incendio
    BuiltInCategory.OST_NurseCallDevices,     # Chamada enfermagem
    BuiltInCategory.OST_SecurityDevices,      # Dispositivos seguranca
    BuiltInCategory.OST_TelephoneDevices,     # Dispositivos telefone

    # MECANICO / HVAC
    BuiltInCategory.OST_DuctCurves,           # Dutos
    BuiltInCategory.OST_DuctFitting,          # Conexoes de duto
    BuiltInCategory.OST_DuctAccessory,        # Acessorios de duto
    BuiltInCategory.OST_FlexDuctCurves,       # Dutos flexiveis
    BuiltInCategory.OST_DuctTerminal,         # Terminais (difusores, grelhas)
    BuiltInCategory.OST_MechanicalEquipment,  # Equipamentos mecanicos

    # GENERICO MEP
    BuiltInCategory.OST_GenericModel,         # Modelos genericos
    BuiltInCategory.OST_MechanicalControlDevices,  # Controles mecanicos
]

# IDs das categorias para verificacao rapida
MEP_CATEGORY_IDS = set()

def _init_mep_category_ids():
    """Inicializa set de IDs de categorias MEP para lookup rapido."""
    global MEP_CATEGORY_IDS
    for cat in MEP_CATEGORIES:
        try:
            cat_id = ElementId(cat)
            if hasattr(cat_id, 'Value'):
                MEP_CATEGORY_IDS.add(cat_id.Value)
            else:
                MEP_CATEGORY_IDS.add(cat_id.IntegerValue)
        except:
            pass

_init_mep_category_ids()

# Cache de regex patterns
_MARK_PATTERNS = {}

def _get_mark_pattern(prefixo):
    """Retorna pattern cacheado para prefixo."""
    if prefixo not in _MARK_PATTERNS:
        _MARK_PATTERNS[prefixo] = re.compile(r"^{}-(\d+)$".format(re.escape(prefixo)))
    return _MARK_PATTERNS[prefixo]

# ============================================================================
# FILTRO DE SELECAO MEP
# ============================================================================

class MEPSelectionFilter(ISelectionFilter):
    """Filtro que permite apenas elementos MEP (hidro, eletrico, mecanico)."""

    def AllowElement(self, element):
        """Verifica se elemento e de categoria MEP permitida."""
        if not element:
            return False

        try:
            cat = element.Category
            if not cat:
                return False

            # Verificar se e categoria de modelo
            if cat.CategoryType != CategoryType.Model:
                return False

            # Verificar se esta na lista de categorias MEP
            cat_id = cat.Id
            if hasattr(cat_id, 'Value'):
                return cat_id.Value in MEP_CATEGORY_IDS
            else:
                return cat_id.IntegerValue in MEP_CATEGORY_IDS

        except Exception as e:
            output.print_md("*Aviso filtro: {}*".format(str(e)))
            return False

    def AllowReference(self, reference, position):
        """Permite referencias de elementos MEP."""
        return True

# ============================================================================
# XAML - Interface Unificada SIMPLIFICADA
# ============================================================================

XAML_WINDOW = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Coordenadas XYZ v9.11 - Fluxo Unificado"
        Height="680" Width="460"
        WindowStartupLocation="CenterScreen"
        ResizeMode="NoResize"
        Background="#F8FAFC">
    <Grid>
        <Grid.RowDefinitions>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="*"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
        </Grid.RowDefinitions>

        <!-- HEADER -->
        <Border Grid.Row="0" Background="#4F46E5" Padding="15,12">
            <StackPanel>
                <TextBlock Text="Coordenadas XYZ" FontSize="18" FontWeight="Bold" Foreground="White"/>
                <TextBlock Text="Selecione, numere e gere coordenadas em um clique" FontSize="11" Foreground="#C7D2FE" Margin="0,2,0,0"/>
                <TextBlock Text="Filtro MEP ativo: apenas elementos hidro/eletrico/mecanico" FontSize="10" Foreground="#A5B4FC" Margin="0,4,0,0"/>
            </StackPanel>
        </Border>

        <!-- CONTEUDO PRINCIPAL -->
        <ScrollViewer Grid.Row="1" VerticalScrollBarVisibility="Auto" Padding="5">
            <StackPanel Margin="12">

                <!-- 1. SELECAO -->
                <Border BorderBrush="#E2E8F0" BorderThickness="1" CornerRadius="6" Padding="12" Margin="0,0,0,12" Background="White">
                    <StackPanel>
                        <TextBlock Text="1. Selecao de Elementos" FontWeight="SemiBold" FontSize="13" Foreground="#1E293B" Margin="0,0,0,10"/>
                        <Button x:Name="btnSelect" Content="Selecionar Elementos MEP..." Height="36" Background="#3B82F6" Foreground="White" FontWeight="Medium" Cursor="Hand"/>
                        <TextBlock x:Name="txtCount" Text="0 elementos selecionados" FontSize="12" Foreground="#64748B" Margin="0,8,0,0" FontWeight="Medium"/>
                        <TextBlock x:Name="txtCategories" Text="" FontSize="10" Foreground="#94A3B8" Margin="0,4,0,0" TextWrapping="Wrap"/>
                    </StackPanel>
                </Border>

                <!-- 1.5 PONTO DE REFERENCIA -->
                <Border BorderBrush="#E2E8F0" BorderThickness="1" CornerRadius="6" Padding="12" Margin="0,0,0,12" Background="White">
                    <StackPanel>
                        <TextBlock Text="Ponto de Referencia (Origem)" FontWeight="SemiBold" FontSize="13" Foreground="#1E293B" Margin="0,0,0,10"/>
                        <TextBlock Text="Coordenadas serao calculadas relativas a este ponto" FontSize="11" Foreground="#64748B" Margin="0,0,0,8"/>
                        <RadioButton x:Name="rbOrigemProjeto" GroupName="OrigemGroup" Content="Origem do Projeto (0, 0, 0)" IsChecked="True" Margin="0,0,0,5" FontSize="12"/>
                        <StackPanel Orientation="Horizontal" Margin="0,5,0,0">
                            <RadioButton x:Name="rbOrigemCustom" GroupName="OrigemGroup" Content="Ponto Customizado:" VerticalAlignment="Center" FontSize="12"/>
                            <Button x:Name="btnPickPoint" Content="Selecionar Ponto..." Width="130" Height="26" Margin="10,0,0,0" Background="#F59E0B" Foreground="White" FontWeight="Medium" Cursor="Hand" IsEnabled="False"/>
                        </StackPanel>
                        <TextBlock x:Name="txtBasePoint" Text="" FontSize="11" Foreground="#059669" Margin="0,6,0,0" FontWeight="Medium"/>
                    </StackPanel>
                </Border>

                <!-- 2. NUMERACAO -->
                <Border BorderBrush="#E2E8F0" BorderThickness="1" CornerRadius="6" Padding="12" Margin="0,0,0,12" Background="White">
                    <StackPanel>
                        <TextBlock Text="2. Prefixo da Numeracao" FontWeight="SemiBold" FontSize="13" Foreground="#1E293B" Margin="0,0,0,10"/>

                        <!-- Opcao Somente Coordenadas -->
                        <CheckBox x:Name="chkSomenteCoordenadas" Content="Somente Coordenadas (manter marcas existentes)" Margin="0,0,0,10" FontSize="12" Foreground="#DC2626" FontWeight="Medium"/>

                        <StackPanel x:Name="pnlPrefixos">
                            <TextBlock Text="Elementos serao numerados sequencialmente (ex: SP-001, SP-002...)" FontSize="11" Foreground="#64748B" Margin="0,0,0,8"/>
                            <RadioButton x:Name="rbSP" GroupName="PrefixGroup" Content="SP - Plumbing (Sanitario/Hidraulico)" IsChecked="True" Margin="0,0,0,5" FontSize="12"/>
                            <RadioButton x:Name="rbEP" GroupName="PrefixGroup" Content="EP - Electrical (Eletrico)" Margin="0,0,0,5" FontSize="12"/>
                            <RadioButton x:Name="rbMP" GroupName="PrefixGroup" Content="MP - Mechanical (HVAC)" Margin="0,0,0,5" FontSize="12"/>
                            <StackPanel Orientation="Horizontal" Margin="0,5,0,0">
                                <RadioButton x:Name="rbCustom" GroupName="PrefixGroup" Content="Customizado:" VerticalAlignment="Center" FontSize="12"/>
                                <TextBox x:Name="txtPrefix" Text="XX" Width="60" Height="26" Margin="10,0,0,0" IsEnabled="False" VerticalContentAlignment="Center" HorizontalContentAlignment="Center" FontWeight="Bold"/>
                            </StackPanel>
                        </StackPanel>
                    </StackPanel>
                </Border>

                <!-- 3. SAIDAS -->
                <Border BorderBrush="#E2E8F0" BorderThickness="1" CornerRadius="6" Padding="12" Background="White">
                    <StackPanel>
                        <TextBlock Text="3. Opcoes de Saida" FontWeight="SemiBold" FontSize="13" Foreground="#1E293B" Margin="0,0,0,10"/>

                        <CheckBox x:Name="chkScheduleCoord" Content="Criar Schedule de Coordenadas (Marca, X, Y, Z)" IsChecked="True" Margin="0,0,0,8" FontSize="12"/>

                        <CheckBox x:Name="chkScheduleQty" Content="Criar Schedule de Quantitativos (Marca, Stage, QTY)" IsChecked="True" Margin="0,0,0,8" FontSize="12"/>

                        <CheckBox x:Name="chkCSV" Content="Exportar CSV" IsChecked="True" Margin="0,0,0,8" FontSize="12"/>

                        <StackPanel x:Name="pnlFolder" Orientation="Horizontal" Margin="20,0,0,0">
                            <TextBox x:Name="txtFolder" Width="280" Height="28" IsReadOnly="True" Background="#F1F5F9" VerticalContentAlignment="Center" Padding="8,0"/>
                            <Button x:Name="btnFolder" Content="..." Width="35" Height="28" Margin="5,0,0,0"/>
                        </StackPanel>
                    </StackPanel>
                </Border>

            </StackPanel>
        </ScrollViewer>

        <!-- STATUS BAR -->
        <Border Grid.Row="2" Background="#F1F5F9" Padding="12,8" BorderBrush="#E2E8F0" BorderThickness="0,1,0,0">
            <TextBlock x:Name="txtStatus" Text="Pronto. Selecione elementos MEP para comecar." FontSize="11" Foreground="#64748B"/>
        </Border>

        <!-- BOTOES -->
        <Border Grid.Row="3" Background="White" Padding="15,12" BorderBrush="#E2E8F0" BorderThickness="0,1,0,0">
            <StackPanel Orientation="Horizontal" HorizontalAlignment="Right">
                <Button x:Name="btnCancel" Content="Cancelar" Width="100" Height="36" Margin="0,0,10,0" FontSize="12"/>
                <Button x:Name="btnExecute" Content="EXECUTAR" Width="150" Height="36" Background="#10B981" Foreground="White" FontWeight="Bold" FontSize="13" Cursor="Hand"/>
            </StackPanel>
        </Border>
    </Grid>
</Window>
"""

# ============================================================================
# WINDOW CLASS
# ============================================================================

class CoordWindow(object):
    """Janela WPF unificada."""

    def __init__(self):
        self.resultado = None
        self.dados = {}
        self.element_ids = []
        self.selected_categories = set()  # Categorias dos elementos selecionados
        self.export_folder = ""
        self.mep_filter = MEPSelectionFilter()
        self.base_point = None  # XYZ customizado ou None para origem

        # Carregar XAML
        stream = MemoryStream(Encoding.UTF8.GetBytes(XAML_WINDOW))
        self.window = XamlReader.Load(stream)

        self._find_controls()
        self._wire_events()
        self._load_state()
        self._update_ui()

    def _find_controls(self):
        self.btnSelect = self.window.FindName("btnSelect")
        self.txtCount = self.window.FindName("txtCount")
        self.txtCategories = self.window.FindName("txtCategories")
        self.chkSomenteCoordenadas = self.window.FindName("chkSomenteCoordenadas")
        self.pnlPrefixos = self.window.FindName("pnlPrefixos")
        self.rbSP = self.window.FindName("rbSP")
        self.rbEP = self.window.FindName("rbEP")
        self.rbMP = self.window.FindName("rbMP")
        self.rbCustom = self.window.FindName("rbCustom")
        self.txtPrefix = self.window.FindName("txtPrefix")
        self.chkScheduleCoord = self.window.FindName("chkScheduleCoord")
        self.chkScheduleQty = self.window.FindName("chkScheduleQty")
        self.chkCSV = self.window.FindName("chkCSV")
        self.pnlFolder = self.window.FindName("pnlFolder")
        self.txtFolder = self.window.FindName("txtFolder")
        self.btnFolder = self.window.FindName("btnFolder")
        self.rbOrigemProjeto = self.window.FindName("rbOrigemProjeto")
        self.rbOrigemCustom = self.window.FindName("rbOrigemCustom")
        self.btnPickPoint = self.window.FindName("btnPickPoint")
        self.txtBasePoint = self.window.FindName("txtBasePoint")
        self.txtStatus = self.window.FindName("txtStatus")
        self.btnCancel = self.window.FindName("btnCancel")
        self.btnExecute = self.window.FindName("btnExecute")

    def _wire_events(self):
        self.btnSelect.Click += self.on_select
        self.rbOrigemProjeto.Checked += self.on_origem_changed
        self.rbOrigemCustom.Checked += self.on_origem_changed
        self.btnPickPoint.Click += self.on_pick_point
        self.chkSomenteCoordenadas.Checked += self.on_somente_coord_changed
        self.chkSomenteCoordenadas.Unchecked += self.on_somente_coord_changed
        self.rbSP.Checked += self.on_prefix_changed
        self.rbEP.Checked += self.on_prefix_changed
        self.rbMP.Checked += self.on_prefix_changed
        self.rbCustom.Checked += self.on_prefix_changed
        self.chkCSV.Checked += self.on_csv_changed
        self.chkCSV.Unchecked += self.on_csv_changed
        self.btnFolder.Click += self.on_folder
        self.btnCancel.Click += self.on_cancel
        self.btnExecute.Click += self.on_execute

    def _load_state(self):
        try:
            if os.path.exists(STATE_FILE):
                with codecs.open(STATE_FILE, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                self.chkSomenteCoordenadas.IsChecked = state.get("somente_coordenadas", False)
                prefix = state.get("prefix", "SP")
                if prefix == "EP":
                    self.rbEP.IsChecked = True
                elif prefix == "MP":
                    self.rbMP.IsChecked = True
                elif prefix not in ["SP", "EP", "MP"]:
                    self.rbCustom.IsChecked = True
                    self.txtPrefix.Text = prefix
                self.chkScheduleCoord.IsChecked = state.get("schedule_coord", True)
                self.chkScheduleQty.IsChecked = state.get("schedule_qty", True)
                self.chkCSV.IsChecked = state.get("csv", True)
                self.export_folder = state.get("folder", "")
                self.txtFolder.Text = self.export_folder
                if state.get("origem_custom", False):
                    self.rbOrigemCustom.IsChecked = True
        except Exception as e:
            output.print_md("*Aviso ao carregar state: {}*".format(str(e)))

    def _save_state(self):
        try:
            if not os.path.exists(STATE_FOLDER):
                os.makedirs(STATE_FOLDER)
            state = {
                "somente_coordenadas": self.chkSomenteCoordenadas.IsChecked,
                "prefix": self._get_prefix(),
                "schedule_coord": self.chkScheduleCoord.IsChecked,
                "schedule_qty": self.chkScheduleQty.IsChecked,
                "csv": self.chkCSV.IsChecked,
                "folder": self.export_folder,
                "origem_custom": self.rbOrigemCustom.IsChecked
            }
            with codecs.open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            output.print_md("*Aviso ao salvar state: {}*".format(str(e)))

    def _update_ui(self):
        self.txtCount.Text = "{} elementos selecionados".format(len(self.element_ids))

        # Mostrar categorias selecionadas
        if self.selected_categories:
            cat_names = sorted(list(self.selected_categories))
            if len(cat_names) > 3:
                self.txtCategories.Text = "Categorias: {}, ... (+{})".format(
                    ", ".join(cat_names[:3]), len(cat_names) - 3
                )
            else:
                self.txtCategories.Text = "Categorias: {}".format(", ".join(cat_names))
        else:
            self.txtCategories.Text = ""

        self.txtPrefix.IsEnabled = self.rbCustom.IsChecked

        # Habilitar botao pick point apenas quando custom selecionado
        self.btnPickPoint.IsEnabled = self.rbOrigemCustom.IsChecked

        # Mostrar texto do ponto base
        if self.rbOrigemCustom.IsChecked and self.base_point:
            self.txtBasePoint.Text = "Ponto: X={:.3f}, Y={:.3f}, Z={:.3f}".format(
                self.base_point.X, self.base_point.Y, self.base_point.Z)
        elif self.rbOrigemProjeto.IsChecked:
            self.txtBasePoint.Text = ""
        elif self.rbOrigemCustom.IsChecked and not self.base_point:
            self.txtBasePoint.Text = "Nenhum ponto selecionado"

        # Mostrar/ocultar prefixos baseado na opcao Somente Coordenadas
        if self.chkSomenteCoordenadas.IsChecked:
            self.pnlPrefixos.Visibility = Visibility.Collapsed
        else:
            self.pnlPrefixos.Visibility = Visibility.Visible

        # Mostrar/ocultar pasta CSV
        if self.chkCSV.IsChecked:
            self.pnlFolder.Visibility = Visibility.Visible
        else:
            self.pnlFolder.Visibility = Visibility.Collapsed

    def _get_prefix(self):
        if self.rbSP.IsChecked:
            return "SP"
        elif self.rbEP.IsChecked:
            return "EP"
        elif self.rbMP.IsChecked:
            return "MP"
        else:
            return self.txtPrefix.Text.upper().strip() or "XX"

    def _set_status(self, text):
        self.txtStatus.Text = text

    # EVENTOS
    def on_select(self, sender, args):
        self._set_status("Selecione elementos MEP no modelo...")
        self.window.Hide()
        try:
            refs = uidoc.Selection.PickObjects(
                ObjectType.Element,
                self.mep_filter,  # FILTRO MEP APLICADO
                "Selecione elementos MEP (SHIFT adiciona) - ESC cancela"
            )
            if refs:
                self.element_ids = []
                self.selected_categories = set()
                for ref in refs:
                    elem = doc.GetElement(ref.ElementId)
                    if elem:
                        self.element_ids.append(elem.Id)
                        # Coletar categorias
                        if hasattr(elem, 'Category') and elem.Category:
                            self.selected_categories.add(elem.Category.Name)
                self._set_status("{} elementos MEP selecionados.".format(len(self.element_ids)))
        except OperationCanceledException:
            self._set_status("Selecao cancelada.")
        except Exception as e:
            self._set_status("Erro: {}".format(str(e)))
            output.print_md("**Erro na selecao:** {}".format(str(e)))
        self._update_ui()
        self.window.ShowDialog()

    def on_origem_changed(self, sender, args):
        if self.rbOrigemProjeto.IsChecked:
            self.base_point = None
        self._update_ui()

    def on_pick_point(self, sender, args):
        self._set_status("Clique em um ponto no modelo...")
        self.window.Hide()
        try:
            from Autodesk.Revit.DB import ObjectSnapTypes
            picked = uidoc.Selection.PickPoint(ObjectSnapTypes.Endpoints | ObjectSnapTypes.Midpoints | ObjectSnapTypes.Intersections, "Selecione o ponto de referencia - ESC cancela")
            if picked:
                self.base_point = picked
                self._set_status("Ponto de referencia definido.")
        except OperationCanceledException:
            self._set_status("Selecao de ponto cancelada.")
        except Exception:
            # Fallback: PickPoint sem snap (versoes antigas)
            try:
                picked = uidoc.Selection.PickPoint("Selecione o ponto de referencia - ESC cancela")
                if picked:
                    self.base_point = picked
                    self._set_status("Ponto de referencia definido.")
            except OperationCanceledException:
                self._set_status("Selecao de ponto cancelada.")
            except Exception as e2:
                self._set_status("Erro: {}".format(str(e2)))
        self._update_ui()
        self.window.ShowDialog()

    def on_somente_coord_changed(self, sender, args):
        self._update_ui()

    def on_prefix_changed(self, sender, args):
        self._update_ui()

    def on_csv_changed(self, sender, args):
        self._update_ui()

    def on_folder(self, sender, args):
        folder = forms.pick_folder()
        if folder:
            self.export_folder = folder
            self.txtFolder.Text = folder

    def on_cancel(self, sender, args):
        self.resultado = None
        self._save_state()
        self.window.Close()

    def on_execute(self, sender, args):
        if not self.element_ids:
            forms.alert("Selecione pelo menos um elemento!", title="Aviso")
            return
        if self.chkCSV.IsChecked and not self.export_folder:
            forms.alert("Selecione uma pasta para o CSV!", title="Aviso")
            return

        # Validar ponto customizado
        if self.rbOrigemCustom.IsChecked and not self.base_point:
            forms.alert("Selecione um ponto de referencia!", title="Aviso")
            return

        self.dados = {
            'element_ids': list(self.element_ids),
            'selected_categories': list(self.selected_categories),
            'somente_coordenadas': self.chkSomenteCoordenadas.IsChecked,
            'prefix': self._get_prefix(),
            'schedule_coord': self.chkScheduleCoord.IsChecked,
            'schedule_qty': self.chkScheduleQty.IsChecked,
            'export_csv': self.chkCSV.IsChecked,
            'export_folder': self.export_folder,
            'base_point': self.base_point
        }
        self.resultado = "execute"
        self._save_state()
        self.window.Close()

    def ShowDialog(self):
        return self.window.ShowDialog()


# ============================================================================
# FUNCOES DE PARAMETROS
# ============================================================================

def obter_parameter_group():
    if rvt_year >= 2022 and GroupTypeId is not None and hasattr(GroupTypeId, 'Data'):
        return GroupTypeId.Data
    if BuiltInParameterGroup is not None:
        return BuiltInParameterGroup.PG_DATA
    return None


def obter_categorias_dos_elementos(element_ids):
    """Obtem set de categorias dos elementos selecionados."""
    categorias = set()
    for eid in element_ids:
        try:
            elem = doc.GetElement(eid)
            if elem and hasattr(elem, 'Category') and elem.Category:
                categorias.add(elem.Category)
        except Exception as e:
            output.print_md("*Aviso categoria: {}*".format(str(e)))
    return categorias


# GUIDs OFICIAIS dos parametros PYAMBAR (do arquivo PYAMBAR_CoordXYZ.txt)
# Estes GUIDs garantem compatibilidade entre projetos
GUIDS_OFICIAIS = {
    "Coord_X": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
    "Coord_Y": "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e",
    "Coord_Z": "c3d4e5f6-a7b8-4c9d-0e1f-2a3b4c5d6e7f",
    "Coord_DataGeracao": "d4e5f6a7-b8c9-4d0e-1f2a-3b4c5d6e7f8a",
    "QTY": "e5f6a7b8-c9d0-4e1f-2a3b-4c5d6e7f8a9b"
}

def is_shared_parameter_field(field):
    """
    Verifica se um SchedulableField corresponde a um shared parameter.
    Shared parameters tem ParameterId positivo que aponta para SharedParameterElement.
    Built-in parameters tem ParameterId negativo.

    Returns:
        bool: True se for shared parameter, False se for built-in
    """
    try:
        param_id = field.ParameterId
        if param_id and param_id != ElementId.InvalidElementId:
            # Shared parameters tem ID positivo
            id_value = param_id.Value if hasattr(param_id, 'Value') else param_id.IntegerValue
            if id_value > 0:
                # Verificar se eh realmente um SharedParameterElement
                elem = doc.GetElement(param_id)
                if elem is not None and hasattr(elem, 'GuidValue'):
                    return True
    except:
        pass
    return False


def obter_guid_do_parametro_bound(nome_param):
    """
    Obtem o GUID do parametro que esta EFETIVAMENTE VINCULADO (bound) no projeto.
    Usa: ParameterBindings -> InternalDefinition -> ElementId -> SharedParameterElement -> GuidValue

    Returns:
        str: GUID lowercase do parametro bound, ou None se nao encontrado/nao shared
    """
    try:
        iterator = doc.ParameterBindings.ForwardIterator()
        iterator.Reset()
        while iterator.MoveNext():
            definition = iterator.Key
            if definition.Name == nome_param:
                # Obter o SharedParameterElement pelo Id da definition
                param_elem = doc.GetElement(definition.Id)
                if param_elem is not None:
                    # Tentar GuidValue (propriedade direta do SharedParameterElement)
                    if hasattr(param_elem, 'GuidValue'):
                        guid_val = str(param_elem.GuidValue).lower()
                        output.print_md("*DEBUG: {} bound GUID = {}*".format(nome_param, guid_val))
                        return guid_val
                    # Fallback: tentar GetDefinition().GUID
                    if hasattr(param_elem, 'GetDefinition'):
                        ext_def = param_elem.GetDefinition()
                        if ext_def and hasattr(ext_def, 'GUID'):
                            guid_val = str(ext_def.GUID).lower()
                            output.print_md("*DEBUG: {} bound GUID (via GetDefinition) = {}*".format(nome_param, guid_val))
                            return guid_val
                output.print_md("*DEBUG: {} - encontrado no binding mas sem GUID acessivel*".format(nome_param))
                return "NO_GUID"
    except Exception as e:
        output.print_md("*Erro ao obter GUID bound de {}: {}*".format(nome_param, str(e)))
    return None


def remover_todos_bindings_por_nome(nome_param):
    """
    Remove TODOS os bindings de parametros com esse nome
    E DELETA os SharedParameterElement orfaos do projeto.
    Sem isso, o schedule pode encontrar o campo antigo (sem dados).
    """
    removidos = 0
    spe_ids_para_deletar = []
    max_tentativas = 5

    for tentativa in range(max_tentativas):
        try:
            iterator = doc.ParameterBindings.ForwardIterator()
            iterator.Reset()
            encontrou = False
            while iterator.MoveNext():
                definition = iterator.Key
                if definition.Name == nome_param:
                    # Guardar o ElementId do SharedParameterElement para deletar depois
                    spe_ids_para_deletar.append(definition.Id)
                    success = doc.ParameterBindings.Remove(definition)
                    if success:
                        removidos += 1
                        output.print_md("**MIGRACAO:** Binding removido para '{}' (tentativa {})".format(nome_param, tentativa + 1))
                    encontrou = True
                    break  # Iterator invalidado, recomecar

            if not encontrou:
                break

        except Exception as e:
            output.print_md("*Erro ao remover binding {}: {}*".format(nome_param, str(e)))
            break

    # DELETAR os SharedParameterElement orfaos do projeto
    # Isso evita que o schedule encontre campos duplicados (antigo vs novo)
    for spe_id in spe_ids_para_deletar:
        try:
            spe = doc.GetElement(spe_id)
            if spe is not None:
                doc.Delete(spe_id)
                output.print_md("**MIGRACAO:** SharedParameterElement deletado (ID {})".format(spe_id))
        except Exception as e:
            output.print_md("*Aviso: nao foi possivel deletar SPE {}: {}*".format(spe_id, str(e)))

    return removidos


def criar_parametro_compartilhado(nome_param, categorias_alvo=None, elementos_ref=None):
    """
    Cria parametro usando arquivo FIXO com GUIDs constantes.

    LOGICA DE MIGRACAO:
    1. Obter GUID do parametro BOUND (vinculado aos elementos)
    2. Se GUID == oficial -> usa existente
    3. Se GUID != oficial -> remove TODOS bindings antigos + cria novo
    4. Se nao existe -> cria novo

    Args:
        nome_param: Nome do parametro
        categorias_alvo: Categorias onde adicionar
        elementos_ref: (mantido para compatibilidade)
    """
    original_file = None
    try:
        guid_oficial = GUIDS_OFICIAIS.get(nome_param, "").lower()

        # VERIFICACAO: Qual o GUID do parametro atualmente BOUND?
        guid_bound = obter_guid_do_parametro_bound(nome_param)

        if guid_bound is not None:
            # Parametro existe no binding
            if guid_bound == guid_oficial:
                output.print_md("*Parametro {} OK (GUID oficial)*".format(nome_param))
                return True
            else:
                # GUID diferente do oficial - MIGRAR
                output.print_md("**MIGRACAO:** '{}' GUID bound [{}] != oficial [{}]".format(
                    nome_param, guid_bound[:12], guid_oficial[:12]))
                # Remover TODOS os bindings com esse nome (pode haver duplicados)
                remover_todos_bindings_por_nome(nome_param)

        # Parametro nao existe ou foi removido - criar novo
        output.print_md("*Criando parametro {} com GUID oficial [{}...]*".format(nome_param, guid_oficial[:12]))

        # Verificar arquivo fixo
        if not os.path.exists(SHARED_PARAMS_FILE):
            output.print_md("**ERRO:** Arquivo de parametros nao encontrado: {}".format(SHARED_PARAMS_FILE))
            return False

        original_file = app.SharedParametersFilename
        app.SharedParametersFilename = SHARED_PARAMS_FILE

        shared_file = app.OpenSharedParameterFile()
        if not shared_file:
            output.print_md("**ERRO:** Nao foi possivel abrir arquivo de parametros")
            return False

        grupo = shared_file.Groups.get_Item("PYAMBAR_Coordenadas")
        if not grupo:
            output.print_md("**ERRO:** Grupo PYAMBAR_Coordenadas nao encontrado")
            return False

        definition = None
        for defn in grupo.Definitions:
            if defn.Name == nome_param:
                definition = defn
                break

        if not definition:
            output.print_md("**ERRO:** Definicao {} nao encontrada".format(nome_param))
            return False

        # OTIMIZADO: Usar apenas categorias dos elementos selecionados
        categories = app.Create.NewCategorySet()

        if categorias_alvo:
            # Usar categorias especificadas
            for cat in categorias_alvo:
                try:
                    if cat.AllowsBoundParameters:
                        categories.Insert(cat)
                except Exception as e:
                    output.print_md("*Aviso ao inserir categoria {}: {}*".format(cat.Name, str(e)))
        else:
            # Fallback: categorias MEP apenas
            for bic in MEP_CATEGORIES:
                try:
                    cat = doc.Settings.Categories.get_Item(bic)
                    if cat and cat.AllowsBoundParameters:
                        categories.Insert(cat)
                except:
                    pass

        if categories.Size == 0:
            output.print_md("**ERRO:** Nenhuma categoria valida para parametro")
            return False

        binding = app.Create.NewInstanceBinding(categories)
        param_group = obter_parameter_group()

        if param_group:
            success = doc.ParameterBindings.Insert(definition, binding, param_group)
            if not success:
                success = doc.ParameterBindings.ReInsert(definition, binding, param_group)
        else:
            success = doc.ParameterBindings.Insert(definition, binding)
            if not success:
                success = doc.ParameterBindings.ReInsert(definition, binding)

        return success

    except Exception as e:
        output.print_md("**ERRO parametro {}:** {}".format(nome_param, str(e)))
        return False
    finally:
        if original_file:
            try:
                app.SharedParametersFilename = original_file
            except Exception as e:
                output.print_md("*Aviso ao restaurar arquivo params: {}*".format(str(e)))


# ============================================================================
# FUNCOES DE NUMERACAO
# ============================================================================

def criar_filtro_categorias_mep():
    """Cria filtro combinado para categorias MEP."""
    filters_list = []
    for bic in MEP_CATEGORIES:
        try:
            cat_filter = ElementCategoryFilter(bic)
            filters_list.append(cat_filter)
        except:
            pass

    if not filters_list:
        return None

    # Criar LogicalOrFilter com List[ElementFilter]
    filters_net = List[ElementFilter](filters_list)
    return LogicalOrFilter(filters_net)


def encontrar_maior_numero(prefixo):
    """
    Busca maior numero existente para um prefixo.
    OTIMIZADO: Filtra apenas categorias MEP (nao todos elementos do documento).
    """
    maior = 0
    pattern = _get_mark_pattern(prefixo)  # Pattern cacheado

    # Criar filtro MEP
    mep_filter = criar_filtro_categorias_mep()
    if not mep_filter:
        output.print_md("*Aviso: filtro MEP vazio, usando collector completo*")
        collector = FilteredElementCollector(doc).WhereElementIsNotElementType()
    else:
        collector = FilteredElementCollector(doc).WherePasses(mep_filter).WhereElementIsNotElementType()

    for elem in collector:
        try:
            mark_param = elem.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if mark_param:
                marca = mark_param.AsString()
                if marca:
                    match = pattern.match(marca)
                    if match:
                        num = int(match.group(1))
                        if num > maior:
                            maior = num
        except:
            pass
    return maior


def verificar_marcas_existentes(elementos):
    """Verifica quantos elementos ja tem marca."""
    com_marca = 0
    for elem in elementos:
        try:
            mark_param = elem.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
            if mark_param:
                marca = mark_param.AsString()
                if marca and marca.strip():
                    com_marca += 1
        except Exception as e:
            output.print_md("*Aviso verificacao marca: {}*".format(str(e)))
    return com_marca


# ============================================================================
# FUNCOES DE CSV
# ============================================================================

def gerar_caminho_csv_unico(pasta, nome_base, timestamp):
    """
    Gera caminho para CSV com nome unico.
    Se arquivo ja existe, adiciona sufixo _1, _2, etc.
    """
    nome_arquivo = "Coordenadas_{}_{}.csv".format(nome_base.replace(" ", "_"), timestamp)
    caminho = os.path.join(pasta, nome_arquivo)

    if not os.path.exists(caminho):
        return caminho

    # Arquivo existe - buscar nome unico
    for contador in range(1, 1000):  # Limite aumentado
        nome_arquivo = "Coordenadas_{}_{}_{}.csv".format(nome_base.replace(" ", "_"), timestamp, contador)
        caminho = os.path.join(pasta, nome_arquivo)
        if not os.path.exists(caminho):
            return caminho

    # Ultimo recurso: usar timestamp completo
    ts_full = datetime.now().strftime("%m_%d_%y_%H%M%S")
    nome_arquivo = "Coordenadas_{}_{}.csv".format(nome_base.replace(" ", "_"), ts_full)
    return os.path.join(pasta, nome_arquivo)


def exportar_csv_com_bom(caminho, dados_csv):
    """
    Exporta CSV com BOM UTF-8 para Excel reconhecer acentos corretamente.
    """
    try:
        # BOM UTF-8 = \xef\xbb\xbf
        with open(caminho, 'wb') as f:
            # Escrever BOM
            f.write(b'\xef\xbb\xbf')

            # Cabecalho
            header = "Marca,Comentario,Stage,Coord_X,Coord_Y,Coord_Z,Coord_DataGeracao\n"
            f.write(header.encode('utf-8'))

            # Dados
            for dado in dados_csv:
                linha = "{},{},{},{:.8f},{:.8f},{:.8f},{}\n".format(
                    dado.get('mark', ''),
                    dado.get('comentario', ''),
                    dado.get('stage', ''),
                    dado.get('x', 0),
                    dado.get('y', 0),
                    dado.get('z', 0),
                    dado.get('data', '')
                )
                f.write(linha.encode('utf-8'))

        return True
    except Exception as e:
        output.print_md("**Erro ao exportar CSV:** {}".format(str(e)))
        return False


# ============================================================================
# FUNCOES DE SCHEDULE
# ============================================================================

def obter_categoria_predominante(element_ids):
    """Retorna a categoria mais comum entre os elementos selecionados."""
    contagem = {}
    for eid in element_ids:
        try:
            elem = doc.GetElement(eid)
            if elem and hasattr(elem, 'Category') and elem.Category:
                cat_id = elem.Category.Id
                if cat_id not in contagem:
                    contagem[cat_id] = {'count': 0, 'cat': elem.Category}
                contagem[cat_id]['count'] += 1
        except:
            pass

    if not contagem:
        return None

    # Retornar categoria com maior contagem
    mais_comum = max(contagem.values(), key=lambda x: x['count'])
    return mais_comum['cat']


def criar_schedule_coordenadas(nome_vista, timestamp, element_ids):
    """
    Cria ou reutiliza schedule de coordenadas.
    OTIMIZADO: Usa categoria predominante dos elementos (nao Multi-Category).
    """
    nome = "Coord_XYZ_{}_{}".format(nome_vista, timestamp)

    # Verificar se schedule ja existe - REUTILIZAR
    existente = buscar_schedule_por_nome(doc, nome)
    if existente:
        output.print_md("*Schedule existente encontrado: {}*".format(nome))
        return existente

    # SEMPRE usar Multi-Category para garantir que Stage (shared parameter externo) apareca
    # Stage pode nao estar bound a todas as categorias MEP
    cat_id = ElementId.InvalidElementId
    output.print_md("*Criando Multi-Category schedule (para incluir Stage)*")

    # Criar novo schedule
    schedule = ViewSchedule.CreateSchedule(doc, cat_id)
    schedule.Name = nome

    definition = schedule.Definition

    # Ordem EXATA dos campos (igual CSV): Marca, Comentarios, Stage, X, Y, Z, Data
    # Lista explicita para garantir ordem (dict nao garante em IronPython)
    campos_ordenados = ["Marca", "Comentarios", "Stage", PARAM_COORD_X, PARAM_COORD_Y, PARAM_COORD_Z, PARAM_DATA]

    # Aliases para nomes em PT/EN
    campos_aliases = {
        "Marca": ["Mark", "Marca"],
        "Comentarios": ["Comments", "Comentários", "Comentarios"],
        "Stage": ["Stage"],
        PARAM_COORD_X: [PARAM_COORD_X],
        PARAM_COORD_Y: [PARAM_COORD_Y],
        PARAM_COORD_Z: [PARAM_COORD_Z],
        PARAM_DATA: [PARAM_DATA]
    }

    # Coletar todos os schedulable fields por nome
    # Para campos com mesmo nome, guardar lista para depois escolher o correto
    all_fields = {}
    fields_duplicados = {}  # campos com mesmo nome (ex: Stage)
    for field in definition.GetSchedulableFields():
        try:
            fname = field.GetName(doc)
            if fname in all_fields:
                # Campo duplicado - guardar ambos para escolher depois
                if fname not in fields_duplicados:
                    fields_duplicados[fname] = [all_fields[fname]]
                fields_duplicados[fname].append(field)
            all_fields[fname] = field
        except:
            pass

    # Debug: mostrar campos disponiveis (primeiros 30)
    campos_lista = sorted(all_fields.keys())
    output.print_md("*Campos disponiveis ({} total): {}{}*".format(
        len(campos_lista),
        ", ".join(campos_lista[:30]),
        "..." if len(campos_lista) > 30 else ""
    ))

    # Debug: mostrar duplicados
    if fields_duplicados:
        output.print_md("*Campos duplicados: {}*".format(", ".join(fields_duplicados.keys())))

    # Encontrar campos pelos aliases
    # Para Stage e outros duplicados, preferir SHARED PARAMETER (Multiplas Categorias)
    fields_disponiveis = {}
    for campo_key, aliases in campos_aliases.items():
        for alias in aliases:
            if alias in all_fields:
                # Se tem duplicados, escolher o shared parameter
                if alias in fields_duplicados:
                    for candidate in fields_duplicados[alias]:
                        if is_shared_parameter_field(candidate):
                            fields_disponiveis[campo_key] = candidate
                            output.print_md("*Campo '{}' = shared parameter (Multiplas Categorias)*".format(campo_key))
                            break
                    # Se nenhum for shared, usar o ultimo
                    if campo_key not in fields_disponiveis:
                        fields_disponiveis[campo_key] = all_fields[alias]
                        output.print_md("*Campo '{}' encontrado (sem shared param)*".format(campo_key))
                else:
                    fields_disponiveis[campo_key] = all_fields[alias]
                    output.print_md("*Campo '{}' encontrado como '{}'*".format(campo_key, alias))
                break
        if campo_key not in fields_disponiveis:
            output.print_md("**Campo '{}' NAO encontrado (aliases: {})**".format(campo_key, aliases))

    # Segundo: adicionar NA ORDEM CORRETA
    campos_add = []
    field_data = None
    field_marca = None

    for campo_nome in campos_ordenados:
        if campo_nome in fields_disponiveis:
            try:
                sf = definition.AddField(fields_disponiveis[campo_nome])
                campos_add.append(campo_nome)
                if campo_nome == PARAM_DATA:
                    field_data = sf
                if campo_nome == "Marca":
                    field_marca = sf
                if campo_nome in [PARAM_COORD_X, PARAM_COORD_Y, PARAM_COORD_Z]:
                    try:
                        fo = sf.GetFormatOptions()
                        fo.UseDefault = False
                        fo.Accuracy = 0.001
                        if hasattr(fo, 'SuppressUnitSuffix'):
                            fo.SuppressUnitSuffix = True
                        sf.SetFormatOptions(fo)
                    except Exception as e:
                        output.print_md("*Aviso formato {}: {}*".format(campo_nome, str(e)))
            except Exception as e:
                output.print_md("*Aviso ao adicionar campo {}: {}*".format(campo_nome, str(e)))

    # Filtro por data
    if field_data:
        try:
            filtro = ScheduleFilter(field_data.FieldId, ScheduleFilterType.Equal, timestamp)
            definition.AddFilter(filtro)
        except Exception as e:
            output.print_md("*Aviso filtro data: {}*".format(str(e)))

    # Ordenar por Marca (ascending) - Usando construtor correto
    if field_marca:
        try:
            from Autodesk.Revit.DB import ScheduleSortGroupField, ScheduleSortOrder
            # Criar com FieldId E SortOrder no construtor
            sortGroupField = ScheduleSortGroupField(field_marca.FieldId, ScheduleSortOrder.Ascending)
            # Configurar para NAO agrupar (apenas ordenar)
            sortGroupField.ShowHeader = False
            sortGroupField.ShowFooter = False
            sortGroupField.ShowBlankLine = False
            # Adicionar ao schedule
            definition.AddSortGroupField(sortGroupField)
        except Exception as e:
            output.print_md("**Aviso ordenacao:** {}".format(str(e)))

    # Definir Schedule Category para identificacao
    try:
        param = schedule.LookupParameter(PARAM_SCHEDULE_CATEGORY)
        if param and not param.IsReadOnly:
            param.Set("Coordenadas_XYZ")
    except:
        pass  # Parametro pode nao existir

    return schedule


def criar_schedule_quantitativos(nome_vista, timestamp, element_ids):
    """
    Cria ou reutiliza schedule de quantitativos.
    Multi-Category para garantir Stage.
    """
    nome = "QTY_Pontos_{}_{}".format(nome_vista, timestamp)

    # Verificar se schedule ja existe - REUTILIZAR
    existente = buscar_schedule_por_nome(doc, nome)
    if existente:
        output.print_md("*Schedule existente encontrado: {}*".format(nome))
        return existente

    # SEMPRE usar Multi-Category para garantir que Stage apareca
    cat_id = ElementId.InvalidElementId

    # Criar novo schedule
    schedule = ViewSchedule.CreateSchedule(doc, cat_id)
    schedule.Name = nome

    definition = schedule.Definition

    # Aliases para campos
    campos_aliases = {
        "Marca": ["Mark", "Marca"],
        "Stage": ["Stage"],
        PARAM_QTY: [PARAM_QTY]
    }

    # Coletar todos os campos por nome (detectar duplicados para Stage)
    all_fields = {}
    fields_duplicados = {}
    for field in definition.GetSchedulableFields():
        try:
            fname = field.GetName(doc)
            if fname in all_fields:
                if fname not in fields_duplicados:
                    fields_duplicados[fname] = [all_fields[fname]]
                fields_duplicados[fname].append(field)
            all_fields[fname] = field
        except:
            pass

    # Encontrar campos por aliases (preferir shared parameter para Stage)
    fields_disponiveis = {}
    for campo_key, aliases in campos_aliases.items():
        for alias in aliases:
            if alias in all_fields:
                if alias in fields_duplicados:
                    # Para duplicados, preferir shared parameter
                    for candidate in fields_duplicados[alias]:
                        if is_shared_parameter_field(candidate):
                            fields_disponiveis[campo_key] = candidate
                            break
                    if campo_key not in fields_disponiveis:
                        fields_disponiveis[campo_key] = all_fields[alias]
                else:
                    fields_disponiveis[campo_key] = all_fields[alias]
                break

    # Adicionar campos encontrados
    campos_add = []
    field_marca = None

    for campo_key in ["Marca", "Stage", PARAM_QTY]:
        if campo_key in fields_disponiveis and campo_key not in campos_add:
            try:
                sf = definition.AddField(fields_disponiveis[campo_key])
                campos_add.append(campo_key)
                if campo_key == "Marca":
                    field_marca = sf
            except Exception as e:
                output.print_md("*Aviso campo QTY {}: {}*".format(campo_key, str(e)))

    # Ordenar por Marca (ascending) - Usando construtor correto
    if field_marca:
        try:
            from Autodesk.Revit.DB import ScheduleSortGroupField, ScheduleSortOrder
            sortGroupField = ScheduleSortGroupField(field_marca.FieldId, ScheduleSortOrder.Ascending)
            sortGroupField.ShowHeader = False
            sortGroupField.ShowFooter = False
            sortGroupField.ShowBlankLine = False
            definition.AddSortGroupField(sortGroupField)
        except Exception as e:
            output.print_md("**Aviso ordenacao QTY:** {}".format(str(e)))

    # Definir Schedule Category para identificacao (igual ao schedule de coordenadas)
    try:
        param = schedule.LookupParameter(PARAM_SCHEDULE_CATEGORY)
        if param and not param.IsReadOnly:
            param.Set("Coordenadas_XYZ")
    except:
        pass  # Parametro pode nao existir

    return schedule


# ============================================================================
# PROCESSAMENTO PRINCIPAL
# ============================================================================

def processar(dados):
    """Processa tudo: numera, gera coordenadas, cria schedules, exporta CSV."""
    output.print_md("# Processando...")

    element_ids = dados['element_ids']
    somente_coordenadas = dados.get('somente_coordenadas', False)
    prefixo = dados['prefix']
    criar_coord = dados['schedule_coord']
    criar_qty = dados['schedule_qty']
    export_csv = dados['export_csv']
    export_folder = dados['export_folder']
    base_point = dados.get('base_point', None)  # XYZ ou None

    if base_point:
        output.print_md("**Ponto de Referencia:** X={:.3f}, Y={:.3f}, Z={:.3f}".format(
            base_point.X, base_point.Y, base_point.Z))
    else:
        output.print_md("**Ponto de Referencia:** Origem do Projeto (0, 0, 0)")

    timestamp = datetime.now().strftime("%m_%d_%y")
    nome_vista = doc.ActiveView.Name if doc.ActiveView else "Vista"

    # Obter elementos
    elementos = [doc.GetElement(eid) for eid in element_ids]
    elementos = [e for e in elementos if e]

    # Obter categorias dos elementos selecionados (para parametros)
    categorias_selecionadas = obter_categorias_dos_elementos(element_ids)
    output.print_md("**Categorias:** {}".format(", ".join([c.Name for c in categorias_selecionadas])))

    # Modo somente coordenadas - nao altera marcas
    if somente_coordenadas:
        output.print_md("**Modo: Somente Coordenadas** (marcas existentes serao mantidas)")
        modo = "somente_coord"
        inicio = 1  # nao usado, mas necessario
        maior_existente = 0
    else:
        # Verificar marcas existentes
        com_marca = verificar_marcas_existentes(elementos)
        maior_existente = encontrar_maior_numero(prefixo)

        modo = "reiniciar"
        if com_marca > 0 or maior_existente > 0:
            msg = "Detectado:\n"
            if com_marca > 0:
                msg += "- {} elementos ja tem marca\n".format(com_marca)
            if maior_existente > 0:
                msg += "- Maior existente: {}-{:03d}\n".format(prefixo, maior_existente)
            msg += "\nComo proceder?"

            opcoes = ["Continuar (a partir de {}-{:03d})".format(prefixo, maior_existente + 1),
                      "Reiniciar (limpar e comecar do 001)",
                      "Cancelar"]
            escolha = forms.CommandSwitchWindow.show(opcoes, message=msg)

            if not escolha or escolha == "Cancelar":
                output.print_md("**Cancelado.**")
                return
            elif "Continuar" in escolha:
                modo = "continuar"

    # TRANSACAO 1: Criar parametros, numerar, preencher coordenadas
    with ef_Transaction(doc, "Coordenadas XYZ - Processar", debug=False):
        # Criar parametros - APENAS se nao existirem
        # Passa elementos como referencia para verificar se param ja existe neles
        for p in [PARAM_COORD_X, PARAM_COORD_Y, PARAM_COORD_Z, PARAM_DATA, PARAM_QTY]:
            criar_parametro_compartilhado(p, categorias_selecionadas, elementos)
        doc.Regenerate()

        # Determinar numero inicial (apenas se nao for somente_coord)
        if modo == "somente_coord":
            inicio = 1  # placeholder
        elif modo == "continuar":
            inicio = maior_existente + 1
        else:
            inicio = 1
            # Limpar marcas se reiniciando
            for elem in elementos:
                try:
                    mp = elem.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
                    if mp and not mp.IsReadOnly:
                        mp.Set("")
                except Exception as e:
                    output.print_md("*Aviso limpeza marca: {}*".format(str(e)))

        # Ponto de referencia para coordenadas relativas
        bp_x = base_point.X if base_point else 0
        bp_y = base_point.Y if base_point else 0
        bp_z = base_point.Z if base_point else 0

        # Ordenar por distancia do ponto de referencia
        elem_pos = []
        for elem in elementos:
            centro = obter_centro_elemento(elem)
            if centro:
                dx = centro.X - bp_x
                dy = centro.Y - bp_y
                dist = (dx ** 2 + dy ** 2) ** 0.5
                elem_pos.append((elem, dist, centro.Y, centro.X, centro))
            else:
                elem_pos.append((elem, float('inf'), 0, 0, None))
        elem_pos.sort(key=lambda t: (t[1], t[2], t[3]))

        # Processar cada elemento
        dados_csv = []
        for i, (elem, dist, y, x, centro) in enumerate(elem_pos, start=inicio):
            # Numerar (apenas se NAO for somente_coordenadas)
            if modo == "somente_coord":
                # Manter marca existente
                try:
                    mp = elem.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
                    marca = mp.AsString() if mp else ""
                    if not marca:
                        marca = "SEM_MARCA"
                except Exception as e:
                    marca = "SEM_MARCA"
                    output.print_md("*Aviso leitura marca: {}*".format(str(e)))
            else:
                # Gerar nova marca
                marca = "{}-{:03d}".format(prefixo, i)
                try:
                    mp = elem.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
                    if mp and not mp.IsReadOnly:
                        mp.Set(marca)
                except Exception as e:
                    output.print_md("*Aviso set marca: {}*".format(str(e)))

            # Coordenadas (relativas ao ponto de referencia)
            cx, cy, cz = 0, 0, 0
            if centro:
                cx = centro.X - bp_x
                cy = centro.Y - bp_y
                cz = centro.Z - bp_z
                for pname, val in [(PARAM_COORD_X, cx), (PARAM_COORD_Y, cy), (PARAM_COORD_Z, cz)]:
                    try:
                        p = elem.LookupParameter(pname)
                        if p and not p.IsReadOnly:
                            p.Set(val)
                    except Exception as e:
                        output.print_md("*Aviso set {}: {}*".format(pname, str(e)))

            # Data
            try:
                pd = elem.LookupParameter(PARAM_DATA)
                if pd and not pd.IsReadOnly:
                    pd.Set(timestamp)
            except Exception as e:
                output.print_md("*Aviso set data: {}*".format(str(e)))

            # QTY = 1
            try:
                pq = elem.LookupParameter(PARAM_QTY)
                if pq and not pq.IsReadOnly:
                    pq.Set(1)
            except Exception as e:
                output.print_md("*Aviso set QTY: {}*".format(str(e)))

            # Coletar dados CSV
            stage = ""
            comentario = ""
            try:
                sp = elem.LookupParameter("Stage")
                if sp:
                    stage = sp.AsString() or ""
            except:
                pass
            try:
                cp = elem.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                if cp:
                    comentario = cp.AsString() or ""
            except:
                pass

            dados_csv.append({
                'mark': marca,
                'comentario': comentario,
                'stage': stage,
                'x': cx if centro else 0,
                'y': cy if centro else 0,
                'z': cz if centro else 0,
                'data': timestamp
            })

    if modo == "somente_coord":
        output.print_md("**{} elementos processados** (coordenadas atualizadas, marcas mantidas)".format(len(elem_pos)))
    else:
        output.print_md("**{} elementos processados:** {}-{:03d} ate {}-{:03d}".format(
            len(elem_pos), prefixo, inicio, prefixo, inicio + len(elem_pos) - 1
        ))

    # TRANSACAO 2: Criar schedules
    schedule_coord = None
    schedule_qty = None

    if criar_coord or criar_qty:
        with ef_Transaction(doc, "Criar Schedules", debug=False):
            if criar_coord:
                schedule_coord = criar_schedule_coordenadas(nome_vista, timestamp, element_ids)
                output.print_md("**Schedule Coordenadas:** {}".format(schedule_coord.Name))
            if criar_qty:
                schedule_qty = criar_schedule_quantitativos(nome_vista, timestamp, element_ids)
                output.print_md("**Schedule Quantitativos:** {}".format(schedule_qty.Name))
            doc.Regenerate()

    # Ativar primeiro schedule criado - FORA de transaction
    if schedule_coord:
        try:
            uidoc.ActiveView = schedule_coord
        except Exception as e:
            output.print_md("*Aviso ao ativar schedule: {}*".format(str(e)))

    # Exportar CSV com BOM UTF-8
    if export_csv and export_folder:
        dados_csv.sort(key=lambda x: x.get('mark', ''))
        caminho_csv = gerar_caminho_csv_unico(export_folder, nome_vista, timestamp)
        if exportar_csv_com_bom(caminho_csv, dados_csv):
            output.print_md("**CSV exportado:** {}".format(caminho_csv))

    output.print_md("# Concluido!")


# ============================================================================
# ENTRY POINT
# ============================================================================

def main():
    try:
        window = CoordWindow()
        window.ShowDialog()

        if window.resultado == "execute":
            processar(window.dados)

    except Exception as e:
        output.print_md("**Erro:** {}".format(str(e)))
        import traceback
        output.print_md("```\n{}\n```".format(traceback.format_exc()))


if __name__ == "__main__":
    main()
