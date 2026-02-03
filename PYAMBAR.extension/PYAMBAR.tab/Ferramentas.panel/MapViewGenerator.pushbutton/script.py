# -*- coding: utf-8 -*-
"""
Gerador de Mapa de Vista v3.1
Cria vistas MAP automaticamente para localização em projetos

Autor: Thiago Barreto Sobral Nunes
Versão: 3.1

CHANGELOG:
v3.1 - Padronizacao: usar revit.doc/uidoc em vez de __revit__
"""

__title__ = "Gerador de\nMapa de Vista"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "3.3"
# __persistentengine__ removido - usa ShowDialog (modal)

# ============================================================================
# IMPORTAÇÕES
# ============================================================================

import clr

clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")

from Autodesk.Revit.DB import *
from pyrevit import forms, revit
from System.Collections.Generic import List
from System.IO import MemoryStream
from System.Text import Encoding
from System.Windows.Markup import XamlReader

# Importar do Snippets
try:
    from Snippets._transaction import ef_Transaction
    from Snippets.core._revit_version_helpers import get_element_id_value
except ImportError:
    import contextlib
    @contextlib.contextmanager
    def ef_Transaction(doc, title, debug=False, exitscript=False):
        t = Transaction(doc, title)
        t.Start()
        try:
            yield
            t.Commit()
        except Exception:
            t.RollBack()
            if exitscript:
                raise

# ============================================================================
# VARIÁVEIS GLOBAIS
# ============================================================================

doc = revit.doc
uidoc = revit.uidoc

# ============================================================================
# COMPATIBILIDADE REVIT API
# ============================================================================

def create_element_id(id_value):
    """Cria ElementId a partir de inteiro (compatível Revit 2023-2026)."""
    try:
        from System import Int64
        return ElementId(Int64(id_value))
    except:
        return ElementId(int(id_value))

# ============================================================================
# FUNÇÕES AUXILIARES - VIEW COLLECTION
# ============================================================================

def collect_valid_views():
    """Coleta vistas válidas COM vistas dependentes."""
    valid_view_types = [
        ViewType.FloorPlan,
        ViewType.CeilingPlan,
        ViewType.EngineeringPlan,
        ViewType.Section,
        ViewType.Elevation,
        ViewType.AreaPlan
    ]

    all_views = FilteredElementCollector(doc).OfClass(View).ToElements()
    views_dict = {}

    for view in all_views:
        if view.ViewType not in valid_view_types:
            continue
        if view.IsTemplate:
            continue
        if view.Name.startswith("MAP - "):
            continue
        if not view.CanViewBeDuplicated(ViewDuplicateOption.Duplicate):
            continue

        try:
            dependent_ids = view.GetDependentViewIds()
            dependent_count = len(dependent_ids) if dependent_ids else 0
            if dependent_count == 0:
                continue

            views_dict[view.Name] = {
                "view": view,
                "dependents_count": dependent_count
            }
        except:
            continue

    return views_dict

# ============================================================================
# FUNÇÕES AUXILIARES - FILLED REGION
# ============================================================================

def collect_filled_region_types():
    """Coleta tipos de FilledRegion disponíveis."""
    all_types = FilteredElementCollector(doc).OfClass(FilledRegionType).ToElements()
    types_dict = {}

    for fr_type in all_types:
        type_name = fr_type.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if type_name and type_name.HasValue:
            types_dict[type_name.AsString()] = fr_type

    return types_dict


def get_or_create_mapa_filled_region_type():
    """Obtém ou cria tipo FilledRegion 'MAPA' azul."""
    existing_types = collect_filled_region_types()

    if "MAPA" in existing_types:
        return existing_types["MAPA"]

    try:
        all_types = list(existing_types.values())
        if not all_types:
            raise Exception("Nenhum tipo de FilledRegion encontrado")

        base_type = all_types[0]
        duplicate_result = base_type.Duplicate("MAPA")

        if isinstance(duplicate_result, ElementId):
            new_type = doc.GetElement(duplicate_result)
        else:
            new_type = duplicate_result

        if not new_type:
            raise Exception("Falha ao duplicar tipo")

        blue_color = Color(0, 0, 255)

        solid_pattern_id = None
        solid_patterns = FilteredElementCollector(doc).OfClass(FillPatternElement).ToElements()

        for pattern in solid_patterns:
            fill_pattern = pattern.GetFillPattern()
            if fill_pattern and fill_pattern.IsSolidFill:
                solid_pattern_id = pattern.Id
                break

        if solid_pattern_id:
            new_type.ForegroundPatternId = solid_pattern_id
            new_type.ForegroundPatternColor = blue_color

        new_type.BackgroundPatternId = ElementId.InvalidElementId
        return new_type

    except Exception:
        if existing_types:
            return list(existing_types.values())[0]
        raise


