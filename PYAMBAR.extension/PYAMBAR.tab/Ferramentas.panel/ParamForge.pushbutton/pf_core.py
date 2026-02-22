# -*- coding: utf-8 -*-
"""
ParamForge - Pipeline core: categorias -> parametros -> valores -> ElementIds.
"""
from System.Collections.Generic import List

from Autodesk.Revit.DB import (
    FilteredElementCollector, ElementId, ElementMulticategoryFilter,
    ViewSchedule, StorageType, SharedParameterElement,
    Transaction, ViewDuplicateOption, ScheduleFilter, ScheduleFilterType
)

from pf_helpers import get_id_value, is_useful_category, get_param_value


def get_categories(doc, active_view_id=None):
    """Retorna categorias de modelo com elementos, excluindo sistema/DWG/links."""
    if active_view_id:
        collector = FilteredElementCollector(doc, active_view_id)
    else:
        collector = FilteredElementCollector(doc)
    collector = collector.WhereElementIsNotElementType()

    categories = []
    unique_cats = set()
    for elem in collector:
        cat = elem.Category
        if cat:
            cat_id_val = get_id_value(cat.Id)
            if cat_id_val not in unique_cats and is_useful_category(cat):
                unique_cats.add(cat_id_val)
                categories.append(cat)
    categories.sort(key=lambda x: x.Name)
    return categories


def get_categories_from_elements(elements):
    """Retorna categorias unicas de uma lista de elementos."""
    categories = []
    unique_cats = set()
    for elem in elements:
        cat = elem.Category
        if cat:
            cat_id_val = get_id_value(cat.Id)
            if cat_id_val not in unique_cats and is_useful_category(cat):
                unique_cats.add(cat_id_val)
                categories.append(cat)
    categories.sort(key=lambda x: x.Name)
    return categories


def get_parameters(doc, selected_cats, active_view_id=None, type_cache=None):
    """Retorna parametros comuns entre as categorias selecionadas."""
    if type_cache is None:
        type_cache = {}
    selected_cat_ids = set([get_id_value(c.Id) for c in selected_cats])
    cat_params = {cid: set() for cid in selected_cat_ids}

    if active_view_id:
        collector = FilteredElementCollector(doc, active_view_id)
    else:
        collector = FilteredElementCollector(doc)
    collector = collector.WhereElementIsNotElementType()

    def extract_params(element, target_set):
        for p in element.Parameters:
            target_set.add(p.Definition.Name)
        try:
            type_id = element.GetTypeId()
            if type_id != ElementId.InvalidElementId:
                if type_id not in type_cache:
                    et = doc.GetElement(type_id)
                    if et:
                        type_cache[type_id] = et
                et = type_cache.get(type_id)
                if et:
                    for p in et.Parameters:
                        target_set.add(p.Definition.Name)
        except:
            pass

    count_map = {cid: 0 for cid in selected_cat_ids}
    for elem in collector:
        if elem.Category:
            cid = get_id_value(elem.Category.Id)
            if cid in selected_cat_ids and count_map[cid] < 20:
                extract_params(elem, cat_params[cid])
                count_map[cid] += 1

    common_params = None
    for cid in selected_cat_ids:
        if count_map[cid] > 0:
            if common_params is None:
                common_params = cat_params[cid]
            else:
                common_params = common_params.intersection(cat_params[cid])

    if common_params is None:
        common_params = []
    return sorted(list(common_params))


def filter_nonempty_params(doc, selected_cats, param_names, active_view_id=None, type_cache=None):
    """Remove params que so tem <Vazio> como valor (amostra de 50 elementos)."""
    if type_cache is None:
        type_cache = {}
    if not param_names or not selected_cats:
        return param_names

    cat_ids = [c.Id for c in selected_cats]
    cat_filter = ElementMulticategoryFilter(List[ElementId](cat_ids))
    if active_view_id:
        collector = FilteredElementCollector(doc, active_view_id)
    else:
        collector = FilteredElementCollector(doc)
    elements = list(
        collector.WherePasses(cat_filter)
        .WhereElementIsNotElementType()
        .ToElements()
    )
    sample = elements[:50]

    has_value = set()
    for elem in sample:
        for p_name in param_names:
            if p_name in has_value:
                continue
            v = get_param_value(elem, p_name, type_cache)
            if v is not None and v != "<Vazio>":
                has_value.add(p_name)

    return [p for p in param_names if p in has_value]


