# -*- coding: utf-8 -*-
"""
Overhead - Aplicacao de Tags Inteligente para Tubos v2.7

Classifica tubos verticais em 4 categorias baseado em:
- Passagem por lajes (inferior/superior)
- Conexoes nas extremidades (fitting → horizontal ou vertical)

TIPO 1 - RISER DOWN: Vem laje inferior → fitting → tubo horizontal (TOP conecta horizontal)
                     OU: vem de baixo + top desconectado (none)
TIPO 2 - RISER UP+DOWN: Vem inferior → continua vertical → ultrapassa (sem horizontal)
TIPO 3 - RISER UP: Horizontal → fitting → ultrapassa superior (BOTTOM conecta horizontal)
                   OU: ultrapassa + bottom desconectado (none)
TIPO 4 - HORIZONTAL: Tubos horizontais

NOVIDADES v2.7:
- Sistema de unidades automatico (imperial/metric conforme projeto)
- Tratamento de conexoes "none" (desconectadas)
- Bottom=none + ultrapassa → RISER UP
- Top=none + vem_de_baixo → RISER DOWN

VERSAO: 2.7.0
AUTOR: Thiago Barreto Sobral Nunes
"""

__title__ = "Overhead\nTags"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "2.7.0"
__doc__ = """Aplica tags inteligentes em tubos baseado em lajes e conexoes.

4 TIPOS DE CLASSIFICACAO:
- Tipo 1 (RISER DOWN): Vem de baixo, TOP conecta horizontal OU top=none
- Tipo 2 (RISER UP+DOWN): Vem de baixo, ultrapassa, sem horizontal
- Tipo 3 (RISER UP): BOTTOM conecta horizontal + ultrapassa OU bottom=none + ultrapassa
- Tipo 4 (HORIZONTAL): Tubos horizontais

v2.7: Unidades do projeto + conexoes desconectadas (none)."""

__persistentengine__ = True

import clr
import os
import traceback

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
clr.AddReference('PresentationCore')
clr.AddReference('PresentationFramework')
clr.AddReference('WindowsBase')

from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Plumbing import Pipe, PipingSystem
from Autodesk.Revit.DB.Mechanical import MechanicalSystem
from Autodesk.Revit.UI.Selection import *

from pyrevit import revit, forms, script
from pyrevit.forms import WPFWindow

# ============================================================================
# GLOBALS
# ============================================================================
doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()
SCRIPT_DIR = os.path.dirname(__file__)

# Configuracoes
VERTICAL_TOLERANCE = 0.1  # ~3cm - tolerancia para considerar tubo vertical
TAG_OFFSET_DISTANCE = 2.0  # ~60cm

# Tolerancias para deteccao de laje (em pes)
# 1 pe = 30.48 cm
TOLERANCE_XY = 1.0           # ~30cm - area XY da laje
TOLERANCE_Z_PENETRATION = 0.5  # ~15cm - minimo que o tubo deve penetrar na laje

# Debug mode
DEBUG_MODE = False

# ============================================================================
# FUNCOES DE UNIDADES E DEBUG
# ============================================================================

def get_project_length_unit():
    """
    Detecta a unidade de comprimento do projeto.
    Retorna: 'imperial' ou 'metric'
    """
    try:
        # Revit 2022+ usa ForgeTypeId
        from Autodesk.Revit.DB import SpecTypeId, UnitTypeId

        units = doc.GetUnits()
        format_options = units.GetFormatOptions(SpecTypeId.Length)
        unit_type_id = format_options.GetUnitTypeId()

        # Verificar se e imperial (feet, inches)
        imperial_units = [
            UnitTypeId.Feet,
            UnitTypeId.FeetFractionalInches,
            UnitTypeId.Inches,
            UnitTypeId.FractionalInches
        ]

        for imp_unit in imperial_units:
            if unit_type_id == imp_unit:
                return 'imperial'

        return 'metric'
    except:
        # Fallback: tentar detectar pelo TypeId string
        try:
            from Autodesk.Revit.DB import SpecTypeId
            units = doc.GetUnits()
            format_options = units.GetFormatOptions(SpecTypeId.Length)
            unit_str = str(format_options.GetUnitTypeId().TypeId).lower()
            if 'feet' in unit_str or 'inch' in unit_str:
                return 'imperial'
        except:
            pass
        return 'metric'


