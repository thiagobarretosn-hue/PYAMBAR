# -*- coding: utf-8 -*-
__title__ = "Slab\nPasses"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "5.1"
__doc__ = """
Slab Passes - Passagens de Laje v5.1

FUNCIONALIDADES:
- Selecao de tubos VERTICAIS e conduits (locais OU vinculos)
- Filtro DINAMICO por parametro na mesma janela
- Conversao automatica de coordenadas (Link -> Projeto Atual)
- Agrupamento inteligente em tempo real
- Protecao contra duplicidade (in-batch tracking)
- Suporte a Pecas (PipeFitting) E Acessorios (PipeAccessory)
- Auto-carregamento familia WPS padrao
- Sizing inteligente: mesma bitola, +1 ou +2 tamanhos

WORKFLOW:
1. Execute o script
2. Escolha: Tubos LOCAIS ou em VINCULOS
3. Selecione os tubos/conduits VERTICAIS
4. Na janela: escolha filtro (atualiza grupos em tempo real)
5. Configure acessorio/peca e sizing para cada grupo
6. Clique em "Aplicar"

MELHORIAS v5.1:
- Suporte a Conduit (Eletrico) alem de Pipe
- Grupos separados por tipo: [Pipe] e [Conduit]
- WPS sizing aplicado a ambos os tipos

MELHORIAS v5.0:
- Fix duplicidade na mesma execucao
- Suporte a PipeFitting + PipeAccessory
- Auto-load familia WPS (AMBAR ACESSORIO)
- Sizing inteligente por grupo (mesma/+1/+2)
- WPS pre-selecionado como default
"""

__persistentengine__ = True

import clr
import sys
import os
import codecs
from collections import defaultdict

LIB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Plumbing import Pipe
from Autodesk.Revit.DB.Electrical import Conduit
from Autodesk.Revit.DB.Structure import StructuralType
from Autodesk.Revit.UI import *
from Autodesk.Revit.UI.Selection import *
from System.Collections.Generic import List

from pyrevit import script, revit, DB, UI, forms
from pyrevit.forms import WPFWindow

from Snippets._inherit_pipe_params import EXCLUDED_PARAMS

doc = revit.doc
output = script.get_output()
uidoc = revit.uidoc
script_dir = os.path.dirname(__file__)

# ============================================================================
# CONSTANTES - FAMILIA WPS
# ============================================================================
WPS_FAMILY_NAME = "Pipe_Sleeve-Plastic-Watts-WPS_Series(AMBAR ACESSORIO)"
WPS_RFA_PATH = os.path.join(script_dir, WPS_FAMILY_NAME + ".rfa")

# Tamanhos WPS ordenados (polegadas)
WPS_SIZES_INCHES = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0]
WPS_TYPE_NAMES = [
    "WPS-1/2", "WPS-3/4", "WPS-1", "WPS-1 1/2",
    "WPS-2", "WPS-3", "WPS-4", "WPS-5",
    "WPS-6", "WPS-8", "WPS-10", "WPS-12"
]

SIZING_OPTIONS = [u"Mesma bitola", u"+1 tamanho", u"+2 tamanhos"]

# ============================================================================
# 1. SUPRESSAO DE AVISOS DE DUPLICIDADE
# ============================================================================
class DuplicateWarningSwallower(IFailuresPreprocessor):
    def PreprocessFailures(self, failuresAccessor):
        failures = failuresAccessor.GetFailureMessages()
        for f in failures:
            if f.GetSeverity() == FailureSeverity.Warning:
                failuresAccessor.DeleteWarning(f)
        return FailureProcessingResult.Continue

# ============================================================================
# 2. FILTROS DE SELECAO
# ============================================================================
def is_vertical(curve, tolerance=0.05):
    p1 = curve.GetEndPoint(0)
    p2 = curve.GetEndPoint(1)
    horizontal_distance = ((p2.X - p1.X)**2 + (p2.Y - p1.Y)**2)**0.5
    return horizontal_distance < tolerance

class LocalPipeSelectionFilter(ISelectionFilter):
    def AllowElement(self, elem):
        if not isinstance(elem, (Pipe, Conduit)):
            return False
        try:
            location = elem.Location
            if isinstance(location, LocationCurve):
                curve = location.Curve
                if is_vertical(curve):
                    return True
        except Exception as e:
            pass
        return False

    def AllowReference(self, reference, position):
        return True

class LinkedPipeSelectionFilter(ISelectionFilter):
    def __init__(self, doc):
        self.doc = doc

    def AllowElement(self, elem):
        if isinstance(elem, RevitLinkInstance):
            return True
        return False

    def AllowReference(self, reference, position):
        try:
            elem = self.doc.GetElement(reference)
            if isinstance(elem, RevitLinkInstance):
                link_doc = elem.GetLinkDocument()
                if link_doc:
                    linked_element = link_doc.GetElement(reference.LinkedElementId)
                    if isinstance(linked_element, (Pipe, Conduit)):
                        location = linked_element.Location
                        if isinstance(location, LocationCurve):
                            curve = location.Curve
                            if is_vertical(curve):
                                return True
        except Exception as e:
            return False
        return False

