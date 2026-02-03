# -*- coding: utf-8 -*-
__title__ = "Slab\nPasses"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "4.2"
__doc__ = """
Slab Passes - Passagens de Laje v4.1

FUNCIONALIDADES:
- Seleção de tubos VERTICAIS (locais OU vínculos)
- Filtro DINÂMICO por parâmetro na mesma janela
- Conversão automática de coordenadas (Link -> Projeto Atual)
- Agrupamento inteligente em tempo real
- Proteção contra duplicidade

WORKFLOW:
1. Execute o script
2. Escolha: Tubos LOCAIS ou em VÍNCULOS
3. Selecione os tubos VERTICAIS
4. Na janela: escolha filtro (atualiza grupos em tempo real)
5. Configure acessório e nível para cada grupo
6. Clique em "Aplicar"

MELHORIAS v4.1:
- Interface unificada e dinâmica
- Filtro integrado com atualização em tempo real
- Muito mais produtivo e profissional
"""

__persistentengine__ = True

import clr
import sys
import os
import codecs
from collections import defaultdict

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Plumbing import Pipe
from Autodesk.Revit.DB.Structure import StructuralType
from Autodesk.Revit.UI import *
from Autodesk.Revit.UI.Selection import *
from System.Collections.Generic import List

from pyrevit import revit, DB, UI, forms
from pyrevit.forms import WPFWindow

doc = revit.doc
uidoc = revit.uidoc
script_dir = os.path.dirname(__file__)

# ============================================================================
# 1. SUPRESSÃO DE AVISOS DE DUPLICIDADE
# ============================================================================
class DuplicateWarningSwallower(IFailuresPreprocessor):
    """Suprime avisos de 'elementos duplicados' do Revit."""
    def PreprocessFailures(self, failuresAccessor):
        failures = failuresAccessor.GetFailureMessages()
        for f in failures:
            if f.GetSeverity() == FailureSeverity.Warning:
                failuresAccessor.DeleteWarning(f)
        return FailureProcessingResult.Continue

# ============================================================================
# 2. FILTROS DE SELEÇÃO
# ============================================================================
def is_vertical(curve, tolerance=0.05):
    """Verifica se o tubo é vertical (diferença X,Y < tolerância)."""
    p1 = curve.GetEndPoint(0)
    p2 = curve.GetEndPoint(1)
    horizontal_distance = ((p2.X - p1.X)**2 + (p2.Y - p1.Y)**2)**0.5
    return horizontal_distance < tolerance

class LocalPipeSelectionFilter(ISelectionFilter):
    """Permite selecionar apenas Tubos LOCAIS VERTICAIS"""
    def AllowElement(self, elem):
        if not isinstance(elem, Pipe):
            return False
        try:
            location = elem.Location
            if isinstance(location, LocationCurve):
                curve = location.Curve
                if is_vertical(curve):
                    return True
        except:
            pass
        return False

    def AllowReference(self, reference, position):
        return True

class LinkedPipeSelectionFilter(ISelectionFilter):
    """Permite selecionar apenas Tubos VERTICAIS dentro de Vínculos"""
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
                    if isinstance(linked_element, Pipe):
                        location = linked_element.Location
                        if isinstance(location, LocationCurve):
                            curve = location.Curve
                            if is_vertical(curve):
                                return True
        except:
            return False
        return False

# ============================================================================
# 3. FUNÇÕES DE GEOMETRIA E PARÂMETROS
# ============================================================================
def get_pipe_diameter(pipe):
    """Obtém o diâmetro do tubo em formato legível"""
    try:
        diameter_param = pipe.get_Parameter(BuiltInParameter.RBS_PIPE_DIAMETER_PARAM)
        if diameter_param:
            diameter_feet = diameter_param.AsDouble()
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
        return "Unknown"
    except:
        return "Unknown"