def get_crop_region_curves(view):
    """Obtém contorno da crop region da vista."""
    try:
        shape_manager = view.GetCropRegionShapeManager()
        if shape_manager and shape_manager.CanHaveShape:
            crop_curves = shape_manager.GetCropShape()
            if crop_curves and crop_curves.Count > 0:
                return crop_curves
    except:
        pass

    try:
        crop_box = view.CropBox
        if not crop_box:
            return None

        min_pt = crop_box.Min
        max_pt = crop_box.Max

        p0 = XYZ(min_pt.X, min_pt.Y, 0)
        p1 = XYZ(max_pt.X, min_pt.Y, 0)
        p2 = XYZ(max_pt.X, max_pt.Y, 0)
        p3 = XYZ(min_pt.X, max_pt.Y, 0)

        curve_loop = CurveLoop()
        curve_loop.Append(Line.CreateBound(p0, p1))
        curve_loop.Append(Line.CreateBound(p1, p2))
        curve_loop.Append(Line.CreateBound(p2, p3))
        curve_loop.Append(Line.CreateBound(p3, p0))

        list_boundary = List[CurveLoop]()
        list_boundary.Add(curve_loop)
        return list_boundary
    except:
        return None


def create_filled_region_in_cropbox(view, filled_type_id):
    """Cria FilledRegion na CropBox da vista."""
    crop_curves = get_crop_region_curves(view)
    if not crop_curves or crop_curves.Count == 0:
        return None
    return FilledRegion.Create(doc, filled_type_id, view.Id, crop_curves)


def create_filled_region_from_source_crop(target_view, source_view, filled_type_id):
    """Cria FilledRegion usando crop da vista source."""
    crop_curves = get_crop_region_curves(source_view)
    if not crop_curves or crop_curves.Count == 0:
        return None
    try:
        return FilledRegion.Create(doc, filled_type_id, target_view.Id, crop_curves)
    except:
        return None

# ============================================================================
# FUNÇÕES AUXILIARES - GRIDS
# ============================================================================

def hide_all_grid_bubbles(view):
    """Oculta todas as grid bubbles na vista."""
    grids = FilteredElementCollector(doc, view.Id)\
        .OfCategory(BuiltInCategory.OST_Grids)\
        .WhereElementIsNotElementType()\
        .ToElements()

    count = 0
    for grid in grids:
        try:
            if grid.CanBeVisibleInView(view):
                grid.HideBubbleInView(DatumEnds.End0, view)
                grid.HideBubbleInView(DatumEnds.End1, view)
                count += 1
        except:
            continue
    return count

# ============================================================================
# FUNÇÕES AUXILIARES - VIEW MANIPULATION
# ============================================================================

def is_view_name_exists(name):
    """Verifica se nome de vista já existe."""
    all_views = FilteredElementCollector(doc).OfClass(View).ToElements()
    for v in all_views:
        if v.Name == name:
            return True
    return False


def disable_cropbox_limitation(view):
    """Desativa CropBox para mostrar projeto inteiro."""
    view.CropBoxActive = False
    view.CropBoxVisible = False


def copy_crop_region_shape(source_view, target_view):
    """Copia crop region de uma vista para outra."""
    try:
        source_shape_manager = source_view.GetCropRegionShapeManager()
        target_shape_manager = target_view.GetCropRegionShapeManager()

        if source_shape_manager and target_shape_manager:
            if source_shape_manager.CanHaveShape and target_shape_manager.CanHaveShape:
                source_crop_shapes = source_shape_manager.GetCropShape()
                if source_crop_shapes and source_crop_shapes.Count > 0:
                    target_shape_manager.SetCropShape(source_crop_shapes[0])
                    return True

        source_cropbox = source_view.CropBox
        if source_cropbox and target_shape_manager and target_shape_manager.CanHaveShape:
            min_pt = source_cropbox.Min
            max_pt = source_cropbox.Max

            p0 = XYZ(min_pt.X, min_pt.Y, 0)
            p1 = XYZ(max_pt.X, min_pt.Y, 0)
            p2 = XYZ(max_pt.X, max_pt.Y, 0)
            p3 = XYZ(min_pt.X, max_pt.Y, 0)

            curve_loop = CurveLoop()
            curve_loop.Append(Line.CreateBound(p0, p1))
            curve_loop.Append(Line.CreateBound(p1, p2))
            curve_loop.Append(Line.CreateBound(p2, p3))
            curve_loop.Append(Line.CreateBound(p3, p0))

            target_shape_manager.SetCropShape(curve_loop)
            return True

        return False
    except:
        return False


