# -*- coding: utf-8 -*-
"""
ParamForge - Helpers (cores, ElementId, parametros, nomes, categorias).
"""
import contextlib

from Autodesk.Revit.DB import (
    FilteredElementCollector, FillPatternElement, ElementId,
    StorageType, ParameterFilterRuleFactory, Material,
    NamingUtils, ViewSchedule, CategoryType,
    Transaction, TransactionStatus
)


@contextlib.contextmanager
def ef_transaction(doc, name):
    """Context manager para Transaction do Revit (usavel em External Events)."""
    t = Transaction(doc, name)
    t.Start()
    try:
        yield t
        t.Commit()
    except Exception:
        if t.GetStatus() == TransactionStatus.Started:
            t.RollBack()
        raise


def get_id_value(element_id):
    if hasattr(element_id, 'Value'):
        return element_id.Value
    return element_id.IntegerValue


def get_solid_fill(doc):
    patterns = FilteredElementCollector(doc).OfClass(FillPatternElement)
    for p in patterns:
        if p.GetFillPattern().IsSolidFill:
            return p.Id
    first = patterns.FirstElementId()
    return first if first else ElementId.InvalidElementId


# IDs de categorias excluidas
CAT_EXCLUDED = set([
    -2000278, -1,
])

_EXCLUDED_CATS = [
    "OST_RoomSeparationLines", "OST_Cameras", "OST_CurtainGrids",
    "OST_Elev", "OST_Grids", "OST_IOSModelGroups", "OST_Views",
    "OST_SectionBox", "OST_ShaftOpening", "OST_BeamAnalytical",
    "OST_StructuralFramingOpening", "OST_MEPSpaceSeparationLines",
    "OST_DuctSystem", "OST_Lines", "OST_PipingSystem",
    "OST_Matchline", "OST_CenterLines", "OST_CurtainGridsRoof",
    "OST_SWallRectOpening",
    # Anotacoes e sistema
    "OST_RvtLinks", "OST_Levels", "OST_PointClouds",
    "OST_DetailComponents", "OST_Rooms", "OST_Areas",
    "OST_MEPSpaces", "OST_Mass", "OST_Sheets",
    "OST_GenericAnnotation", "OST_TitleBlocks",
    "OST_AreaSchemes", "OST_Divisions",
]


def _init_excluded():
    from Autodesk.Revit.DB import BuiltInCategory
    for name in _EXCLUDED_CATS:
        try:
            bic = getattr(BuiltInCategory, name)
            CAT_EXCLUDED.add(int(bic))
        except Exception as e:
            pass

_init_excluded()


def is_useful_category(cat):
    """Filtra categorias uteis: Model elements, top-level, sem DWGs/links/anotacoes."""
    try:
        if cat.CategoryType != CategoryType.Model:
            return False
        # Excluir subcategorias (Linha de centro, Hidden Lines, etc.)
        if cat.Parent is not None:
            return False
        cat_id_val = get_id_value(cat.Id)
        if cat_id_val in CAT_EXCLUDED:
            return False
        name = cat.Name
        if not name:
            return False
        # Excluir layers DWG importados (nomes com extensao ou prefixo numerico)
        name_lower = name.lower()
        if any(ext in name_lower for ext in ['.dwg', '.dxf', '.dgn', '.sat', '.ifc']):
            return False
        # Padroes tipo "134 - ARCH - GROUND FLOOR PLAN"
        parts = name.split(' ')
        if parts:
            first = parts[0].strip('-').strip()
            if first.isdigit() and len(first) <= 5:
                return False
        return True
    except Exception as e:
        return False