# ============================================================================
# 3. FUNCOES DE GEOMETRIA E PARAMETROS
# ============================================================================
def _format_diameter_string(diameter_feet):
    diameter_inches = diameter_feet * 12
    if diameter_inches % 1 == 0:
        return '{}"'.format(int(diameter_inches))
    else:
        half_inches = round(diameter_inches * 2) / 2
        whole = int(half_inches)
        fraction = half_inches - whole
        if fraction == 0:
            return '{}"'.format(whole)
        else:
            return '{} 1/2"'.format(whole)

def get_element_diameter(elem, element_type):
    try:
        param_id = (BuiltInParameter.RBS_PIPE_DIAMETER_PARAM if element_type == "Pipe"
                    else BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM)
        diameter_param = elem.get_Parameter(param_id)
        if diameter_param:
            return _format_diameter_string(diameter_param.AsDouble())
        return "Unknown"
    except Exception as e:
        return "Unknown"

def get_element_diameter_inches(elem, element_type):
    try:
        param_id = (BuiltInParameter.RBS_PIPE_DIAMETER_PARAM if element_type == "Pipe"
                    else BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM)
        diameter_param = elem.get_Parameter(param_id)
        if diameter_param:
            return diameter_param.AsDouble() * 12.0
        return 0.0
    except Exception as e:
        return 0.0

def parse_diameter_from_key(group_key):
    """Extrai diametro em polegadas de uma group_key tipo '[Pipe] 2"' ou '[Conduit] 2" | System'"""
    try:
        key = group_key.replace("[Pipe] ", "").replace("[Conduit] ", "")
        diam_str = key.split("|")[0].strip().replace('"', '').strip()
        if " 1/2" in diam_str:
            parts = diam_str.split(" 1/2")
            whole = parts[0].strip()
            if whole:
                return float(whole) + 0.5
            return 0.5
        return float(diam_str)
    except Exception as e:
        return 0.0

def get_available_parameters(elements):
    if not elements:
        return []

    first_pipe = next((e for e in elements if isinstance(e, Pipe)), None)
    first_conduit = next((e for e in elements if isinstance(e, Conduit)), None)

    system_params = [
        "Family", "Type", "Comments", "Mark", "Diameter",
        "Level", "Reference Level", "Top Offset", "Bottom Offset",
        "System Classification", "System Type", "System Name",
        "Workset", "Design Option", "Phase Created", "Phase Demolished"
    ]

    all_param_names = set()

    for first_elem in [x for x in [first_pipe, first_conduit] if x is not None]:
        for param in first_elem.Parameters:
            try:
                param_name = param.Definition.Name
                if param_name in system_params:
                    continue
                is_candidate = False
                if param.IsShared:
                    is_candidate = True
                elif not param.IsReadOnly:
                    try:
                        value = param.AsString() or param.AsValueString()
                        if value:
                            is_candidate = True
                    except Exception as e:
                        pass
                if is_candidate:
                    all_param_names.add(param_name)
            except Exception as e:
                continue

    return sorted(list(all_param_names))

def get_parameter_value(elem, param_name):
    try:
        param = elem.LookupParameter(param_name)
        if param:
            value = param.AsString()
            if not value:
                value = param.AsValueString()
            return value if value else "(Vazio)"
        return "(Sem parametro)"
    except Exception as e:
        return "(Erro)"

def has_duplicate_at_location(location_point, placed_points, tolerance=0.1):
    """Verifica duplicidade contra lista em memoria E contra projeto existente."""
    for pt in placed_points:
        if pt.DistanceTo(location_point) < tolerance:
            return True

    for cat in [BuiltInCategory.OST_PipeAccessory, BuiltInCategory.OST_PipeFitting]:
        try:
            collector = FilteredElementCollector(doc)\
                .OfCategory(cat)\
                .OfClass(FamilyInstance)
            for inst in collector:
                loc = inst.Location
                if loc and isinstance(loc, LocationPoint):
                    dist = loc.Point.DistanceTo(location_point)
                    if dist < tolerance:
                        return True
        except Exception as e:
            pass
    return False

# ============================================================================
# 4. PROCESSAMENTO DE TUBOS E CONDUITS
# ============================================================================
class PipeData:
    def __init__(self, pipe_element, center_point_host, diameter, diameter_param,
                 diameter_inches, all_params_dict, element_type):
        self.Element = pipe_element
        self.CenterPoint = center_point_host
        self.Diameter = diameter
        self.DiameterParam = diameter_param
        self.DiameterInches = diameter_inches
        self.AllParams = all_params_dict
        self.ElementType = element_type  # "Pipe" ou "Conduit"