def get_available_parameters(pipes):
    """
    Detecta parâmetros disponíveis nos tubos selecionados.
    Retorna lista de nomes de parâmetros de projeto/compartilhados.
    """
    if not pipes:
        return []

    # Usar primeiro tubo como referência
    first_pipe = pipes[0]
    available_params = []

    for param in first_pipe.Parameters:
        try:
            param_name = param.Definition.Name

            # Excluir parâmetros do sistema conhecidos
            system_params = [
                "Family", "Type", "Comments", "Mark", "Diameter",
                "Level", "Reference Level", "Top Offset", "Bottom Offset",
                "System Classification", "System Type", "System Name",
                "Workset", "Design Option", "Phase Created", "Phase Demolished"
            ]

            if param_name in system_params:
                continue

            # Filtrar apenas parâmetros que parecem ser de projeto/compartilhados
            is_candidate = False

            if param.IsShared:
                is_candidate = True
            elif not param.IsReadOnly:
                try:
                    value = param.AsString() or param.AsValueString()
                    if value:
                        is_candidate = True
                except:
                    pass

            if is_candidate:
                available_params.append(param_name)

        except:
            continue

    # Remover duplicatas e ordenar
    return sorted(list(set(available_params)))

def get_parameter_value(pipe, param_name):
    """Obtém valor de um parâmetro específico do tubo"""
    try:
        param = pipe.LookupParameter(param_name)
        if param:
            value = param.AsString()
            if not value:
                value = param.AsValueString()
            return value if value else "(Vazio)"
        return "(Sem parâmetro)"
    except:
        return "(Erro)"

def has_duplicate_at_location(location_point, tolerance=0.1):
    """Verifica se JÁ EXISTE um acessório neste local (tolerância 10cm)."""
    collector = FilteredElementCollector(doc)\
        .OfCategory(BuiltInCategory.OST_PipeAccessory)\
        .OfClass(FamilyInstance)

    for inst in collector:
        loc = inst.Location
        if loc and isinstance(loc, LocationPoint):
            dist = loc.Point.DistanceTo(location_point)
            if dist < tolerance:
                return True
    return False

# ============================================================================
# 4. PROCESSAMENTO DE TUBOS
# ============================================================================
class PipeData:
    """Armazena dados do tubo processado"""
    def __init__(self, pipe_element, center_point_host, diameter, diameter_param, all_params_dict):
        self.Element = pipe_element
        self.CenterPoint = center_point_host
        self.Diameter = diameter
        self.DiameterParam = diameter_param
        self.AllParams = all_params_dict  # NOVO: Dicionário com todos os parâmetros

def process_local_pipes(pipes, available_params):
    """Processa tubos LOCAIS e extrai TODOS os parâmetros disponíveis"""
    processed_pipes = []

    for pipe in pipes:
        try:
            location = pipe.Location
            if isinstance(location, LocationCurve):
                curve = location.Curve
                p1 = curve.GetEndPoint(0)
                p2 = curve.GetEndPoint(1)
                center_point = (p1 + p2) / 2.0

                diameter = get_pipe_diameter(pipe)
                diameter_param = pipe.get_Parameter(BuiltInParameter.RBS_PIPE_DIAMETER_PARAM)

                # NOVO: Obter valores de TODOS os parâmetros disponíveis
                params_dict = {}
                for param_name in available_params:
                    params_dict[param_name] = get_parameter_value(pipe, param_name)

                p_data = PipeData(pipe, center_point, diameter, diameter_param, params_dict)
                processed_pipes.append(p_data)
        except Exception as e:
            print("Erro ao processar tubo local: {}".format(e))

    return processed_pipes

def process_linked_pipes(references, available_params):
    """Processa tubos em VÍNCULOS e extrai TODOS os parâmetros disponíveis"""
    processed_pipes = []

    for ref in references:
        try:
            link_instance = doc.GetElement(ref.ElementId)
            transform = link_instance.GetTotalTransform()
            link_doc = link_instance.GetLinkDocument()
            linked_pipe = link_doc.GetElement(ref.LinkedElementId)

            if isinstance(linked_pipe, Pipe):
                location = linked_pipe.Location
                if isinstance(location, LocationCurve):
                    curve = location.Curve
                    mid_param = (curve.GetEndParameter(0) + curve.GetEndParameter(1)) / 2
                    internal_mid_point = curve.Evaluate(mid_param, False)
                    host_mid_point = transform.OfPoint(internal_mid_point)

                    diameter = get_pipe_diameter(linked_pipe)
                    diameter_param = linked_pipe.get_Parameter(BuiltInParameter.RBS_PIPE_DIAMETER_PARAM)

                    # NOVO: Obter valores de TODOS os parâmetros disponíveis
                    params_dict = {}
                    for param_name in available_params:
                        params_dict[param_name] = get_parameter_value(linked_pipe, param_name)

                    p_data = PipeData(linked_pipe, host_mid_point, diameter, diameter_param, params_dict)
                    processed_pipes.append(p_data)

        except Exception as e:
            print("Erro ao processar tubo em vínculo: {}".format(e))

    return processed_pipes

