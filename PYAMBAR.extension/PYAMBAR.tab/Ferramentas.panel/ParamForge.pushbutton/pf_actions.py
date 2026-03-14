# -*- coding: utf-8 -*-
"""
ParamForge - Acoes: cores, filtros, legenda, schedules.
"""
import os
import random
import traceback

from System.Collections.Generic import List

from Autodesk.Revit.DB import (
    FilteredElementCollector, ElementId, OverrideGraphicSettings,
    ParameterFilterElement, ElementParameterFilter,
    LogicalAndFilter, FilterRule, ElementFilter,
    View, ViewType, ViewSchedule, ViewDuplicateOption,
    FilledRegion, FilledRegionType, FillPatternElement,
    CurveLoop, Line, XYZ, TextNote, TextNoteType,
    FamilySymbol, IndependentTag, Reference,
    TagMode, TagOrientation,
    Color, BuiltInParameter, StorageType,
    SharedParameterElement
)

from pf_helpers import (
    get_solid_fill, create_filter_rule, sanitize_view_name,
    nome_unico, get_id_value
)
from pf_core import (
    duplicar_e_filtrar, get_param_guid, get_schedule_templates
)


def apply_colors(doc, uidoc, checked_items, ef_transaction, all_views=False):
    """Aplica overrides de cor na vista ativa ou em todas as vistas."""
    solid = get_solid_fill(doc)
    if solid == ElementId.InvalidElementId:
        return "Padrao Solido nao encontrado."

    if all_views:
        target_views = _get_applicable_views(doc)
    else:
        target_views = [doc.ActiveView]

    with ef_transaction(doc, "ParamForge: Aplicar Cores"):
        for item in checked_items:
            ogs = OverrideGraphicSettings()
            c = item.GetRevitColor()
            ogs.SetSurfaceForegroundPatternId(solid)
            ogs.SetSurfaceForegroundPatternColor(c)
            ogs.SetCutForegroundPatternId(solid)
            ogs.SetCutForegroundPatternColor(c)
            for view in target_views:
                for eid in item.ElementIds:
                    try:
                        view.SetElementOverrides(eid, ogs)
                    except:
                        pass

    uidoc.RefreshActiveView()
    scope = "todas as vistas" if all_views else "vista ativa"
    return "Cores aplicadas em {}! ({} valores)".format(scope, len(checked_items))


def _get_applicable_views(doc):
    """Retorna vistas aplicaveis para overrides (exclui templates)."""
    target_views = []
    for v in FilteredElementCollector(doc).OfClass(View).ToElements():
        try:
            if v.IsTemplate:
                continue
            vt = v.ViewType
            if vt in [ViewType.FloorPlan, ViewType.CeilingPlan, ViewType.ThreeD,
                      ViewType.Section, ViewType.Elevation, ViewType.AreaPlan,
                      ViewType.EngineeringPlan, ViewType.Detail]:
                target_views.append(v)
        except:
            pass
    return target_views


def reset_colors(doc, uidoc, current_values, selected_cats, ef_transaction, all_views=False):
    """Reseta overrides de cor na vista ativa ou em todas as vistas."""
    if all_views:
        target_views = _get_applicable_views(doc)
    else:
        target_views = [doc.ActiveView]

    reset_count = 0
    blank = OverrideGraphicSettings()

    with ef_transaction(doc, "ParamForge: Reset"):
        if current_values and len(current_values) > 0:
            for item in current_values:
                for eid in item.ElementIds:
                    for view in target_views:
                        try:
                            view.SetElementOverrides(eid, blank)
                            reset_count += 1
                        except:
                            pass
        elif selected_cats:
            from Autodesk.Revit.DB import ElementMulticategoryFilter
            cat_ids = List[ElementId]([c.Id for c in selected_cats])
            for view in target_views:
                try:
                    coll = FilteredElementCollector(doc, view.Id)\
                        .WherePasses(ElementMulticategoryFilter(cat_ids))\
                        .ToElementIds()
                    for eid in coll:
                        try:
                            view.SetElementOverrides(eid, blank)
                            reset_count += 1
                        except:
                            pass
                except:
                    pass
        else:
            # Sem selecao: resetar TODOS os elementos nas vistas alvo
            for view in target_views:
                try:
                    coll = FilteredElementCollector(doc, view.Id)\
                        .WhereElementIsNotElementType().ToElementIds()
                    for eid in coll:
                        try:
                            view.SetElementOverrides(eid, blank)
                            reset_count += 1
                        except:
                            pass
                except:
                    pass

    uidoc.RefreshActiveView()
    scope = "todas as vistas" if all_views else "vista ativa"
    return "Resetado em {}! ({} elementos)".format(scope, reset_count)


