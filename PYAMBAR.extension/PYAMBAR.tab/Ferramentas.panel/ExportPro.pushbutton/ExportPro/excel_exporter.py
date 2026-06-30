# -*- coding: utf-8 -*-
"""Exporta schedules para .xlsx via OOXML manual (zipfile + XML strings).
Sem dependencias externas — funciona em IronPython 3 e CPython."""

import math
import re
import zipfile
import io

# Caracteres invalidos em XML 1.0 (exceto TAB 0x09, LF 0x0A, CR 0x0D)
_XML_INVALID = re.compile(
    u'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F\uD800-\uDFFF￾￿]'
)

_REL_BASE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def export_excel(schedules_data, file_path, include_headers=True, stacked=False, tab_name=None):
    """
    schedules_data: list de dict com chaves name, headers, rows e
                    opcionalmente include_header (bool, sobrescreve global).
    stacked: True = tudo em uma unica aba empilhado; False = aba por schedule.
    tab_name: nome da aba quando stacked=True (None usa 'Dados').
    """
    if stacked:
        data = _build_ooxml_stacked(schedules_data, include_headers, tab_name=tab_name)
    else:
        sheets = []
        seen = {}
        for s in schedules_data:
            inc = s.get('include_header', include_headers)
            base = _sanitize_name(s['name'])
            if base in seen:
                seen[base] += 1
                name = _sanitize_name('{}-{}'.format(s['name'], seen[base]))
            else:
                seen[base] = 1
                name = base
            sheets.append((
                name,
                s.get('headers', []) if inc else [],
                s.get('rows', []),
            ))
        data = _build_ooxml(sheets)
    try:
        with open(file_path, 'wb') as f:
            f.write(data)
    except (IOError, OSError) as e:
        msg = str(e)
        if 'being used by another process' in msg or getattr(e, 'errno', 0) in (13, 32):
            raise IOError(
                'Arquivo em uso. Feche "{}" no Excel antes de exportar novamente.'.format(
                    file_path.split('\\')[-1])
            )
        raise


# -- OOXML BUILDER -------------------------------------------------------------

def _build_ooxml_stacked(schedules_data, include_headers_global, tab_name=None):
    """Constroi um unico sheet com todos os schedules empilhados (linha em branco entre eles)."""
    sheet_name = tab_name if tab_name else 'Dados'
    sheet_name = _sanitize_name(sheet_name)
    combined_rows = []  # list of (cells: list, is_header: bool)
    for i, sched in enumerate(schedules_data):
        if i > 0:
            combined_rows.append(([], False))  # linha em branco
        inc = sched.get('include_header', include_headers_global)
        if inc and sched.get('headers'):
            combined_rows.append((list(sched['headers']), True))
        for row in sched.get('rows', []):
            combined_rows.append((list(row), False))
    return _build_ooxml([(sheet_name, combined_rows, None)], _stacked=True)


