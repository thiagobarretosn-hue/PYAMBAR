# -*- coding: utf-8 -*-
"""SlabPasses — ressincronizar passes ja lancados com os tubos.

Seis acoes, escolhidas na janela, numa Transaction so (um Ctrl+Z):
    recentralizar   move o passe para o eixo do tubo na meia altura do passe
    bitola          troca o tipo WPS pela regra do papel (riser +1, aranha +2)
    familia         Watts WPS -> Concrete Sleeve (mesmo nome de tipo)
    Qtt e altura    pilha que cobre a laje do vinculo, fundo no fundo da laje
    Comments        regrava "para que serve" (Snippets._passes_papel)
    parametros      copia de novo os parametros de texto do tubo

Trabalha nos passes da laje escolhida na janela principal (nivel do passe).
O casamento passe -> tubo e o do LOG (`_passes_laje.casar`): guloso pela
menor distancia, um tubo por passe, raio de busca. Passe sem tubo nao e
tocado; no fim ele fica selecionado para conferir.

Modulo em cache no motor do pyRevit: nada de `doc` no import.
"""
import os

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, ElementId, ElementTransformUtils,
    FamilyInstance, FilteredElementCollector, LocationCurve, LocationPoint,
    RevitLinkInstance, Transaction, TransactionStatus, XYZ
)
from Autodesk.Revit.DB.Electrical import Conduit
from Autodesk.Revit.DB.Plumbing import Pipe
from System.Collections.Generic import List

from pyrevit import forms
from pyrevit.forms import WPFWindow

from Snippets._passes_laje import (
    PADRAO, arredondar, casar, eh_vertical, passe_para_tubo, polegadas_texto,
    ponto_em_z
)
from Snippets._passes_papel import (
    CONFERIR, NOMES_TUB, NOMES_VANITY, familia_do_papel, FAMILIA_ARANHA,
    passos_do_papel
)
from slp_core import (
    floor_label, write_floor, fill_editable, read_choice, riser_sources,
    LEGACY_FAMILY_NAME, PASS_FAMILY_NAMES, RISER_SOURCE_SYSTEM,
    DuplicateWarningSwallower, SlabFinder, SlabNotFound, comment_for,
    ensure_wps_family_loaded, family_types, fit_sleeve_to_slab,
    get_available_parameters, inherit_text_params, load_options,
    make_pipe_data, save_options, stacks, write_comment
)

XAML_PATH = os.path.join(os.path.dirname(__file__), 'SlabPassesSync.xaml')

RAIO_POL = PADRAO['raio']          # 12" — busca do tubo em volta do passe
MOVE_MIN_POL = 1.0 / 64            # abaixo disso e ruido de modelagem
_Z_TOL = 0.01                      # pes


def _id_value(eid):
    return eid.Value if hasattr(eid, 'Value') else eid.IntegerValue


def _type_name(symbol):
    return symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()

# ============================================================================
# COLETA
# ============================================================================
def _as_pass(fi):
    """Passe = acessorio com `Size Diameter` no tipo (o criterio do LOG).

    O Concrete Sleeve monta a pilha com a Watts ANINHADA (shared): cada pilha
    traz Qtt subcomponentes que o collector devolve como passes soltos
    (medido 06/10/2026). Subcomponente nao e passe.
    """
    if not isinstance(fi, FamilyInstance) or fi.SuperComponent is not None:
        return None
    if fi.Symbol.LookupParameter('Size Diameter') is None:
        return None
    loc = fi.Location
    box = fi.get_BoundingBox(None)
    if not isinstance(loc, LocationPoint) or box is None:
        return None
    return {'id': _id_value(fi.Id), 'elem': fi, 'x': loc.Point.X, 'y': loc.Point.Y,
            'zmin': box.Min.Z, 'zmax': box.Max.Z}


def collect_passes(doc, level):
    """Os passes (sem subcomponentes) do nivel da laje escolhida."""
    collector = FilteredElementCollector(doc)\
        .OfCategory(BuiltInCategory.OST_PipeAccessory)\
        .OfClass(FamilyInstance)
    return [p for p in (_as_pass(fi) for fi in collector)
            if p and p['elem'].LevelId == level.Id]