def configure_dependent_view_visibility(view):
    """Configura visibilidade nas vistas dependentes MAP."""
    try:
        all_categories = doc.Settings.Categories
        grids_cat_id = int(BuiltInCategory.OST_Grids)

        for category in all_categories:
            try:
                if category.CategoryType == CategoryType.Annotation:
                    cat_id_value = get_element_id_value(category.Id)
                    if cat_id_value == grids_cat_id:
                        continue
                    if view.CanCategoryBeHidden(category.Id):
                        view.SetCategoryHidden(category.Id, True)
            except:
                continue

        grid_cat = doc.Settings.Categories.get_Item(BuiltInCategory.OST_Grids)
        if grid_cat and view.CanCategoryBeHidden(grid_cat.Id):
            view.SetCategoryHidden(grid_cat.Id, False)

        detail_items_cat = doc.Settings.Categories.get_Item(BuiltInCategory.OST_DetailComponents)
        if detail_items_cat:
            if view.CanCategoryBeHidden(detail_items_cat.Id):
                view.SetCategoryHidden(detail_items_cat.Id, False)
            overrides = OverrideGraphicSettings()
            overrides.SetSurfaceTransparency(80)
            view.SetCategoryOverrides(detail_items_cat.Id, overrides)

        return True
    except:
        return False

# ============================================================================
# UI XAML
# ============================================================================

XAML_UI = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Gerador de Mapa de Vista v3.0"
        Width="600" Height="650"
        WindowStartupLocation="CenterScreen"
        ResizeMode="NoResize"
        Background="#F5F5F5">

    <Window.Resources>
        <Style TargetType="Button">
            <Setter Property="Padding" Value="15,8"/>
            <Setter Property="Margin" Value="5"/>
            <Setter Property="FontSize" Value="13"/>
            <Setter Property="Cursor" Value="Hand"/>
        </Style>
        <Style TargetType="TextBlock">
            <Setter Property="FontSize" Value="12"/>
            <Setter Property="Margin" Value="5,2"/>
        </Style>
        <Style TargetType="ListBox">
            <Setter Property="FontSize" Value="12"/>
        </Style>
    </Window.Resources>

    <Grid Margin="15">
        <Grid.RowDefinitions>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="*"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
        </Grid.RowDefinitions>

        <!-- HEADER -->
        <Border Grid.Row="0" Background="#2C3E50" Padding="15,10" CornerRadius="5" Margin="0,0,0,15">
            <StackPanel>
                <TextBlock Text="Gerador de Mapa de Vista" FontSize="18" FontWeight="Bold" Foreground="White"/>
                <TextBlock Text="Cria vistas MAP para localização no projeto (tipo MAPA azul)" FontSize="11" Foreground="#ECF0F1" Margin="0,3,0,0"/>
            </StackPanel>
        </Border>

        <!-- SECTION 1: SELEÇÃO DE VISTAS -->
        <StackPanel Grid.Row="1">
            <TextBlock Text="Selecione as Vistas" FontWeight="Bold" FontSize="13" Foreground="#2C3E50" Margin="0,0,0,8"/>
            <TextBlock Text="Apenas vistas COM dependentes são mostradas. Selecione uma ou mais vistas para gerar MAP:"
                       TextWrapping="Wrap" Foreground="#7F8C8D" Margin="0,0,0,5"/>
            <ListBox x:Name="ViewListBox"
                     SelectionMode="Multiple"
                     Height="200"
                     BorderBrush="#BDC3C7"
                     BorderThickness="1"
                     HorizontalContentAlignment="Stretch"/>
            <TextBlock x:Name="ViewCountText" Text="0 vistas selecionadas"
                       Foreground="#7F8C8D" FontSize="11" Margin="5,5,0,0"/>
        </StackPanel>

        <!-- WORKFLOW INFO -->
        <Border Grid.Row="3" Background="#ECF0F1" Padding="10" CornerRadius="3" Margin="0,15,0,15">
            <StackPanel>
                <TextBlock Text="O que será feito:" FontWeight="Bold" FontSize="11" Foreground="#2C3E50"/>
                <TextBlock FontSize="10" Foreground="#34495E" Margin="10,3,0,0">
                    Duplicar vista (com dependentes) | Renomear com prefixo "MAP - "
                </TextBlock>
                <TextBlock FontSize="10" Foreground="#34495E" Margin="10,2,0,0">
                    Criar região destacada AZUL | Apenas Grids visíveis | Itens de Detalhe 80% transparentes
                </TextBlock>
            </StackPanel>
        </Border>

        <!-- BUTTONS -->
        <Grid Grid.Row="4">
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="Auto"/>
                <ColumnDefinition Width="Auto"/>
            </Grid.ColumnDefinitions>

            <Button Grid.Column="1" x:Name="CancelButton" Content="Cancelar"
                    Width="120" Background="#95A5A6" Foreground="White"
                    BorderThickness="0"/>
            <Button Grid.Column="2" x:Name="OkButton" Content="Gerar MAP"
                    Width="120" Background="#27AE60" Foreground="White"
                    BorderThickness="0" FontWeight="Bold"/>
        </Grid>
    </Grid>
