# -*- coding: utf-8 -*-
"""Leitura de ViewSchedule via ViewSchedule.Export().

Usa o proprio mecanismo de exportacao do Revit — respeita filtros de view,
grupos, subtotais, campos calculados e configuracoes de visibilidade,
exatamente como a planilha aparece no Revit.
"""

import csv
import io
import os
import tempfile

from Autodesk.Revit.DB import (
    ExportColumnHeaders,
    ExportTextQualifier,
    FilteredElementCollector,
    ViewSchedule,
    ViewScheduleExportOptions,
)


def get_all_schedules(doc):
    """Retorna lista de ViewSchedule validos, ordenados por nome."""
    schedules = []
    collector = FilteredElementCollector(doc).OfClass(ViewSchedule)
    for s in collector:
        if (not s.IsTitleblockRevisionSchedule
                and s.Definition
                and s.Definition.IsValidObject):
            schedules.append(s)
    return sorted(schedules, key=lambda s: s.Name)


def read_schedule(doc, schedule):
    """
    Exporta o schedule para CSV temporario via ViewSchedule.Export() e le o resultado.
    Respeita todos os filtros, agrupamentos e configuracoes de visibilidade da view.
    Retorna (headers: list[str], rows: list[list[str]]).
    """
    opts = ViewScheduleExportOptions()
    opts.ColumnHeaders = ExportColumnHeaders.OneRow
    opts.TextQualifier = ExportTextQualifier.DoubleQuote
    opts.FieldDelimiter = ','
    opts.Title = False
    opts.HeadersFootersBlanks = False

    tmp_dir = tempfile.gettempdir()
    sched_id = (schedule.Id.Value
                if hasattr(schedule.Id, 'Value')
                else schedule.Id.IntegerValue)
    tmp_name = 'exportpro_tmp_{}.csv'.format(sched_id)
    tmp_path = os.path.join(tmp_dir, tmp_name)

    try:
        schedule.Export(tmp_dir, tmp_name, opts)
        content = _read_file_safe(tmp_path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

    headers = []
    rows = []
    reader = csv.reader(io.StringIO(content))
    first = True
    for row in reader:
        if first:
            headers = row
            first = False
        else:
            rows.append(row)

    return headers, rows


def _read_file_safe(path):
    """Le arquivo tentando varias codificacoes — Revit exporta em encoding do sistema."""
    for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            with io.open(path, 'r', encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
    with open(path, 'rb') as f:
        return f.read().decode('latin-1', errors='replace')