def _vertical_pipes_in(document, origin, transform, z_values):
    pipes = []
    for cls in (Pipe, Conduit):
        for elem in FilteredElementCollector(document).OfClass(cls):
            loc = elem.Location
            if not isinstance(loc, LocationCurve):
                continue
            a = loc.Curve.GetEndPoint(0)
            b = loc.Curve.GetEndPoint(1)
            if transform is not None:
                a, b = transform.OfPoint(a), transform.OfPoint(b)
            p0, p1 = (a.X, a.Y, a.Z), (b.X, b.Y, b.Z)
            if not eh_vertical(p0, p1):
                continue
            lo, hi = min(a.Z, b.Z) - _Z_TOL, max(a.Z, b.Z) + _Z_TOL
            if not any(lo <= z <= hi for z in z_values):
                continue        # nao cruza a meia altura de nenhum passe
            pipes.append({'id': len(pipes), 'p0': p0, 'p1': p1, 'elem': elem,
                          'transform': transform, 'origem': origin})
    return pipes


def collect_vertical_pipes(doc, passes):
    """Tubos/conduits verticais do projeto e dos vinculos carregados."""
    z_values = sorted(set(round((p['zmin'] + p['zmax']) / 2.0, 3) for p in passes))
    pipes = _vertical_pipes_in(doc, u'', None, z_values)
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        link_doc = link.GetLinkDocument()
        if link_doc is None:
            continue
        pipes.extend(_vertical_pipes_in(link_doc, link_doc.Title,
                                        link.GetTotalTransform(), z_values))
    for i, pipe in enumerate(pipes):
        pipe['id'] = i          # indice unico para o casamento
    return pipes

# ============================================================================
# PLANO
# ============================================================================
class SyncItem(object):
    def __init__(self, pass_dict, p_data, desvio_pol, target_xy, has_slab):
        self.Pass = pass_dict
        self.Fitting = pass_dict['elem']
        self.PipeData = p_data
        self.DesvioPol = desvio_pol
        self.TargetXY = target_xy
        self.HasSlab = has_slab
        self.CurrentType = _type_name(self.Fitting.Symbol)
        family = self.Fitting.Symbol.FamilyName
        self.IsWps = family in PASS_FAMILY_NAMES
        self.IsLegacy = family == LEGACY_FAMILY_NAME
        self.NewType = passe_para_tubo(p_data.DiameterInches,
                                       passos_do_papel(p_data.Papel))
        comment = self.Fitting.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        self.CurrentComment = (comment.AsString() or u'') if comment else u''

    @property
    def needs_move(self):
        return arredondar(self.DesvioPol) > MOVE_MIN_POL

    def wanted_type_name(self, actions):
        return self.NewType if actions.get('size') else self.CurrentType

    def target_symbol(self, actions, wps_types, legacy_types):
        """O tipo que o passe deve ter com as acoes marcadas (None = fica)."""
        if not self.IsWps:
            return None
        to_new_family = not self.IsLegacy or actions.get('family')
        symbol = (wps_types if to_new_family else legacy_types).get(
            self.wanted_type_name(actions))
        if symbol is None or symbol.Id == self.Fitting.Symbol.Id:
            return None
        return symbol

    def will_stack(self, actions):
        """Depois das trocas, a familia empilha (Concrete Sleeve)?"""
        if self.IsLegacy:
            return bool(actions.get('family'))
        return stacks(self.Fitting)


