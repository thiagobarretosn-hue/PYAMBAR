# -*- coding: utf-8 -*-
"""SlabPasses — o que o lancamento e a ressincronizacao dividem.

O motor do pyRevit guarda este modulo em cache entre execucoes: nada de
`doc` no import — toda funcao que toca o modelo recebe o documento.
"""
import io
import math
import json
import os

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInFailures, BuiltInParameter, ConnectorType, Face,
    Family, FailureProcessingResult, FailureSeverity, FamilyInstance, FamilySymbol,
    FilteredElementCollector, Floor, HostObjectUtils, IFailuresPreprocessor,
    Level, LocationCurve, LocationPoint, RevitLinkInstance, StorageType,
    Transaction, XYZ
)
from Autodesk.Revit.DB.Electrical import Conduit
from Autodesk.Revit.DB.Plumbing import Pipe
from Autodesk.Revit.DB.Structure import StructuralType

from Snippets._inherit_pipe_params import EXCLUDED_PARAMS
from Snippets._passes_laje import (
    altura_pilha, eh_vertical, elevacao_pelo_fundo, laje_no_ponto, ponto_em_z, qtt_para_laje,
    tem_passe_perto
)
from Snippets._wbs_engine import auto_ordinal
from Snippets._passes_papel import (
    NOMES_TUB, NOMES_VANITY, RISER, classificar, comentario, sem_codigo
)

SCRIPT_DIR = os.path.dirname(__file__)

#: familia padrao desde 06/10/2026: passe empilhavel (Qtt) — mesmos tipos WPS-*
#: e o mesmo `Size Diameter` da Watts, entao o LOG reconhece os dois
WPS_FAMILY_NAME = "Concrete Sleeve"
WPS_RFA_PATH = os.path.join(SCRIPT_DIR, WPS_FAMILY_NAME + ".rfa")
#: a familia antiga: passes ja lancados continuam reconhecidos (e trocaveis)
LEGACY_FAMILY_NAME = "Pipe_Sleeve-Plastic-Watts-WPS_Series(AMBAR ACESSORIO)"
PASS_FAMILY_NAMES = (WPS_FAMILY_NAME, LEGACY_FAMILY_NAME)

QTT_PARAM = "Qtt"
SLEEVE_OFFSET_PARAM = "Sleeve Offset"
_SLAB_TOP_TOL = 0.1            # pes — topo da laje "na cota do nivel" (= _passes_laje._TOPO)
_SLAB_DEPTH = 4.0              # pes — ate onde descer juntando lajes encostadas

#: primeira opcao da fonte do "Riser <valor>": o system type sem o codigo
RISER_SOURCE_SYSTEM = u"Tipo de sistema (sem código)"
#: RBS_DUCT_PIPE_SYSTEM_ABBREVIATION_PARAM — medido 06/10/2026: STORM DRAIN,
#: AC DRAIN, SEWER, CW (o vent tambem e SEWER)
RISER_SOURCE_ABBREV = u"Abreviatura do sistema"

#: os parametros que a equipe mais usa (PLB.txt dos SharedParameters da Ambar,
#: 06/10/2026) — encabecam a lista do "Riser +", na ordem do arquivo
PLB_PARAMS = (
    u"Ambiente", u"PHASE", u"Room", u"Tipologia UH", u"TRADE", u"Type",
    u"Unit ID", u"Stage", u"ARN Split", u"ARN Type", u"Filter-1", u"Filter-2",
    u"Floor", u"Item Description",
)

EMPTY_MARKERS = ("(Vazio)", "(Sem parametro)", "(Erro)")

#: EXCLUDED_PARAMS usa os nomes em ingles; o Revit em portugues chama Mark e
#: Comments de outro jeito. IfcGUID copiado daria ao passe a identidade do tubo
#: (medido 05/10/2026: 73 passes do CIQ receberiam o IfcGUID do tubo).
SLP_EXCLUDED = set([u"IfcGUID", u"IFC GUID", u"Marca", u"Comentários"])