def apply_filters(pipes_data_list):
    """Aplica filtros de verticalidade"""
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
            print("Erro ao filtrar tubo: {}".format(e))
            continue

    return filtered

def group_pipes_data(pipes_data_list, filter_param_name=None):
    """
    Agrupa objetos PipeData por diâmetro [+ parâmetro]

    Args:
        pipes_data_list: Lista de PipeData
        filter_param_name: Nome do parâmetro para agrupar (None = apenas diâmetro)

    Returns:
        dict: {grupo_key: [PipeData]}
    """
    grouped = defaultdict(list)

    for p_data in pipes_data_list:
        if filter_param_name and filter_param_name in p_data.AllParams:
            param_value = p_data.AllParams[filter_param_name]
            group_key = u"{} | {}".format(p_data.Diameter, param_value)
        else:
            group_key = p_data.Diameter

        grouped[group_key].append(p_data)

    return dict(grouped)

# ============================================================================
# 5. FUNÇÕES AUXILIARES
# ============================================================================
def get_all_pipe_accessories():
    """Retorna todos os tipos de Acessórios de Tubulação carregados"""
    try:
        collector = FilteredElementCollector(doc)\
            .OfCategory(BuiltInCategory.OST_PipeAccessory)\
            .WhereElementIsElementType()

        accessories = []
        for type_elem in collector:
            accessories.append(type_elem)

        accessories.sort(key=lambda x: (x.FamilyName, x.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()))
        return accessories
    except:
        return []

def get_all_levels():
    """Retorna todos os níveis do projeto, ordenados por elevação"""
    collector = FilteredElementCollector(doc)\
        .OfClass(Level)\
        .WhereElementIsNotElementType()
    return sorted(collector, key=lambda x: x.Elevation)

def create_fitting_at_point(point_x_y, fitting_type, level, elevation_offset):
    """Cria acessório usando X,Y fornecidos e Z do Nível + Offset"""
    try:
        if not fitting_type.IsActive:
            fitting_type.Activate()
            doc.Regenerate()

        target_z = level.Elevation + elevation_offset
        placement_point = XYZ(point_x_y.X, point_x_y.Y, target_z)

        if has_duplicate_at_location(placement_point):
            return None

        new_fitting = doc.Create.NewFamilyInstance(
            placement_point,
            fitting_type,
            level,
            StructuralType.NonStructural
        )

        param_offset = new_fitting.get_Parameter(BuiltInParameter.INSTANCE_FREE_HOST_OFFSET_PARAM)
        if param_offset and not param_offset.IsReadOnly:
            param_offset.Set(elevation_offset)
        else:
            param_elevation = new_fitting.get_Parameter(BuiltInParameter.INSTANCE_ELEVATION_PARAM)
            if param_elevation and not param_elevation.IsReadOnly:
                param_elevation.Set(target_z)

        return new_fitting

    except Exception as e:
        print("Erro ao criar acessório: {}".format(str(e)))
        return None