def process_local_pipes(pipes, available_params):
    processed_pipes = []

    for pipe in pipes:
        try:
            location = pipe.Location
            if isinstance(location, LocationCurve):
                curve = location.Curve
                p1 = curve.GetEndPoint(0)
                p2 = curve.GetEndPoint(1)
                center_point = (p1 + p2) / 2.0

                element_type = "Conduit" if isinstance(pipe, Conduit) else "Pipe"
                diameter = get_element_diameter(pipe, element_type)
                param_id = (BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM if element_type == "Conduit"
                            else BuiltInParameter.RBS_PIPE_DIAMETER_PARAM)
                diameter_param = pipe.get_Parameter(param_id)
                diameter_inches = get_element_diameter_inches(pipe, element_type)

                params_dict = {}
                for param_name in available_params:
                    params_dict[param_name] = get_parameter_value(pipe, param_name)

                p_data = PipeData(pipe, center_point, diameter, diameter_param,
                                  diameter_inches, params_dict, element_type)
                processed_pipes.append(p_data)
        except Exception as e:
            output.print_md("Erro ao processar elemento local: {}".format(e))

    return processed_pipes

def process_linked_pipes(references, available_params):
    processed_pipes = []

    for ref in references:
        try:
            link_instance = doc.GetElement(ref.ElementId)
            transform = link_instance.GetTotalTransform()
            link_doc = link_instance.GetLinkDocument()
            linked_elem = link_doc.GetElement(ref.LinkedElementId)

            if isinstance(linked_elem, (Pipe, Conduit)):
                location = linked_elem.Location
                if isinstance(location, LocationCurve):
                    curve = location.Curve
                    mid_param = (curve.GetEndParameter(0) + curve.GetEndParameter(1)) / 2
                    internal_mid_point = curve.Evaluate(mid_param, False)
                    host_mid_point = transform.OfPoint(internal_mid_point)

                    element_type = "Conduit" if isinstance(linked_elem, Conduit) else "Pipe"
                    diameter = get_element_diameter(linked_elem, element_type)
                    param_id = (BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM if element_type == "Conduit"
                                else BuiltInParameter.RBS_PIPE_DIAMETER_PARAM)
                    diameter_param = linked_elem.get_Parameter(param_id)
                    diameter_inches = get_element_diameter_inches(linked_elem, element_type)

                    params_dict = {}
                    for param_name in available_params:
                        params_dict[param_name] = get_parameter_value(linked_elem, param_name)

                    p_data = PipeData(linked_elem, host_mid_point, diameter, diameter_param,
                                      diameter_inches, params_dict, element_type)
                    processed_pipes.append(p_data)

        except Exception as e:
            output.print_md("Erro ao processar elemento em vinculo: {}".format(e))

    return processed_pipes

def apply_filters(pipes_data_list):
    filtered = []
    for p_data in pipes_data_list:
        try:
            location = p_data.Element.Location
            if not isinstance(location, LocationCurve):
                continue
            curve = location.Curve
            if not is_vertical(curve):
                continue
            filtered.append(p_data)
        except Exception as e:
            output.print_md("Erro ao filtrar elemento: {}".format(e))
            continue
    return filtered

def group_pipes_data(pipes_data_list, filter_param_name=None):
    grouped = defaultdict(list)
    for p_data in pipes_data_list:
        type_prefix = "[Pipe]" if p_data.ElementType == "Pipe" else "[Conduit]"
        if filter_param_name and filter_param_name in p_data.AllParams:
            param_value = p_data.AllParams[filter_param_name]
            group_key = u"{} {} | {}".format(type_prefix, p_data.Diameter, param_value)
        else:
            group_key = u"{} {}".format(type_prefix, p_data.Diameter)
        grouped[group_key].append(p_data)
    return dict(grouped)

# ============================================================================
# 5. FUNCOES AUXILIARES
# ============================================================================
def get_all_fittings_and_accessories():
    """Retorna todos os tipos de Pecas (PipeFitting) E Acessorios (PipeAccessory)"""
    all_types = []
    categories = [
        (BuiltInCategory.OST_PipeAccessory, u"[Acessorio]"),
        (BuiltInCategory.OST_PipeFitting, u"[Peca]"),
    ]

    for cat, prefix in categories:
        try:
            collector = FilteredElementCollector(doc)\
                .OfCategory(cat)\
                .WhereElementIsElementType()
            for type_elem in collector:
                all_types.append((type_elem, prefix))
        except Exception as e:
            pass

    all_types.sort(key=lambda x: (
        x[0].FamilyName,
        x[0].get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
    ))
    return all_types

def get_all_levels():
    collector = FilteredElementCollector(doc)\
        .OfClass(Level)\
        .WhereElementIsNotElementType()
    return sorted(collector, key=lambda x: x.Elevation)

