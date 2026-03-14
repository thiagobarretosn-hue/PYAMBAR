# -*- coding: utf-8 -*-
"""
ParamForge - Pipeline core: categorias -> parametros -> valores -> ElementIds.
"""
from System.Collections.Generic import List

from Autodesk.Revit.DB import (
    FilteredElementCollector, ElementId, ElementMulticategoryFilter,
    ViewSchedule, StorageType, SharedParameterElement,
    Transaction, ViewDuplicateOption, ScheduleFilter, ScheduleFilterType,
    Level, Phase, Material
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


def get_parameters(doc, selected_cats, active_view_id=None, type_cache=None, elements=None):
    """Retorna parametros comuns entre as categorias selecionadas.
    Se elements fornecido, usa esses em vez de collector.
    """
    if type_cache is None:
        type_cache = {}
    selected_cat_ids = set([get_id_value(c.Id) for c in selected_cats])
    cat_params = {cid: set() for cid in selected_cat_ids}

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

    if elements is not None:
        source = elements
    else:
        if active_view_id:
            collector = FilteredElementCollector(doc, active_view_id)
        else:
            collector = FilteredElementCollector(doc)
        source = collector.WhereElementIsNotElementType()

    count_map = {cid: 0 for cid in selected_cat_ids}
    for elem in source:
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


def filter_nonempty_params(doc, selected_cats, param_names, active_view_id=None, type_cache=None, elements=None):
    """Remove params que so tem <Vazio> como valor (amostra de 50 elementos).
    Se elements fornecido, usa esses em vez de collector.
    """
    if type_cache is None:
        type_cache = {}
    if not param_names or not selected_cats:
        return param_names

    if elements is not None:
        sample = elements[:50]
    else:
        cat_ids = [c.Id for c in selected_cats]
        cat_filter = ElementMulticategoryFilter(List[ElementId](cat_ids))
        if active_view_id:
            collector = FilteredElementCollector(doc, active_view_id)
        else:
            collector = FilteredElementCollector(doc)
        all_elems = list(
            collector.WherePasses(cat_filter)
            .WhereElementIsNotElementType()
            .ToElements()
        )
        sample = all_elems[:50]

    has_value = set()
    for elem in sample:
        for p_name in param_names:
            if p_name in has_value:
                continue
            v = get_param_value(elem, p_name, type_cache)
            if v is not None and v != "<Vazio>":
                has_value.add(p_name)

    return [p for p in param_names if p in has_value]


def get_values(doc, selected_cats, selected_params, active_view_id=None, type_cache=None, elements=None):
    """
    Retorna {valor_combinado: [ElementIds]} para os parametros selecionados.
    Se elements fornecido, usa esses em vez de collector.
    """
    if type_cache is None:
        type_cache = {}

    if elements is not None:
        selected_cat_ids = set([get_id_value(c.Id) for c in selected_cats])
        source = [e for e in elements if e.Category and get_id_value(e.Category.Id) in selected_cat_ids]
    else:
        cat_ids = [c.Id for c in selected_cats]
        cat_filter = ElementMulticategoryFilter(List[ElementId](cat_ids))
        if active_view_id:
            collector = FilteredElementCollector(doc, active_view_id)
        else:
            collector = FilteredElementCollector(doc)
        source = collector.WherePasses(cat_filter).WhereElementIsNotElementType()

    values_map = {}
    for elem in source:
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


def _match_field_name(doc, param_id, guid, nome):
    """Match por GUID (shared) ou nome (GetDefinition + fallback)."""
    try:
        param_el = doc.GetElement(param_id)
        if guid and param_el and isinstance(param_el, SharedParameterElement):
            if str(param_el.GuidValue) == str(guid):
                return True
        if param_el and hasattr(param_el, "GetDefinition"):
            defn = param_el.GetDefinition()
            if defn and defn.Name == nome:
                return True
    except:
        pass
    return False


def _obter_ou_adicionar_field(doc, schedule_def, filtro_info):
    """Encontra ou adiciona field no schedule pelo nome/guid do parametro.

    Matching: GUID > GetDefinition().Name > GetName() (built-in fallback).
    Se nao existe no schedule, adiciona como hidden dos schedulable fields.
    """
    guid = filtro_info.get("guid")
    nome = filtro_info["nome"]

    # Fase 1: procurar nos fields ja existentes
    for i in range(schedule_def.GetFieldCount()):
        field = schedule_def.GetField(i)
        if _match_field_name(doc, field.ParameterId, guid, nome):
            return field
        # Fallback: GetName() para built-in params (Nivel, Level, etc.)
        try:
            if field.GetName() == nome:
                return field
        except:
            pass

    # Fase 2: procurar nos schedulable fields e adicionar como hidden
    for schedulable in schedule_def.GetSchedulableFields():
        try:
            matched = _match_field_name(doc, schedulable.ParameterId, guid, nome)
            # Fallback: GetName(doc) para built-in params
            if not matched:
                try:
                    matched = schedulable.GetName(doc) == nome
                except:
                    pass
            if matched:
                field = schedule_def.AddField(schedulable)
                field.IsHidden = True
                return field
        except:
            continue
    return None


def _resolve_element_id_by_name(doc, display_name):
    """Resolve nome display para ElementId (Level, Phase, Material, ElementType)."""
    # Level (caso mais comum: Nivel, Reference Level, etc.)
    for lvl in FilteredElementCollector(doc).OfClass(Level):
        try:
            if lvl.Name == display_name:
                return lvl.Id
        except:
            pass
    # Phase
    try:
        for phase in doc.Phases:
            if phase.Name == display_name:
                return phase.Id
    except:
        pass
    # Material
    for mat in FilteredElementCollector(doc).OfClass(Material):
        try:
            if mat.Name == display_name:
                return mat.Id
        except:
            pass
    # ElementType generico (Family Types, etc.)
    for et in FilteredElementCollector(doc).WhereElementIsElementType():
        try:
            if et.Name == display_name:
                return et.Id
        except:
            pass
    return None


def _create_schedule_filter(doc, field_id, filtro_info):
    """Cria ScheduleFilter usando o overload correto baseado no StorageType.

    StorageType.String    -> ScheduleFilter(id, type, string)
    StorageType.ElementId -> ScheduleFilter(id, type, ElementId)
    StorageType.Integer   -> ScheduleFilter(id, type, int)
    StorageType.Double    -> ScheduleFilter(id, type, double)
    """
    valor = filtro_info["valor"]
    storage = filtro_info.get("storage_type")
    ft = ScheduleFilterType.Equal

    # <Vazio> -> HasNoValue
    if valor == "<Vazio>":
        return ScheduleFilter(field_id, ScheduleFilterType.HasNoValue)

    # ElementId: resolver nome para ElementId real
    if storage == StorageType.ElementId:
        elem_id = _resolve_element_id_by_name(doc, valor)
        if elem_id:
            return ScheduleFilter(field_id, ft, elem_id)
        # Fallback: tentar como string (alguns campos aceitam)
        try:
            return ScheduleFilter(field_id, ft, valor)
        except:
            pass
        return None

    # Integer
    if storage == StorageType.Integer:
        try:
            return ScheduleFilter(field_id, ft, int(valor))
        except:
            # Fallback string
            return ScheduleFilter(field_id, ft, valor)

    # Double
    if storage == StorageType.Double:
        try:
            return ScheduleFilter(field_id, ft, float(valor))
        except:
            return ScheduleFilter(field_id, ft, valor)

    # String ou desconhecido
    return ScheduleFilter(field_id, ft, valor)


def validar_filtros_schedule(doc, template, filtro_infos, ef_transaction=None):
    """Valida quais parametros podem ser usados como filtro no schedule template.

    Retorna (filtraveis, nao_filtraveis) - listas de nomes.
    Duplica temporariamente o template para testar, depois desfaz.
    """
    if ef_transaction is None:
        import contextlib
        @contextlib.contextmanager
        def _raw_trans(d, name):
            t = Transaction(d, name)
            t.Start()
            try:
                yield
                t.Commit()
            except Exception:
                if t.HasStarted():
                    t.RollBack()
                raise
        ef_transaction = _raw_trans

    filtraveis = []
    nao_filtraveis = []

    try:
        with ef_transaction(doc, "PF - Validar filtros"):
            temp_id = template.Duplicate(ViewDuplicateOption.Duplicate)
            temp = doc.GetElement(temp_id)
            schedule_def = temp.Definition

            for filtro_info in filtro_infos:
                nome = filtro_info["nome"]
                campo = _obter_ou_adicionar_field(doc, schedule_def, filtro_info)
                if not campo:
                    nao_filtraveis.append(nome)
                    continue
                # CanFilterByValue verifica se o campo aceita filtro por valor
                if schedule_def.CanFilterByValue(campo.FieldId):
                    filtraveis.append(nome)
                else:
                    nao_filtraveis.append(nome)

            # Deletar o schedule temporario
            doc.Delete(temp_id)

    except Exception:
        pass

    return filtraveis, nao_filtraveis


def duplicar_e_filtrar(doc, template, filtro_infos, novo_nome, schedule_category=None, ef_transaction=None):
    """Duplica template e aplica filtros em AND logico.
    Pula campos nao-filtraveis (ja validados previamente).
    """
    if ef_transaction is None:
        import contextlib
        @contextlib.contextmanager
        def _raw_trans(d, name):
            t = Transaction(d, name)
            t.Start()
            try:
                yield
                t.Commit()
            except Exception:
                if t.HasStarted():
                    t.RollBack()
                raise
        ef_transaction = _raw_trans

    try:
        with ef_transaction(doc, "PF - Criar {}".format(novo_nome)):
            novo_id = template.Duplicate(ViewDuplicateOption.Duplicate)
            novo = doc.GetElement(novo_id)

            schedule_def = novo.Definition
            schedule_def.ClearFilters()

            for filtro_info in filtro_infos:
                campo = _obter_ou_adicionar_field(doc, schedule_def, filtro_info)
                if not campo:
                    continue  # campo nao encontrado - pular
                # Verificar se pode filtrar
                if not schedule_def.CanFilterByValue(campo.FieldId):
                    continue  # campo nao filtravel - pular
                filtro = _create_schedule_filter(doc, campo.FieldId, filtro_info)
                if not filtro:
                    continue  # filtro nao criado - pular
                try:
                    schedule_def.AddFilter(filtro)
                except:
                    continue  # fallback: pular se ainda falhar

            novo.Name = novo_nome

            if schedule_category:
                try:
                    param = novo.LookupParameter("Schedule Category")
                    if param and not param.IsReadOnly:
                        param.Set(schedule_category)
                except:
                    pass

            return novo

    except Exception:
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