</Window>
"""

# ============================================================================
# UI WINDOW FUNCTIONS
# ============================================================================

def create_and_show_ui(views_dict):
    """Cria e mostra a janela de UI."""
    stream = MemoryStream(Encoding.UTF8.GetBytes(XAML_UI))
    window = XamlReader.Load(stream)

    result = [None]

    view_listbox = window.FindName("ViewListBox")
    view_count_text = window.FindName("ViewCountText")
    ok_button = window.FindName("OkButton")
    cancel_button = window.FindName("CancelButton")

    sorted_views = sorted(views_dict.keys())
    for view_name in sorted_views:
        dep_count = views_dict[view_name]["dependents_count"]
        display_name = "{} ({} dep.)".format(view_name, dep_count)
        view_listbox.Items.Add(display_name)

    def update_view_count(sender=None, args=None):
        count = view_listbox.SelectedItems.Count
        if count == 0:
            view_count_text.Text = "Nenhuma vista selecionada"
        elif count == 1:
            view_count_text.Text = "1 vista selecionada"
        else:
            view_count_text.Text = "{} vistas selecionadas".format(count)

    def on_ok(sender, args):
        if view_listbox.SelectedItems.Count == 0:
            forms.alert("Selecione pelo menos uma vista.", title="Seleção Vazia", warn_icon=True)
            return

        selected_display_names = list(view_listbox.SelectedItems)
        selected_views = []

        for display_name in selected_display_names:
            for view_name, view_data in views_dict.items():
                dep_count = view_data["dependents_count"]
                expected_display = "{} ({} dep.)".format(view_name, dep_count)
                if display_name == expected_display:
                    selected_views.append(view_data["view"])
                    break

        result[0] = {"views": selected_views}
        window.Close()

    def on_cancel(sender, args):
        result[0] = None
        window.Close()

    view_listbox.SelectionChanged += update_view_count
    ok_button.Click += on_ok
    cancel_button.Click += on_cancel

    update_view_count()
    window.ShowDialog()

    return result[0]

# ============================================================================
# PROCESSAMENTO PRINCIPAL
# ============================================================================

def process_view_in_transaction(view, filled_type):
    """Processa uma vista para criar MAP."""
    original_name = view.Name

    try:
        original_dependent_ids = view.GetDependentViewIds()
        original_dependent_count = len(original_dependent_ids)

        # Duplicar vista principal
        new_view_id = view.Duplicate(ViewDuplicateOption.Duplicate)
        new_view = doc.GetElement(new_view_id)

        if not new_view:
            raise Exception("Falha ao duplicar vista principal")

        # Renomear
        map_name = "MAP - {}".format(original_name)
        counter = 1
        final_map_name = map_name
        while is_view_name_exists(final_map_name):
            final_map_name = "{} ({})".format(map_name, counter)
            counter += 1

        new_view.Name = final_map_name

        # Criar dependentes vinculadas
        dependent_views = []
        dependent_original_map = {}

        if original_dependent_count > 0:
            for dep_id in original_dependent_ids:
                try:
                    original_dep_view = doc.GetElement(dep_id)
                    if not original_dep_view:
                        continue

                    new_dep_view_id = new_view.Duplicate(ViewDuplicateOption.AsDependent)
                    new_dep_view = doc.GetElement(new_dep_view_id)

                    if new_dep_view:
                        original_dep_name = original_dep_view.Name
                        if original_dep_name.startswith(original_name):
                            suffix = original_dep_name[len(original_name):].lstrip(" -")
                            new_dep_name = "{} - {}".format(final_map_name, suffix)
                        else:
                            new_dep_name = "MAP - {}".format(original_dep_name)

                        dep_counter = 1
                        final_dep_name = new_dep_name
                        while is_view_name_exists(final_dep_name):
                            final_dep_name = "{} ({})".format(new_dep_name, dep_counter)
                            dep_counter += 1

                        new_dep_view.Name = final_dep_name
                        copy_crop_region_shape(original_dep_view, new_dep_view)
                        dependent_original_map[new_dep_view.Id] = original_dep_view
                        dependent_views.append(new_dep_view)
                except:
                    continue

        # Processar vista principal
        disable_cropbox_limitation(new_view)

        # Processar dependentes
        view_regions = {}
        for dep_view in dependent_views:
            original_dep = dependent_original_map.get(dep_view.Id)
            if original_dep:
                filled_region_dep = create_filled_region_from_source_crop(dep_view, original_dep, filled_type.Id)
                if filled_region_dep:
                    view_regions[dep_view.Id] = filled_region_dep.Id
                disable_cropbox_limitation(dep_view)
                configure_dependent_view_visibility(dep_view)

        # Sistema de isolamento
        for view_to_isolate in dependent_views:
            if view_to_isolate.Id not in view_regions:
                continue
            regions_to_hide = []
            for other_view_id, region_id in view_regions.items():
                if other_view_id != view_to_isolate.Id:
                    regions_to_hide.append(region_id)
            if regions_to_hide:
                try:
                    view_to_isolate.HideElements(List[ElementId](regions_to_hide))
                except:
                    pass

        # Ocultar grid bubbles
        for dep_view in dependent_views:
            try:
                hide_all_grid_bubbles(dep_view)
            except:
                pass

        try:
            hide_all_grid_bubbles(new_view)
        except:
            pass

        all_created_views = [new_view] + dependent_views
        return (True, all_created_views, None)

    except Exception as e:
        return (False, [], str(e))

# ============================================================================
# EXECUÇÃO PRINCIPAL
# ============================================================================

def main():
    """Função principal."""
    # Coletar vistas válidas
    available_views = collect_valid_views()

    if not available_views:
        forms.alert(
            "Nenhuma vista COM vistas dependentes encontrada.\n\n"
            "Crie vistas dependentes primeiro e tente novamente.",
            title="Sem Vistas Disponíveis",
            warn_icon=True,
            exitscript=True
        )

    # Criar/Obter tipo MAPA
    mapa_type = None
    with ef_Transaction(doc, "Criar tipo MAPA", debug=False):
        mapa_type = get_or_create_mapa_filled_region_type()

    if not mapa_type:
        forms.alert(
            "Não foi possível criar o tipo de FilledRegion 'MAPA'.",
            title="Erro",
            warn_icon=True,
            exitscript=True
        )

    # Mostrar UI
    user_selection = create_and_show_ui(available_views)

    if not user_selection:
        return

    selected_views = user_selection["views"]

    # Processar vistas
    success_count = 0
    total_views_created = 0
    failed_views = []

    with ef_Transaction(doc, "Gerar MAP - {} vistas".format(len(selected_views)), debug=False):
        for view in selected_views:
            success, new_views_list, error = process_view_in_transaction(view, mapa_type)
            if success:
                success_count += 1
                total_views_created += len(new_views_list)
            else:
                failed_views.append((view.Name, error))

    # Mensagem final
    if success_count == len(selected_views):
        forms.toast(
            "{} vista(s) MAP criada(s) com sucesso!".format(total_views_created),
            title="Concluído",

        )
    elif success_count > 0:
        forms.alert(
            "Processamento parcial:\n"
            "Sucessos: {}\n"
            "Falhas: {}".format(success_count, len(failed_views)),
            title="Aviso",
            warn_icon=True
        )
    else:
        forms.alert(
            "Não foi possível criar nenhuma vista MAP.\n"
            "Erro: {}".format(failed_views[0][1] if failed_views else "Desconhecido"),
            title="Erro",
            warn_icon=True
        )

# ============================================================================
# PONTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    main()