def create_view_filters(doc, uidoc, checked_items, selected_param_names,
                         selected_cats, all_views, rvt_year, ef_transaction):
    """Cria filtros de vista com cores para os valores marcados."""
    cat_ids = List[ElementId]([c.Id for c in selected_cats])
    solid = get_solid_fill(doc)

    first_elem_id = checked_items[0].ElementIds[0]
    first_elem = doc.GetElement(first_elem_id)

    params = {}
    for p_name in selected_param_names:
        p = first_elem.LookupParameter(p_name)
        if not p:
            try:
                p = doc.GetElement(first_elem.GetTypeId()).LookupParameter(p_name)
            except:
                pass
        if p:
            params[p_name] = p

    if len(params) != len(selected_param_names):
        return "Nao foi possivel encontrar os parametros selecionados."

    with ef_transaction(doc, "ParamForge: Criar Filtros"):
        for item in checked_items:
            val_parts = item.Value.split(" | ")
            if len(val_parts) != len(selected_param_names):
                continue

            rules = List[FilterRule]()
            for i, p_name in enumerate(selected_param_names):
                param = params[p_name]
                val = val_parts[i]
                rule = create_filter_rule(doc, param, val, rvt_year)
                if rule:
                    rules.Add(rule)

            if rules.Count == 0:
                continue

            if rules.Count == 1:
                final_filter = ElementParameterFilter(rules[0])
            else:
                elem_filters = List[ElementFilter]()
                for r in rules:
                    elem_filters.Add(ElementParameterFilter(r))
                final_filter = LogicalAndFilter(elem_filters)

            p_names_str = "_".join(selected_param_names)
            safe_val = "".join([c for c in item.Value if c.isalnum() or c in (' ', '_', '-')])
            f_name = "{} = {}".format(p_names_str, safe_val)

            f_elem = None
            exist = FilteredElementCollector(doc).OfClass(ParameterFilterElement)
            for e in exist:
                if e.Name == f_name:
                    f_elem = e
                    break

            if not f_elem:
                try:
                    f_elem = ParameterFilterElement.Create(doc, f_name, cat_ids, final_filter)
                except:
                    continue
            else:
                try:
                    f_elem.SetCategories(cat_ids)
                except:
                    pass

            ogs = OverrideGraphicSettings()
            c = item.GetRevitColor()
            ogs.SetSurfaceForegroundPatternId(solid)
            ogs.SetSurfaceForegroundPatternColor(c)
            ogs.SetCutForegroundPatternId(solid)
            ogs.SetCutForegroundPatternColor(c)

            if all_views:
                target_views = []
                for v in FilteredElementCollector(doc).OfClass(View).ToElements():
                    try:
                        if v.IsTemplate:
                            continue
                        vt = v.ViewType
                        if vt in [ViewType.FloorPlan, ViewType.CeilingPlan, ViewType.ThreeD,
                                  ViewType.Section, ViewType.Elevation, ViewType.AreaPlan,
                                  ViewType.EngineeringPlan, ViewType.Detail]:
                            target_views.append(v)
                    except:
                        pass
            else:
                target_views = [doc.ActiveView]

            for view in target_views:
                try:
                    view.AddFilter(f_elem.Id)
                    view.SetFilterVisibility(f_elem.Id, True)
                    view.SetFilterOverrides(f_elem.Id, ogs)
                except:
                    pass

    scope = "todas as vistas" if all_views else "vista ativa"
    return "Filtros criados em {}! ({} valores)".format(scope, len(checked_items))