# ============================================================================
# 6. INTERFACE WPF DINÂMICA - TUDO EM UMA JANELA
# ============================================================================
class DynamicAcessoriosWindow(WPFWindow):
    """Janela unificada com filtro dinâmico integrado"""

    def __init__(self, pipes_data_list, available_params, all_accessories, total_selected, total_filtered, mode):
        self.pipes_data_list = pipes_data_list  # Lista completa de PipeData
        self.available_params = available_params  # Parâmetros disponíveis
        self.all_accessories = all_accessories
        self.total_selected = total_selected
        self.total_filtered = total_filtered
        self.mode = mode

        self.current_filter_param = None  # Filtro atual
        self.current_grouped_data = {}    # Grupos atuais
        self.selected_fittings = {}       # Acessórios escolhidos
        self.selected_level = None
        self.elevation_offset = 0.0

        xaml_path = self.create_xaml()
        WPFWindow.__init__(self, xaml_path)
        self.setup_ui()

        # Event handlers
        self.combo_filter.SelectionChanged += self.on_filter_changed
        self.btn_apply.Click += self.apply_fittings
        self.btn_cancel.Click += self.cancel

    def create_xaml(self):
        header = '<?xml version="1.0" encoding="utf-8"?>\n'
        xaml_content = header + '''<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Slab Passes - Configuração Dinâmica"
        Height="700" Width="800"
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
        <TextBlock Grid.Row="0" Text="Configuração de Passagens de Laje"
                   FontSize="16" FontWeight="Bold" Margin="0,0,0,15"/>

        <!-- FILTRO DINÂMICO -->
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

                    <TextBlock Grid.Column="0" Text="Parâmetro:" VerticalAlignment="Center"
                              Margin="0,0,10,0" FontWeight="SemiBold"/>
                    <ComboBox x:Name="combo_filter" Grid.Column="1" Height="32" FontSize="12"
                             ToolTip="Escolha um parâmetro para agrupar os tubos além do diâmetro"/>
                </Grid>
            </Grid>
        </Border>

        <!-- GRUPOS DE TUBOS -->
        <Border Grid.Row="2" BorderBrush="#DDD" BorderThickness="1" CornerRadius="3">
            <ScrollViewer VerticalScrollBarVisibility="Auto">
                <StackPanel x:Name="diameter_panel" Margin="5"/>
            </ScrollViewer>
        </Border>

        <!-- CONFIGURAÇÕES DE NÍVEL -->
        <Border Grid.Row="3" Background="#F5F5F5" Padding="12" Margin="0,15,0,0" CornerRadius="3">
            <Grid>
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="Auto"/>
                    <ColumnDefinition Width="*"/>
                    <ColumnDefinition Width="Auto"/>
                    <ColumnDefinition Width="100"/>
                </Grid.ColumnDefinitions>

                <TextBlock Grid.Column="0" Text="Nível de Referência:" FontWeight="SemiBold"
                          VerticalAlignment="Center" Margin="0,0,10,0"/>
                <ComboBox x:Name="combo_level" Grid.Column="1" Height="30"/>

                <TextBlock Grid.Column="2" Text="Ajuste Fino (m):" FontWeight="SemiBold"
                          VerticalAlignment="Center" Margin="20,0,10,0"
                          ToolTip="Offset vertical em metros. 0 = nível zero"/>
                <TextBox x:Name="txt_elevation" Grid.Column="3" Height="30" Text="0"
                        VerticalContentAlignment="Center"/>
            </Grid>
        </Border>

        <!-- STATUS -->
        <TextBlock x:Name="status_text" Grid.Row="4"
                   Text="Status..." Foreground="#666" FontSize="11"
                   Margin="0,10,0,0" TextWrapping="Wrap"/>

        <!-- BOTÕES -->
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
        """Configuração inicial da interface"""

        # Popular níveis
        levels = get_all_levels()
        for level in levels:
            self.combo_level.Items.Add(level.Name)
        if levels:
            self.combo_level.SelectedIndex = 0
            self.selected_level = levels[0]
        self.combo_level.SelectionChanged += self.on_level_changed

        # Popular combo de filtros
        self.combo_filter.Items.Add(u"(Nenhum - Apenas Diâmetro)")
        for param_name in self.available_params:
            self.combo_filter.Items.Add(param_name)
        self.combo_filter.SelectedIndex = 0

        # Atualizar status inicial
        self.update_status()

        # Renderizar grupos inicial (sem filtro)
        self.render_groups()

    def update_status(self):
        """Atualiza texto de status"""
        mode_text = u"LOCAIS" if self.mode == "LOCAL" else u"em VÍNCULOS"
        filter_text = u" | Filtro: {}".format(self.current_filter_param) if self.current_filter_param else u""

        self.status_text.Text = u"Modo: Tubos {}{} | {} selecionados → {} verticais válidos | {} grupos".format(
            mode_text,
            filter_text,
            self.total_selected,
            self.total_filtered,
            len(self.current_grouped_data)
        )

    def on_filter_changed(self, sender, args):
        """Callback quando filtro é alterado - ATUALIZA GRUPOS EM TEMPO REAL"""
        if self.combo_filter.SelectedIndex == 0:
            # "(Nenhum - Apenas Diâmetro)"
            self.current_filter_param = None
        else:
            self.current_filter_param = self.available_params[self.combo_filter.SelectedIndex - 1]

        # Reprocessar grupos e re-renderizar
        self.render_groups()

    def render_groups(self):
        """Renderiza os grupos de tubos baseado no filtro atual"""
        from System.Windows.Controls import StackPanel, TextBlock, ComboBox, Border
        from System.Windows import Thickness, CornerRadius, FontWeights
        from System.Windows.Media import SolidColorBrush, Color

        # Limpar painel
        self.diameter_panel.Children.Clear()

        # Reagrupar dados com filtro atual
        self.current_grouped_data = group_pipes_data(self.pipes_data_list, self.current_filter_param)

        # Atualizar status
        self.update_status()

        # Cores baseadas no modo
        if self.mode == "LOCAL":
            bg_color = Color.FromRgb(232, 245, 233)
            border_color = Color.FromRgb(76, 175, 80)
        else:
            bg_color = Color.FromRgb(227, 242, 253)
            border_color = Color.FromRgb(33, 150, 243)

        # Criar UI para cada grupo
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

            # Título do grupo
            title = TextBlock()
            title.Text = u"{} ({} tubos)".format(group_key, len(p_data_list))
            title.FontSize = 14
            title.FontWeight = FontWeights.Bold
            title.Margin = Thickness(0, 0, 0, 8)
            inner_panel.Children.Add(title)

            # ComboBox de acessórios
            combo = ComboBox()
            combo.Height = 32
            combo.Tag = group_key
            combo.FontSize = 12

            if self.all_accessories:
                for acc in self.all_accessories:
                    name = acc.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
                    family_name = acc.FamilyName
                    combo.Items.Add("{} - {}".format(family_name, name))

                # Manter seleção anterior se existir
                if group_key in self.selected_fittings:
                    try:
                        idx = self.all_accessories.index(self.selected_fittings[group_key])
                        combo.SelectedIndex = idx
                    except:
                        combo.SelectedIndex = -1
                        combo.Text = u"Selecione um acessório..."
                else:
                    combo.SelectedIndex = -1
                    combo.Text = u"Selecione um acessório..."

                combo.SelectionChanged += self.on_fitting_selected
            else:
                combo.Items.Add(u"Nenhum acessório carregado")
                combo.IsEnabled = False

            inner_panel.Children.Add(combo)
            border.Child = inner_panel
            container.Children.Add(border)

            self.diameter_panel.Children.Add(container)

    def on_level_changed(self, sender, args):
        levels = get_all_levels()
        if self.combo_level.SelectedIndex >= 0:
            self.selected_level = levels[self.combo_level.SelectedIndex]

    def on_fitting_selected(self, sender, args):
        combo = sender
        group_key = combo.Tag
        if combo.SelectedIndex >= 0 and combo.IsEnabled:
            if combo.SelectedIndex < len(self.all_accessories):
                self.selected_fittings[group_key] = self.all_accessories[combo.SelectedIndex]

    def apply_fittings(self, sender, args):
        try:
            try:
                raw_val_meters = float(self.txt_elevation.Text.replace(',', '.'))
                self.elevation_offset = raw_val_meters / 0.3048
            except:
                forms.alert(u"Elevação inválida!", exitscript=True)
                return

            if not self.selected_level:
                forms.alert(u"Selecione um nível!", exitscript=True)
                return

            self.DialogResult = True
            self.Close()

        except Exception as e:
            forms.alert("Erro: {}".format(str(e)))

    def cancel(self, sender, args):
        self.DialogResult = False
        self.Close()

# ============================================================================
# 7. EXECUÇÃO PRINCIPAL
# ============================================================================

if not doc:
    forms.alert(u"Nenhum documento ativo!", exitscript=True)

# PASSO 1: Escolher modo (LOCAL ou VÍNCULOS)
escolha = forms.CommandSwitchWindow.show(
    [u'Tubos LOCAIS (no projeto atual)', u'Tubos em VÍNCULOS (Revit Links)'],
    message=u'Selecione o tipo de tubos que deseja processar:'
)

if not escolha:
    sys.exit()

# PASSO 2: Seleção baseada na escolha
selected_pipes_for_detection = []

if escolha == u'Tubos LOCAIS (no projeto atual)':
    MODE = "LOCAL"
    try:
        with forms.WarningBar(title=u"Selecione tubos VERTICAIS no projeto e clique em Concluir"):
            selection = list(uidoc.Selection.PickObjects(
                ObjectType.Element,
                LocalPipeSelectionFilter(),
                u"Selecione Tubos Verticais"
            ))
    except:
        sys.exit()

    if not selection:
        sys.exit()

    selected_pipes_for_detection = [doc.GetElement(ref) for ref in selection]

else:  # Vínculos
    MODE = "LINKS"
    try:
        with forms.WarningBar(title=u"Selecione tubos VERTICAIS no modelo vinculado e clique em Concluir"):
            references = uidoc.Selection.PickObjects(
                ObjectType.LinkedElement,
                LinkedPipeSelectionFilter(doc),
                u"Selecione Tubos no Vínculo"
            )
    except:
        sys.exit()

    if not references:
        sys.exit()

    # Obter pipes dos vínculos para detecção de parâmetros
    for ref in references:
        try:
            link_instance = doc.GetElement(ref.ElementId)
            link_doc = link_instance.GetLinkDocument()
            linked_pipe = link_doc.GetElement(ref.LinkedElementId)
            if isinstance(linked_pipe, Pipe):
                selected_pipes_for_detection.append(linked_pipe)
        except:
            pass

# PASSO 3: Detectar parâmetros disponíveis
available_params = get_available_parameters(selected_pipes_for_detection)

# PASSO 4: Processar tubos com TODOS os parâmetros
if MODE == "LOCAL":
    all_pipes_data = process_local_pipes(selected_pipes_for_detection, available_params)
else:
    all_pipes_data = process_linked_pipes(references, available_params)

if not all_pipes_data:
    forms.alert(u"Nenhum tubo válido encontrado na seleção.", exitscript=True)

# PASSO 5: Aplicar filtros de verticalidade
filtered_pipes_data = apply_filters(all_pipes_data)

if not filtered_pipes_data:
    forms.alert(u"Nenhum tubo passou pelos filtros:\n\n" +
               u"- Deve ser VERTICAL\n\n" +
               u"Tubos analisados: {}".format(len(all_pipes_data)),
               exitscript=True)

# PASSO 6: Carregar Acessórios
all_accessories = get_all_pipe_accessories()

if not all_accessories:
    forms.alert(u"Nenhuma família de Acessório de Tubulação carregada no projeto.", exitscript=True)

# PASSO 7: Abrir Janela DINÂMICA (tudo integrado)
window = DynamicAcessoriosWindow(
    filtered_pipes_data,
    available_params,
    all_accessories,
    len(all_pipes_data),
    len(filtered_pipes_data),
    MODE
)
result = window.ShowDialog()

# PASSO 8: Se usuário confirmou, aplicar
if result:
    t = Transaction(doc, u"Slab Passes - Aplicar Acessórios")

    fail_opt = t.GetFailureHandlingOptions()
    fail_opt.SetFailuresPreprocessor(DuplicateWarningSwallower())
    t.SetFailureHandlingOptions(fail_opt)

    t.Start()

    try:
        created_count = 0
        skipped_count = 0

        with forms.ProgressBar(title=u"Aplicando Acessórios... {value}/{max_value}") as pb:
            total_to_process = sum(len(p_data_list) for group_key, p_data_list in window.current_grouped_data.items() if group_key in window.selected_fittings)
            current = 0

            for group_key, p_data_list in window.current_grouped_data.items():
                if group_key in window.selected_fittings:
                    fitting_type = window.selected_fittings[group_key]

                    for p_data in p_data_list:
                        pb.update_progress(current, total_to_process)
                        current += 1

                        fitting = create_fitting_at_point(
                            p_data.CenterPoint,
                            fitting_type,
                            window.selected_level,
                            window.elevation_offset
                        )

                        if fitting:
                            try:
                                if p_data.DiameterParam:
                                    pipe_diam = p_data.DiameterParam.AsDouble()
                                    p_diam_inst = fitting.LookupParameter(u"Diâmetro Nominal") or \
                                                 fitting.LookupParameter("Diameter")
                                    if p_diam_inst and not p_diam_inst.IsReadOnly:
                                        p_diam_inst.Set(pipe_diam)
                            except:
                                pass

                            created_count += 1
                        else:
                            skipped_count += 1

        t.Commit()

        # Relatório Final
        msg_title = u"SUCESSO - Slab Passes | Criados: {} | Ignorados: {}".format(
            created_count, skipped_count
        )
        with forms.WarningBar(title=msg_title):
            pass

    except Exception as e:
        t.RollBack()
        forms.alert(u"Erro fatal: {}".format(str(e)))