def format_length(feet_value):
    """
    Formata um valor em pes para a unidade do projeto.

    Imperial: X'-Y" ou X'-Y Z/W"
    Metric: X.XX cm ou X.XX m
    """
    try:
        unit_system = get_project_length_unit()

        if unit_system == 'imperial':
            # Converter para feet-inches
            total_inches = float(feet_value) * 12.0
            feet_part = int(total_inches // 12)
            inches_part = total_inches % 12

            # Formatar com fracoes comuns
            whole_inches = int(inches_part)
            frac = inches_part - whole_inches

            # Fracoes comuns: 1/16, 1/8, 3/16, 1/4, 5/16, 3/8, 7/16, 1/2, etc.
            if frac < 0.03125:
                frac_str = ""
            elif frac < 0.09375:
                frac_str = " 1/16"
            elif frac < 0.15625:
                frac_str = " 1/8"
            elif frac < 0.21875:
                frac_str = " 3/16"
            elif frac < 0.28125:
                frac_str = " 1/4"
            elif frac < 0.34375:
                frac_str = " 5/16"
            elif frac < 0.40625:
                frac_str = " 3/8"
            elif frac < 0.46875:
                frac_str = " 7/16"
            elif frac < 0.53125:
                frac_str = " 1/2"
            elif frac < 0.59375:
                frac_str = " 9/16"
            elif frac < 0.65625:
                frac_str = " 5/8"
            elif frac < 0.71875:
                frac_str = " 11/16"
            elif frac < 0.78125:
                frac_str = " 3/4"
            elif frac < 0.84375:
                frac_str = " 13/16"
            elif frac < 0.90625:
                frac_str = " 7/8"
            elif frac < 0.96875:
                frac_str = " 15/16"
            else:
                whole_inches += 1
                frac_str = ""
                if whole_inches >= 12:
                    feet_part += 1
                    whole_inches = 0

            if feet_part > 0:
                if whole_inches > 0 or frac_str:
                    return "{:d}'-{:d}{}\"".format(feet_part, whole_inches, frac_str)
                else:
                    return "{:d}'-0\"".format(feet_part)
            else:
                return "{:d}{}\"".format(whole_inches, frac_str)
        else:
            # Metrico - converter para cm
            cm_value = float(feet_value) * 30.48
            if cm_value >= 100:
                return "{:.2f} m".format(cm_value / 100.0)
            else:
                return "{:.1f} cm".format(cm_value)
    except:
        # Fallback: retornar em pes decimais
        return "{:.2f} ft".format(float(feet_value))


def debug_print(msg):
    """Imprime mensagem se DEBUG_MODE estiver ativo"""
    if DEBUG_MODE:
        print(msg)


# ============================================================================
# CLASSES DE DADOS
# ============================================================================
class PipeClassification:
    """Classificacao de tubos verticais baseado em lajes e conexoes."""
    RISER_DOWN = 1      # Vem inferior, TOP conecta horizontal
    RISER_UP_DOWN = 2   # Vem inferior, ultrapassa, sem horizontal
    RISER_UP = 3        # BOTTOM conecta horizontal, ultrapassa
    HORIZONTAL = 4      # Tubo horizontal

    @staticmethod
    def get_name(classification):
        names = {
            1: "RISER DOWN (Top→Horiz)",
            2: "RISER UP+DOWN (Vertical)",
            3: "RISER UP (Bottom→Horiz)",
            4: "Horizontal"
        }
        return names.get(classification, "Desconhecido")


class FloorData:
    """Armazena dados de uma laje/piso com sua transformacao"""
    def __init__(self, floor_element, source_doc, transform=None, link_instance=None):
        self.Element = floor_element
        self.SourceDoc = source_doc
        self.Transform = transform
        self.LinkInstance = link_instance
        self.IsLinked = link_instance is not None
        self._bbox_cache = None

    def get_bounding_box(self):
        """Obtem BoundingBox transformada para coordenadas do host"""
        if self._bbox_cache:
            return self._bbox_cache

        try:
            bb = self.Element.get_BoundingBox(None)
            if bb and self.Transform:
                min_pt = self.Transform.OfPoint(bb.Min)
                max_pt = self.Transform.OfPoint(bb.Max)
                new_bb = BoundingBoxXYZ()
                new_bb.Min = XYZ(
                    min(min_pt.X, max_pt.X),
                    min(min_pt.Y, max_pt.Y),
                    min(min_pt.Z, max_pt.Z)
                )
                new_bb.Max = XYZ(
                    max(min_pt.X, max_pt.X),
                    max(min_pt.Y, max_pt.Y),
                    max(min_pt.Z, max_pt.Z)
                )
                self._bbox_cache = new_bb
                return new_bb
            self._bbox_cache = bb
            return bb
        except:
            return None

    def get_z_range(self):
        """Retorna (z_bottom, z_top) da laje"""
        bb = self.get_bounding_box()
        if bb:
            return bb.Min.Z, bb.Max.Z
        return None, None


class PipeData:
    """Armazena dados de um tubo processado"""
    def __init__(self, pipe_element, center_point, bottom_point, top_point,
                 classification, is_linked=False, link_instance=None, source_doc=None,
                 debug_info=None):
        self.Element = pipe_element
        self.CenterPoint = center_point
        self.BottomPoint = bottom_point
        self.TopPoint = top_point
        self.Classification = classification
        self.IsLinked = is_linked
        self.LinkInstance = link_instance
        self.SourceDoc = source_doc or doc
        self.DebugInfo = debug_info or {}

    def get_reference_for_tagging(self):
        """Retorna Reference apropriada para criacao de tag."""
        if self.IsLinked and self.LinkInstance:
            try:
                internal_ref = Reference(self.Element)
                link_ref = internal_ref.CreateLinkReference(self.LinkInstance)
                return link_ref
            except:
                return None
        else:
            return Reference(self.Element)


# ============================================================================
# FILTROS DE SELECAO
# ============================================================================
def is_vertical(curve, tolerance=VERTICAL_TOLERANCE):
    """Verifica se o tubo e vertical."""
    p1 = curve.GetEndPoint(0)
    p2 = curve.GetEndPoint(1)
    horizontal_distance = ((p2.X - p1.X)**2 + (p2.Y - p1.Y)**2)**0.5
    return horizontal_distance < tolerance


class LocalPipeSelectionFilter(ISelectionFilter):
    def AllowElement(self, elem):
        return isinstance(elem, Pipe)

    def AllowReference(self, reference, position):
        return True


class LinkedPipeSelectionFilter(ISelectionFilter):
    def __init__(self, doc):
        self.doc = doc

    def AllowElement(self, elem):
        return isinstance(elem, RevitLinkInstance)

    def AllowReference(self, reference, position):
        try:
            elem = self.doc.GetElement(reference)
            if isinstance(elem, RevitLinkInstance):
                link_doc = elem.GetLinkDocument()
                if link_doc:
                    linked_element = link_doc.GetElement(reference.LinkedElementId)
                    return isinstance(linked_element, Pipe)
        except:
            return False
        return False


# ============================================================================
# FUNCOES DE COLETA DE LAJES
# ============================================================================
def get_all_revit_links():
    links = []
    try:
        collector = FilteredElementCollector(doc)\
            .OfClass(RevitLinkInstance)\
            .ToElements()

        for link in collector:
            try:
                link_doc = link.GetLinkDocument()
                if link_doc:
                    links.append({
                        'instance': link,
                        'document': link_doc,
                        'transform': link.GetTotalTransform(),
                        'name': link.Name
                    })
            except:
                continue
    except:
        pass
    return links


def get_all_floors_from_all_sources():
    all_floors = []

    try:
        host_floors = FilteredElementCollector(doc)\
            .OfCategory(BuiltInCategory.OST_Floors)\
            .WhereElementIsNotElementType()\
            .ToElements()

        for floor in host_floors:
            all_floors.append(FloorData(floor, doc, None, None))
    except:
        pass

    links = get_all_revit_links()
    for link_info in links:
        try:
            link_doc = link_info['document']
            transform = link_info['transform']
            link_instance = link_info['instance']

            link_floors = FilteredElementCollector(link_doc)\
                .OfCategory(BuiltInCategory.OST_Floors)\
                .WhereElementIsNotElementType()\
                .ToElements()

            for floor in link_floors:
                all_floors.append(FloorData(floor, link_doc, transform, link_instance))

        except:
            continue

    return all_floors


# ============================================================================
# FUNCOES DE DETECCAO - NOVA LOGICA v2.3
# ============================================================================
def get_pipe_endpoints_transformed(pipe, transform=None):
    """Obtem endpoints ordenados por Z (bottom, top)."""
    try:
        location = pipe.Location
        if isinstance(location, LocationCurve):
            curve = location.Curve
            p1 = curve.GetEndPoint(0)
            p2 = curve.GetEndPoint(1)

            if transform:
                p1 = transform.OfPoint(p1)
                p2 = transform.OfPoint(p2)

            if p1.Z <= p2.Z:
                return p1, p2
            else:
                return p2, p1
    except:
        pass
    return None, None


def pipe_is_in_floor_xy_area(pipe_x, pipe_y, floor_data, tolerance=TOLERANCE_XY):
    """Verifica se a posicao XY do tubo esta dentro da area da laje."""
    try:
        bb = floor_data.get_bounding_box()
        if not bb:
            return False

        return (bb.Min.X - tolerance <= pipe_x <= bb.Max.X + tolerance and
                bb.Min.Y - tolerance <= pipe_y <= bb.Max.Y + tolerance)
    except:
        return False


def pipe_passes_through_floor(pipe_bottom_z, pipe_top_z, floor_bottom_z, floor_top_z, min_penetration=TOLERANCE_Z_PENETRATION):
    """
    Verifica se o tubo ATRAVESSA a laje.

    NOVA LOGICA v2.3:
    O tubo atravessa a laje se:
    1. O tubo comeca ABAIXO ou DENTRO da laje E
    2. O tubo termina ACIMA ou DENTRO da laje E
    3. O tubo penetra pelo menos 'min_penetration' na laje

    Isso garante que o tubo realmente CRUZA a laje, nao apenas fica perto.
    """
    # Tubo totalmente abaixo da laje
    if pipe_top_z <= floor_bottom_z:
        return False

    # Tubo totalmente acima da laje
    if pipe_bottom_z >= floor_top_z:
        return False

    # Calcular quanto do tubo esta dentro da laje
    overlap_bottom = max(pipe_bottom_z, floor_bottom_z)
    overlap_top = min(pipe_top_z, floor_top_z)
    penetration = overlap_top - overlap_bottom

    # Deve penetrar pelo menos o minimo
    return penetration >= min_penetration


def analyze_pipe_floor_intersections_v2(pipe_bottom_z, pipe_top_z, pipe_x, pipe_y, all_floors_data):
    """
    NOVA LOGICA v2.4: Analisa todas as lajes que o tubo atravessa.

    Encontra a laje mais BAIXA e mais ALTA que o tubo atravessa, e verifica:
    - "Vem de baixo" = pipe_bottom esta AT ou ABAIXO da laje mais baixa
    - "Ultrapassa" = pipe_top esta AT ou ACIMA da laje mais alta

    Retorna: (vem_de_baixo, ultrapassa, crossed_floors, debug_info)
    """
    crossed_floors = []

    for floor_data in all_floors_data:
        # Verificar se esta na area XY
        if not pipe_is_in_floor_xy_area(pipe_x, pipe_y, floor_data):
            continue

        floor_bottom_z, floor_top_z = floor_data.get_z_range()
        if floor_bottom_z is None:
            continue

        # Verificar se o tubo ATRAVESSA esta laje
        if pipe_passes_through_floor(pipe_bottom_z, pipe_top_z, floor_bottom_z, floor_top_z):
            crossed_floors.append({
                'data': floor_data,
                'bottom_z': floor_bottom_z,
                'top_z': floor_top_z
            })
            debug_print("  -> Tubo ATRAVESSA laje: Z=[{}, {}]".format(
                format_length(floor_bottom_z), format_length(floor_top_z)))

    if not crossed_floors:
        return False, False, [], {}

    # Ordenar por Z para encontrar a mais baixa e mais alta
    crossed_floors.sort(key=lambda x: x['bottom_z'])

    lowest_floor = crossed_floors[0]
    highest_floor = crossed_floors[-1]

    # Tolerancia para comparacao
    tolerance = TOLERANCE_Z_PENETRATION

    # "Vem de baixo" = pipe bottom esta AT ou ABAIXO do fundo da laje mais baixa
    vem_de_baixo = pipe_bottom_z <= lowest_floor['bottom_z'] + tolerance

    # "Ultrapassa" = pipe top esta AT ou ACIMA do topo da laje mais alta
    ultrapassa = pipe_top_z >= highest_floor['top_z'] - tolerance

    debug_info = {
        'lowest_floor_z': (format_length(lowest_floor['bottom_z']), format_length(lowest_floor['top_z'])),
        'highest_floor_z': (format_length(highest_floor['bottom_z']), format_length(highest_floor['top_z'])),
    }

    debug_print("  Laje mais BAIXA: Z=[{}, {}]".format(
        debug_info['lowest_floor_z'][0], debug_info['lowest_floor_z'][1]))
    debug_print("  Laje mais ALTA: Z=[{}, {}]".format(
        debug_info['highest_floor_z'][0], debug_info['highest_floor_z'][1]))
    debug_print("  pipe_bottom ({}) <= lowest_floor_bottom ({}) + tol? {}".format(
        format_length(pipe_bottom_z), format_length(lowest_floor['bottom_z']), vem_de_baixo))
    debug_print("  pipe_top ({}) >= highest_floor_top ({}) - tol? {}".format(
        format_length(pipe_top_z), format_length(highest_floor['top_z']), ultrapassa))

    return vem_de_baixo, ultrapassa, crossed_floors, debug_info


# ============================================================================
# FUNCOES DE ANALISE DE CONEXOES - v2.5
# ============================================================================
def get_connector_manager_safe(element):
    """Obtem ConnectorManager de forma segura para pipes e fittings."""
    try:
        # Para MEPCurve (Pipe, Duct, etc)
        if hasattr(element, 'ConnectorManager'):
            return element.ConnectorManager

        # Para FamilyInstance (fittings, equipamentos)
        if hasattr(element, 'MEPModel'):
            mep_model = element.MEPModel
            if mep_model and hasattr(mep_model, 'ConnectorManager'):
                return mep_model.ConnectorManager
    except:
        pass
    return None


def get_connector_at_point(element, point, tolerance=0.5):
    """Encontra conector mais proximo de um ponto."""
    try:
        cm = get_connector_manager_safe(element)
        if not cm:
            return None

        closest_conn = None
        min_dist = tolerance

        for conn in cm.Connectors:
            dist = conn.Origin.DistanceTo(point)
            if dist < min_dist:
                min_dist = dist
                closest_conn = conn

        return closest_conn
    except:
        return None


def get_connected_elements_from_connector(connector, exclude_element_id=None):
    """Retorna elementos conectados a um conector."""
    connected = []
    try:
        if not connector or not connector.IsConnected:
            return connected

        for ref_conn in connector.AllRefs:
            try:
                owner = ref_conn.Owner
                if owner and (exclude_element_id is None or owner.Id != exclude_element_id):
                    connected.append(owner)
            except:
                continue
    except:
        pass
    return connected


def is_pipe_fitting(element):
    """Verifica se elemento e um fitting de tubulacao."""
    try:
        if isinstance(element, FamilyInstance):
            # Verificar categoria
            cat = element.Category
            if cat:
                cat_id = cat.Id.IntegerValue if hasattr(cat.Id, 'IntegerValue') else cat.Id.Value
                # OST_PipeFitting = -2008055
                if cat_id == -2008055:
                    return True

            # Verificar se tem MEPModel (fittings tem)
            if hasattr(element, 'MEPModel') and element.MEPModel:
                return True
        return False
    except:
        return False


def is_plumbing_fixture(element):
    """
    Verifica se elemento e uma peca hidrosanitaria (floor drain, sink, etc).

    Plumbing fixtures sao pontos terminais - indicam onde o fluxo
    comeca ou termina (ex: ralo, pia, vaso sanitario).
    """
    try:
        if isinstance(element, FamilyInstance):
            cat = element.Category
            if cat:
                cat_id = cat.Id.IntegerValue if hasattr(cat.Id, 'IntegerValue') else cat.Id.Value
                # OST_PlumbingFixtures = -2008049
                if cat_id == -2008049:
                    return True
        return False
    except:
        return False


def is_element_horizontal(element, tolerance=VERTICAL_TOLERANCE):
    """Verifica se um elemento (pipe) e horizontal."""
    try:
        if not isinstance(element, Pipe):
            return False

        location = element.Location
        if isinstance(location, LocationCurve):
            curve = location.Curve
            p1 = curve.GetEndPoint(0)
            p2 = curve.GetEndPoint(1)

            # Distancia vertical
            vertical_dist = abs(p2.Z - p1.Z)
            # Distancia horizontal
            horiz_dist = ((p2.X - p1.X)**2 + (p2.Y - p1.Y)**2)**0.5

            # E horizontal se distancia vertical e pequena comparada a horizontal
            if horiz_dist > tolerance:
                return vertical_dist < tolerance
        return False
    except:
        return False


def trace_connection_for_horizontal(element, source_doc, visited_ids=None, max_depth=3):
    """
    Traca conexao a partir de um elemento procurando tubo horizontal.

    Segue atraves de fittings ate encontrar:
    - Tubo horizontal → retorna True
    - Tubo vertical → retorna False
    - Nada conectado → retorna False
    - Max depth atingido → retorna False

    Args:
        element: Elemento inicial (fitting ou pipe)
        source_doc: Documento fonte
        visited_ids: Set de IDs ja visitados (evita loops)
        max_depth: Profundidade maxima de busca

    Returns:
        bool: True se encontrou tubo horizontal na cadeia
    """
    if visited_ids is None:
        visited_ids = set()

    if max_depth <= 0:
        return False

    try:
        elem_id = element.Id.IntegerValue if hasattr(element.Id, 'IntegerValue') else element.Id.Value

        if elem_id in visited_ids:
            return False
        visited_ids.add(elem_id)

        # Se e um Pipe, verificar se e horizontal
        if isinstance(element, Pipe):
            return is_element_horizontal(element)

        # Se e um fitting, seguir para proximos elementos
        if is_pipe_fitting(element):
            cm = get_connector_manager_safe(element)
            if not cm:
                return False

            for conn in cm.Connectors:
                connected = get_connected_elements_from_connector(conn, element.Id)
                for next_elem in connected:
                    if trace_connection_for_horizontal(next_elem, source_doc, visited_ids, max_depth - 1):
                        return True

        return False
    except:
        return False


def trace_connection_for_horizontal_or_fixture(element, source_doc, visited_ids=None, max_depth=3):
    """
    v2.7: Traca conexao procurando tubo horizontal OU plumbing fixture.

    Segue atraves de fittings ate encontrar:
    - Plumbing fixture (floor drain, etc) → retorna (True, False)
    - Tubo horizontal → retorna (False, True)
    - Tubo vertical ou nada → retorna (False, False)

    Args:
        element: Elemento inicial (fitting ou pipe)
        source_doc: Documento fonte
        visited_ids: Set de IDs ja visitados (evita loops)
        max_depth: Profundidade maxima de busca

    Returns:
        tuple: (found_fixture, found_horizontal)
    """
    if visited_ids is None:
        visited_ids = set()

    if max_depth <= 0:
        return False, False

    try:
        elem_id = element.Id.IntegerValue if hasattr(element.Id, 'IntegerValue') else element.Id.Value

        if elem_id in visited_ids:
            return False, False
        visited_ids.add(elem_id)

        # Verificar se e plumbing fixture
        if is_plumbing_fixture(element):
            return True, False

        # Se e um Pipe, verificar se e horizontal
        if isinstance(element, Pipe):
            return False, is_element_horizontal(element)

        # Se e um fitting, seguir para proximos elementos
        if is_pipe_fitting(element):
            cm = get_connector_manager_safe(element)
            if not cm:
                return False, False

            for conn in cm.Connectors:
                connected = get_connected_elements_from_connector(conn, element.Id)
                for next_elem in connected:
                    found_fix, found_horiz = trace_connection_for_horizontal_or_fixture(
                        next_elem, source_doc, visited_ids, max_depth - 1
                    )
                    if found_fix:
                        return True, False
                    if found_horiz:
                        return False, True

        return False, False
    except:
        return False, False


def analyze_endpoint_connection(pipe, endpoint, source_doc):
    """
    Analisa conexao em um endpoint de tubo vertical.

    Verifica se o endpoint conecta (direta ou via fitting) a um tubo horizontal
    ou a uma peca hidrosanitaria (plumbing fixture).

    Args:
        pipe: Pipe element
        endpoint: XYZ do endpoint (bottom ou top)
        source_doc: Documento fonte

    Returns:
        dict: {
            'has_connection': bool,
            'connects_to_horizontal': bool,
            'connects_to_fixture': bool,
            'connection_type': str ('none', 'direct_horizontal', 'fitting_to_horizontal',
                                   'fitting_to_vertical', 'direct_vertical', 'fixture')
        }
    """
    result = {
        'has_connection': False,
        'connects_to_horizontal': False,
        'connects_to_fixture': False,
        'connection_type': 'none'
    }

    try:
        # Encontrar conector no endpoint
        connector = get_connector_at_point(pipe, endpoint)
        if not connector:
            return result

        # Verificar se esta conectado
        if not connector.IsConnected:
            return result

        result['has_connection'] = True

        # Obter elementos conectados
        connected_elements = get_connected_elements_from_connector(connector, pipe.Id)

        if not connected_elements:
            result['connection_type'] = 'none'
            return result

        for connected_elem in connected_elements:
            # v2.7: Conexao a plumbing fixture (floor drain, sink, etc)
            if is_plumbing_fixture(connected_elem):
                result['connects_to_fixture'] = True
                result['connection_type'] = 'fixture'
                debug_print("    -> Detectado plumbing fixture!")
                return result

            # Conexao direta a Pipe
            if isinstance(connected_elem, Pipe):
                if is_element_horizontal(connected_elem):
                    result['connects_to_horizontal'] = True
                    result['connection_type'] = 'direct_horizontal'
                    return result
                else:
                    result['connection_type'] = 'direct_vertical'

            # Conexao a fitting - seguir cadeia
            elif is_pipe_fitting(connected_elem):
                visited = set()
                visited.add(pipe.Id.IntegerValue if hasattr(pipe.Id, 'IntegerValue') else pipe.Id.Value)

                # v2.7: Verificar se o fitting conecta a fixture ou horizontal
                found_fixture, found_horizontal = trace_connection_for_horizontal_or_fixture(
                    connected_elem, source_doc, visited, max_depth=3
                )

                if found_fixture:
                    result['connects_to_fixture'] = True
                    result['connection_type'] = 'fitting_to_fixture'
                    debug_print("    -> Detectado fitting → fixture!")
                    return result
                elif found_horizontal:
                    result['connects_to_horizontal'] = True
                    result['connection_type'] = 'fitting_to_horizontal'
                    return result
                else:
                    result['connection_type'] = 'fitting_to_vertical'

        return result

    except Exception as e:
        debug_print("  Erro ao analisar conexao: {}".format(str(e)))
        return result


def analyze_pipe_connections(pipe, bottom_point, top_point, source_doc):
    """
    Analisa conexoes em ambas extremidades de um tubo vertical.

    Returns:
        dict: {
            'bottom': resultado de analyze_endpoint_connection para bottom,
            'top': resultado de analyze_endpoint_connection para top,
            'bottom_has_horizontal': bool,
            'top_has_horizontal': bool,
            'bottom_has_fixture': bool,
            'top_has_fixture': bool
        }
    """
    bottom_analysis = analyze_endpoint_connection(pipe, bottom_point, source_doc)
    top_analysis = analyze_endpoint_connection(pipe, top_point, source_doc)

    return {
        'bottom': bottom_analysis,
        'top': top_analysis,
        'bottom_has_horizontal': bottom_analysis['connects_to_horizontal'],
        'top_has_horizontal': top_analysis['connects_to_horizontal'],
        'bottom_has_fixture': bottom_analysis.get('connects_to_fixture', False),
        'top_has_fixture': top_analysis.get('connects_to_fixture', False)
    }


# ============================================================================
# CLASSIFICACAO v2.5 - LAJES + CONEXOES
# ============================================================================
def classify_vertical_pipe_v5(pipe, bottom_point, top_point, all_floors_data, source_doc):
    """
    Classifica tubo vertical baseado em LAJES + CONEXOES.

    LOGICA v2.7:
    1. Analisar atravessamento de lajes (vem_de_baixo, ultrapassa)
    2. Analisar conexoes nas extremidades (bottom/top → horizontal?)
    3. Classificar:
       - RISER DOWN: vem_de_baixo + TOP conecta horizontal
       - RISER UP+DOWN: vem_de_baixo + ultrapassa + SEM horizontal
       - RISER UP: BOTTOM conecta horizontal + ultrapassa

    Returns: (classificacao, debug_info)
    """
    pipe_x = (bottom_point.X + top_point.X) / 2
    pipe_y = (bottom_point.Y + top_point.Y) / 2
    pipe_bottom_z = bottom_point.Z
    pipe_top_z = top_point.Z

    debug_info = {
        'pipe_bottom_z': format_length(pipe_bottom_z),
        'pipe_top_z': format_length(pipe_top_z),
        'pipe_length': format_length(pipe_top_z - pipe_bottom_z),
        'floors_crossed': 0,
        'vem_de_baixo': False,
        'ultrapassa': False,
        'bottom_has_horizontal': False,
        'top_has_horizontal': False,
        'bottom_connection_type': 'none',
        'top_connection_type': 'none'
    }

    debug_print("\nAnalisando tubo: Z=[{}, {}], comprimento={}".format(
        debug_info['pipe_bottom_z'],
        debug_info['pipe_top_z'],
        debug_info['pipe_length']))

    # ========== FASE 1: Analisar lajes ==========
    vem_de_baixo, ultrapassa, crossed_floors, floor_debug = analyze_pipe_floor_intersections_v2(
        pipe_bottom_z, pipe_top_z, pipe_x, pipe_y, all_floors_data
    )

    debug_info['floors_crossed'] = len(crossed_floors)
    debug_info['vem_de_baixo'] = vem_de_baixo
    debug_info['ultrapassa'] = ultrapassa
    debug_info.update(floor_debug)

    debug_print("  LAJES: vem_de_baixo={}, ultrapassa={}, atravessadas={}".format(
        vem_de_baixo, ultrapassa, len(crossed_floors)))

    # ========== FASE 2: Analisar conexoes ==========
    connections = analyze_pipe_connections(pipe, bottom_point, top_point, source_doc)

    debug_info['bottom_has_horizontal'] = connections['bottom_has_horizontal']
    debug_info['top_has_horizontal'] = connections['top_has_horizontal']
    debug_info['bottom_connection_type'] = connections['bottom']['connection_type']
    debug_info['top_connection_type'] = connections['top']['connection_type']

    debug_print("  CONEXOES: bottom_horiz={} ({}), top_horiz={} ({})".format(
        connections['bottom_has_horizontal'],
        connections['bottom']['connection_type'],
        connections['top_has_horizontal'],
        connections['top']['connection_type']))

    # ========== FASE 3: Classificar ==========
    bottom_horiz = connections['bottom_has_horizontal']
    top_horiz = connections['top_has_horizontal']
    bottom_type = connections['bottom']['connection_type']
    top_type = connections['top']['connection_type']

    # ===== v2.7: Tratamento de conexoes "none" (desconectadas) =====
    # Se bottom=none E ultrapassa → RISER UP (tubo solto em baixo, sobe)
    if bottom_type == 'none' and ultrapassa:
        classification = PipeClassification.RISER_UP
        debug_print("  -> TIPO 3 (RISER UP): Bottom=none, ultrapassa laje superior")

    # Se top=none E vem_de_baixo → RISER DOWN (tubo vem de baixo, termina solto)
    elif top_type == 'none' and vem_de_baixo:
        classification = PipeClassification.RISER_DOWN
        debug_print("  -> TIPO 1 (RISER DOWN): Top=none, vem de baixo")

    # ===== Logica original v2.5 =====
    # RISER DOWN: Vem de baixo + TOP conecta horizontal
    elif vem_de_baixo and top_horiz:
        classification = PipeClassification.RISER_DOWN
        debug_print("  -> TIPO 1 (RISER DOWN): Vem de baixo, TOP→horizontal")

    # RISER UP+DOWN: Vem de baixo + ultrapassa + SEM horizontal em nenhum lado
    elif vem_de_baixo and ultrapassa and not top_horiz and not bottom_horiz:
        classification = PipeClassification.RISER_UP_DOWN
        debug_print("  -> TIPO 2 (RISER UP+DOWN): Vem de baixo, ultrapassa, vertical continuo")

    # RISER UP: BOTTOM conecta horizontal + ultrapassa
    elif bottom_horiz and ultrapassa:
        classification = PipeClassification.RISER_UP
        debug_print("  -> TIPO 3 (RISER UP): BOTTOM→horizontal, ultrapassa")

    # Fallback: se vem de baixo mas nao ultrapassa → RISER DOWN
    elif vem_de_baixo and not ultrapassa:
        classification = PipeClassification.RISER_DOWN
        debug_print("  -> TIPO 1 (RISER DOWN): Vem de baixo, NAO ultrapassa")

    # Fallback: se ultrapassa mas nao vem de baixo e nao tem horizontal → RISER UP
    elif ultrapassa and not vem_de_baixo:
        classification = PipeClassification.RISER_UP
        debug_print("  -> TIPO 3 (RISER UP): NAO vem de baixo, ultrapassa")

    # Default: RISER DOWN
    else:
        classification = PipeClassification.RISER_DOWN
        debug_print("  -> TIPO 1 (RISER DOWN): Default")

    return classification, debug_info


def classify_pipe(pipe, pipe_transform, all_floors_data, source_doc):
    """Classifica um tubo usando logica v2.5 (lajes + conexoes)."""
    try:
        location = pipe.Location
        if not isinstance(location, LocationCurve):
            return PipeClassification.HORIZONTAL, None, None, {}

        curve = location.Curve

        if is_vertical(curve):
            bottom_point, top_point = get_pipe_endpoints_transformed(pipe, pipe_transform)

            if bottom_point and top_point:
                classification, debug_info = classify_vertical_pipe_v5(
                    pipe, bottom_point, top_point, all_floors_data, source_doc
                )
                return classification, bottom_point, top_point, debug_info
            else:
                return PipeClassification.RISER_DOWN, None, None, {}
        else:
            return PipeClassification.HORIZONTAL, None, None, {}

    except:
        return PipeClassification.HORIZONTAL, None, None, {}


def get_pipe_center(pipe, transform=None):
    """Obtem o ponto central do tubo"""
    try:
        location = pipe.Location
        if isinstance(location, LocationCurve):
            curve = location.Curve
            p1 = curve.GetEndPoint(0)
            p2 = curve.GetEndPoint(1)
            center = XYZ((p1.X + p2.X) / 2, (p1.Y + p2.Y) / 2, (p1.Z + p2.Z) / 2)

            if transform:
                center = transform.OfPoint(center)

            return center
    except:
        pass
    return None


# ============================================================================
# FUNCOES DE TAGS
# ============================================================================
def get_pipe_tag_types():
    try:
        tag_types = FilteredElementCollector(doc)\
            .OfCategory(BuiltInCategory.OST_PipeTags)\
            .WhereElementIsElementType()\
            .ToElements()

        result = []
        for tt in tag_types:
            try:
                family_name = tt.FamilyName if hasattr(tt, 'FamilyName') else ""
                type_name_param = tt.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
                type_name = type_name_param.AsString() if type_name_param else ""
                display_name = "{} : {}".format(family_name, type_name) if family_name else type_name
                result.append({
                    'element': tt,
                    'id': tt.Id,
                    'name': display_name,
                    'family': family_name,
                    'type': type_name
                })
            except:
                continue

        result.sort(key=lambda x: x['name'])
        return result
    except:
        return []


def calculate_smart_tag_position(center_point, view, existing_tag_positions, offset=TAG_OFFSET_DISTANCE):
    try:
        right = view.RightDirection
        up = view.UpDirection
    except:
        right = XYZ(1, 0, 0)
        up = XYZ(0, 1, 0)

    directions = [
        right,
        (right + up).Normalize(),
        up,
        (right.Negate() + up).Normalize(),
        right.Negate(),
        (right.Negate() + up.Negate()).Normalize(),
        up.Negate(),
        (right + up.Negate()).Normalize(),
    ]

    min_distance_threshold = 1.5

    for multiplier in [1.0, 1.5, 2.0]:
        for direction in directions:
            test_pos = XYZ(
                center_point.X + direction.X * offset * multiplier,
                center_point.Y + direction.Y * offset * multiplier,
                center_point.Z
            )

            is_valid = True
            for existing_pos in existing_tag_positions:
                dist = test_pos.DistanceTo(existing_pos)
                if dist < min_distance_threshold:
                    is_valid = False
                    break

            if is_valid:
                return test_pos

    return XYZ(
        center_point.X + right.X * offset * 3,
        center_point.Y + right.Y * offset * 3,
        center_point.Z
    )


def create_pipe_tag(view, reference, tag_type_id, point, add_leader=False):
    try:
        tag = IndependentTag.Create(
            doc,
            tag_type_id,
            view.Id,
            reference,
            add_leader,
            TagOrientation.Horizontal,
            point
        )

        if add_leader and tag:
            try:
                if tag.CanLeaderEndConditionBeAssigned(LeaderEndCondition.Free):
                    tag.LeaderEndCondition = LeaderEndCondition.Free
            except:
                pass

        return tag
    except:
        return None


# ============================================================================
# PROCESSAMENTO DE TUBOS
# ============================================================================
def process_local_pipes(pipes, all_floors_data):
    processed = []

    for pipe in pipes:
        try:
            classification, bottom_pt, top_pt, debug_info = classify_pipe(
                pipe, None, all_floors_data, doc
            )
            center = get_pipe_center(pipe)

            if center:
                p_data = PipeData(
                    pipe, center, bottom_pt, top_pt, classification,
                    is_linked=False, link_instance=None, source_doc=doc,
                    debug_info=debug_info
                )
                processed.append(p_data)
        except:
            continue

    return processed


def process_linked_pipes(references, all_floors_data):
    processed = []

    for ref in references:
        try:
            link_instance = doc.GetElement(ref.ElementId)
            if not isinstance(link_instance, RevitLinkInstance):
                continue

            transform = link_instance.GetTotalTransform()
            link_doc = link_instance.GetLinkDocument()

            if not link_doc:
                continue

            linked_pipe = link_doc.GetElement(ref.LinkedElementId)

            if not isinstance(linked_pipe, Pipe):
                continue

            classification, bottom_pt, top_pt, debug_info = classify_pipe(
                linked_pipe, transform, all_floors_data, link_doc
            )
            center = get_pipe_center(linked_pipe, transform)

            if center:
                p_data = PipeData(
                    linked_pipe, center, bottom_pt, top_pt, classification,
                    is_linked=True, link_instance=link_instance, source_doc=link_doc,
                    debug_info=debug_info
                )
                processed.append(p_data)

        except:
            continue

    return processed


def group_pipes_by_classification(pipes_data):
    grouped = {
        PipeClassification.RISER_DOWN: [],
        PipeClassification.RISER_UP_DOWN: [],
        PipeClassification.RISER_UP: [],
        PipeClassification.HORIZONTAL: []
    }

    for p_data in pipes_data:
        if p_data.Classification in grouped:
            grouped[p_data.Classification].append(p_data)

    return grouped


# ============================================================================
# INTERFACE WPF
# ============================================================================
class OverheadWindow(WPFWindow):
    def __init__(self, grouped_pipes, tag_types, floor_count):
        self.grouped_pipes = grouped_pipes
        self.tag_types = tag_types
        self.floor_count = floor_count
        self.selected_tags = {}
        self.add_leaders = False
        self.smart_position = True

        xaml_path = os.path.join(SCRIPT_DIR, 'ui.xaml')
        WPFWindow.__init__(self, xaml_path)

        self.setup_ui()

    def setup_ui(self):
        count_type1 = len(self.grouped_pipes.get(PipeClassification.RISER_DOWN, []))
        count_type2 = len(self.grouped_pipes.get(PipeClassification.RISER_UP_DOWN, []))
        count_type3 = len(self.grouped_pipes.get(PipeClassification.RISER_UP, []))
        count_type4 = len(self.grouped_pipes.get(PipeClassification.HORIZONTAL, []))
        total = count_type1 + count_type2 + count_type3 + count_type4

        linked_count = sum(1 for pipes in self.grouped_pipes.values() for p in pipes if p.IsLinked)

        info_text = "Total: {} tubos | {} lajes (host+links)".format(total, self.floor_count)
        if linked_count > 0:
            info_text += " | {} em vinculos".format(linked_count)
        self.lbl_total.Text = info_text

        self.lbl_type1_count.Text = "{} tubos".format(count_type1)
        self.lbl_type2_count.Text = "{} tubos".format(count_type2)
        self.lbl_type3_count.Text = "{} tubos".format(count_type3)
        self.lbl_type4_count.Text = "{} tubos".format(count_type4)

        tag_names = ["(Nenhum - Nao Aplicar Tag)"] + [t['name'] for t in self.tag_types]

        for name in tag_names:
            self.combo_tag_type1.Items.Add(name)
            self.combo_tag_type2.Items.Add(name)
            self.combo_tag_type3.Items.Add(name)
            self.combo_tag_type4.Items.Add(name)

        self.combo_tag_type1.SelectedIndex = 0
        self.combo_tag_type2.SelectedIndex = 0
        self.combo_tag_type3.SelectedIndex = 0
        self.combo_tag_type4.SelectedIndex = 0

        self.combo_tag_type1.IsEnabled = count_type1 > 0
        self.combo_tag_type2.IsEnabled = count_type2 > 0
        self.combo_tag_type3.IsEnabled = count_type3 > 0
        self.combo_tag_type4.IsEnabled = count_type4 > 0

        self.btn_apply.Click += self.on_apply
        self.btn_cancel.Click += self.on_cancel

    def get_selected_tag_type(self, combo):
        if combo.SelectedIndex <= 0:
            return None
        return self.tag_types[combo.SelectedIndex - 1]

    def on_apply(self, sender, args):
        self.selected_tags = {
            PipeClassification.RISER_DOWN: self.get_selected_tag_type(self.combo_tag_type1),
            PipeClassification.RISER_UP_DOWN: self.get_selected_tag_type(self.combo_tag_type2),
            PipeClassification.RISER_UP: self.get_selected_tag_type(self.combo_tag_type3),
            PipeClassification.HORIZONTAL: self.get_selected_tag_type(self.combo_tag_type4)
        }
        self.add_leaders = self.chk_leaders.IsChecked if hasattr(self, 'chk_leaders') else False
        self.smart_position = self.chk_smart_position.IsChecked if hasattr(self, 'chk_smart_position') else True
        self.DialogResult = True
        self.Close()

    def on_cancel(self, sender, args):
        self.DialogResult = False
        self.Close()


# ============================================================================
# EXECUCAO PRINCIPAL
# ============================================================================
def main():
    global DEBUG_MODE

    active_view = doc.ActiveView
    if not active_view:
        forms.alert("Nenhuma vista ativa!", exitscript=True)

    valid_view_types = [
        ViewType.FloorPlan, ViewType.CeilingPlan, ViewType.Section,
        ViewType.Elevation, ViewType.Detail, ViewType.ThreeD
    ]

    if active_view.ViewType not in valid_view_types:
        forms.alert("A vista ativa nao suporta tags.\nUse uma planta, corte ou elevacao.", exitscript=True)

    escolha = forms.CommandSwitchWindow.show(
        ['Tubos LOCAIS', 'Tubos em VINCULOS', '[DEBUG] Tubos LOCAIS'],
        message='Selecione o modo de operacao:'
    )

    if not escolha:
        return

    if '[DEBUG]' in escolha:
        DEBUG_MODE = True
        output.print_md("## DEBUG MODE ATIVO - v2.7")
        output.print_md("**Nova logica:** Lajes + Conexoes + 'none'")
        output.print_md("- RISER DOWN: Vem de baixo + TOP→horizontal OU top=none")
        output.print_md("- RISER UP+DOWN: Vem de baixo + ultrapassa + SEM horizontal")
        output.print_md("- RISER UP: BOTTOM→horizontal + ultrapassa OU bottom=none + ultrapassa")
        output.print_md("---")

    all_floors_data = get_all_floors_from_all_sources()
    floor_count = len(all_floors_data)

    if DEBUG_MODE:
        output.print_md("### Lajes detectadas: {}".format(floor_count))
        for i, fd in enumerate(all_floors_data[:10]):
            z_bot, z_top = fd.get_z_range()
            if z_bot is not None:
                output.print_md("  - Laje {}: Z=[{}, {}], espessura={}".format(
                    i+1, format_length(z_bot), format_length(z_top), format_length(z_top - z_bot)))
        if floor_count > 10:
            output.print_md("  - ... e mais {} lajes".format(floor_count - 10))
        output.print_md("---")

    if floor_count == 0:
        resp = forms.alert(
            "Nenhuma laje/piso encontrada no projeto ou vinculos.\n\n"
            "Deseja continuar?",
            yes=True, no=True
        )
        if not resp:
            return

    pipes_data = []
    is_local = 'LOCAIS' in escolha

    if is_local:
        try:
            with forms.WarningBar(title="Selecione os tubos e clique em Concluir"):
                selection = list(uidoc.Selection.PickObjects(
                    ObjectType.Element,
                    LocalPipeSelectionFilter(),
                    "Selecione Tubos"
                ))
        except:
            return

        if not selection:
            return

        pipes = [doc.GetElement(ref) for ref in selection]
        pipes_data = process_local_pipes(pipes, all_floors_data)

    else:
        try:
            with forms.WarningBar(title="Selecione tubos no modelo vinculado"):
                references = uidoc.Selection.PickObjects(
                    ObjectType.LinkedElement,
                    LinkedPipeSelectionFilter(doc),
                    "Selecione Tubos no Vinculo"
                )
        except:
            return

        if not references:
            return

        pipes_data = process_linked_pipes(references, all_floors_data)

    if not pipes_data:
        forms.alert("Nenhum tubo valido encontrado.", exitscript=True)

    if DEBUG_MODE:
        output.print_md("### Classificacao dos tubos:")
        for i, p in enumerate(pipes_data):
            z_bot = p.DebugInfo.get('pipe_bottom_z', '0')
            z_top = p.DebugInfo.get('pipe_top_z', '0')
            output.print_md("**Tubo {}**: {} - Z=[{}, {}]".format(
                i+1,
                PipeClassification.get_name(p.Classification),
                z_bot,
                z_top
            ))
            output.print_md("  - Lajes: {} | Vem baixo: {} | Ultrapassa: {}".format(
                p.DebugInfo.get('floors_crossed', 0),
                p.DebugInfo.get('vem_de_baixo', False),
                p.DebugInfo.get('ultrapassa', False)
            ))
            output.print_md("  - Conexoes: Bottom→{} ({}) | Top→{} ({})".format(
                "HORIZ" if p.DebugInfo.get('bottom_has_horizontal', False) else "vert",
                p.DebugInfo.get('bottom_connection_type', 'none'),
                "HORIZ" if p.DebugInfo.get('top_has_horizontal', False) else "vert",
                p.DebugInfo.get('top_connection_type', 'none')
            ))
        output.print_md("---")

    grouped_pipes = group_pipes_by_classification(pipes_data)

    tag_types = get_pipe_tag_types()

    if not tag_types:
        forms.alert("Nenhum tipo de Tag de Tubo carregado no projeto.", exitscript=True)

    window = OverheadWindow(grouped_pipes, tag_types, floor_count)
    result = window.ShowDialog()

    if not result:
        return

    selected_tags = window.selected_tags
    add_leaders = window.add_leaders
    smart_position = window.smart_position

    has_selection = any(t is not None for t in selected_tags.values())
    if not has_selection:
        forms.alert("Nenhum tipo de tag foi selecionado.", exitscript=True)

    t = Transaction(doc, "Overhead v2.7 - Aplicar Tags")
    t.Start()

    try:
        created_count = 0
        error_count = 0
        linked_count = 0
        created_tag_positions = []

        for classification, tag_info in selected_tags.items():
            if tag_info is None:
                continue

            tag_type_id = tag_info['id']
            pipes_in_group = grouped_pipes.get(classification, [])

            for p_data in pipes_in_group:
                try:
                    ref = p_data.get_reference_for_tagging()

                    if ref is None:
                        error_count += 1
                        continue

                    if smart_position:
                        tag_position = calculate_smart_tag_position(
                            p_data.CenterPoint, active_view, created_tag_positions
                        )
                    else:
                        tag_position = p_data.CenterPoint

                    tag = create_pipe_tag(active_view, ref, tag_type_id, tag_position, add_leaders)

                    if tag:
                        created_count += 1
                        created_tag_positions.append(tag_position)
                        if p_data.IsLinked:
                            linked_count += 1
                    else:
                        error_count += 1

                except:
                    error_count += 1

        t.Commit()

        msg = "Tags criadas: {}".format(created_count)
        if linked_count > 0:
            msg += "\n  - Em vinculos: {}".format(linked_count)
        if error_count > 0:
            msg += "\nErros: {}".format(error_count)

        forms.alert(msg, title="Overhead v2.7 - Concluido")

    except Exception as e:
        t.RollBack()
        forms.alert("Erro ao criar tags:\n{}".format(str(e)), title="Erro")


# ============================================================================
# ENTRY POINT
# ============================================================================
if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        output.print_md("**ERRO:**\n```\n{}\n```".format(traceback.format_exc()))