def build_plan(passes, pipes, finder):
    """-> ([SyncItem], [passe sem tubo])."""
    pairs = casar(passes, pipes, RAIO_POL)
    matched_pipes = [pipes[i]['elem'] for i, _ in pairs.values()]
    available_params = get_available_parameters(matched_pipes)

    items, unmatched = [], []
    for pass_dict in passes:
        if pass_dict['id'] not in pairs:
            unmatched.append(pass_dict)
            continue
        index, desvio = pairs[pass_dict['id']]
        pipe = pipes[index]
        p_data = make_pipe_data(pipe['elem'], pipe['transform'], available_params)
        z = (pass_dict['zmin'] + pass_dict['zmax']) / 2.0
        target_xy = ponto_em_z(pipe, z)
        fitting = pass_dict['elem']
        level = fitting.Document.GetElement(fitting.LevelId)
        has_slab = finder.slab_at(pass_dict['x'], pass_dict['y'], level.Elevation) is not None
        items.append(SyncItem(pass_dict, p_data, desvio, target_xy, has_slab))
    return items, unmatched

# ============================================================================
# JANELA
# ============================================================================
class SyncWindow(WPFWindow):
    def __init__(self, items, unmatched, level, wps_types, legacy_types,
                 available_params):
        self.items = items
        self.unmatched = unmatched
        self.level = level
        self.wps_types = wps_types or {}
        self.legacy_types = legacy_types
        self.available_params = available_params
        self.options = load_options()
        self.actions = {}

        WPFWindow.__init__(self, XAML_PATH)
        self.setup_ui()
        for control in (self.chk_move, self.chk_size, self.chk_family, self.chk_slab,
                        self.chk_comments, self.chk_params):
            control.Checked += self.refresh
            control.Unchecked += self.refresh
        for combo in (self.combo_riser_source, self.combo_tub, self.combo_vanity):
            combo.SelectionChanged += self.refresh
            combo.LostFocus += self.refresh          # texto digitado
        self.btn_apply.Click += self.apply
        self.btn_cancel.Click += self.cancel
        self.refresh(None, None)

    def setup_ui(self):
        fill_editable(self.combo_riser_source, riser_sources(self.available_params),
                      self.options['riser_source'])
        fill_editable(self.combo_tub, list(NOMES_TUB), self.options['nome_tub'])
        fill_editable(self.combo_vanity, list(NOMES_VANITY), self.options['nome_vanity'])

        aranha = sum(1 for it in self.items
                     if familia_do_papel(it.PipeData.Papel) == FAMILIA_ARANHA)
        conferir = sum(1 for it in self.items if it.PipeData.Papel == CONFERIR)
        lines = [
            u"Passes na laje {} ({}): {}".format(self.level.Name, floor_label(self.level),
                                                len(self.items) + len(self.unmatched)),
            u"Com tubo (raio {}): {}  —  riser {}, aranha {}".format(
                polegadas_texto(RAIO_POL), len(self.items), len(self.items) - aranha, aranha),
            u"Sem tubo: {} (não serão tocados; ficam selecionados no fim)".format(len(self.unmatched)),
        ]
        if conferir:
            lines.append(u"Aranha sem peça reconhecida no pé: {} (Comments não gravado)".format(conferir))
        legacy = sum(1 for it in self.items if it.IsLegacy)
        lines.append(u"Família antiga (Watts WPS): {}".format(legacy))
        if not self.wps_types:
            lines.append(u"Concrete Sleeve não disponível: bitola, família e Qtt desligados")
            for control in (self.chk_size, self.chk_family, self.chk_slab):
                control.IsChecked = False
                control.IsEnabled = False
        self.txt_summary.Text = u"\n".join(lines)

    def _read_options(self):
        source, typed = read_choice(self.combo_riser_source, RISER_SOURCE_SYSTEM)
        self.options['riser_source'] = source
        self.options['riser_is_text'] = typed
        self.options['nome_tub'] = read_choice(self.combo_tub, NOMES_TUB[0])[0]
        self.options['nome_vanity'] = read_choice(self.combo_vanity, NOMES_VANITY[0])[0]
        self.actions = {
            'move': bool(self.chk_move.IsChecked),
            'size': bool(self.chk_size.IsChecked),
            'family': bool(self.chk_family.IsChecked),
            'slab': bool(self.chk_slab.IsChecked),
            'comments': bool(self.chk_comments.IsChecked),
            'params': bool(self.chk_params.IsChecked),
        }

    def refresh(self, sender, args):
        self._read_options()
        moves = [it for it in self.items if it.needs_move]
        types = [it for it in self.items
                 if it.target_symbol(self.actions, self.wps_types, self.legacy_types)]
        missing = set(it.wanted_type_name(self.actions) for it in self.items
                      if it.IsWps and (not it.IsLegacy or self.actions['family'])
                      and it.wanted_type_name(self.actions) not in self.wps_types)
        stacking = [it for it in self.items if it.will_stack(self.actions)]
        comments = 0
        for it in self.items:
            text = comment_for(it.PipeData, self.options)
            if text and text != it.CurrentComment:
                comments += 1
        not_wps = sum(1 for it in self.items if not it.IsWps)
        biggest = max([it.DesvioPol for it in moves] or [0.0])

        lines = []
        if self.actions['move']:
            lines.append(u"Recentralizar: {} passes (maior desvio {})".format(
                len(moves), polegadas_texto(arredondar(biggest))))
        if self.actions['size'] or self.actions['family']:
            text = u"Tipo/família: {} trocas".format(len(types))
            if self.actions['family']:
                text += u" (Watts → Concrete Sleeve: {})".format(
                    sum(1 for it in self.items if it.IsLegacy))
            if not_wps:
                text += u" — {} passes de outra família ficam como estão".format(not_wps)
            if missing:
                text += u" — tipo não carregado: {}".format(u", ".join(sorted(missing)))
            lines.append(text)
        if self.actions['slab']:
            no_slab = sum(1 for it in stacking if not it.HasSlab)
            text = u"Qtt e altura pela laje: {} passes".format(len(stacking) - no_slab)
            if no_slab:
                text += u" — sem laje na cota: {}".format(no_slab)
            if len(stacking) < len(self.items):
                text += u" — {} sem Qtt (família antiga sem troca)".format(
                    len(self.items) - len(stacking))
            lines.append(text)
        if self.actions['comments']:
            lines.append(u"Comments: {} mudam".format(comments))
        if self.actions['params']:
            lines.append(u"Parâmetros do tubo + Floor {}: nos {} passes com tubo".format(
                floor_label(self.level), len(self.items)))
        self.txt_preview.Text = u"\n".join(lines) or u"Nenhuma ação marcada."

    def apply(self, sender, args):
        self._read_options()
        if not any(self.actions.values()):
            forms.alert(u"Marque ao menos uma ação.")
            return
        save_options(self.options)
        self.DialogResult = True
        self.Close()

    def cancel(self, sender, args):
        self.DialogResult = False
        self.Close()

