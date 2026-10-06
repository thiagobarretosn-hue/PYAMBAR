# -*- coding: utf-8 -*-
__title__ = "Slab\nPasses"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "6.0"
__doc__ = """
Slab Passes - Passagens de Laje v6.0

WORKFLOW:
1. Execute: a janela abre direto
2. Escolha a laje (nivel) e as origens (projeto e/ou vinculos)
3. Os tubos e conduits que atravessam a laje sao detectados e agrupados
   por papel (Riser / Aranha) e diametro
4. Confira familia e bitola de cada grupo e clique em "Lancar passes"
   - ou "Ressincronizar" para os passes ja lancados naquela laje

FUNCIONALIDADES:
- Deteccao pela laje do vinculo estrutural: o eixo passa pela meia altura
- Papel do tubo: riser ou ponto da aranha (toilet / tub-shower / vanity-laundry)
- Bitola: riser +1, aranha +2 tamanhos WPS, minimo WPS-1 1/2 (editavel por grupo)
- Concrete Sleeve: Qtt pela espessura da laje, fundo da pilha no fundo dela
- Comments ("Riser <valor>" ou o ponto da aranha) e Floor pelo nivel (2nd)
- Protecao contra duplicidade; Pecas e Acessorios

MELHORIAS v6.0:
- Sem selecao e sem local/vinculo: escolhe a laje, a ferramenta detecta
- Origens escolhidas na janela (projeto e cada vinculo, um ou todos)
- Sem nivel de referencia e sem ajuste fino: a posicao vem da laje
- Floor pelo nivel da laje; Ressincronizar virou botao da janela

MELHORIAS v5.3:
- Ressincronizar (recentralizar, bitola, familia, Qtt, Comments, parametros)
- Concrete Sleeve como familia padrao (a Watts WPS continua reconhecida)
- Opcoes lembradas em APPDATA/pyRevit/PYAMBAR/SlabPasses
"""

import clr
import sys
import os
from collections import defaultdict

LIB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

clr.AddReference('RevitAPI')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
from Autodesk.Revit.DB import (
    BuiltInParameter, Transaction, TransactionStatus, ViewPlan, XYZ
)

from pyrevit import revit, forms
from pyrevit.forms import WPFWindow

from Snippets._passes_laje import (
    passe_para_tubo, chave_do_grupo, texto_do_grupo, ordem_do_grupo,
    polegadas_texto, tem_passe_perto
)
from Snippets._passes_papel import (
    CONFERIR, FAMILIA_ARANHA, NOMES_TUB, NOMES_VANITY, familia_do_papel
)
from slp_core import (
    WPS_FAMILY_NAME, PASS_FAMILY_NAMES, RISER_SOURCE_SYSTEM, fill_editable,
    read_choice, riser_sources,
    DuplicateWarningSwallower, SlabFinder, SlabNotFound, collect_existing_passes,
    comment_for, create_fitting_at_point, detect_crossings, ensure_wps_family_loaded,
    fit_sleeve_to_slab, floor_label, get_all_fittings_and_accessories,
    get_all_levels, get_available_parameters, inherit_text_params, list_sources,
    load_options, make_pipe_data, save_options, stacks, write_comment, write_floor
)

doc = revit.doc
uidoc = revit.uidoc
script_dir = os.path.dirname(__file__)
XAML_PATH = os.path.join(script_dir, 'SlabPasses.xaml')

# indice = quantos tamanhos WPS acima do tubo (tabela em Snippets._passes_laje);
# o padrao de cada grupo vem do papel: riser +1, aranha +2
SIZING_OPTIONS = [u"Mesma bitola", u"+1 tamanho", u"+2 tamanhos"]

ACTION_APPLY = 'apply'
ACTION_SYNC = 'sync'