def _build_ooxml(sheets, _stacked=False):
    buf = io.BytesIO()
    all_strings = []
    string_index = {}

    def get_si(value):
        s = str(value) if not isinstance(value, str) else value
        if s not in string_index:
            string_index[s] = len(all_strings)
            all_strings.append(s)
        return string_index[s]

    sheet_xmls = []
    for sheet_name, headers, rows in sheets:
        rows_xml = []
        row_num = 1
        if _stacked:
            # rows ja e list de (cells, is_header) — formato especial do stacked
            data_rows = rows if rows else []
        else:
            data_rows = []
            if headers:
                data_rows.append((list(headers), True))
            for row in (rows or []):
                data_rows.append((list(row), False))

        for row_data, is_header in data_rows:
            cells_xml = []
            for col_idx, value in enumerate(row_data):
                col_letter = _col_letter(col_idx)
                cell_ref = '{}{}'.format(col_letter, row_num)
                s_attr = ' s="1"' if is_header else ''
                val_str = str(value).strip() if value is not None else ''
                try:
                    num = float(val_str)
                    if val_str.strip() == '' or math.isnan(num) or math.isinf(num):
                        raise ValueError()
                    cells_xml.append('<c r="{}"{}><v>{}</v></c>'.format(
                        cell_ref, s_attr, num))
                except (ValueError, TypeError):
                    si = get_si(val_str)
                    cells_xml.append('<c r="{}" t="s"{}><v>{}</v></c>'.format(
                        cell_ref, s_attr, si))
            rows_xml.append('<row r="{}">{}</row>'.format(
                row_num, ''.join(cells_xml)))
            row_num += 1

        sheet_xmls.append('\n'.join(rows_xml))

    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # [Content_Types].xml
        sheet_overrides = '\n  '.join(
            '<Override PartName="/xl/worksheets/sheet{}.xml"'
            ' ContentType="application/vnd.openxmlformats-officedocument'
            '.spreadsheetml.worksheet+xml"/>'.format(i + 1)
            for i in range(len(sheets))
        )
        zf.writestr('[Content_Types].xml', (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
            '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
            '  <Default Extension="xml" ContentType="application/xml"/>\n'
            '  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>\n'
            '  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>\n'
            '  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>\n'
            '  {}\n'
            '</Types>'
        ).format(sheet_overrides).encode('utf-8'))

        # _rels/.rels
        zf.writestr('_rels/.rels', (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            '  <Relationship Id="rId1" Type="{}/officeDocument" Target="xl/workbook.xml"/>\n'
            '</Relationships>'
        ).format(_REL_BASE).encode('utf-8'))

        # xl/workbook.xml — r:id referencia rId2..rId(N+1) para worksheets
        sheets_elements = '\n    '.join(
            '<sheet name="{}" sheetId="{}" r:id="rId{}"/>'.format(
                _esc(name), i + 1, i + 2)
            for i, (name, _, _) in enumerate(sheets)
        )
        zf.writestr('xl/workbook.xml', (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
            ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">\n'
            '  <sheets>\n    {}\n  </sheets>\n</workbook>'
        ).format(sheets_elements).encode('utf-8'))

        # xl/_rels/workbook.xml.rels
        # rId1 = styles, rId2..N+1 = worksheets, rId(N+2) = sharedStrings
        wb_sheet_rels = '\n  '.join(
            '<Relationship Id="rId{}" Type="{}/worksheet" Target="worksheets/sheet{}.xml"/>'.format(
                i + 2, _REL_BASE, i + 1)
            for i in range(len(sheets))
        )
        ss_rid = len(sheets) + 2
        zf.writestr('xl/_rels/workbook.xml.rels', (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            '  <Relationship Id="rId1" Type="{rel}/styles" Target="styles.xml"/>\n'
            '  {sheet_rels}\n'
            '  <Relationship Id="rId{ss}" Type="{rel}/sharedStrings" Target="sharedStrings.xml"/>\n'
            '</Relationships>'
        ).format(rel=_REL_BASE, sheet_rels=wb_sheet_rels, ss=ss_rid).encode('utf-8'))

        # xl/styles.xml
        zf.writestr('xl/styles.xml', (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
            '  <fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>\n'
            '  <fills count="2"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill></fills>\n'
            '  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>\n'
            '  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>\n'
            '  <cellXfs>\n'
            '    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>\n'
            '    <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>\n'
            '  </cellXfs>\n'
            '</styleSheet>'
        ).encode('utf-8'))

        # worksheets
        for i, (sheet_name, headers, rows) in enumerate(sheets):
            zf.writestr(
                'xl/worksheets/sheet{}.xml'.format(i + 1),
                (
                    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
                    '  <sheetData>\n    {}\n  </sheetData>\n</worksheet>'
                ).format(sheet_xmls[i]).encode('utf-8')
            )

        # xl/sharedStrings.xml
        si_entries = '\n  '.join(
            '<si><t xml:space="preserve">{}</t></si>'.format(_esc(s))
            for s in all_strings
        )
        zf.writestr('xl/sharedStrings.xml', (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
            ' count="{c}" uniqueCount="{c}">\n  {si}\n</sst>'
        ).format(c=len(all_strings), si=si_entries).encode('utf-8'))

    return buf.getvalue()


def _sanitize_name(name):
    invalid = set('[]:*?/\\')
    sanitized = ''.join(c for c in name if c not in invalid)
    return sanitized[:31] if sanitized else 'Sheet'


def _col_letter(col_idx):
    result = ''
    n = col_idx + 1
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _esc(value):
    """Escapa valor para XML 1.0: remove chars invalidos, escapa especiais."""
    s = str(value) if not isinstance(value, str) else value
    s = _XML_INVALID.sub('', s)
    return (s.replace('&', '&amp;')
             .replace('<', '&lt;')
             .replace('>', '&gt;')
             .replace('"', '&quot;')
             .replace("'", '&apos;'))