# ============================================================================
# APLICAR
# ============================================================================
def apply_plan(doc, items, actions, options, wps_types, legacy_types, floor_text):
    counts = {'move': 0, 'size': 0, 'slab': 0, 'no_slab': 0, 'comments': 0, 'params': 0}
    finder = SlabFinder(doc) if actions['slab'] else None
    errors = []

    def fail(item, what, error):
        errors.append(u"{} #{}: {}".format(what, item.Pass['id'], error))

    t = Transaction(doc, u"Slab Passes v6.0 - Ressincronizar passes")
    fail_opt = t.GetFailureHandlingOptions()
    fail_opt.SetFailuresPreprocessor(DuplicateWarningSwallower())
    t.SetFailureHandlingOptions(fail_opt)
    t.Start()
    try:
        for item in items:
            fitting = item.Fitting
            if actions['move'] and item.needs_move and item.TargetXY:
                try:
                    delta = XYZ(item.TargetXY[0] - item.Pass['x'],
                                item.TargetXY[1] - item.Pass['y'], 0)
                    ElementTransformUtils.MoveElement(doc, fitting.Id, delta)
                    counts['move'] += 1
                except Exception as e:
                    fail(item, u"Mover", e)

            if actions['size'] or actions['family']:
                symbol = item.target_symbol(actions, wps_types, legacy_types)
                if symbol is not None:
                    try:
                        if not symbol.IsActive:
                            symbol.Activate()
                            doc.Regenerate()
                        # devolve InvalidElementId quando o Revit recusa, sem excecao
                        if fitting.ChangeTypeId(symbol.Id) == ElementId.InvalidElementId:
                            fail(item, u"Tipo", u"o Revit não trocou para {}".format(
                                item.wanted_type_name(actions)))
                        else:
                            counts['size'] += 1
                    except Exception as e:
                        fail(item, u"Tipo", e)

            # depois da troca: a familia nova empilha, o offset mudou com o tipo
            if finder is not None and stacks(fitting):
                try:
                    fit_sleeve_to_slab(doc, fitting, finder)
                    counts['slab'] += 1
                except SlabNotFound:
                    counts['no_slab'] += 1
                except Exception as e:
                    fail(item, u"Qtt/altura", e)

            if actions['params']:
                try:
                    inherit_text_params(fitting, item.PipeData)
                    write_floor(fitting, floor_text)     # depois da heranca: o Floor e da laje
                    counts['params'] += 1
                except Exception as e:
                    fail(item, u"Parâmetros", e)

            # depois da heranca: o Comments do passe e o papel, nao o do tubo
            if actions['comments']:
                text = comment_for(item.PipeData, options)
                if text:
                    try:
                        if write_comment(fitting, text):
                            counts['comments'] += 1
                    except Exception as e:
                        fail(item, u"Comments", e)
        status = t.Commit()
    except Exception:
        t.RollBack()
        raise
    return counts, errors, status