def ensure_wps_family_loaded():
    """Verifica/carrega familia WPS. Retorna dict {type_name: FamilySymbol} ou None"""
    collector = FilteredElementCollector(doc)\
        .OfClass(Family)

    wps_family = None
    for fam in collector:
        if getattr(fam, 'Name', '') == WPS_FAMILY_NAME:
            wps_family = fam
            break

    if not wps_family:
        if not os.path.exists(WPS_RFA_PATH):
            output.print_md("Arquivo RFA nao encontrado: {}".format(WPS_RFA_PATH))
            return None

        t = Transaction(doc, "Carregar Familia WPS")
        t.Start()
        try:
            result = clr.Reference[Family]()
            loaded = doc.LoadFamily(WPS_RFA_PATH, result)
            if loaded:
                wps_family = result.Value
            else:
                for fam in FilteredElementCollector(doc).OfClass(Family):
                    if getattr(fam, 'Name', '') == WPS_FAMILY_NAME:
                        wps_family = fam
                        break
            t.Commit()
        except Exception as e:
            t.RollBack()
            output.print_md("Erro ao carregar familia WPS: {}".format(e))
            return None

    if not wps_family:
        return None

    wps_types = {}
    symbol_ids = wps_family.GetFamilySymbolIds()
    for sid in symbol_ids:
        symbol = doc.GetElement(sid)
        if symbol:
            type_name = symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
            wps_types[type_name] = symbol

    return wps_types

def get_wps_type_for_diameter(wps_types, pipe_diameter_inches, sizing_offset=0):
    if not wps_types:
        return None

    match_idx = None
    for i, size in enumerate(WPS_SIZES_INCHES):
        if size >= pipe_diameter_inches - 0.01:
            match_idx = i
            break

    if match_idx is None:
        match_idx = len(WPS_SIZES_INCHES) - 1

    target_idx = min(match_idx + sizing_offset, len(WPS_SIZES_INCHES) - 1)
    target_type_name = WPS_TYPE_NAMES[target_idx]

    return wps_types.get(target_type_name)

def get_wps_type_name_for_diameter(pipe_diameter_inches, sizing_offset=0):
    match_idx = None
    for i, size in enumerate(WPS_SIZES_INCHES):
        if size >= pipe_diameter_inches - 0.01:
            match_idx = i
            break
    if match_idx is None:
        match_idx = len(WPS_SIZES_INCHES) - 1
    target_idx = min(match_idx + sizing_offset, len(WPS_SIZES_INCHES) - 1)
    return WPS_TYPE_NAMES[target_idx]

def create_fitting_at_point(point_x_y, fitting_type, level, elevation_offset, placed_points):
    """Cria acessorio/peca usando X,Y fornecidos e Z do Nivel + Offset"""
    try:
        if not fitting_type.IsActive:
            fitting_type.Activate()
            doc.Regenerate()

        target_z = level.Elevation + elevation_offset
        placement_point = XYZ(point_x_y.X, point_x_y.Y, target_z)

        if has_duplicate_at_location(placement_point, placed_points):
            return None

        new_fitting = doc.Create.NewFamilyInstance(
            placement_point,
            fitting_type,
            level,
            StructuralType.NonStructural
        )

        placed_points.append(placement_point)

        param_offset = new_fitting.get_Parameter(BuiltInParameter.INSTANCE_FREE_HOST_OFFSET_PARAM)
        if param_offset and not param_offset.IsReadOnly:
            param_offset.Set(elevation_offset)
        else:
            param_elevation = new_fitting.get_Parameter(BuiltInParameter.INSTANCE_ELEVATION_PARAM)
            if param_elevation and not param_elevation.IsReadOnly:
                param_elevation.Set(target_z)

        return new_fitting

    except Exception as e:
        output.print_md("Erro ao criar fitting: {}".format(str(e)))
        return None