# ============================================================================
# CONFIG DO USUARIO (%APPDATA%) — nunca na pasta do script
# ============================================================================
_APPDATA_DIR = os.path.join(os.getenv('APPDATA', ''), 'pyRevit', 'PYAMBAR', 'SlabPasses')
_APPDATA_CONFIG = os.path.join(_APPDATA_DIR, 'config.json')

DEFAULT_OPTIONS = {
    'riser_source': RISER_SOURCE_SYSTEM,
    'riser_is_text': False,     # True: riser_source e texto digitado, nao parametro
    'nome_tub': NOMES_TUB[0],
    'nome_vanity': NOMES_VANITY[0],
    'write_comments': True,
    'write_floor': True,
    'fit_slab': True,
    'inherit_params': True,
    'level_name': u'',
    'sources_off': [],          # rotulos das origens desmarcadas
}


def load_options():
    options = dict(DEFAULT_OPTIONS)
    if os.path.exists(_APPDATA_CONFIG):
        try:
            with io.open(_APPDATA_CONFIG, 'r', encoding='utf-8') as f:
                options.update(json.load(f))
        except Exception:
            pass        # config corrompida: segue com o padrao
    return options


def save_options(options):
    if not os.path.exists(_APPDATA_DIR):
        os.makedirs(_APPDATA_DIR)
    with io.open(_APPDATA_CONFIG, 'w', encoding='utf-8') as f:
        f.write(json.dumps(options, indent=2, ensure_ascii=False))

# ============================================================================
# AVISOS
# ============================================================================
_DUPLICATE_GUID = BuiltInFailures.OverlapFailures.DuplicateInstances.Guid


class DuplicateWarningSwallower(IFailuresPreprocessor):
    """Apaga so o warning de instancia duplicada — os outros chegam ao usuario."""
    def PreprocessFailures(self, failuresAccessor):
        failures = failuresAccessor.GetFailureMessages()
        for f in failures:
            if f.GetSeverity() == FailureSeverity.Warning and \
                    f.GetFailureDefinitionId().Guid == _DUPLICATE_GUID:
                failuresAccessor.DeleteWarning(f)
        return FailureProcessingResult.Continue

# ============================================================================
# PARAMETROS DO TUBO
# ============================================================================
def get_element_diameter_inches(elem, element_type):
    param_id = (BuiltInParameter.RBS_PIPE_DIAMETER_PARAM if element_type == "Pipe"
                else BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM)
    diameter_param = elem.get_Parameter(param_id)
    return diameter_param.AsDouble() * 12.0 if diameter_param else 0.0


def get_available_parameters(elements):
    """Nomes dos parametros candidatos, unidos de UM elemento por (modelo, classe).

    Ate 06/10/2026 lia so o primeiro tubo: com a deteccao pela laje o primeiro
    vinha do vinculo MIIIQLUX-MEC, sem os parametros PLB — e os 98 passes do L3
    nasceram sem PHASE/TRADE/Unit ID. Cada vinculo tem o seu jogo de parametros.
    """
    if not elements:
        return []

    representatives = {}
    for elem in elements:
        if not isinstance(elem, (Pipe, Conduit)):
            continue
        key = (elem.Document.PathName or elem.Document.Title, isinstance(elem, Pipe))
        if key not in representatives:
            representatives[key] = elem

    system_params = [
        "Family", "Type", "Comments", "Mark", "Diameter",
        "Level", "Reference Level", "Top Offset", "Bottom Offset",
        "System Classification", "System Type", "System Name",
        "Workset", "Design Option", "Phase Created", "Phase Demolished"
    ]

    all_param_names = set()
    for first_elem in representatives.values():
        for param in first_elem.Parameters:
            param_name = param.Definition.Name
            if param_name in system_params:
                continue
            if param.IsShared:
                all_param_names.add(param_name)
            elif not param.IsReadOnly and (param.AsString() or param.AsValueString()):
                all_param_names.add(param_name)

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
    except Exception:
        return "(Erro)"