def group_pipes_data(pipes_data_list, filter_param_name=None):
    """{(categoria, Ø pol, valor): [PipeData]} — chave em Snippets._passes_laje.

    A categoria leva a familia do papel ('Pipe Riser' / 'Pipe Aranha'): riser e
    aranha do mesmo Ø pedem bitolas diferentes, nao cabem no mesmo grupo."""
    grouped = defaultdict(list)
    for p_data in pipes_data_list:
        param_value = None
        if filter_param_name and filter_param_name in p_data.AllParams:
            param_value = p_data.AllParams[filter_param_name]
        categoria = u"{} {}".format(p_data.ElementType, familia_do_papel(p_data.Papel))
        group_key = chave_do_grupo(categoria, p_data.DiameterInches, param_value)
        grouped[group_key].append(p_data)
    return dict(grouped)


# ============================================================================
# JANELA
# ============================================================================
class PassesWindow(WPFWindow):

    def __init__(self, all_types_with_prefix, wps_types):
        self.all_types_with_prefix = all_types_with_prefix
        self.wps_types = wps_types
        self.options = load_options()
        self.action = None

        self.levels = get_all_levels(doc)
        self.sources = list_sources(doc)
        self.finder = SlabFinder(doc)
        self.existing_points = collect_existing_passes(doc, PASS_FAMILY_NAMES)

        self.selected_level = None
        self.crossings = []
        self.counts = {}
        self.pipes_data_list = []
        self._all_pipes = []
        self.available_params = []
        self.current_filter_param = None
        self.current_grouped_data = {}
        self.selected_fittings = {}
        self.selected_sizing = {}
        self._combo_refs = {}
        self._source_checks = {}
        self._loading = True

        WPFWindow.__init__(self, XAML_PATH)
        self.setup_ui()
        self._loading = False
        self.detect()

        self.combo_level.SelectionChanged += self.on_level_changed
        self.combo_filter.SelectionChanged += self.on_filter_changed
        self.btn_apply.Click += self.on_apply
        self.btn_sync.Click += self.on_sync
        self.btn_cancel.Click += self.on_cancel

    # ------------------------------------------------------------ montagem
    def _default_level_index(self):
        names = [lvl.Name for lvl in self.levels]
        if self.options.get('level_name') in names:
            return names.index(self.options['level_name'])
        view = doc.ActiveView
        if isinstance(view, ViewPlan) and view.GenLevel is not None and view.GenLevel.Name in names:
            return names.index(view.GenLevel.Name)
        return 0

    def setup_ui(self):
        from System.Windows.Controls import CheckBox
        from System.Windows import Thickness

        for level in self.levels:
            self.combo_level.Items.Add(level.Name)
        if self.levels:
            self.combo_level.SelectedIndex = self._default_level_index()
            self.selected_level = self.levels[self.combo_level.SelectedIndex]

        off = set(self.options.get('sources_off') or [])
        for source in self.sources:
            check = CheckBox()
            check.Content = source.Label
            check.IsChecked = source.Label not in off
            check.Margin = Thickness(0, 0, 18, 4)
            check.Tag = source.Label
            check.Checked += self.on_source_toggled
            check.Unchecked += self.on_source_toggled
            self.panel_sources.Children.Add(check)
            self._source_checks[source.Label] = check

        fill_editable(self.combo_tub, list(NOMES_TUB), self.options['nome_tub'])
        fill_editable(self.combo_vanity, list(NOMES_VANITY), self.options['nome_vanity'])
        self.chk_comments.IsChecked = bool(self.options['write_comments'])
        self.chk_fit_slab.IsChecked = bool(self.options['fit_slab'])
        self.chk_inherit_params.IsChecked = bool(self.options['inherit_params'])
        self.chk_floor.IsChecked = bool(self.options['write_floor'])

    def _checked_sources(self):
        return set(label for label, check in self._source_checks.items() if check.IsChecked)

    # ------------------------------------------------------------ deteccao
    def detect(self):
        """Le os tubos que cruzam a laje do nivel (todas as origens, uma vez)."""
        if self.selected_level is None:
            return
        self.crossings, self.counts = detect_crossings(
            self.sources, self.selected_level, self.finder, self.existing_points)
        elements = [c.Vertical['elem'] for c in self.crossings]
        self.available_params = get_available_parameters(elements)

        self._all_pipes = []
        for crossing in self.crossings:
            vertical = crossing.Vertical
            p_data = make_pipe_data(vertical['elem'], vertical['source'].Transform,
                                    self.available_params)
            if p_data is None:
                continue
            p_data.CrossXY = crossing.XY
            p_data.Slab = crossing.Slab
            p_data.SourceLabel = vertical['source'].Label
            self._all_pipes.append(p_data)

        for source in self.sources:
            self._source_checks[source.Label].Content = u"{} ({})".format(
                source.Label, self.counts.get(source.Label, 0))

        current_source = (self.combo_riser_source.Text or u'').strip() or self.options['riser_source']
        fill_editable(self.combo_riser_source, riser_sources(self.available_params), current_source)
        self._fill_filter_combo()
        self.update_slab_text()
        self.apply_source_filter()

    def _fill_filter_combo(self):
        self._loading = True
        self.combo_filter.Items.Clear()
        self.combo_filter.Items.Add(u"(Nenhum - papel e diâmetro)")
        for name in self.available_params:
            self.combo_filter.Items.Add(name)
        if self.current_filter_param in self.available_params:
            self.combo_filter.SelectedIndex = self.available_params.index(self.current_filter_param) + 1
        else:
            self.current_filter_param = None
            self.combo_filter.SelectedIndex = 0
        self._loading = False

    def apply_source_filter(self):
        checked = self._checked_sources()
        self.pipes_data_list = [p for p in self._all_pipes if p.SourceLabel in checked]
        self.render_groups()

    def update_slab_text(self):
        thicknesses = {}
        for crossing in self.crossings:
            key = round((crossing.Slab[0] - crossing.Slab[1]) * 12.0, 3)
            thicknesses[key] = thicknesses.get(key, 0) + 1
        if not thicknesses:
            self.txt_slab.Text = u"Nenhum tubo atravessa uma laje nesta cota."
            return
        parts = [u"{} ({})".format(polegadas_texto(k), n)
                 for k, n in sorted(thicknesses.items(), key=lambda kv: -kv[1])]
        self.txt_slab.Text = u"Laje: {}  —  Floor: {}".format(
            u", ".join(parts), floor_label(self.selected_level))

    def update_status(self):
        aranha = sum(1 for p in self.pipes_data_list if familia_do_papel(p.Papel) == FAMILIA_ARANHA)
        conferir = sum(1 for p in self.pipes_data_list if p.Papel == CONFERIR)
        text = u"{} tubos atravessam a laje  —  riser {}, aranha {}  |  {} grupos".format(
            len(self.pipes_data_list), len(self.pipes_data_list) - aranha, aranha,
            len(self.current_grouped_data))
        if self.counts.get('existing'):
            text += u"  |  já com passe: {}".format(self.counts['existing'])
        if self.counts.get('no_slab'):
            text += u"  |  sem laje no ponto (shaft/abertura): {}".format(self.counts['no_slab'])
        if conferir:
            text += u"  |  aranha sem peça no pé: {} (sem Comments)".format(conferir)
        if not self.wps_types:
            text += u"  |  Concrete Sleeve não carregado"
        self.status_text.Text = text

    # ------------------------------------------------------------ grupos
    def _get_display_name(self, type_elem, prefix):
        name = type_elem.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
        return u"{} {} - {}".format(prefix, type_elem.FamilyName, name)

    def _find_wps_index_in_combo(self, wps_type_name):
        for i, (type_elem, prefix) in enumerate(self.all_types_with_prefix):
            if type_elem.FamilyName == WPS_FAMILY_NAME:
                name = type_elem.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
                if name == wps_type_name:
                    return i
        return -1

    def _default_sizing(self, group_key):
        """Riser +1, aranha +2 (regra do Thiago, 05/10/2026)."""
        return 2 if FAMILIA_ARANHA in group_key[0] else 1

    def render_groups(self):
        from System.Windows.Controls import (
            StackPanel, TextBlock, ComboBox, Border, Grid, ColumnDefinition
        )
        from System.Windows import Thickness, CornerRadius, FontWeights, GridLength, GridUnitType
        from System.Windows.Media import SolidColorBrush, Color

        self.diameter_panel.Children.Clear()
        self._combo_refs = {}
        self.current_grouped_data = group_pipes_data(self.pipes_data_list, self.current_filter_param)
        self.update_status()

        if not self.current_grouped_data:
            empty = TextBlock()
            empty.Text = u"Nenhum tubo novo atravessa esta laje nas origens marcadas."
            empty.Margin = Thickness(8)
            empty.Foreground = SolidColorBrush(Color.FromRgb(120, 120, 120))
            self.diameter_panel.Children.Add(empty)
            return

        for group_key in sorted(self.current_grouped_data.keys(), key=ordem_do_grupo):
            p_data_list = self.current_grouped_data[group_key]
            if FAMILIA_ARANHA in group_key[0]:
                bg, edge = Color.FromRgb(232, 245, 233), Color.FromRgb(76, 175, 80)
            else:
                bg, edge = Color.FromRgb(227, 242, 253), Color.FromRgb(33, 150, 243)

            border = Border()
            border.Background = SolidColorBrush(bg)
            border.BorderBrush = SolidColorBrush(edge)
            border.BorderThickness = Thickness(1.5)
            border.CornerRadius = CornerRadius(5)
            border.Padding = Thickness(10)
            border.Margin = Thickness(0, 0, 0, 8)

            inner = StackPanel()
            title = TextBlock()
            title.Text = u"{}  ({} tubos)".format(texto_do_grupo(group_key), len(p_data_list))
            title.FontSize = 13
            title.FontWeight = FontWeights.Bold
            title.Margin = Thickness(0, 0, 0, 6)
            inner.Children.Add(title)

            row = Grid()
            col1 = ColumnDefinition()
            col1.Width = GridLength(1, GridUnitType.Star)
            col2 = ColumnDefinition()
            col2.Width = GridLength(150, GridUnitType.Pixel)
            row.ColumnDefinitions.Add(col1)
            row.ColumnDefinitions.Add(col2)

            combo = ComboBox()
            combo.Height = 30
            combo.Tag = group_key
            combo.Margin = Thickness(0, 0, 8, 0)
            Grid.SetColumn(combo, 0)
            if self.all_types_with_prefix:
                for type_elem, prefix in self.all_types_with_prefix:
                    combo.Items.Add(self._get_display_name(type_elem, prefix))
                chosen = self.selected_fittings.get(group_key)
                index = -1
                if chosen is not None:
                    index = next((i for i, (te, _) in enumerate(self.all_types_with_prefix)
                                  if te.Id == chosen.Id), -1)
                if index < 0 and self.wps_types:
                    sizing = self.selected_sizing.get(group_key, self._default_sizing(group_key))
                    index = self._find_wps_index_in_combo(passe_para_tubo(group_key[1], sizing))
                if index >= 0:
                    combo.SelectedIndex = index
                    self.selected_fittings[group_key] = self.all_types_with_prefix[index][0]
                combo.SelectionChanged += self.on_fitting_selected
            else:
                combo.Items.Add(u"Nenhum acessório/peça carregado")
                combo.IsEnabled = False
            self._combo_refs[group_key] = combo
            row.Children.Add(combo)

            combo_sizing = ComboBox()
            combo_sizing.Height = 30
            combo_sizing.Tag = group_key
            Grid.SetColumn(combo_sizing, 1)
            for opt in SIZING_OPTIONS:
                combo_sizing.Items.Add(opt)
            combo_sizing.SelectedIndex = self.selected_sizing.get(group_key, self._default_sizing(group_key))
            combo_sizing.SelectionChanged += self.on_sizing_changed
            if not self.wps_types:
                combo_sizing.IsEnabled = False
            row.Children.Add(combo_sizing)

            inner.Children.Add(row)
            border.Child = inner
            self.diameter_panel.Children.Add(border)

    # ------------------------------------------------------------ eventos
    def on_level_changed(self, sender, args):
        if self._loading or self.combo_level.SelectedIndex < 0:
            return
        self.selected_level = self.levels[self.combo_level.SelectedIndex]
        self.detect()

    def on_source_toggled(self, sender, args):
        if not self._loading and self.crossings is not None:
            self.apply_source_filter()

    def on_filter_changed(self, sender, args):
        if self._loading:
            return
        index = self.combo_filter.SelectedIndex
        self.current_filter_param = None if index <= 0 else self.available_params[index - 1]
        self.render_groups()

    def on_fitting_selected(self, sender, args):
        index = sender.SelectedIndex
        if 0 <= index < len(self.all_types_with_prefix):
            self.selected_fittings[sender.Tag] = self.all_types_with_prefix[index][0]

    def on_sizing_changed(self, sender, args):
        group_key = sender.Tag
        sizing = sender.SelectedIndex
        if sizing < 0 or not self.wps_types:
            return
        self.selected_sizing[group_key] = sizing
        index = self._find_wps_index_in_combo(passe_para_tubo(group_key[1], sizing))
        if index >= 0 and group_key in self._combo_refs:
            self._combo_refs[group_key].SelectedIndex = index
            self.selected_fittings[group_key] = self.all_types_with_prefix[index][0]

    def read_options(self):
        source, typed = read_choice(self.combo_riser_source, RISER_SOURCE_SYSTEM)
        self.options['riser_source'] = source
        self.options['riser_is_text'] = typed
        self.options['nome_tub'] = read_choice(self.combo_tub, NOMES_TUB[0])[0]
        self.options['nome_vanity'] = read_choice(self.combo_vanity, NOMES_VANITY[0])[0]
        self.options['write_comments'] = bool(self.chk_comments.IsChecked)
        self.options['fit_slab'] = bool(self.chk_fit_slab.IsChecked)
        self.options['inherit_params'] = bool(self.chk_inherit_params.IsChecked)
        self.options['write_floor'] = bool(self.chk_floor.IsChecked)
        self.options['level_name'] = self.selected_level.Name if self.selected_level else u''
        self.options['sources_off'] = [label for label, check in self._source_checks.items()
                                       if not check.IsChecked]
        save_options(self.options)

    def on_apply(self, sender, args):
        if not any(key in self.selected_fittings for key in self.current_grouped_data):
            forms.alert(u"Nenhum grupo com acessório/peça escolhido.")
            return
        self.read_options()
        self.action = ACTION_APPLY
        self.DialogResult = True
        self.Close()

    def on_sync(self, sender, args):
        if self.selected_level is None:
            return
        self.read_options()
        self.action = ACTION_SYNC
        self.DialogResult = True
        self.Close()

    def on_cancel(self, sender, args):
        self.DialogResult = False
        self.Close()