# ============================================================================
# 6. INTERFACE WPF DINAMICA
# ============================================================================
class DynamicAcessoriosWindow(WPFWindow):

    def __init__(self, pipes_data_list, available_params, all_types_with_prefix,
                 wps_types, total_selected, total_filtered, mode):
        self.pipes_data_list = pipes_data_list
        self.available_params = available_params
        self.all_types_with_prefix = all_types_with_prefix
        self.wps_types = wps_types
        self.total_selected = total_selected
        self.total_filtered = total_filtered
        self.mode = mode

        self.current_filter_param = None
        self.current_grouped_data = {}
        self.selected_fittings = {}
        self.selected_sizing = {}
        self.selected_level = None
        self.elevation_offset = 0.0
        self.inherit_params = True

        self._combo_refs = {}
        self._sizing_refs = {}

        xaml_path = self.create_xaml()
        WPFWindow.__init__(self, xaml_path)
        self.setup_ui()

        self.combo_filter.SelectionChanged += self.on_filter_changed
        self.btn_apply.Click += self.apply_fittings
        self.btn_cancel.Click += self.cancel

    def create_xaml(self):
        header = '<?xml version="1.0" encoding="utf-8"?>\n'
        xaml_content = header + '''<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Slab Passes v5.1 - Pipes &amp; Conduits"
        Height="750" Width="850"
        WindowStartupLocation="CenterScreen"
        ResizeMode="CanResize">
    <Grid Margin="15">
        <Grid.RowDefinitions>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="*"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
        </Grid.RowDefinitions>

        <!-- HEADER -->
        <TextBlock Grid.Row="0" Text="Passagens de Laje - Slab Passes v5.1"
                   FontSize="16" FontWeight="Bold" Margin="0,0,0,15"/>

        <!-- FILTRO DINAMICO -->
        <Border Grid.Row="1" Background="#E3F2FD" BorderBrush="#2196F3" BorderThickness="2"
                CornerRadius="5" Padding="15" Margin="0,0,0,15">
            <Grid>
                <Grid.RowDefinitions>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="Auto"/>
                </Grid.RowDefinitions>

                <TextBlock Grid.Row="0" Text="Filtro de Agrupamento (Opcional):"
                          FontWeight="Bold" FontSize="13" Margin="0,0,0,8"/>

                <Grid Grid.Row="1">
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="Auto"/>
                        <ColumnDefinition Width="*"/>
                    </Grid.ColumnDefinitions>

                    <TextBlock Grid.Column="0" Text="Parametro:" VerticalAlignment="Center"
                              Margin="0,0,10,0" FontWeight="SemiBold"/>
                    <ComboBox x:Name="combo_filter" Grid.Column="1" Height="32" FontSize="12"
                             ToolTip="Escolha um parametro para agrupar os tubos alem do diametro"/>
                </Grid>
            </Grid>
        </Border>

        <!-- GRUPOS DE TUBOS -->
        <Border Grid.Row="2" BorderBrush="#DDD" BorderThickness="1" CornerRadius="3">
            <ScrollViewer VerticalScrollBarVisibility="Auto">
                <StackPanel x:Name="diameter_panel" Margin="5"/>
            </ScrollViewer>
        </Border>

        <!-- CONFIGURACOES DE NIVEL + OPCOES -->
        <Border Grid.Row="3" Background="#F5F5F5" Padding="12" Margin="0,15,0,0" CornerRadius="3">
            <StackPanel>
                <Grid>
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="Auto"/>
                        <ColumnDefinition Width="*"/>
                        <ColumnDefinition Width="Auto"/>
                        <ColumnDefinition Width="100"/>
                    </Grid.ColumnDefinitions>

                    <TextBlock Grid.Column="0" Text="Nivel de Referencia:" FontWeight="SemiBold"
                              VerticalAlignment="Center" Margin="0,0,10,0"/>
                    <ComboBox x:Name="combo_level" Grid.Column="1" Height="30"/>

                    <TextBlock Grid.Column="2" Text="Ajuste Fino (m):" FontWeight="SemiBold"
                              VerticalAlignment="Center" Margin="20,0,10,0"
                              ToolTip="Offset vertical em metros. 0 = nivel zero"/>
                    <TextBox x:Name="txt_elevation" Grid.Column="3" Height="30" Text="0"
                            VerticalContentAlignment="Center"/>
                </Grid>
                <CheckBox x:Name="chk_inherit_params" Content="Herdar parametros de texto do tubo"
                         IsChecked="True" Margin="0,10,0,0" FontSize="12"
                         ToolTip="Copia parametros de texto do tubo de referencia para a peca/acessorio criado"/>
            </StackPanel>
        </Border>

        <!-- STATUS -->
        <TextBlock x:Name="status_text" Grid.Row="4"
                   Text="Status..." Foreground="#666" FontSize="11"
                   Margin="0,10,0,0" TextWrapping="Wrap"/>

        <!-- BOTOES -->
        <StackPanel Grid.Row="5" Orientation="Horizontal" HorizontalAlignment="Right"
                   Margin="0,15,0,0">
            <Button x:Name="btn_cancel" Content="Cancelar" Width="110" Height="35"
                   Margin="0,0,10,0" FontSize="12"/>
            <Button x:Name="btn_apply" Content="Aplicar" Width="110" Height="35"
                    Background="#1976D2" Foreground="White" FontWeight="Bold" FontSize="12"/>
        </StackPanel>
    </Grid>
</Window>'''

        xaml_path = os.path.join(script_dir, 'temp_ui.xaml')
        with codecs.open(xaml_path, 'w', encoding='utf-8') as f:
            f.write(xaml_content)
        return xaml_path

    def setup_ui(self):
        levels = get_all_levels()
        for level in levels:
            self.combo_level.Items.Add(level.Name)

        pipe_level_idx = self._detect_pipe_level(levels)
        if pipe_level_idx >= 0:
            self.combo_level.SelectedIndex = pipe_level_idx
            self.selected_level = levels[pipe_level_idx]
        elif levels:
            self.combo_level.SelectedIndex = 0
            self.selected_level = levels[0]
        self.combo_level.SelectionChanged += self.on_level_changed

        self.combo_filter.Items.Add(u"(Nenhum - Apenas Diametro)")
        for param_name in self.available_params:
            self.combo_filter.Items.Add(param_name)
        self.combo_filter.SelectedIndex = 0

        self.update_status()
        self.render_groups()

    def update_status(self):
        mode_text = u"LOCAIS" if self.mode == "LOCAL" else u"em VINCULOS"
        filter_text = u" | Filtro: {}".format(self.current_filter_param) if self.current_filter_param else u""
        wps_text = u" | WPS carregada" if self.wps_types else u" | WPS nao disponivel"

        pipe_count = sum(1 for p in self.pipes_data_list if p.ElementType == "Pipe")
        conduit_count = sum(1 for p in self.pipes_data_list if p.ElementType == "Conduit")

        if conduit_count > 0:
            counts_text = u"{} pipes + {} conduits".format(pipe_count, conduit_count)
        else:
            counts_text = u"{} selecionados".format(self.total_selected)

        self.status_text.Text = u"Modo: Tubos {}{}{} | {} > {} verticais | {} grupos".format(
            mode_text, filter_text, wps_text,
            counts_text, self.total_filtered,
            len(self.current_grouped_data)
        )

    def on_filter_changed(self, sender, args):
        if self.combo_filter.SelectedIndex == 0:
            self.current_filter_param = None
        else:
            self.current_filter_param = self.available_params[self.combo_filter.SelectedIndex - 1]
        self.render_groups()

    def _get_display_name(self, type_elem, prefix):
        name = type_elem.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
        family_name = type_elem.FamilyName
        return u"{} {} - {}".format(prefix, family_name, name)

    def _find_wps_index_in_combo(self, wps_type_name):
        for i, (type_elem, prefix) in enumerate(self.all_types_with_prefix):
            if type_elem.FamilyName == WPS_FAMILY_NAME:
                name = type_elem.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
                if name == wps_type_name:
                    return i
        return -1

    def render_groups(self):
        from System.Windows.Controls import (
            StackPanel, TextBlock, ComboBox, Border, Grid,
            ColumnDefinition, RowDefinition, Orientation
        )
        from System.Windows import (
            Thickness, CornerRadius, FontWeights, GridLength, GridUnitType,
            HorizontalAlignment
        )
        from System.Windows.Media import SolidColorBrush, Color

        self.diameter_panel.Children.Clear()
        self._combo_refs = {}
        self._sizing_refs = {}

        self.current_grouped_data = group_pipes_data(self.pipes_data_list, self.current_filter_param)
        self.update_status()

        if self.mode == "LOCAL":
            bg_color = Color.FromRgb(232, 245, 233)
            border_color = Color.FromRgb(76, 175, 80)
        else:
            bg_color = Color.FromRgb(227, 242, 253)
            border_color = Color.FromRgb(33, 150, 243)

        for group_key in sorted(self.current_grouped_data.keys()):
            p_data_list = self.current_grouped_data[group_key]

            container = StackPanel()
            container.Margin = Thickness(0, 0, 0, 12)

            border = Border()
            border.Background = SolidColorBrush(bg_color)
            border.BorderBrush = SolidColorBrush(border_color)
            border.BorderThickness = Thickness(2)
            border.CornerRadius = CornerRadius(5)
            border.Padding = Thickness(12)

            inner_panel = StackPanel()

            title = TextBlock()
            title.Text = u"{} ({} elementos)".format(group_key, len(p_data_list))
            title.FontSize = 14
            title.FontWeight = FontWeights.Bold
            title.Margin = Thickness(0, 0, 0, 8)
            inner_panel.Children.Add(title)

            row_grid = Grid()
            col1 = ColumnDefinition()
            col1.Width = GridLength(1, GridUnitType.Star)
            col2 = ColumnDefinition()
            col2.Width = GridLength(160, GridUnitType.Pixel)
            row_grid.ColumnDefinitions.Add(col1)
            row_grid.ColumnDefinitions.Add(col2)

            combo = ComboBox()
            combo.Height = 32
            combo.Tag = group_key
            combo.FontSize = 11
            combo.Margin = Thickness(0, 0, 8, 0)
            Grid.SetColumn(combo, 0)

            if self.all_types_with_prefix:
                for type_elem, prefix in self.all_types_with_prefix:
                    combo.Items.Add(self._get_display_name(type_elem, prefix))

                pre_selected = False
                if group_key in self.selected_fittings:
                    try:
                        for idx, (te, _) in enumerate(self.all_types_with_prefix):
                            if te.Id == self.selected_fittings[group_key].Id:
                                combo.SelectedIndex = idx
                                pre_selected = True
                                break
                    except Exception as e:
                        pass

                if not pre_selected and self.wps_types:
                    diam_inches = parse_diameter_from_key(group_key)
                    sizing = self.selected_sizing.get(group_key, 0)
                    wps_name = get_wps_type_name_for_diameter(diam_inches, sizing)
                    idx = self._find_wps_index_in_combo(wps_name)
                    if idx >= 0:
                        combo.SelectedIndex = idx
                        self.selected_fittings[group_key] = self.all_types_with_prefix[idx][0]

                if combo.SelectedIndex < 0:
                    combo.Text = u"Selecione..."

                combo.SelectionChanged += self.on_fitting_selected
            else:
                combo.Items.Add(u"Nenhum acessorio/peca carregado")
                combo.IsEnabled = False

            self._combo_refs[group_key] = combo
            row_grid.Children.Add(combo)

            combo_sizing = ComboBox()
            combo_sizing.Height = 32
            combo_sizing.Tag = group_key
            combo_sizing.FontSize = 11
            Grid.SetColumn(combo_sizing, 1)

            for opt in SIZING_OPTIONS:
                combo_sizing.Items.Add(opt)

            current_sizing = self.selected_sizing.get(group_key, 0)
            combo_sizing.SelectedIndex = current_sizing
            combo_sizing.SelectionChanged += self.on_sizing_changed

            if not self.wps_types:
                combo_sizing.IsEnabled = False
                combo_sizing.ToolTip = u"Familia WPS nao carregada"

            self._sizing_refs[group_key] = combo_sizing
            row_grid.Children.Add(combo_sizing)

            inner_panel.Children.Add(row_grid)
            border.Child = inner_panel
            container.Children.Add(border)
            self.diameter_panel.Children.Add(container)

    def _detect_pipe_level(self, levels):
        if not self.pipes_data_list or not levels:
            return -1
        level_counts = {}
        for p_data in self.pipes_data_list:
            try:
                pipe = p_data.Element
                lvl_param = pipe.get_Parameter(BuiltInParameter.RBS_START_LEVEL_PARAM)
                if not lvl_param:
                    continue
                lvl_id = lvl_param.AsElementId()
                if lvl_id:
                    lvl_val = lvl_id.Value if hasattr(lvl_id, 'Value') else lvl_id.IntegerValue
                    level_counts[lvl_val] = level_counts.get(lvl_val, 0) + 1
            except Exception:
                continue
        if not level_counts:
            return -1
        most_common_val = max(level_counts, key=level_counts.get)
        for i, lvl in enumerate(levels):
            lvl_val = lvl.Id.Value if hasattr(lvl.Id, 'Value') else lvl.Id.IntegerValue
            if lvl_val == most_common_val:
                return i
        return -1

    def on_level_changed(self, sender, args):
        levels = get_all_levels()
        if self.combo_level.SelectedIndex >= 0:
            self.selected_level = levels[self.combo_level.SelectedIndex]

    def on_fitting_selected(self, sender, args):
        combo = sender
        group_key = combo.Tag
        if combo.SelectedIndex >= 0 and combo.IsEnabled:
            if combo.SelectedIndex < len(self.all_types_with_prefix):
                self.selected_fittings[group_key] = self.all_types_with_prefix[combo.SelectedIndex][0]

    def on_sizing_changed(self, sender, args):
        combo_sizing = sender
        group_key = combo_sizing.Tag
        sizing_idx = combo_sizing.SelectedIndex

        if sizing_idx < 0 or not self.wps_types:
            return

        self.selected_sizing[group_key] = sizing_idx

        diam_inches = parse_diameter_from_key(group_key)
        wps_name = get_wps_type_name_for_diameter(diam_inches, sizing_idx)
        combo_idx = self._find_wps_index_in_combo(wps_name)

        if combo_idx >= 0 and group_key in self._combo_refs:
            combo_fitting = self._combo_refs[group_key]
            combo_fitting.SelectedIndex = combo_idx
            self.selected_fittings[group_key] = self.all_types_with_prefix[combo_idx][0]

    def apply_fittings(self, sender, args):
        try:
            try:
                raw_val_meters = float(self.txt_elevation.Text.replace(',', '.'))
                self.elevation_offset = raw_val_meters / 0.3048
            except Exception as e:
                forms.alert(u"Elevacao invalida!")
                return

            if not self.selected_level:
                forms.alert(u"Selecione um nivel!")
                return

            has_any = False
            for group_key in self.current_grouped_data:
                if group_key in self.selected_fittings:
                    has_any = True
                    break

            if not has_any:
                forms.alert(u"Selecione ao menos um acessorio/peca!")
                return

            self.inherit_params = self.chk_inherit_params.IsChecked
            self.DialogResult = True
            self.Close()

        except Exception as e:
            forms.alert("Erro: {}".format(str(e)))

    def cancel(self, sender, args):
        self.DialogResult = False
        self.Close()