def clean_value(value):
    return u'' if not value or value in EMPTY_MARKERS else value


def system_type_of(elem):
    """Nome do system type do tubo ('' em conduit ou sem sistema)."""
    param = elem.get_Parameter(BuiltInParameter.RBS_PIPING_SYSTEM_TYPE_PARAM)
    return (param.AsValueString() or u'') if param else u''


def foot_family_of(elem):
    """FamilyName da peca no conector de BAIXO do tubo — o ponto da aranha.

    Medido 05/10/2026: closet bend / P-Trap / elbow no pe; Cap ou aberto em
    cima. Le conectores de vinculo sem problema.
    """
    if not isinstance(elem, Pipe):
        return None
    ends = [c for c in elem.ConnectorManager.Connectors
            if c.ConnectorType == ConnectorType.End]
    if not ends:
        return None
    lowest = min(ends, key=lambda c: c.Origin.Z)
    for ref in lowest.AllRefs:
        if ref.Owner.Id == elem.Id or ref.ConnectorType == ConnectorType.Logical:
            continue
        if isinstance(ref.Owner, FamilyInstance):
            return ref.Owner.Symbol.FamilyName
    return None

# ============================================================================
# TUBO PROCESSADO
# ============================================================================
class PipeData:
    def __init__(self, pipe_element, p0_host, p1_host, diameter_param,
                 diameter_inches, all_params_dict, element_type,
                 system_type, foot_family):
        self.Element = pipe_element
        self.P0 = p0_host            # extremos do eixo, coordenadas do projeto
        self.P1 = p1_host
        self.DiameterParam = diameter_param
        self.DiameterInches = diameter_inches
        self.AllParams = all_params_dict
        self.ElementType = element_type  # "Pipe" ou "Conduit"
        self.SystemType = system_type
        self.FootFamily = foot_family
        self.Papel = classificar(system_type, foot_family) \
            if element_type == "Pipe" else RISER

    def point_at_z(self, z):
        """(x, y) do eixo na cota z; None se o tubo nao chega la."""
        tubo = {'p0': (self.P0.X, self.P0.Y, self.P0.Z),
                'p1': (self.P1.X, self.P1.Y, self.P1.Z)}
        return ponto_em_z(tubo, z)


def make_pipe_data(elem, transform, available_params):
    location = elem.Location
    if not isinstance(location, LocationCurve):
        return None
    curve = location.Curve
    p0 = curve.GetEndPoint(0)
    p1 = curve.GetEndPoint(1)
    if transform is not None:
        p0 = transform.OfPoint(p0)
        p1 = transform.OfPoint(p1)

    element_type = "Conduit" if isinstance(elem, Conduit) else "Pipe"
    param_id = (BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM if element_type == "Conduit"
                else BuiltInParameter.RBS_PIPE_DIAMETER_PARAM)
    diameter_param = elem.get_Parameter(param_id)
    diameter_inches = get_element_diameter_inches(elem, element_type)

    params_dict = {}
    for param_name in available_params:
        params_dict[param_name] = get_parameter_value(elem, param_name)

    return PipeData(elem, p0, p1, diameter_param, diameter_inches,
                    params_dict, element_type,
                    system_type_of(elem) if element_type == "Pipe" else u'',
                    foot_family_of(elem))

# ============================================================================
# COMMENTS E HERANCA
# ============================================================================
def riser_sources(available_params):
    """Opcoes do "Riser +": o padrao (tipo de sistema) e o resto em ordem
    alfabetica — abreviatura, os PLB e os parametros dos tubos."""
    others = set([RISER_SOURCE_ABBREV]) | set(PLB_PARAMS) | set(available_params)
    others.discard(RISER_SOURCE_SYSTEM)
    return [RISER_SOURCE_SYSTEM] + sorted(others, key=lambda name: name.lower())