def run(doc, uidoc, level):
    passes = collect_passes(doc, level)
    if not passes:
        forms.alert(u"Nenhum passe (acessório com 'Size Diameter') no nível {}.".format(level.Name),
                    title=u"Slab Passes — Ressincronizar")
        return

    with forms.ProgressBar(title=u"Lendo tubos do projeto e dos vínculos...") as pb:
        pb.update_progress(1, 3)
        pipes = collect_vertical_pipes(doc, passes)
        pb.update_progress(2, 3)
        items, unmatched = build_plan(passes, pipes, SlabFinder(doc))
        pb.update_progress(3, 3)

    wps_types = ensure_wps_family_loaded(doc, forms.alert)
    legacy_types = family_types(doc, LEGACY_FAMILY_NAME)
    available_params = get_available_parameters([it.PipeData.Element for it in items])

    window = SyncWindow(items, unmatched, level, wps_types, legacy_types,
                        available_params)
    if not window.ShowDialog():
        return

    counts, errors, status = apply_plan(doc, items, window.actions, window.options,
                                        wps_types or {}, legacy_types, floor_label(level))
    if status != TransactionStatus.Committed:
        forms.alert(u"O Revit não confirmou a Transaction ({}): nada foi gravado.".format(status),
                    title=u"Slab Passes v6.0 — Ressincronizar", warn_icon=True)
        return

    lines = []
    if window.actions['move']:
        lines.append(u"Recentralizados: {}".format(counts['move']))
    if window.actions['size'] or window.actions['family']:
        lines.append(u"Tipo/família trocados: {}".format(counts['size']))
    if window.actions['slab']:
        lines.append(u"Qtt e altura pela laje: {}{}".format(
            counts['slab'], u" — sem laje na cota: {}".format(counts['no_slab'])
            if counts['no_slab'] else u""))
    if window.actions['comments']:
        lines.append(u"Comments gravados: {}".format(counts['comments']))
    if window.actions['params']:
        lines.append(u"Parâmetros copiados: {}".format(counts['params']))
    if unmatched:
        ids = List[ElementId]([p['elem'].Id for p in unmatched])
        uidoc.Selection.SetElementIds(ids)
        lines.append(u"Sem tubo (selecionados agora): {}".format(len(unmatched)))
    if errors:
        lines.append(u"Erros: {} — {}".format(len(errors), errors[0]))
    forms.alert(u"\n".join(lines), title=u"Slab Passes v6.0 — Ressincronizar",
                warn_icon=bool(errors))