# ============================================================================
# 7. EXECUCAO PRINCIPAL
# ============================================================================

if not doc:
    forms.alert(u"Nenhum documento ativo!", exitscript=True)

# PASSO 1: Escolher modo
escolha = forms.CommandSwitchWindow.show(
    [u'Tubos LOCAIS (no projeto atual)', u'Tubos em VINCULOS (Revit Links)'],
    message=u'Selecione o tipo de tubos que deseja processar:'
)

if not escolha:
    sys.exit()

# PASSO 2: Selecao
selected_pipes_for_detection = []

if escolha == u'Tubos LOCAIS (no projeto atual)':
    MODE = "LOCAL"
    try:
        with forms.WarningBar(title=u"Selecione tubos/conduits VERTICAIS no projeto e clique em Concluir"):
            selection = list(uidoc.Selection.PickObjects(
                ObjectType.Element,
                LocalPipeSelectionFilter(),
                u"Selecione Tubos e Conduits Verticais"
            ))
    except Exception as e:
        sys.exit()

    if not selection:
        sys.exit()

    selected_pipes_for_detection = [doc.GetElement(ref) for ref in selection]

else:
    MODE = "LINKS"
    try:
        with forms.WarningBar(title=u"Selecione tubos/conduits VERTICAIS no modelo vinculado e clique em Concluir"):
            references = uidoc.Selection.PickObjects(
                ObjectType.LinkedElement,
                LinkedPipeSelectionFilter(doc),
                u"Selecione Tubos e Conduits no Vinculo"
            )
    except Exception as e:
        sys.exit()

    if not references:
        sys.exit()

    for ref in references:
        try:
            link_instance = doc.GetElement(ref.ElementId)
            link_doc = link_instance.GetLinkDocument()
            linked_elem = link_doc.GetElement(ref.LinkedElementId)
            if isinstance(linked_elem, (Pipe, Conduit)):
                selected_pipes_for_detection.append(linked_elem)
        except Exception as e:
            pass