def riser_value(p_data, riser_source, is_text=False):
    if is_text:
        return riser_source         # digitado pelo usuario: vai como esta
    if riser_source == RISER_SOURCE_SYSTEM:
        return sem_codigo(p_data.SystemType)
    if riser_source == RISER_SOURCE_ABBREV:
        param = p_data.Element.get_Parameter(BuiltInParameter.RBS_DUCT_PIPE_SYSTEM_ABBREVIATION_PARAM)
        return (param.AsString() or u'') if param else u''
    return clean_value(get_parameter_value(p_data.Element, riser_source))


def comment_for(p_data, options):
    """Texto do Comments do passe; None quando o papel nao e certo (CONFERIR)."""
    return comentario(p_data.Papel,
                      riser_value(p_data, options['riser_source'],
                                  options.get('riser_is_text', False)),
                      options['nome_tub'], options['nome_vanity'])


# ---- combos editaveis: escolher da lista OU digitar (Thiago, 06/10/2026)
def fill_editable(combo, items, current):
    """Preenche e mostra `current` — da lista ou texto digitado antes."""
    combo.Items.Clear()
    for item in items:
        combo.Items.Add(item)
    if current in items:
        combo.SelectedIndex = list(items).index(current)
    else:
        combo.SelectedIndex = -1
        combo.Text = current or u''


def read_choice(combo, default):
    """-> (valor, digitado). Texto que nao e item da lista = digitado."""
    text = (combo.Text or u'').strip()
    if not text:
        return default, False
    items = [combo.Items[i] for i in range(combo.Items.Count)]
    return text, text not in items


def write_comment(fitting, text):
    """True se gravou. Erro sobe para quem chamou contar."""
    param = fitting.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    if param is None or param.IsReadOnly:
        raise Exception(u"Comments somente leitura")
    if (param.AsString() or u'') == text:
        return False
    param.Set(text)
    return True


def _writable_text_param(element, name):
    """O parametro de texto gravavel com esse nome; o compartilhado tem a vez
    (no Revit em ingles, 'Type' tambem e o tipo da familia)."""
    found = None
    for param in element.GetParameters(name):
        if param.IsReadOnly or param.StorageType != StorageType.String:
            continue
        if param.IsShared:
            return param
        found = found or param
    return found


def inherit_text_params(fitting, p_data):
    """Copia os parametros de texto do tubo para o passe. -> quantos mudaram.

    EXCLUDED_PARAMS fala dos parametros internos ('Type' = tipo da familia,
    'Comments'...): parametro COMPARTILHADO com o mesmo nome passa — o 'Type'
    do PLB (ex.: 1BD#07_R) nunca era herdado (06/10/2026).
    """
    changed = 0
    for pname, pval in p_data.AllParams.items():
        if pname in SLP_EXCLUDED or not clean_value(pval):
            continue
        tgt = _writable_text_param(fitting, pname)
        if tgt is None or (pname in EXCLUDED_PARAMS and not tgt.IsShared):
            continue
        if (tgt.AsString() or u'') != pval:
            tgt.Set(pval)
            changed += 1
    return changed

# ============================================================================
# FAMILIAS E MODELO
# ============================================================================
def collect_existing_passes(doc, family_names):
    """(x, y, z) dos passes ja no projeto — so das familias escolhidas, uma vez."""
    points = []
    for cat in [BuiltInCategory.OST_PipeAccessory, BuiltInCategory.OST_PipeFitting]:
        collector = FilteredElementCollector(doc)\
            .OfCategory(cat)\
            .OfClass(FamilyInstance)
        for inst in collector:
            if inst.SuperComponent is not None or inst.Symbol.FamilyName not in family_names:
                continue
            loc = inst.Location
            if isinstance(loc, LocationPoint):
                points.append((loc.Point.X, loc.Point.Y, loc.Point.Z))
    return points


def get_all_fittings_and_accessories(doc):
    """Todos os tipos de Pecas (PipeFitting) E Acessorios (PipeAccessory)."""
    all_types = []
    categories = [
        (BuiltInCategory.OST_PipeAccessory, u"[Acessorio]"),
        (BuiltInCategory.OST_PipeFitting, u"[Peca]"),
    ]
    for cat, prefix in categories:
        collector = FilteredElementCollector(doc)\
            .OfCategory(cat)\
            .WhereElementIsElementType()
        for type_elem in collector:
            all_types.append((type_elem, prefix))

    all_types.sort(key=lambda x: (
        x[0].FamilyName,
        x[0].get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
    ))
    return all_types


