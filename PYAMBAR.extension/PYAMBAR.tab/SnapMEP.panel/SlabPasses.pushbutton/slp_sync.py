# -*- coding: utf-8 -*-
"""SlabPasses — ressincronizar passes ja lancados com os tubos.

Seis acoes, escolhidas na janela, numa Transaction so (um Ctrl+Z):
    recentralizar   move o passe para o eixo do tubo na meia altura do passe —
                    ou pelos passes do nivel de baixo / de cima / o mais
                    perto dos dois, ate N pol (Snippets._passes_alinhar)
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
from Snippets._passes_alinhar import (
    BAIXO, CIMA, PERTO, PUXAR_PADRAO, TUBO, alvos, ler_polegadas, mais_proximo,
    niveis_vizinhos
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


def collect_passes_by_level(doc):
    """{id do nivel: (nivel, [passe])} — todos os passes (sem subcomponentes)."""
    by_level = {}
    collector = FilteredElementCollector(doc)\
        .OfCategory(BuiltInCategory.OST_PipeAccessory)\
        .OfClass(FamilyInstance)
    for pass_dict in (_as_pass(fi) for fi in collector):
        if pass_dict is None:
            continue
        key = _id_value(pass_dict['elem'].LevelId)
        if key not in by_level:
            by_level[key] = (doc.GetElement(pass_dict['elem'].LevelId), [])
        by_level[key][1].append(pass_dict)
    return by_level


def neighbor_passes(by_level, level):
    """((nivel, passes) de baixo, (nivel, passes) de cima) — entre os niveis
    que TEM passe; None quando nao existe."""
    by_elevation = dict((lvl.Elevation, (lvl, passes))
                        for lvl, passes in by_level.values() if lvl is not None)
    below, above = niveis_vizinhos(list(by_elevation), level.Elevation)
    return (by_elevation.get(below) if below is not None else None,
            by_elevation.get(above) if above is not None else None)


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
                 available_params, below=None, above=None):
        self.items = items
        self.unmatched = unmatched
        self.level = level
        self.all_passes = [it.Pass for it in items] + list(unmatched)
        self.below = below          # (nivel, passes) ou None
        self.above = above
        self.align = {}
        self.align_out = []
        self._refs = []
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
        self.combo_move_ref.SelectionChanged += self.refresh
        self.txt_pull.LostFocus += self.refresh
        self.btn_apply.Click += self.apply
        self.btn_cancel.Click += self.cancel
        self.refresh(None, None)

    def setup_move_refs(self):
        """Referencias do recentralizar: so as que existem neste modelo."""
        self._refs = [(TUBO, u"Eixo do tubo")]
        if self.below:
            self._refs.append((BAIXO, u"Passes do nível de baixo ({})".format(self.below[0].Name)))
        if self.above:
            self._refs.append((CIMA, u"Passes do nível de cima ({})".format(self.above[0].Name)))
        if self.below or self.above:
            self._refs.append((PERTO, u"O mais próximo (baixo ou cima)"))
        for _, label in self._refs:
            self.combo_move_ref.Items.Add(label)
        keys = [key for key, _ in self._refs]
        wanted = self.options.get('move_ref', TUBO)
        self.combo_move_ref.SelectedIndex = keys.index(wanted) if wanted in keys else 0
        self.txt_pull.Text = u"{:g}".format(self.options.get('pull_in', PUXAR_PADRAO))

    def setup_ui(self):
        self.setup_move_refs()
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
            'move_ref': self._refs[max(self.combo_move_ref.SelectedIndex, 0)][0],
            'pull': ler_polegadas(self.txt_pull.Text),
        }
        self.options['move_ref'] = self.actions['move_ref']
        self.options['pull_in'] = self.actions['pull']

    def _compute_align(self):
        ref = self.actions['move_ref']
        if not self.actions['move'] or ref == TUBO:
            self.align, self.align_out = {}, []
            return
        self.align = alvos(self.all_passes,
                           self.below[1] if self.below else None,
                           self.above[1] if self.above else None,
                           ref, self.actions['pull'])
        self.align_out = [p for p in self.all_passes if p['id'] not in self.align]

    def _align_line(self):
        ref = self.actions['move_ref']
        moving = [d for (_, _, d, _) in self.align.values() if d > MOVE_MIN_POL]
        name = {BAIXO: self.below[0].Name if self.below else u'',
                CIMA: self.above[0].Name if self.above else u'',
                PERTO: u"baixo ou cima"}[ref]
        text = u"Alinhar pelos passes de {}: {} movem (maior desvio {})".format(
            name, len(moving), polegadas_texto(arredondar(max(moving or [0.0]))))
        text += u" — já alinhados: {}".format(len(self.align) - len(moving))
        if self.align_out:
            text += u" — fora de {}: {} (não se movem; ficam selecionados)".format(
                polegadas_texto(self.actions['pull']), len(self.align_out))
        return text

    def refresh(self, sender, args):
        self._read_options()
        self._compute_align()
        self.txt_pull.IsEnabled = self.actions['move_ref'] != TUBO
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
        if self.actions['move'] and self.actions['move_ref'] == TUBO:
            lines.append(u"Recentralizar no tubo: {} passes (maior desvio {})".format(
                len(moves), polegadas_texto(arredondar(biggest))))
        elif self.actions['move']:
            lines.append(self._align_line())
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
        if not any(self.actions[key] for key in
                   ('move', 'size', 'family', 'slab', 'comments', 'params')):
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
def apply_plan(doc, items, actions, options, wps_types, legacy_types, floor_text,
               align=None, all_passes=()):
    counts = {'move': 0, 'size': 0, 'slab': 0, 'no_slab': 0, 'comments': 0, 'params': 0}
    by_tube = actions['move'] and actions.get('move_ref', TUBO) == TUBO
    finder = SlabFinder(doc) if actions['slab'] else None
    errors = []

    def fail(item, what, error):
        errors.append(u"{} #{}: {}".format(what, item.Pass['id'], error))

    t = Transaction(doc, u"Slab Passes v6.1 - Ressincronizar passes")
    fail_opt = t.GetFailureHandlingOptions()
    fail_opt.SetFailuresPreprocessor(DuplicateWarningSwallower())
    t.SetFailureHandlingOptions(fail_opt)
    t.Start()
    try:
        # pelos passes do vizinho: TODOS os passes do nivel, com ou sem tubo
        for pass_dict in all_passes:
            target = (align or {}).get(pass_dict['id'])
            if target is None or target[2] <= MOVE_MIN_POL:
                continue
            try:
                delta = XYZ(target[0] - pass_dict['x'], target[1] - pass_dict['y'], 0)
                ElementTransformUtils.MoveElement(doc, pass_dict['elem'].Id, delta)
                counts['move'] += 1
            except Exception as e:
                errors.append(u"Alinhar #{}: {}".format(pass_dict['id'], e))

        for item in items:
            fitting = item.Fitting
            if by_tube and item.needs_move and item.TargetXY:
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


# ============================================================================
# RELATORIO DAS PENDENCIAS (Thiago, 22/10/2026) — so se ele pedir no aviso final
# ============================================================================
REPORT_OPTION = u"Abrir relatório das pendências"


def _pass_info(pass_dict):
    fitting = pass_dict['elem']
    comment = fitting.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    return u"{} · {}".format(_type_name(fitting.Symbol),
                             (comment.AsString() if comment else None) or u"sem Comments")


def show_report(level, unmatched, align_out, window):
    """Janela de output com link por passe: clicar seleciona e da zoom."""
    from pyrevit import script
    output = script.get_output()
    output.set_title(u"Slab Passes — pendências {}".format(level.Name))
    out_ids = set(p['id'] for p in align_out)
    unmatched_ids = set(p['id'] for p in unmatched)
    both = out_ids & unmatched_ids

    output.print_md(u"## Pendências do Ressincronizar — {} ({})".format(
        level.Name, floor_label(level)))
    output.print_md(u"{} passes distintos (é o que ficou selecionado); {} estão nas duas listas.".format(
        len(out_ids | unmatched_ids), len(both)))

    if align_out:
        ref = window.actions['move_ref']
        output.print_md(u"### Fora de {} do nível vizinho — não foram movidos ({})".format(
            polegadas_texto(window.actions['pull']), len(align_out)))
        output.print_md(u"A referência mais próxima está longe demais para ser desvio: "
                        u"posição diferente, passe faltando no vizinho ou passe a mais aqui.")
        for pass_dict in sorted(align_out, key=lambda p: p['id']):
            near = mais_proximo(pass_dict,
                                window.below[1] if window.below else None,
                                window.above[1] if window.above else None, ref)
            line = u"- {} {}".format(output.linkify(pass_dict['elem'].Id), _pass_info(pass_dict))
            if near is not None:
                neighbor, dist, side = near
                level_name = (window.below if side == BAIXO else window.above)[0].Name
                line += u" — vizinho mais perto a **{}** em {}: {}".format(
                    polegadas_texto(arredondar(dist)), level_name,
                    output.linkify([pass_dict['elem'].Id, neighbor['elem'].Id], u"ver os dois"))
            if pass_dict['id'] in both:
                line += u" · *também sem tubo*"
            output.print_md(line)

    if unmatched:
        output.print_md(u"### Sem tubo a {} — Comments, bitola e parâmetros não atualizados ({})".format(
            polegadas_texto(RAIO_POL), len(unmatched)))
        output.print_md(u"Nenhum tubo vertical livre passa a até {} do eixo do passe: tubo "
                        u"deslocado, removido ou num vínculo descarregado.".format(polegadas_texto(RAIO_POL)))
        for pass_dict in sorted(unmatched, key=lambda p: p['id']):
            line = u"- {} {}".format(output.linkify(pass_dict['elem'].Id), _pass_info(pass_dict))
            if pass_dict['id'] in both:
                line += u" · *também fora do raio*"
            output.print_md(line)

    every = [p['elem'].Id for p in list(unmatched) + [q for q in align_out if q['id'] not in unmatched_ids]]
    output.print_md(u"---\n{}".format(output.linkify(every, u"Selecionar todas as {} pendências".format(len(every)))))


def run(doc, uidoc, level):
    by_level = collect_passes_by_level(doc)
    passes = by_level.get(_id_value(level.Id), (level, []))[1]
    below, above = neighbor_passes(by_level, level)
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
                        available_params, below, above)
    if not window.ShowDialog():
        return

    counts, errors, status = apply_plan(doc, items, window.actions, window.options,
                                        wps_types or {}, legacy_types, floor_label(level),
                                        window.align, window.all_passes)
    if status != TransactionStatus.Committed:
        forms.alert(u"O Revit não confirmou a Transaction ({}): nada foi gravado.".format(status),
                    title=u"Slab Passes v6.1 — Ressincronizar", warn_icon=True)
        return

    lines = []
    if window.actions['move']:
        lines.append(u"{}: {}".format(
            u"Recentralizados no tubo" if window.actions['move_ref'] == TUBO
            else u"Alinhados pelo nível vizinho", counts['move']))
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
    to_select = list(unmatched) + [p for p in window.align_out if p not in unmatched]
    if unmatched:
        lines.append(u"Sem tubo: {}".format(len(unmatched)))
    if window.align_out:
        lines.append(u"Fora de {} do nível vizinho (não movidos): {}".format(
            polegadas_texto(window.actions['pull']), len(window.align_out)))
    if to_select:
        uidoc.Selection.SetElementIds(List[ElementId]([p['elem'].Id for p in to_select]))
        lines.append(u"Selecionados agora (as duas listas, sem repetir): {}".format(len(to_select)))
    if errors:
        lines.append(u"Erros: {} — {}".format(len(errors), errors[0]))
    if not to_select:
        forms.alert(u"\n".join(lines), title=u"Slab Passes v6.1 — Ressincronizar",
                    warn_icon=bool(errors))
        return
    choice = forms.alert(u"\n".join(lines), title=u"Slab Passes v6.1 — Ressincronizar",
                         warn_icon=bool(errors), options=[REPORT_OPTION, u"Fechar"])
    if choice == REPORT_OPTION:
        show_report(level, unmatched, window.align_out, window)