# PASSO 3: Auto-carregar familia WPS
wps_types = ensure_wps_family_loaded()

# PASSO 4: Detectar parametros
available_params = get_available_parameters(selected_pipes_for_detection)

# PASSO 5: Processar elementos
if MODE == "LOCAL":
    all_pipes_data = process_local_pipes(selected_pipes_for_detection, available_params)
else:
    all_pipes_data = process_linked_pipes(references, available_params)

if not all_pipes_data:
    forms.alert(u"Nenhum elemento valido encontrado na selecao.", exitscript=True)

# PASSO 6: Filtros de verticalidade
filtered_pipes_data = apply_filters(all_pipes_data)

if not filtered_pipes_data:
    forms.alert(u"Nenhum elemento passou pelos filtros:\n\n" +
               u"- Deve ser VERTICAL\n\n" +
               u"Elementos analisados: {}".format(len(all_pipes_data)),
               exitscript=True)

# PASSO 7: Carregar Pecas + Acessorios
all_types_with_prefix = get_all_fittings_and_accessories()

if not all_types_with_prefix:
    forms.alert(u"Nenhuma familia de Peca ou Acessorio carregada no projeto.", exitscript=True)

# PASSO 8: Janela Dinamica
window = DynamicAcessoriosWindow(
    filtered_pipes_data,
    available_params,
    all_types_with_prefix,
    wps_types,
    len(all_pipes_data),
    len(filtered_pipes_data),
    MODE
)
result = window.ShowDialog()