def get_all_levels(doc):
    collector = FilteredElementCollector(doc)\
        .OfClass(Level)\
        .WhereElementIsNotElementType()
    return sorted(collector, key=lambda x: x.Elevation)


def ensure_wps_family_loaded(doc, alert):
    """Verifica/carrega a familia WPS. -> {type_name: FamilySymbol} ou None."""
    wps_family = None
    for fam in FilteredElementCollector(doc).OfClass(Family):
        if getattr(fam, 'Name', '') == WPS_FAMILY_NAME:
            wps_family = fam
            break

    if not wps_family:
        if not os.path.exists(WPS_RFA_PATH):
            alert(u"Arquivo .rfa nao encontrado: {}".format(WPS_RFA_PATH))
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
            alert(u"Erro ao carregar familia WPS: {}".format(e))
            return None

    if not wps_family:
        return None

    wps_types = {}
    for sid in wps_family.GetFamilySymbolIds():
        symbol = doc.GetElement(sid)
        if symbol:
            type_name = symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
            wps_types[type_name] = symbol
    return wps_types


def create_fitting_at_point(doc, placement_point, fitting_type, level, elevation_offset):
    """Cria acessorio/peca no ponto. Devolve (instancia, None) ou (None, erro)."""
    try:
        if not fitting_type.IsActive:
            fitting_type.Activate()
            doc.Regenerate()

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
                param_elevation.Set(placement_point.Z)

        return new_fitting, None

    except Exception as e:
        return None, str(e)

# ============================================================================
# PILHA PELA LAJE (Concrete Sleeve) — medido 06/10/2026, ver _passes_laje
# ============================================================================
class SlabNotFound(Exception):
    pass


class SlabFinder(object):
    """Lajes (Floor) do projeto e dos vinculos carregados, lidas uma vez.

    No CIQ cada passe tem 3 a 8 lajes empilhadas sob o XY (uma por pavimento):
    vale a de topo na cota do nivel do passe.
    """
    def __init__(self, doc):
        self._floors = []
        self._add(doc, None)
        for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
            link_doc = link.GetLinkDocument()
            if link_doc is not None:
                self._add(link_doc, link.GetTotalTransform())

    def _add(self, document, transform):
        inverse = transform.Inverse if transform is not None else None
        for floor in FilteredElementCollector(document).OfClass(Floor):
            box = floor.get_BoundingBox(None)
            if box is not None:
                self._floors.append((floor, transform, inverse, box))

    @staticmethod
    def _z_on(floor, transform, refs, local):
        """Z (projeto) da face sob o ponto; None se a face nao esta ali."""
        for ref in refs:
            face = floor.GetGeometryObjectFromReference(ref)
            if not isinstance(face, Face):
                continue
            proj = face.Project(local)
            if proj is None:
                continue
            p = proj.XYZPoint
            if math.hypot(p.X - local.X, p.Y - local.Y) > 0.01:
                continue
            return (transform.OfPoint(p) if transform is not None else p).Z
        return None

    def slab_at(self, x, y, top_z):
        """(topo, fundo) em pes, coordenadas do projeto; None se nao ha laje.

        Junta TODAS as lajes sob o XY ate _SLAB_DEPTH abaixo da cota e deixa
        `laje_no_ponto` decidir: a mais funda entre as de topo na cota, mais as
        encostadas embaixo (engrossamento modelado como laje separada).
        """
        point = XYZ(x, y, top_z)
        slabs = []
        for floor, transform, inverse, box in self._floors:
            local = inverse.OfPoint(point) if inverse is not None else point
            if not (box.Min.X <= local.X <= box.Max.X and box.Min.Y <= local.Y <= box.Max.Y):
                continue
            if box.Max.Z < local.Z - _SLAB_DEPTH or box.Min.Z > local.Z + _SLAB_TOP_TOL:
                continue            # laje de outro pavimento
            top = self._z_on(floor, transform, HostObjectUtils.GetTopFaces(floor), local)
            if top is None or not (top_z - _SLAB_DEPTH <= top <= top_z + _SLAB_TOP_TOL):
                continue
            bottom = self._z_on(floor, transform, HostObjectUtils.GetBottomFaces(floor), local)
            if bottom is None:
                thickness = floor.get_Parameter(BuiltInParameter.FLOOR_ATTR_THICKNESS_PARAM)
                bottom = top - thickness.AsDouble() if thickness else None
            if bottom is not None:
                slabs.append((top, bottom))
        return laje_no_ponto(slabs, top_z, _SLAB_TOP_TOL)