# ============================================================================
# LANCAR
# ============================================================================
def apply_passes(window):
    level = window.selected_level
    top_z = level.Elevation
    options = window.options
    floor_text = floor_label(level)
    jobs = [(window.selected_fittings[key], p_data_list)
            for key, p_data_list in window.current_grouped_data.items()
            if key in window.selected_fittings]
    placed = collect_existing_passes(doc, set(PASS_FAMILY_NAMES) |
                                     set(fitting_type.FamilyName for fitting_type, _ in jobs))

    counts = {'created': 0, 'existing': 0, 'failed': 0, 'stack': 0, 'no_slab': 0,
              'comments': 0, 'floor': 0}
    first_error = [None]
    param_errors = []

    t = Transaction(doc, u"Slab Passes v6.0 - Lançar passes")
    fail_opt = t.GetFailureHandlingOptions()
    fail_opt.SetFailuresPreprocessor(DuplicateWarningSwallower())
    t.SetFailureHandlingOptions(fail_opt)
    t.Start()
    try:
        with forms.ProgressBar(title=u"Lançando passes... {value}/{max_value}") as pb:
            total = sum(len(p_data_list) for _, p_data_list in jobs)
            current = 0
            for fitting_type, p_data_list in jobs:
                is_pass_family = fitting_type.FamilyName in PASS_FAMILY_NAMES
                for p_data in p_data_list:
                    current += 1
                    pb.update_progress(current, total)
                    x, y = p_data.CrossXY
                    if tem_passe_perto((x, y, top_z), placed, tol_z=1.0):
                        counts['existing'] += 1
                        continue

                    fitting, error = create_fitting_at_point(doc, XYZ(x, y, top_z),
                                                             fitting_type, level, 0.0)
                    if not fitting:
                        counts['failed'] += 1
                        if first_error[0] is None:
                            first_error[0] = error
                        continue
                    placed.append((x, y, top_z))

                    # passe WPS: o tamanho e o tipo — gravar o Ø do tubo desfaria a escolha
                    if not is_pass_family:
                        try:
                            if p_data.DiameterParam:
                                target = fitting.LookupParameter(u"Diametro Nominal") or \
                                    fitting.LookupParameter("Diameter")
                                if target and not target.IsReadOnly:
                                    target.Set(p_data.DiameterParam.AsDouble())
                        except Exception as e:
                            param_errors.append(u"Diâmetro: {}".format(e))

                    if options['inherit_params']:
                        try:
                            inherit_text_params(fitting, p_data)
                        except Exception as e:
                            param_errors.append(u"Herdar parâmetros: {}".format(e))

                    # depois da heranca: Comments e Floor sao do passe, nao do tubo
                    text = comment_for(p_data, options) if options['write_comments'] else None
                    if text:
                        try:
                            write_comment(fitting, text)
                            counts['comments'] += 1
                        except Exception as e:
                            param_errors.append(u"Comments: {}".format(e))
                    if options['write_floor']:
                        try:
                            if write_floor(fitting, floor_text):
                                counts['floor'] += 1
                        except Exception as e:
                            param_errors.append(u"Floor: {}".format(e))

                    if options['fit_slab'] and stacks(fitting):
                        try:
                            fit_sleeve_to_slab(doc, fitting, window.finder)
                            counts['stack'] += 1
                        except SlabNotFound:
                            counts['no_slab'] += 1
                        except Exception as e:
                            param_errors.append(u"Qtt/altura: {}".format(e))

                    counts['created'] += 1
        status = t.Commit()
    except Exception as e:
        t.RollBack()
        forms.alert(u"Erro fatal: {}".format(e), title=u"Slab Passes v6.0", warn_icon=True)
        return

    if status != TransactionStatus.Committed:
        forms.alert(u"O Revit não confirmou a Transaction ({}): nada foi gravado.".format(status),
                    title=u"Slab Passes v6.0", warn_icon=True)
        return

    lines = [
        u"Laje {} ({})".format(level.Name, floor_text),
        u"Criados: {}  —  Comments {}, Floor {}".format(
            counts['created'], counts['comments'], counts['floor']),
        u"Qtt e altura pela laje: {}{}".format(
            counts['stack'], u" — sem laje: {}".format(counts['no_slab']) if counts['no_slab'] else u""),
    ]
    if counts['existing']:
        lines.append(u"Já existia passe no local: {}".format(counts['existing']))
    if counts['failed']:
        lines.append(u"Falharam: {} — {}".format(counts['failed'], first_error[0]))
    if param_errors:
        lines.append(u"Parâmetro não gravado: {} — {}".format(len(param_errors), param_errors[0]))
    forms.alert(u"\n".join(lines), title=u"Slab Passes v6.0",
                warn_icon=bool(counts['failed'] or param_errors))


# ============================================================================
# EXECUCAO
# ============================================================================
def main():
    """Sem sys.exit(): o pyRevit devolve Result.Cancelled ao Revit quando o
    script sai por SystemExit, e o Revit DESFAZ todas as Transactions do
    comando (ScriptCommands.cs, 05/10/2026). Toda saida aqui e `return`."""
    if not doc:
        forms.alert(u"Nenhum documento ativo!")
        return

    wps_types = ensure_wps_family_loaded(doc, forms.alert)
    all_types_with_prefix = get_all_fittings_and_accessories(doc)
    if not all_types_with_prefix:
        forms.alert(u"Nenhuma família de Peça ou Acessório carregada no projeto.")
        return

    window = PassesWindow(all_types_with_prefix, wps_types)
    if not window.ShowDialog():
        return

    if window.action == ACTION_SYNC:
        import slp_sync
        slp_sync.run(doc, uidoc, window.selected_level)
    elif window.action == ACTION_APPLY:
        apply_passes(window)


main()