# PASSO 9: Aplicar
if result:
    t = Transaction(doc, u"Slab Passes v5.1 - Aplicar Passagens")

    fail_opt = t.GetFailureHandlingOptions()
    fail_opt.SetFailuresPreprocessor(DuplicateWarningSwallower())
    t.SetFailureHandlingOptions(fail_opt)

    t.Start()

    try:
        created_count = 0
        skipped_count = 0
        placed_points = []

        with forms.ProgressBar(title=u"Aplicando Passagens... {value}/{max_value}") as pb:
            total_to_process = sum(
                len(p_data_list)
                for group_key, p_data_list in window.current_grouped_data.items()
                if group_key in window.selected_fittings
            )
            current = 0

            for group_key, p_data_list in window.current_grouped_data.items():
                if group_key not in window.selected_fittings:
                    continue

                fitting_type = window.selected_fittings[group_key]

                for p_data in p_data_list:
                    pb.update_progress(current, total_to_process)
                    current += 1

                    fitting = create_fitting_at_point(
                        p_data.CenterPoint,
                        fitting_type,
                        window.selected_level,
                        window.elevation_offset,
                        placed_points
                    )

                    if fitting:
                        try:
                            if p_data.DiameterParam:
                                pipe_diam = p_data.DiameterParam.AsDouble()
                                p_diam_inst = fitting.LookupParameter(u"Diametro Nominal") or \
                                             fitting.LookupParameter("Diameter")
                                if p_diam_inst and not p_diam_inst.IsReadOnly:
                                    p_diam_inst.Set(pipe_diam)
                        except Exception as e:
                            pass

                        if window.inherit_params:
                            try:
                                for pname, pval in p_data.AllParams.items():
                                    if pname in EXCLUDED_PARAMS:
                                        continue
                                    if not pval or pval in ("(Vazio)", "(Sem parametro)", "(Erro)"):
                                        continue
                                    tgt = fitting.LookupParameter(pname)
                                    if tgt and not tgt.IsReadOnly and tgt.StorageType == StorageType.String:
                                        tgt.Set(pval)
                            except Exception as e:
                                pass

                        created_count += 1
                    else:
                        skipped_count += 1

        t.Commit()

        msg_title = u"SUCESSO - Slab Passes | Criados: {} | Ignorados: {}".format(
            created_count, skipped_count
        )
        with forms.WarningBar(title=msg_title):
            pass

    except Exception as e:
        t.RollBack()
        forms.alert(u"Erro fatal: {}".format(str(e)))