def stacks(fitting):
    """A familia empilha (tem Qtt e Sleeve Offset)?"""
    return fitting.LookupParameter(QTT_PARAM) is not None and \
        fitting.LookupParameter(SLEEVE_OFFSET_PARAM) is not None


def fit_sleeve_to_slab(doc, fitting, finder):
    """Qtt = o menor que cobre a laje; fundo da pilha no fundo da laje.

    -> (qtt_antes, qtt_depois). Levanta SlabNotFound sem laje na cota do nivel.
    A altura do 1o passe e lida da instancia (a familia usa 8 1/8", o spec diz
    8" em 8/10/12") — nada de numero decorado.
    """
    qtt_param = fitting.LookupParameter(QTT_PARAM)
    before = qtt_param.AsInteger()
    if before < 1:
        qtt_param.Set(1)        # Qtt 0 some com a geometria: sem caixa para medir
    doc.Regenerate()            # offset (formula) e caixa depois de criar/trocar tipo

    level = doc.GetElement(fitting.LevelId)
    point = fitting.Location.Point
    slab = finder.slab_at(point.X, point.Y, level.Elevation)
    if slab is None:
        raise SlabNotFound(u"sem laje com topo na cota de {}".format(level.Name))
    top, bottom = slab

    qtt = qtt_param.AsInteger()
    offset = fitting.LookupParameter(SLEEVE_OFFSET_PARAM).AsDouble() * 12.0
    box = fitting.get_BoundingBox(None)
    first = (box.Max.Z - box.Min.Z) * 12.0 - (qtt - 1) * offset

    new_qtt = qtt_para_laje((top - bottom) * 12.0, first, offset)
    if new_qtt != qtt:
        qtt_param.Set(new_qtt)
    elevation = elevacao_pelo_fundo(bottom, altura_pilha(new_qtt, first, offset), level.Elevation)
    fitting.get_Parameter(BuiltInParameter.INSTANCE_ELEVATION_PARAM).Set(elevation)
    return before, new_qtt


def family_types(doc, family_name):
    """{nome do tipo: FamilySymbol} de uma familia carregada ({} se nao esta)."""
    types = {}
    for symbol in FilteredElementCollector(doc).OfClass(FamilySymbol):
        if symbol.FamilyName == family_name:
            types[symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()] = symbol
    return types

# ============================================================================
# FLOOR (Thiago, 06/10/2026): o pavimento da laje, no padrao do modelo (2nd)
# ============================================================================
FLOOR_PARAM = u"Floor"


def floor_label(level):
    """'02 - LEVEL 2' -> '2nd' (o mesmo auto_ordinal do Unit Mapper e da aranha)."""
    return auto_ordinal(level.Name)


def write_floor(fitting, text):
    """True se gravou; parametro ausente ou somente leitura -> False."""
    param = fitting.LookupParameter(FLOOR_PARAM)
    if param is None or param.IsReadOnly or param.StorageType != StorageType.String:
        return False
    if (param.AsString() or u'') == text:
        return False
    param.Set(text)
    return True