def create_legend(doc, uidoc, checked_items, config, ef_transaction):
    """Cria legenda com FilledRegions + Tags."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    tag_family_path = os.path.join(script_dir, "TAG Legenda items.rfa")
    tag_family_loaded = False

    for symbol in FilteredElementCollector(doc).OfClass(FamilySymbol):
        try:
            if symbol.Family.Name == "TAG Legenda items":
                tag_family_loaded = True
                break
        except:
            pass

    if not tag_family_loaded:
        if os.path.exists(tag_family_path):
            try:
                with ef_transaction(doc, "Importar Familia Tag"):
                    if not doc.LoadFamily(tag_family_path):
                        return "ERRO: LoadFamily retornou False"
            except Exception as e:
                return "ERRO ao importar familia: {}".format(str(e))
        else:
            return "ERRO: TAG Legenda items.rfa nao encontrado em {}".format(script_dir)

    if config["order"] == "alpha":
        checked_items = sorted(checked_items, key=lambda x: x.Value)
    elif config["order"] == "count":
        checked_items = sorted(checked_items, key=lambda x: x.Count, reverse=True)

    solid = get_solid_fill(doc)
    if solid == ElementId.InvalidElementId:
        return "Padrao solido nao encontrado."

    # Buscar legendas existentes
    existing_legends = []
    for v in FilteredElementCollector(doc).OfClass(View):
        try:
            if v.ViewType == ViewType.Legend and not v.IsTemplate:
                existing_legends.append(v)
        except:
            pass

    template_view = None
    if not existing_legends:
        return "Nenhuma legenda existente no projeto. Crie uma legenda vazia primeiro (View > Legends > Legend) e execute novamente."
    else:
        template_view = existing_legends[0]

    def inches_to_feet(inches):
        return inches / 12.0

    with ef_transaction(doc, "ParamForge: Criar Legenda"):
        new_view_id = template_view.Duplicate(ViewDuplicateOption.Duplicate)
        view = doc.GetElement(new_view_id)

        try:
            view.Name = config["title"]
        except:
            view.Name = config["title"] + "_{}".format(random.randint(1, 999))

        try:
            view.Scale = 12
        except:
            pass

        # Limpar conteudo existente
        elements_to_delete = []
        for elem in FilteredElementCollector(doc, view.Id).ToElements():
            if isinstance(elem, FilledRegion) or isinstance(elem, TextNote):
                elements_to_delete.append(elem.Id)
        if elements_to_delete:
            try:
                doc.Delete(List[ElementId](elements_to_delete))
            except:
                pass

        box_width = inches_to_feet(config["width"])
        box_height = inches_to_feet(config["height"])
        text_offset = inches_to_feet(config["offset"])
        line_spacing = inches_to_feet(config["spacing"])
        title_spacing = inches_to_feet(config["title_spacing"])
        border_offset = inches_to_feet(config["border_offset"])

        # CS_Border_White
        border_fr_type = None
        for frt in FilteredElementCollector(doc).OfClass(FilledRegionType):
            try:
                if frt.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString() == "CS_Border_White":
                    border_fr_type = frt
                    break
            except:
                pass
        if not border_fr_type:
            temp = FilteredElementCollector(doc).OfClass(FilledRegionType).FirstElement()
            if temp:
                border_fr_type = temp.Duplicate("CS_Border_White")
                border_fr_type.ForegroundPatternId = solid
                border_fr_type.ForegroundPatternColor = Color(255, 255, 255)
                border_fr_type.BackgroundPatternId = ElementId.InvalidElementId
                try:
                    border_fr_type.IsMasking = False
                except:
                    pass

        border_top = -inches_to_feet(3.0)
        title_y = border_top - inches_to_feet(1.0)
        title_x = border_offset + (box_width / 2.0)

        start_y = title_y - title_spacing
        y = start_y
        max_tag_x = border_offset + box_width + text_offset

        regions_created = 0
        texts_created = 0

        # Cache: FilledRegionTypes e tag symbol (evitar collectors repetidos)
        fr_type_cache = {}
        for frt in FilteredElementCollector(doc).OfClass(FilledRegionType):
            try:
                name = frt.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString()
                fr_type_cache[name] = frt
            except:
                pass
        fr_base_type = FilteredElementCollector(doc).OfClass(FilledRegionType).FirstElement()

        tag_symbol = None
        for symbol in FilteredElementCollector(doc).OfClass(FamilySymbol):
            try:
                if symbol.Family.Name == "TAG Legenda items":
                    tag_symbol = symbol
                    break
            except:
                pass

        for item in checked_items:
            filled_region = None
            fr_name = "CS_RGB_{}_{}_{}".format(item.R, item.G, item.B)
            fr_type = fr_type_cache.get(fr_name)

            if not fr_type and fr_base_type:
                try:
                    fr_type = fr_base_type.Duplicate(fr_name)
                    fr_type.ForegroundPatternId = solid
                    fr_type.ForegroundPatternColor = item.GetRevitColor()
                    fr_type.BackgroundPatternId = ElementId.InvalidElementId
                    fr_type_cache[fr_name] = fr_type
                except:
                    pass

            if fr_type:
                x_start = border_offset
                x_end = border_offset + box_width

                loop = CurveLoop()
                loop.Append(Line.CreateBound(XYZ(x_start, y, 0), XYZ(x_end, y, 0)))
                loop.Append(Line.CreateBound(XYZ(x_end, y, 0), XYZ(x_end, y - box_height, 0)))
                loop.Append(Line.CreateBound(XYZ(x_end, y - box_height, 0), XYZ(x_start, y - box_height, 0)))
                loop.Append(Line.CreateBound(XYZ(x_start, y - box_height, 0), XYZ(x_start, y, 0)))

                try:
                    filled_region = FilledRegion.Create(doc, fr_type.Id, view.Id, List[CurveLoop]([loop]))
                    regions_created += 1

                    text_content = item.Value
                    if config["show_count"]:
                        text_content = "{} ({})".format(item.Value, item.Count)

                    try:
                        cp = filled_region.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                        if cp and not cp.IsReadOnly:
                            cp.Set(text_content)
                    except:
                        pass
                except:
                    pass

            if filled_region:
                doc.Regenerate()
                try:
                    if tag_symbol:
                        if not tag_symbol.IsActive:
                            tag_symbol.Activate()

                        tag_x = border_offset + box_width + text_offset
                        tag_y = y - (box_height / 2.0)

                        try:
                            new_tag = IndependentTag.Create(
                                doc, view.Id, Reference(filled_region),
                                False, TagMode.TM_ADDBY_CATEGORY,
                                TagOrientation.Horizontal, XYZ(tag_x, tag_y, 0)
                            )
                            if new_tag:
                                new_tag.ChangeTypeId(tag_symbol.Id)
                                texts_created += 1
                                doc.Regenerate()
                                try:
                                    tag_bbox = new_tag.get_BoundingBox(view)
                                    if tag_bbox and tag_bbox.Max.X > max_tag_x:
                                        max_tag_x = tag_bbox.Max.X
                                except:
                                    pass
                        except:
                            pass
                except:
                    pass

            y -= (box_height + line_spacing)

        # Borda
        if border_fr_type:
            try:
                border_right_temp = max_tag_x + inches_to_feet(2.0)
                border_bottom = y - inches_to_feet(config["border_bottom"])
                border_left = 0.0

                border_loop = CurveLoop()
                border_loop.Append(Line.CreateBound(XYZ(border_left, border_top, 0), XYZ(border_right_temp, border_top, 0)))
                border_loop.Append(Line.CreateBound(XYZ(border_right_temp, border_top, 0), XYZ(border_right_temp, border_bottom, 0)))
                border_loop.Append(Line.CreateBound(XYZ(border_right_temp, border_bottom, 0), XYZ(border_left, border_bottom, 0)))
                border_loop.Append(Line.CreateBound(XYZ(border_left, border_bottom, 0), XYZ(border_left, border_top, 0)))

                border_region = FilledRegion.Create(doc, border_fr_type.Id, view.Id, List[CurveLoop]([border_loop]))

                cp = border_region.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                if cp and not cp.IsReadOnly:
                    cp.Set(config["title"])
                doc.Regenerate()

                # Tag do titulo (usa tag_symbol ja cacheado)
                title_right_x = 0.0

                if tag_symbol:
                    if not tag_symbol.IsActive:
                        tag_symbol.Activate()
                        doc.Regenerate()

                    temp_pos = XYZ(border_left + inches_to_feet(1.0), border_top - inches_to_feet(0.5), 0)
                    title_tag_temp = IndependentTag.Create(
                        doc, view.Id, Reference(border_region),
                        False, TagMode.TM_ADDBY_CATEGORY,
                        TagOrientation.Horizontal, temp_pos
                    )
                    title_tag_temp.ChangeTypeId(tag_symbol.Id)
                    doc.Regenerate()
                    title_tag_temp.TagHeadPosition = XYZ(title_x, title_y, 0)
                    doc.Regenerate()

                    try:
                        tbbox = title_tag_temp.get_BoundingBox(view)
                        if tbbox:
                            title_right_x = tbbox.Max.X
                    except:
                        pass

                # Calcular borda final
                if title_right_x > max_tag_x:
                    border_right = title_right_x + border_offset
                else:
                    border_right = max_tag_x + inches_to_feet(1.0)

                largura_total = border_right - border_left
                title_x = border_left + (largura_total / 2.0)

                # Deletar temp e recriar
                doc.Delete(border_region.Id)
                doc.Regenerate()

                final_loop = CurveLoop()
                final_loop.Append(Line.CreateBound(XYZ(border_left, border_top, 0), XYZ(border_right, border_top, 0)))
                final_loop.Append(Line.CreateBound(XYZ(border_right, border_top, 0), XYZ(border_right, border_bottom, 0)))
                final_loop.Append(Line.CreateBound(XYZ(border_right, border_bottom, 0), XYZ(border_left, border_bottom, 0)))
                final_loop.Append(Line.CreateBound(XYZ(border_left, border_bottom, 0), XYZ(border_left, border_top, 0)))

                final_border = FilledRegion.Create(doc, border_fr_type.Id, view.Id, List[CurveLoop]([final_loop]))
                fcp = final_border.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                if fcp and not fcp.IsReadOnly:
                    fcp.Set(config["title"])
                doc.Regenerate()

                if tag_symbol:
                    temp_pos2 = XYZ(border_left + inches_to_feet(1.0), border_top - inches_to_feet(0.5), 0)
                    title_tag = IndependentTag.Create(
                        doc, view.Id, Reference(final_border),
                        False, TagMode.TM_ADDBY_CATEGORY,
                        TagOrientation.Horizontal, temp_pos2
                    )
                    title_tag.ChangeTypeId(tag_symbol.Id)
                    doc.Regenerate()
                    title_tag.TagHeadPosition = XYZ(title_x, title_y, 0)
                    doc.Regenerate()
                    try:
                        tbbox2 = title_tag.get_BoundingBox(view)
                        if tbbox2:
                            tw = tbbox2.Max.X - tbbox2.Min.X
                            cx = title_x - (tw / 2.0)
                            title_tag.TagHeadPosition = XYZ(cx, title_y, 0)
                            doc.Regenerate()
                    except:
                        pass

            except Exception as e:
                print("Erro ao criar borda: {}".format(str(e)))

    try:
        uidoc.ActiveView = view
    except:
        pass

    return "Legenda criada! ({} itens)".format(len(checked_items))