def create_filter_rule(doc, param, value_string, rvt_year):
    """Cria FilterRule baseada no StorageType do parametro."""
    try:
        param_id = param.Id
        storage = param.StorageType

        if value_string == "<Vazio>":
            return None

        if storage == StorageType.String:
            if rvt_year >= 2023:
                return ParameterFilterRuleFactory.CreateEqualsRule(param_id, value_string)
            else:
                return ParameterFilterRuleFactory.CreateEqualsRule(param_id, value_string, True)

        elif storage == StorageType.ElementId:
            found_id = None
            for mat in FilteredElementCollector(doc).OfClass(Material):
                if mat.Name == value_string:
                    found_id = mat.Id
                    break
            if not found_id:
                for et in FilteredElementCollector(doc).WhereElementIsElementType():
                    if hasattr(et, 'Name') and et.Name == value_string:
                        found_id = et.Id
                        break
            if found_id:
                if rvt_year >= 2023:
                    return ParameterFilterRuleFactory.CreateEqualsRule(param_id, found_id)
                else:
                    return ParameterFilterRuleFactory.CreateEqualsRule(param_id, found_id, True)
            return None

        elif storage == StorageType.Double:
            try:
                val = float(value_string)
                if rvt_year >= 2023:
                    return ParameterFilterRuleFactory.CreateEqualsRule(param_id, val, 0.0001)
                else:
                    return ParameterFilterRuleFactory.CreateEqualsRule(param_id, val, 0.0001, True)
            except ValueError:
                return None

        elif storage == StorageType.Integer:
            try:
                val = int(value_string)
                if rvt_year >= 2023:
                    return ParameterFilterRuleFactory.CreateEqualsRule(param_id, val)
                else:
                    return ParameterFilterRuleFactory.CreateEqualsRule(param_id, val, True)
            except ValueError:
                return None

        return None
    except Exception as e:
        return None


def sanitize_view_name(name):
    _PROHIBITED = ['/', '\\', ':', '*', '?', '"', '<', '>', '|',
                    '{', '}', '[', ']', ';', '~', '`']
    result = name
    for ch in _PROHIBITED:
        result = result.replace(ch, '-')
    while '--' in result:
        result = result.replace('--', '-')
    result = result.strip('-. ')
    if not result:
        result = "Schedule"
    try:
        if not NamingUtils.IsValidName(result):
            cleaned = ""
            for ch in result:
                if ch.isalnum() or ch in (' ', '-', '_'):
                    cleaned += ch
            result = cleaned.strip() or "Schedule"
    except Exception as e:
        pass
    return result


def nome_unico(doc, base):
    existentes = set()
    for s in FilteredElementCollector(doc).OfClass(ViewSchedule):
        try:
            existentes.add(s.Name)
        except Exception as e:
            pass
    if base not in existentes:
        return base
    i = 2
    while "{} ({})".format(base, i) in existentes:
        i += 1
    return "{} ({})".format(base, i)


DISCIPLINE_KEYWORDS = {
    "Piping": [
        "pipe", "tubo", "tubula", "plumbing", "hidro", "sanit",
        "esgoto", "flex pipe", "pipe fitting", "pipe accessor",
        "sprinkler", "peça", "pecas", "hidráulic", "hydraulic",
    ],
    "Mechanical": [
        "duct", "duto", "hvac", "mechanical", "mecânic", "mecanico",
        "air terminal", "terminal de ar", "flex duct",
        "duct fitting", "duct accessor", "duct lining", "duct insul",
    ],
    "Electrical": [
        "electri", "elétric", "eletric", "cable tray", "conduit",
        "eletroduto", "lighting", "ilumina", "fire alarm", "alarme",
        "communication", "data device", "telephone", "security",
        "nurse call",
    ],
    "Structure": [
        "structur", "estrutur",
    ],
}


def get_discipline(cat):
    """Retorna disciplina da categoria: Piping, Mechanical, Electrical, Structure, Architecture."""
    name_lower = cat.Name.lower()
    for disc, keywords in DISCIPLINE_KEYWORDS.items():
        for kw in keywords:
            if kw in name_lower:
                return disc
    return "Architecture"


def get_param_value(elem, param_name, type_cache):
    """Le valor de parametro (instance ou type). Retorna string ou '<Vazio>'."""
    param = elem.LookupParameter(param_name)
    if not param:
        try:
            type_id = elem.GetTypeId()
            if type_id != ElementId.InvalidElementId:
                if type_id not in type_cache:
                    type_cache[type_id] = elem.Document.GetElement(type_id)
                t = type_cache[type_id]
                if t:
                    param = t.LookupParameter(param_name)
        except Exception as e:
            pass
    if not param:
        for p in elem.Parameters:
            if p.Definition.Name == param_name:
                param = p
                break
    if not param:
        return None
    if param.StorageType == StorageType.String:
        v = param.AsString()
    else:
        v = param.AsValueString()
    return v if v and v.strip() != "" else "<Vazio>"