# ============================================================================
# DETECCAO PELA LAJE — sem selecao: tubos e conduits verticais que cruzam a laje
# ============================================================================
_NEAR_LEVEL_BELOW = 4.0         # pes — tubo tem de chegar perto da laje para entrar na conta
_NEAR_LEVEL_ABOVE = 1.0
_SAME_AXIS = 0.1                # pes — dois trechos que se encontram na laje = um tubo


class PipeSource(object):
    """Uma origem de tubos: o projeto ou um vinculo carregado."""
    def __init__(self, label, document, transform):
        self.Label = label
        self.Document = document
        self.Transform = transform
        self._verticals = None

    def verticals(self):
        """Tubos/conduits verticais desta origem, lidos uma vez (cache)."""
        if self._verticals is None:
            self._verticals = []
            for cls in (Pipe, Conduit):
                for elem in FilteredElementCollector(self.Document).OfClass(cls):
                    loc = elem.Location
                    if not isinstance(loc, LocationCurve):
                        continue
                    a = loc.Curve.GetEndPoint(0)
                    b = loc.Curve.GetEndPoint(1)
                    if self.Transform is not None:
                        a, b = self.Transform.OfPoint(a), self.Transform.OfPoint(b)
                    p0, p1 = (a.X, a.Y, a.Z), (b.X, b.Y, b.Z)
                    if eh_vertical(p0, p1):
                        self._verticals.append({'elem': elem, 'p0': p0, 'p1': p1,
                                                'source': self})
        return self._verticals


def list_sources(doc):
    """[PipeSource] — o projeto e cada vinculo carregado (rotulo unico)."""
    sources = [PipeSource(u"Projeto", doc, None)]
    seen = {}
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        link_doc = link.GetLinkDocument()
        if link_doc is None:
            continue
        label = link_doc.Title
        seen[label] = seen.get(label, 0) + 1
        if seen[label] > 1:
            label = u"{} ({})".format(label, seen[label])
        sources.append(PipeSource(label, link_doc, link.GetTotalTransform()))
    return sources


class Crossing(object):
    """Um tubo que cruza a laje: o tubo, a laje sob ele e o XY do eixo nela."""
    def __init__(self, vertical, slab, xy):
        self.Vertical = vertical
        self.Slab = slab            # (topo, fundo) em pes
        self.XY = xy


def detect_crossings(sources, level, finder, existing_points):
    """Tubos das origens que atravessam a laje do nivel.

    -> (crossings, contagem): contagem = {origem: n, 'existing': n, 'no_slab': n}.
    Atravessa = o eixo passa pela meia altura da laje lida sob ele (o criterio
    do LOG). Sem laje no XY (shaft, abertura) nao entra: e contado.
    """
    top_z = level.Elevation
    crossings, counts, taken = [], {'existing': 0, 'no_slab': 0}, []
    for source in sources:
        counts[source.Label] = 0
        for vertical in source.verticals():
            p0, p1 = vertical['p0'], vertical['p1']
            lo, hi = min(p0[2], p1[2]), max(p0[2], p1[2])
            if hi < top_z - _NEAR_LEVEL_BELOW or lo > top_z + _NEAR_LEVEL_ABOVE:
                continue
            probe = ponto_em_z(vertical, min(max(top_z, lo), hi))
            if probe is None:
                continue
            slab = finder.slab_at(probe[0], probe[1], top_z)
            if slab is None:
                if ponto_em_z(vertical, top_z - 0.34) is not None:     # ~4": metade de laje padrao
                    counts['no_slab'] += 1
                continue
            xy = ponto_em_z(vertical, (slab[0] + slab[1]) / 2.0)
            if xy is None:
                continue        # chega na laje mas nao atravessa
            if any(abs(xy[0] - x) < _SAME_AXIS and abs(xy[1] - y) < _SAME_AXIS for x, y in taken):
                continue
            taken.append(xy)
            if tem_passe_perto((xy[0], xy[1], top_z), existing_points, tol_z=1.0):
                counts['existing'] += 1
                continue
            counts[source.Label] += 1
            crossings.append(Crossing(vertical, slab, xy))
    return crossings, counts
