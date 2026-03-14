# -*- coding: utf-8 -*-
"""
ParamForge - Janela principal e dialogs.
"""
import random

import clr
clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")

from System.Collections.ObjectModel import ObservableCollection
from System.IO import MemoryStream
from System.Text import Encoding
from System.Windows import Window, WindowStartupLocation, ResizeMode, Thickness
from System.Windows.Controls import CheckBox as WpfCheckBox, ComboBox, TextBlock, StackPanel, Orientation
from System.Windows.Forms import Application as WinFormsApp
from System.Windows.Forms import ColorDialog, DialogResult
from System.Windows.Markup import XamlReader
from System.Windows.Media import BrushConverter, Brushes

import System

from Autodesk.Revit.DB import (
    FilteredElementCollector, ElementId, ViewSchedule
)
from System.Collections.Generic import List

from pyrevit import forms

from Snippets.views._view3d_helpers import find_3d_view, compute_bounding_box, set_section_box

from pf_models import ValueItem, NomeItem
from pf_managers import StateManager, PresetManager
from pf_helpers import get_id_value, sanitize_view_name, nome_unico, get_param_value, get_discipline
from pf_core import (
    get_categories, get_categories_from_elements,
    get_parameters, get_values, scan_view_filters,
    get_schedule_templates, get_categories_with_schedules,
    duplicar_e_filtrar, get_param_guid, filter_nonempty_params,
    validar_filtros_schedule
)
from pf_xaml import XAML_MAIN, XAML_LEGEND, XAML_CONFIRM
from pf_actions import (
    apply_colors, reset_colors, create_view_filters, create_legend
)


# ============================================================================
# LEGEND CONFIG DIALOG
# ============================================================================

FRAC_VALUES = {0: 0.25, 1: 0.5, 2: 0.75, 3: 0.875, 4: 1.0, 5: 1.25, 6: 1.5, 7: 2.0}
SPACING_VALUES = {0: 0.125, 1: 0.25, 2: 0.375, 3: 0.5, 4: 1.0, 5: 1.5, 6: 2.0}
TITLE_SPACING_VALUES = {0: 0.5, 1: 0.75, 2: 1.0, 3: 1.25, 4: 1.5, 5: 2.0}
BORDER_BOTTOM_VALUES = {0: 0.25, 1: 0.5, 2: 0.75, 3: 0.875, 4: 1.0, 5: 1.25, 6: 1.5, 7: 2.0}


class LegendConfigWindow(object):
    def __init__(self, callback, items_count):
        self.callback = callback
        stream = MemoryStream(Encoding.UTF8.GetBytes(XAML_LEGEND))
        self.window = XamlReader.Load(stream)

        self.txtTitle = self.window.FindName("txtTitle")
        self.cmbWidth = self.window.FindName("cmbWidth")
        self.cmbHeight = self.window.FindName("cmbHeight")
        self.cmbOffset = self.window.FindName("cmbOffset")
        self.cmbSpacing = self.window.FindName("cmbSpacing")
        self.cmbTitleSpacing = self.window.FindName("cmbTitleSpacing")
        self.cmbBorderOffset = self.window.FindName("cmbBorderOffset")
        self.cmbBorderBottom = self.window.FindName("cmbBorderBottom")
        self.chkShowCount = self.window.FindName("chkShowCount")
        self.rbOrderOriginal = self.window.FindName("rbOrderOriginal")
        self.rbOrderAlpha = self.window.FindName("rbOrderAlpha")
        self.rbOrderCount = self.window.FindName("rbOrderCount")
        self.btnCreate = self.window.FindName("btnCreate")
        self.btnCancel = self.window.FindName("btnCancel")

        self._load_state()

        self.btnCreate.Click += self._on_create
        self.btnCancel.Click += self._on_cancel

    def _load_state(self):
        try:
            state = StateManager.load()
            ls = state.get("legend_config", {})
            if ls:
                if "width_idx" in ls: self.cmbWidth.SelectedIndex = ls["width_idx"]
                if "height_idx" in ls: self.cmbHeight.SelectedIndex = ls["height_idx"]
                if "offset_idx" in ls: self.cmbOffset.SelectedIndex = ls["offset_idx"]
                if "spacing_idx" in ls: self.cmbSpacing.SelectedIndex = ls["spacing_idx"]
                if "title_spacing_idx" in ls: self.cmbTitleSpacing.SelectedIndex = ls["title_spacing_idx"]
                if "border_offset_idx" in ls: self.cmbBorderOffset.SelectedIndex = ls["border_offset_idx"]
                if "border_bottom_idx" in ls: self.cmbBorderBottom.SelectedIndex = ls["border_bottom_idx"]
                if "show_count" in ls: self.chkShowCount.IsChecked = ls["show_count"]
                order = ls.get("order", "original")
                if order == "alpha": self.rbOrderAlpha.IsChecked = True
                elif order == "count": self.rbOrderCount.IsChecked = True
        except:
            pass

    def ShowDialog(self):
        return self.window.ShowDialog()

    def Close(self):
        try: self.window.Close()
        except: pass

    def _on_create(self, sender, args):
        try:
            config = {
                "title": self.txtTitle.Text,
                "width": FRAC_VALUES[self.cmbWidth.SelectedIndex],
                "height": FRAC_VALUES[self.cmbHeight.SelectedIndex],
                "offset": SPACING_VALUES[self.cmbOffset.SelectedIndex],
                "spacing": SPACING_VALUES[self.cmbSpacing.SelectedIndex],
                "title_spacing": TITLE_SPACING_VALUES[self.cmbTitleSpacing.SelectedIndex],
                "border_offset": FRAC_VALUES[self.cmbBorderOffset.SelectedIndex],
                "border_bottom": BORDER_BOTTOM_VALUES[self.cmbBorderBottom.SelectedIndex],
                "show_count": self.chkShowCount.IsChecked,
                "order": "original" if self.rbOrderOriginal.IsChecked else ("alpha" if self.rbOrderAlpha.IsChecked else "count")
            }
            try:
                state = StateManager.load()
                state["legend_config"] = {
                    "width_idx": self.cmbWidth.SelectedIndex,
                    "height_idx": self.cmbHeight.SelectedIndex,
                    "offset_idx": self.cmbOffset.SelectedIndex,
                    "spacing_idx": self.cmbSpacing.SelectedIndex,
                    "title_spacing_idx": self.cmbTitleSpacing.SelectedIndex,
                    "border_offset_idx": self.cmbBorderOffset.SelectedIndex,
                    "border_bottom_idx": self.cmbBorderBottom.SelectedIndex,
                    "show_count": config["show_count"],
                    "order": config["order"]
                }
                StateManager.save(state)
            except:
                pass
            self.callback(config)
            self.window.Close()
        except Exception as e:
            forms.alert("Erro: {}".format(str(e)))

    def _on_cancel(self, sender, args):
        self.window.Close()