def get_values(doc, selected_cats, selected_params, active_view_id=None, type_cache=None):
    """
    Retorna {valor_combinado: [ElementIds]} para os parametros selecionados.
    """
    if type_cache is None:
        type_cache = {}
    cat_ids = [c.Id for c in selected_cats]
    cat_filter = ElementMulticategoryFilter(List[ElementId](cat_ids))

    if active_view_id:
        collector = FilteredElementCollector(doc, active_view_id)
    else:
        collector = FilteredElementCollector(doc)
    collector = collector.WherePasses(cat_filter).WhereElementIsNotElementType()

    values_map = {}
    for elem in collector:
        val_parts = []
        valid = False
        for p_name in selected_params:
            v = get_param_value(elem, p_name, type_cache)
            if v is not None:
                val_parts.append(v)
                valid = True
            else:
                val_parts.append("-")

        if not valid:
            continue

        full_val = " | ".join(val_parts)
        if full_val not in values_map:
            values_map[full_val] = []
        values_map[full_val].append(elem.Id)

    return values_map


def scan_view_filters(doc):
    """Mapeia cores de filtros ja aplicados na vista ativa."""
    view = doc.ActiveView
    filter_colors = {}
    try:
        filters = view.GetFilters()
        for fid in filters:
            felem = doc.GetElement(fid)
            ogs = view.GetFilterOverrides(fid)
            color = ogs.SurfaceForegroundPatternColor
            if color.IsValid:
                filter_colors[felem.Name] = (color.Red, color.Green, color.Blue)
    except:
        pass
    return filter_colors


# ============================================================================
# SCHEDULE HELPERS
# ============================================================================

def get_schedule_templates(doc, cat_id_val=None):
    """
    Retorna schedules filtrados por categoria.
    Se cat_id_val=None, retorna todos.
    """
    resultado = []
    for s in FilteredElementCollector(doc).OfClass(ViewSchedule):
        try:
            if s.IsTemplate:
                continue
            if cat_id_val is not None:
                if get_id_value(s.Definition.CategoryId) != cat_id_val:
                    continue
            resultado.append(s)
        except:
            continue
    return sorted(resultado, key=lambda x: x.Name)


def get_categories_with_schedules(doc):
    """
    Retorna dict {cat_id_val: [schedules]} para categorias que tem templates.
    """
    result = {}
    for s in FilteredElementCollector(doc).OfClass(ViewSchedule):
        try:
            if s.IsTemplate:
                continue
            cat_id_val = get_id_value(s.Definition.CategoryId)
            if cat_id_val not in result:
                result[cat_id_val] = []
            result[cat_id_val].append(s)
        except:
            continue
    return result


def _obter_ou_adicionar_field(doc, schedule_def, filtro_info):
    """Encontra ou adiciona field no schedule pelo nome/guid do parametro."""
    guid = filtro_info.get("guid")
    nome = filtro_info["nome"]

    def _match(field):
        try:
            param_el = doc.GetElement(field.ParameterId)
            if guid and isinstance(param_el, SharedParameterElement):
                return param_el.GuidValue == guid
            if param_el and hasattr(param_el, "GetDefinition"):
                defn = param_el.GetDefinition()
                return defn and defn.Name == nome
        except:
            pass
        return False

    for i in range(schedule_def.GetFieldCount()):
        if _match(schedule_def.GetField(i)):
            return schedule_def.GetField(i)

    for schedulable in schedule_def.GetSchedulableFields():
        try:
            param_el = doc.GetElement(schedulable.ParameterId)
            matched = False
            if guid and isinstance(param_el, SharedParameterElement):
                matched = param_el.GuidValue == guid
            elif param_el and hasattr(param_el, "GetDefinition"):
                defn = param_el.GetDefinition()
                matched = defn and defn.Name == nome
            if matched:
                field = schedule_def.AddField(schedulable)
                field.IsHidden = True
                return field
        except:
            continue
    return None


def duplicar_e_filtrar(doc, template, filtro_infos, novo_nome, schedule_category=None):
    """Duplica template e aplica filtros em AND logico."""
    t = Transaction(doc, "PF - Criar {}".format(novo_nome))
    t.Start()
    try:
        novo_id = template.Duplicate(ViewDuplicateOption.Duplicate)
        novo = doc.GetElement(novo_id)

        schedule_def = novo.Definition
        schedule_def.ClearFilters()

        for filtro_info in filtro_infos:
            campo = _obter_ou_adicionar_field(doc, schedule_def, filtro_info)
            if not campo:
                t.RollBack()
                return None
            filtro = ScheduleFilter(campo.FieldId, ScheduleFilterType.Equal, filtro_info["valor"])
            schedule_def.AddFilter(filtro)

        novo.Name = novo_nome

        # Schedule Category para organizar no Project Browser
        if schedule_category:
            try:
                param = novo.LookupParameter("Schedule Category")
                if param and not param.IsReadOnly:
                    param.Set(schedule_category)
            except:
                pass

        t.Commit()
        return novo

    except Exception:
        if t.HasStarted():
            t.RollBack()
        return None


def get_param_guid(doc, param):
    """Retorna GUID do parametro shared ou None."""
    try:
        param_el = doc.GetElement(param.Definition.Id)
        if isinstance(param_el, SharedParameterElement):
            return param_el.GuidValue
    except:
        pass
    return None