# ============================================================================
# CONFIRM DIALOG (SCHEDULES)
# ============================================================================

class ConfirmDialog(Window):
    def __init__(self, plano_items):
        self._items = plano_items
        self.plano_final = None

        self.Title = "Confirmar criacao de schedules"
        n = len(plano_items)
        self.Height = max(350, min(140 + n * 36 + 80, 620))
        self.Width = 780
        self.WindowStartupLocation = WindowStartupLocation.CenterScreen
        self.ResizeMode = ResizeMode.CanResize
        self.Background = BrushConverter().ConvertFrom("#FFFFFF")

        stream = MemoryStream(Encoding.UTF8.GetBytes(XAML_CONFIRM))
        self.Content = XamlReader.Load(stream)

        self.lblHeader = self.Content.FindName("lblHeader")
        self.itemsList = self.Content.FindName("itemsList")
        self.btnConfirmar = self.Content.FindName("btnConfirmar")
        self.btnCancelar = self.Content.FindName("btnCancelar")

        self.lblHeader.Text = "Criar {} schedule{}".format(n, "s" if n != 1 else "")

        col = ObservableCollection[object]()
        for item in plano_items:
            col.Add(item)
        self.itemsList.ItemsSource = col

        self.btnConfirmar.Click += self._on_confirmar
        self.btnCancelar.Click += self._on_cancelar

    def _on_confirmar(self, sender, args):
        self.plano_final = [item for item in self._items if item.IsChecked]
        self.Close()

    def _on_cancelar(self, sender, args):
        self.Close()


# ============================================================================
# MAIN WINDOW
# ============================================================================

class ParamForgeWindow(Window):
    def __init__(self, doc, uidoc, rvt_year, ef_transaction):
        self.doc = doc
        self.uidoc = uidoc
        self.rvt_year = rvt_year
        self.ef_transaction = ef_transaction
        self.resultado = None
        self._sel_elements = []
        self._mode = "vista"

        self.Title = "ParamForge"
        self.Height = 680
        self.Width = 1050
        self.MinWidth = 850
        self.MinHeight = 550
        self.WindowStartupLocation = WindowStartupLocation.CenterScreen
        self.ResizeMode = ResizeMode.CanResize
        self.Background = BrushConverter().ConvertFrom("#F9FAFB")

        self.type_cache = {}
        self.existing_filters_cache = scan_view_filters(doc)
        self._schedule_cat_map = get_categories_with_schedules(doc)

        stream = MemoryStream(Encoding.UTF8.GetBytes(XAML_MAIN))
        self.Content = XamlReader.Load(stream)

        # Controls - Mode
        self.btnModoSelecao = self.Content.FindName("btnModoSelecao")
        self.btnModoVista = self.Content.FindName("btnModoVista")
        self.btnModoProjeto = self.Content.FindName("btnModoProjeto")

        # Controls - Config
        self.lbCategories = self.Content.FindName("lbCategories")
        self.lbParameters = self.Content.FindName("lbParameters")
        self.chkDiscArch = self.Content.FindName("chkDiscArch")
        self.chkDiscStruct = self.Content.FindName("chkDiscStruct")
        self.chkDiscMech = self.Content.FindName("chkDiscMech")
        self.chkDiscElec = self.Content.FindName("chkDiscElec")
        self.chkDiscPipe = self.Content.FindName("chkDiscPipe")
        self.txtCatSearch = self.Content.FindName("txtCatSearch")
        self.txtSearch = self.Content.FindName("txtSearch")
        self.txtStatus = self.Content.FindName("txtStatus")

        # Controls - Values
        self.lvValues = self.Content.FindName("lvValues")
        self.btnSelectAll = self.Content.FindName("btnSelectAll")
        self.btnDeselectAll = self.Content.FindName("btnDeselectAll")
        self.btnRandom = self.Content.FindName("btnRandom")
        self.btnGradient = self.Content.FindName("btnGradient")
        self.btnSavePreset = self.Content.FindName("btnSavePreset")
        self.btnLoadPreset = self.Content.FindName("btnLoadPreset")
        self.btnReset = self.Content.FindName("btnReset")

        # Controls - Visualizar
        self.btnApply = self.Content.FindName("btnApply")
        self.btnResetCores = self.Content.FindName("btnResetCores")
        self.btnFilters = self.Content.FindName("btnFilters")
        self.btnLegend = self.Content.FindName("btnLegend")
        self.chkAllViews = self.Content.FindName("chkAllViews")

        # Controls - Documentar
        self.pnlTemplates = self.Content.FindName("pnlTemplates")
        self.chkVerTodos = self.Content.FindName("chkVerTodos")
        self.txtPrefix = self.Content.FindName("txtPrefix")
        self.btnCreateSchedules = self.Content.FindName("btnCreateSchedules")

        # Controls - Preview
        self.btnPreviewSel = self.Content.FindName("btnPreviewSel")
        self.btnPreviewIso = self.Content.FindName("btnPreviewIso")
        self.btnPreview3D = self.Content.FindName("btnPreview3D")

        # Template combos/checks: {cat_name: ComboBox/CheckBox}
        self._template_combos = {}
        self._template_checks = {}

        # Persistent selections (survives search filtering)
        self._selected_params = set()
        self._selected_cat_names = set()
        self._updating_params = False
        self._suppress_cat_events = False

        # All items (unfiltered)
        self.all_params = []
        self.all_categories = []
        self._all_cat_dict = {}  # {name: Category}

        # Events - Mode
        self.btnModoSelecao.Click += self._on_modo_selecao
        self.btnModoVista.Click += self._on_modo_vista
        self.btnModoProjeto.Click += self._on_modo_projeto

        # Events - Config (discipline checkboxes)
        for chk in [self.chkDiscArch, self.chkDiscStruct, self.chkDiscMech,
                     self.chkDiscElec, self.chkDiscPipe]:
            chk.Checked += self._on_discipline_changed
            chk.Unchecked += self._on_discipline_changed
        self.lbCategories.SelectionChanged += self._on_cat_changed
        self.lbParameters.SelectionChanged += self._on_param_changed
        self.txtCatSearch.GotFocus += self._on_cat_search_focus
        self.txtCatSearch.TextChanged += self._on_cat_search_changed
        self.txtSearch.GotFocus += self._on_search_focus
        self.txtSearch.TextChanged += self._on_search_changed

        # Events - Values
        self.btnSelectAll.Click += self._on_select_all
        self.btnDeselectAll.Click += self._on_deselect_all
        self.btnRandom.Click += self._on_random
        self.btnGradient.Click += self._on_gradient
        self.lvValues.MouseDoubleClick += self._on_value_dblclick
        self.btnSavePreset.Click += self._on_save_preset
        self.btnLoadPreset.Click += self._on_load_preset
        self.btnReset.Click += self._on_reset_preset

        # Events - Visualizar
        self.btnApply.Click += self._on_apply
        self.btnResetCores.Click += self._on_reset_cores
        self.btnFilters.Click += self._on_create_filters
        self.btnLegend.Click += self._on_open_legend

        # Events - Documentar
        self.chkVerTodos.Checked += self._on_ver_todos_changed
        self.chkVerTodos.Unchecked += self._on_ver_todos_changed
        self.btnCreateSchedules.Click += self._on_create_schedules

        # Events - Preview
        self.btnPreviewSel.Click += self._on_preview_sel
        self.btnPreviewIso.Click += self._on_preview_iso
        self.btnPreview3D.Click += self._on_preview_3d

        # Events - Window
        self.Closing += self._on_closing

        # Data
        self.current_values = ObservableCollection[object]()
        self.lvValues.ItemsSource = self.current_values
        self.saved_state = StateManager.load()

        # Init
        self._style_mode_buttons("vista")
        self._populate_categories()
        self._restore_state()

    # -----------------------------------------------------------------------
    # HELPERS
    # -----------------------------------------------------------------------

    def _bring_to_front(self):
        """Traz janela para frente apos dialogs."""
        try:
            self.Activate()
            self.Topmost = True
            self.Topmost = False
        except:
            pass

    def _get_selected_cats(self):
        """Retorna lista de Category objects selecionados (persistente)."""
        return [self._all_cat_dict[n] for n in self._selected_cat_names
                if n in self._all_cat_dict]

    # -----------------------------------------------------------------------
    # MODE SELECTION
    # -----------------------------------------------------------------------

    def _on_modo_selecao(self, sender, args):
        self.resultado = "__RESELECT__"
        self.Close()

    def _on_modo_vista(self, sender, args):
        self._sel_elements = []
        self._mode = "vista"
        self._style_mode_buttons("vista")
        self._selected_cat_names.clear()
        self._selected_params.clear()
        self._populate_categories()

    def _on_modo_projeto(self, sender, args):
        self._sel_elements = []
        self._mode = "projeto"
        self._style_mode_buttons("projeto")
        self._selected_cat_names.clear()
        self._selected_params.clear()
        self._populate_categories()

    def _style_mode_buttons(self, modo):
        _c = BrushConverter()
        _act_bg = _c.ConvertFrom("#7C3AED")
        _act_fg = _c.ConvertFrom("#FFFFFF")
        _inact_bg = _c.ConvertFrom("#FFFFFF")
        _inact_fg = _c.ConvertFrom("#374151")
        _inact_bd = _c.ConvertFrom("#D1D5DB")
        _t0 = Thickness(0)
        _t1 = Thickness(1)

        buttons = [self.btnModoSelecao, self.btnModoVista, self.btnModoProjeto]
        modes = ["selecao", "vista", "projeto"]

        for btn, m in zip(buttons, modes):
            if m == modo:
                btn.Background = _act_bg
                btn.Foreground = _act_fg
                btn.BorderThickness = _t0
            else:
                btn.Background = _inact_bg
                btn.Foreground = _inact_fg
                btn.BorderBrush = _inact_bd
                btn.BorderThickness = _t1

    def set_selection(self, elements):
        """Chamado pelo main() apos selecao."""
        self._sel_elements = elements
        self._mode = "selecao"
        n = len(elements)

        if n > 0:
            self._style_mode_buttons("selecao")
            cats = get_categories_from_elements(elements)
            self.all_categories = cats
            self._all_cat_dict = {c.Name: c for c in cats}
            self._selected_cat_names = set(c.Name for c in cats)
            # Aplicar filtro de disciplina e restaurar selecao
            self._filter_categories()
            self._update_params()
            self._update_templates()
            self.txtStatus.Text = "{} elementos, {} categorias.".format(n, len(cats))

    # -----------------------------------------------------------------------
    # CATEGORIES
    # -----------------------------------------------------------------------

    def _get_active_view_id(self):
        if self._mode == "vista":
            return self.doc.ActiveView.Id
        return None

    def _populate_categories(self):
        cats = get_categories(self.doc, self._get_active_view_id())
        self.all_categories = cats
        self._all_cat_dict = {c.Name: c for c in cats}
        self.lbParameters.ItemsSource = None
        self.current_values.Clear()
        self.all_params = []
        self._selected_params.clear()
        # Aplicar filtro de disciplina + busca
        self._filter_categories()
        self.txtStatus.Text = "{} categorias.".format(len(cats))

    def _get_active_disciplines(self):
        """Retorna set de disciplinas ativas (checkboxes marcadas)."""
        active = set()
        if self.chkDiscArch.IsChecked: active.add("Architecture")
        if self.chkDiscStruct.IsChecked: active.add("Structure")
        if self.chkDiscMech.IsChecked: active.add("Mechanical")
        if self.chkDiscElec.IsChecked: active.add("Electrical")
        if self.chkDiscPipe.IsChecked: active.add("Piping")
        return active

    def _filter_categories(self):
        """Filtra categorias por disciplinas + texto de busca."""
        active_discs = self._get_active_disciplines()
        text = self.txtCatSearch.Text.lower()
        has_text = text and text != "buscar categoria..."

        items = self.all_categories
        if len(active_discs) < 5:
            items = [c for c in items if get_discipline(c) in active_discs]
        if has_text:
            items = [c for c in items if text in c.Name.lower()]

        self._suppress_cat_events = True
        self.lbCategories.ItemsSource = items
        for c in items:
            if c.Name in self._selected_cat_names:
                self.lbCategories.SelectedItems.Add(c)
        self._suppress_cat_events = False

    def _on_discipline_changed(self, sender, args):
        self._filter_categories()

    def _on_cat_search_focus(self, sender, args):
        if self.txtCatSearch.Text == "Buscar categoria...":
            self.txtCatSearch.Text = ""
            self.txtCatSearch.Foreground = Brushes.Black

    def _on_cat_search_changed(self, sender, args):
        self._filter_categories()

    def _on_cat_changed(self, sender, args):
        if self._suppress_cat_events:
            return
        # Atualizar selecao persistente
        current_visible = set()
        if self.lbCategories.ItemsSource:
            for c in self.lbCategories.Items:
                current_visible.add(c.Name)
        current_selected = set(c.Name for c in self.lbCategories.SelectedItems)
        for name in current_visible:
            if name in current_selected:
                self._selected_cat_names.add(name)
            else:
                self._selected_cat_names.discard(name)

        self._update_params()
        self._update_templates()
        if self._selected_params:
            self._update_values()

    # -----------------------------------------------------------------------
    # PARAMETERS
    # -----------------------------------------------------------------------

    def _update_params(self):
        selected_cats = self._get_selected_cats()
        if not selected_cats:
            self.lbParameters.ItemsSource = None
            self.all_params = []
            return

        self.txtStatus.Text = "Analisando parametros..."
        WinFormsApp.DoEvents()

        elems = self._sel_elements if self._mode == "selecao" and self._sel_elements else None
        raw_params = get_parameters(
            self.doc, selected_cats, self._get_active_view_id(), self.type_cache,
            elements=elems)

        # Filtrar params que so tem <Vazio>
        self.all_params = filter_nonempty_params(
            self.doc, selected_cats, raw_params,
            self._get_active_view_id(), self.type_cache,
            elements=elems)

        # Preservar selecao valida
        valid_params = set(self.all_params)
        self._selected_params = self._selected_params.intersection(valid_params)

        self._updating_params = True
        self.lbParameters.ItemsSource = self.all_params
        for p in self.all_params:
            if p in self._selected_params:
                self.lbParameters.SelectedItems.Add(p)
        self._updating_params = False

        self.txtStatus.Text = "{} parametros.".format(len(self.all_params))

    def _on_search_focus(self, sender, args):
        if self.txtSearch.Text == "Buscar...":
            self.txtSearch.Text = ""
            self.txtSearch.Foreground = Brushes.Black

    def _on_search_changed(self, sender, args):
        text = self.txtSearch.Text.lower()
        if not text or text == "buscar...":
            items = self.all_params
        else:
            items = [p for p in self.all_params if text in p.lower()]

        self._updating_params = True
        self.lbParameters.ItemsSource = items
        for p in items:
            if p in self._selected_params:
                self.lbParameters.SelectedItems.Add(p)
        self._updating_params = False

    def _on_param_changed(self, sender, args):
        if self._updating_params:
            return
        # Atualizar selecao persistente
        current_visible = set()
        if self.lbParameters.ItemsSource:
            for p in self.lbParameters.Items:
                current_visible.add(p)
        current_selected = set(self.lbParameters.SelectedItems)
        for p in current_visible:
            if p in current_selected:
                self._selected_params.add(p)
            else:
                self._selected_params.discard(p)

        self._update_values()

    # -----------------------------------------------------------------------
    # VALUES
    # -----------------------------------------------------------------------

    def _update_values(self):
        selected_params = sorted(list(self._selected_params))
        if not selected_params:
            self.current_values.Clear()
            return

        selected_cats = self._get_selected_cats()
        if not selected_cats:
            self.current_values.Clear()
            return

        self.current_values.Clear()
        self.txtStatus.Text = "Lendo valores..."
        WinFormsApp.DoEvents()

        elems = self._sel_elements if self._mode == "selecao" and self._sel_elements else None
        values_map = get_values(
            self.doc, selected_cats, selected_params,
            self._get_active_view_id(), self.type_cache,
            elements=elems)

        saved_colors = self.saved_state.get("colors", {})
        saved_checked = self.saved_state.get("checked", {})

        for key in sorted(values_map.keys()):
            r, g, b = None, None, None
            is_checked = saved_checked.get(key, False)

            if key in saved_colors:
                r, g, b = saved_colors[key]
            else:
                p_names_str = "_".join(selected_params)
                safe_val = "".join([c for c in key if c.isalnum() or c in (' ', '_', '-')])
                expected = "{} = {}".format(p_names_str, safe_val)
                if expected in self.existing_filters_cache:
                    r, g, b = self.existing_filters_cache[expected]

            self.current_values.Add(ValueItem(key, values_map[key], r, g, b, is_checked))

        self.txtStatus.Text = "{} valores.".format(len(self.current_values))

    def _get_checked_items(self):
        return [item for item in self.current_values if item.IsChecked]

    def _get_checked_ids(self):
        ids = []
        for item in self.current_values:
            if item.IsChecked:
                ids.extend(item.ElementIds)
        return ids

    # -----------------------------------------------------------------------
    # VALUE CONTROLS
    # -----------------------------------------------------------------------

    def _on_select_all(self, sender, args):
        for item in self.current_values:
            item.IsChecked = True
        self.lvValues.Items.Refresh()

    def _on_deselect_all(self, sender, args):
        for item in self.current_values:
            item.IsChecked = False
        self.lvValues.Items.Refresh()

    def _on_random(self, sender, args):
        for item in self.current_values:
            item.R = random.randint(50, 240)
            item.G = random.randint(50, 240)
            item.B = random.randint(50, 240)
            item.UpdateBrush()
        self.lvValues.Items.Refresh()

    def _on_gradient(self, sender, args):
        if len(self.current_values) < 2:
            return
        steps = len(self.current_values)
        sR, sG, sB = 65, 105, 225
        eR, eG, eB = 220, 20, 60
        for i, item in enumerate(self.current_values):
            r = float(i) / (steps - 1)
            item.R = int(sR + (eR - sR) * r)
            item.G = int(sG + (eG - sG) * r)
            item.B = int(sB + (eB - sB) * r)
            item.UpdateBrush()
        self.lvValues.Items.Refresh()

    def _on_value_dblclick(self, sender, args):
        if self.lvValues.SelectedItem:
            item = self.lvValues.SelectedItem
            try:
                cd = ColorDialog()
                cd.Color = System.Drawing.Color.FromArgb(item.R, item.G, item.B)
                if cd.ShowDialog() == DialogResult.OK:
                    item.R, item.G, item.B = cd.Color.R, cd.Color.G, cd.Color.B
                    item.UpdateBrush()
                    self.lvValues.Items.Refresh()
            except:
                pass
            self._bring_to_front()

    # -----------------------------------------------------------------------
    # PRESETS
    # -----------------------------------------------------------------------

    def _on_save_preset(self, sender, args):
        if not self.current_values:
            return
        name = forms.ask_for_string(prompt="Nome do preset:", title="Salvar Preset", default="Meu Preset")
        self._bring_to_front()
        if not name:
            return
        colors_data = {}
        for item in self.current_values:
            colors_data[item.Value] = (item.R, item.G, item.B)
        if PresetManager.save_preset(name, colors_data):
            self.txtStatus.Text = "Preset '{}' salvo.".format(name)

    def _on_load_preset(self, sender, args):
        if not self.current_values:
            return
        presets = PresetManager.list_presets()
        if not presets:
            forms.alert("Nenhum preset salvo.", exitscript=False)
            self._bring_to_front()
            return
        options = presets + ["Deletar preset..."]
        selected = forms.CommandSwitchWindow.show(options, message="Selecione preset:")
        self._bring_to_front()
        if not selected:
            return
        if selected == "Deletar preset...":
            to_del = forms.CommandSwitchWindow.show(presets, message="Deletar qual?")
            self._bring_to_front()
            if to_del:
                PresetManager.delete_preset(to_del)
                self.txtStatus.Text = "Preset '{}' deletado.".format(to_del)
            return
        colors_data = PresetManager.load_preset(selected)
        if not colors_data:
            return
        applied = 0
        for item in self.current_values:
            if item.Value in colors_data:
                r, g, b = colors_data[item.Value]
                item.R, item.G, item.B = int(r), int(g), int(b)
                item.UpdateBrush()
                applied += 1
        self.lvValues.Items.Refresh()
        self.txtStatus.Text = "Preset '{}': {}/{} cores.".format(selected, applied, len(self.current_values))

    def _on_reset_preset(self, sender, args):
        """Restaura cores do state salvo ou gera novas aleatorias."""
        saved_colors = self.saved_state.get("colors", {})
        for item in self.current_values:
            if item.Value in saved_colors:
                item.R, item.G, item.B = [int(c) for c in saved_colors[item.Value]]
            else:
                item.R = random.randint(50, 240)
                item.G = random.randint(50, 240)
                item.B = random.randint(50, 240)
            item.UpdateBrush()
        self.lvValues.Items.Refresh()

    # -----------------------------------------------------------------------
    # VISUALIZAR
    # -----------------------------------------------------------------------

    def _on_apply(self, sender, args):
        checked = self._get_checked_items()
        if not checked:
            forms.alert("Nenhum valor marcado!", exitscript=False)
            self._bring_to_front()
            return
        all_views = bool(self.chkAllViews.IsChecked)
        msg = apply_colors(self.doc, self.uidoc, checked, self.ef_transaction, all_views)
        self.txtStatus.Text = msg

    def _on_reset_cores(self, sender, args):
        selected_cats = self._get_selected_cats()
        all_views = bool(self.chkAllViews.IsChecked)
        msg = reset_colors(self.doc, self.uidoc, self.current_values,
                           selected_cats, self.ef_transaction, all_views)
        self.txtStatus.Text = msg

    def _on_create_filters(self, sender, args):
        checked = self._get_checked_items()
        if not checked:
            forms.alert("Nenhum valor marcado!", exitscript=False)
            self._bring_to_front()
            return
        selected_params = sorted(list(self._selected_params))
        selected_cats = self._get_selected_cats()
        if not selected_params or not selected_cats:
            forms.alert("Selecione categorias e parametros.", exitscript=False)
            self._bring_to_front()
            return
        all_views = bool(self.chkAllViews.IsChecked)
        msg = create_view_filters(
            self.doc, self.uidoc, checked, selected_params,
            selected_cats, all_views, self.rvt_year, self.ef_transaction)
        self.txtStatus.Text = msg

    def _on_open_legend(self, sender, args):
        checked = self._get_checked_items()
        if not checked:
            forms.alert("Nenhum valor marcado!", exitscript=False)
            self._bring_to_front()
            return

        def callback(config):
            msg = create_legend(self.doc, self.uidoc, list(checked), config, self.ef_transaction)
            self.txtStatus.Text = msg
            if "criada" in msg.lower():
                try:
                    self.Close()
                except:
                    pass

        legend_win = LegendConfigWindow(callback, len(checked))
        legend_win.ShowDialog()
        self._bring_to_front()

    # -----------------------------------------------------------------------
    # DOCUMENTAR
    # -----------------------------------------------------------------------

    def _update_templates(self):
        self.pnlTemplates.Children.Clear()
        self._template_combos = {}
        self._template_checks = {}

        selected_cats = self._get_selected_cats()
        if not selected_cats:
            return

        ver_todos = bool(self.chkVerTodos.IsChecked)
        all_schedules = None
        if ver_todos:
            all_schedules = get_schedule_templates(self.doc)

        for cat in selected_cats:
            cat_name = cat.Name
            cat_id_val = get_id_value(cat.Id)

            # Header row: CheckBox + label
            row = StackPanel()
            row.Orientation = Orientation.Horizontal
            row.Margin = Thickness(0, 2, 0, 1)

            chk = WpfCheckBox()
            chk.IsChecked = True
            chk.VerticalAlignment = System.Windows.VerticalAlignment.Center
            chk.Margin = Thickness(0, 0, 4, 0)

            label = TextBlock()
            label.Text = "{}:".format(cat_name)
            label.FontSize = 10
            label.Foreground = BrushConverter().ConvertFrom("#6B7280")
            label.VerticalAlignment = System.Windows.VerticalAlignment.Center

            row.Children.Add(chk)
            row.Children.Add(label)

            cmb = ComboBox()
            cmb.Height = 22
            cmb.FontSize = 10
            cmb.Margin = Thickness(0, 0, 0, 4)

            if ver_todos:
                schedules = all_schedules
            else:
                schedules = self._schedule_cat_map.get(cat_id_val, [])
                if not schedules:
                    if all_schedules is None:
                        all_schedules = get_schedule_templates(self.doc)
                    schedules = all_schedules

            for s in schedules:
                cmb.Items.Add(s.Name)
            if cmb.Items.Count > 0:
                cmb.SelectedIndex = 0

            self.pnlTemplates.Children.Add(row)
            self.pnlTemplates.Children.Add(cmb)
            self._template_combos[cat_name] = cmb
            self._template_checks[cat_name] = chk

    def _on_ver_todos_changed(self, sender, args):
        self._update_templates()

    def _on_create_schedules(self, sender, args):
        checked = self._get_checked_items()
        if not checked:
            forms.alert("Nenhum valor marcado!", exitscript=False)
            self._bring_to_front()
            return

        selected_params = sorted(list(self._selected_params))
        if not selected_params:
            forms.alert("Selecione parametros.", exitscript=False)
            self._bring_to_front()
            return

        selected_cats = self._get_selected_cats()
        if not selected_cats:
            forms.alert("Selecione categorias.", exitscript=False)
            self._bring_to_front()
            return

        # Verificar templates (somente categorias marcadas)
        templates_por_cat = {}
        all_schedules_list = list(FilteredElementCollector(self.doc).OfClass(ViewSchedule))
        enabled_cats = []
        for cat in selected_cats:
            cat_name = cat.Name
            chk = self._template_checks.get(cat_name)
            if chk and not chk.IsChecked:
                continue  # skip unchecked categories
            enabled_cats.append(cat)
            cmb = self._template_combos.get(cat_name)
            if not cmb or cmb.SelectedItem is None:
                forms.alert("Template para '{}' nao selecionado.".format(cat_name), exitscript=False)
                self._bring_to_front()
                return
            template_name = str(cmb.SelectedItem)
            template = None
            for s in all_schedules_list:
                try:
                    if not s.IsTemplate and s.Name == template_name:
                        template = s
                        break
                except:
                    continue
            if not template:
                forms.alert("Template '{}' nao encontrado.".format(template_name), exitscript=False)
                self._bring_to_front()
                return
            templates_por_cat[cat_name] = template

        if not enabled_cats:
            forms.alert("Nenhuma categoria habilitada.", exitscript=False)
            self._bring_to_front()
            return

        # GUIDs
        first_elem = self.doc.GetElement(checked[0].ElementIds[0])
        if not first_elem:
            forms.alert("Elemento de referencia nao encontrado. Atualize os valores.", exitscript=False)
            self._bring_to_front()
            return
        prefix = self.txtPrefix.Text.strip() if self.txtPrefix.Text else ""

        # Validar quais parametros podem ser filtrados no schedule
        # Usar primeiro template disponivel para teste
        first_template = list(templates_por_cat.values())[0]
        test_infos = []
        for p_name in selected_params:
            p = first_elem.LookupParameter(p_name)
            if not p:
                try:
                    p = self.doc.GetElement(first_elem.GetTypeId()).LookupParameter(p_name)
                except:
                    pass
            guid = get_param_guid(self.doc, p) if p else None
            storage = p.StorageType if p else None
            test_infos.append({"nome": p_name, "guid": guid, "valor": "test", "storage_type": storage})

        filtraveis, nao_filtraveis = validar_filtros_schedule(
            self.doc, first_template, test_infos, self.ef_transaction)

        if nao_filtraveis:
            msg = "Parametros nao suportados como filtro de schedule:\n\n"
            for nf in nao_filtraveis:
                msg += "  - {}\n".format(nf)
            if filtraveis:
                msg += "\nParametros que serao usados:\n\n"
                for f in filtraveis:
                    msg += "  - {}\n".format(f)
                msg += "\nContinuar sem os parametros nao suportados?"
                if not forms.alert(msg, yes=True, no=True, exitscript=False):
                    self._bring_to_front()
                    return
            else:
                forms.alert(msg + "\nNenhum parametro pode ser usado como filtro.", exitscript=False)
                self._bring_to_front()
                return
            # Filtrar apenas parametros validos
            selected_params = [p for p in selected_params if p in filtraveis]
        self._bring_to_front()

        # Construir plano
        plano_items = []
        for item in checked:
            val_parts = item.Value.split(" | ")
            filtro_infos = []
            for i, p_name in enumerate(selected_params):
                p = first_elem.LookupParameter(p_name)
                if not p:
                    try:
                        p = self.doc.GetElement(first_elem.GetTypeId()).LookupParameter(p_name)
                    except:
                        pass
                guid = get_param_guid(self.doc, p) if p else None
                storage = p.StorageType if p else None
                valor = val_parts[i] if i < len(val_parts) else item.Value
                filtro_infos.append({"nome": p_name, "guid": guid, "valor": valor, "storage_type": storage})

            for cat in enabled_cats:
                cat_name = cat.Name
                template = templates_por_cat.get(cat_name)
                if not template:
                    continue

                if prefix:
                    nome_base = "{} - {} - {}".format(prefix, template.Name, item.Value)
                else:
                    nome_base = "{} - {}".format(template.Name, item.Value)

                nome_proposto = nome_unico(self.doc, sanitize_view_name(nome_base))
                sched_cat = item.Value.replace(" | ", " - ")
                plano_items.append(NomeItem(
                    cat_name, item.Value, nome_proposto, template, filtro_infos, sched_cat))

        if not plano_items:
            forms.alert("Nenhum schedule configurado.", exitscript=False)
            self._bring_to_front()
            return

        confirm = ConfirmDialog(plano_items)
        confirm.ShowDialog()
        self._bring_to_front()

        if not confirm.plano_final:
            return

        # Criar schedules (apenas os marcados, com category por item)
        criados = []
        for nome_item in confirm.plano_final:
            nome_editado = nome_item.Nome.strip() or "Schedule"
            novo_nome = nome_unico(self.doc, sanitize_view_name(nome_editado))
            sched_cat = nome_item.ScheduleCategory.strip() if nome_item.ScheduleCategory else ""
            novo = duplicar_e_filtrar(
                self.doc, nome_item.Template, nome_item.FiltroInfos,
                novo_nome, sched_cat, self.ef_transaction)
            if novo:
                criados.append(novo)

        if criados:
            try:
                self.uidoc.ActiveView = criados[-1]
                self.uidoc.RefreshActiveView()
            except:
                pass
            self.txtStatus.Text = "{} schedule(s) criado(s).".format(len(criados))
        else:
            self.txtStatus.Text = "Nenhum schedule criado."

    # -----------------------------------------------------------------------
    # PREVIEW
    # -----------------------------------------------------------------------

    def _on_preview_sel(self, sender, args):
        ids = self._get_checked_ids()
        if not ids:
            forms.alert("Nenhum valor marcado!", exitscript=False)
            self._bring_to_front()
            return
        self.uidoc.Selection.SetElementIds(List[ElementId](ids))
        self.txtStatus.Text = "{} elementos selecionados.".format(len(ids))

    def _on_preview_iso(self, sender, args):
        ids = self._get_checked_ids()
        if not ids:
            forms.alert("Nenhum valor marcado!", exitscript=False)
            self._bring_to_front()
            return
        view = self.doc.ActiveView
        try:
            with self.ef_transaction(self.doc, "ParamForge: Isolar"):
                view.IsolateElementsTemporary(List[ElementId](ids))
            self.uidoc.RefreshActiveView()
            self.txtStatus.Text = "{} elementos isolados.".format(len(ids))
        except Exception as e:
            forms.alert("Erro ao isolar: {}".format(str(e)), exitscript=False)
            self._bring_to_front()

    def _on_preview_3d(self, sender, args):
        ids = self._get_checked_ids()
        if not ids:
            forms.alert("Nenhum valor marcado!", exitscript=False)
            self._bring_to_front()
            return
        view3d = find_3d_view(self.doc, self.uidoc)
        if not view3d:
            forms.alert("Nenhuma vista 3D encontrada.", exitscript=False)
            self._bring_to_front()
            return
        bbox = compute_bounding_box(self.doc, ids)
        if not bbox:
            forms.alert("Elementos sem geometria.", exitscript=False)
            self._bring_to_front()
            return
        try:
            with self.ef_transaction(self.doc, "ParamForge: Section Box 3D"):
                set_section_box(view3d, bbox)
            self.uidoc.ActiveView = view3d
            self.uidoc.RefreshActiveView()
            self.txtStatus.Text = "Section Box 3D: {} elementos.".format(len(ids))
        except Exception as e:
            forms.alert("Erro: {}".format(str(e)), exitscript=False)
            self._bring_to_front()

    # -----------------------------------------------------------------------
    # STATE
    # -----------------------------------------------------------------------

    def _restore_state(self):
        if not self.saved_state:
            return

        saved_mode = self.saved_state.get("mode", "vista")
        if saved_mode == "projeto":
            self._mode = "projeto"
            self._style_mode_buttons("projeto")
            self._populate_categories()

        saved_cats = self.saved_state.get("categories", [])
        if saved_cats:
            self._suppress_cat_events = True
            for item in self.lbCategories.Items:
                if item.Name in saved_cats:
                    self.lbCategories.SelectedItems.Add(item)
                    self._selected_cat_names.add(item.Name)
            self._suppress_cat_events = False
            self._update_params()
            self._update_templates()

        saved_params = self.saved_state.get("parameters", [])
        if saved_params:
            self._selected_params = set(p for p in saved_params if p in self.all_params)
            self._updating_params = True
            for p_name in saved_params:
                if p_name in self.all_params:
                    self.lbParameters.SelectedItems.Add(p_name)
            self._updating_params = False
            self._update_values()

    def _on_closing(self, sender, args):
        state = {
            "mode": self._mode,
            "categories": sorted(list(self._selected_cat_names)),
            "parameters": sorted(list(self._selected_params)),
            "colors": {item.Value: (item.R, item.G, item.B) for item in self.current_values},
            "checked": {item.Value: item.IsChecked for item in self.current_values}
        }
        old_state = StateManager.load()
        if "legend_config" in old_state:
            state["legend_config"] = old_state["legend_config"]
        StateManager.save(state)
