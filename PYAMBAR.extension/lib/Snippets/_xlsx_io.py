# -*- coding: utf-8 -*-
"""Leitura e escrita de .xlsx sem dependencia externa.

Um .xlsx e um ZIP com partes XML (OOXML/SpreadsheetML). Este modulo gera e
le esse pacote usando apenas zipfile + xml.etree da stdlib.

Motivacao: o CSV depende do separador de lista do Windows (',' ou ';' conforme
o locale da maquina). O mesmo arquivo abre certo em uma maquina e embaralhado
em outra. O xlsx nao tem esse problema — o conteudo e XML, nao texto separado.

Nao usa ClosedXML/OpenXML/Excel COM de proposito:
  - sem DLL para distribuir e sem conflito com o ClosedXML que o add-in C#
    ja carrega no mesmo processo do Revit;
  - nao exige Excel instalado na maquina do usuario;
  - sendo Python puro, roda em CPython e e testavel fora do Revit.

Uso:
    write_xlsx(caminho, ['Nome', 'Qtd'], [['Tubo', '3'], ['Luva', '10']])
    headers, rows = read_xlsx(caminho)
"""

import os
import re
import zipfile
import xml.etree.ElementTree as ET

__all__ = ['write_xlsx', 'read_xlsx', 'column_letter', 'column_index']

# Namespaces OOXML
_NS_MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
_NS_REL_DOC = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
_NS_REL_PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'
_NS_CONTENT_TYPES = 'http://schemas.openxmlformats.org/package/2006/content-types'

# Numero puro: aceita sinal, separador decimal ponto e notacao cientifica.
# Proposital NAO aceitar virgula decimal nem separador de milhar: "1,5" e
# ambiguo entre locales e deve ir para o Excel como texto, preservado.
_NUMERIC_RE = re.compile(r'^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$')

# Caracteres que o XML 1.0 nao aceita (o Excel recusa o arquivo inteiro se
# algum escapar). Parametros do Revit as vezes trazem controles vindos de
# copiar/colar.
_ILLEGAL_XML_RE = re.compile(
    u'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]')


def column_letter(index):
    """Indice 0-based -> letra da coluna ('A', 'B', ... 'Z', 'AA', 'AB', ...)"""
    if index < 0:
        raise ValueError("indice de coluna nao pode ser negativo: {}".format(index))

    letters = ""
    current = index + 1  # A notacao do Excel e 1-based
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        letters = chr(ord('A') + remainder) + letters
    return letters


def column_index(letters):
    """Letra da coluna -> indice 0-based ('A' -> 0, 'AA' -> 26)"""
    result = 0
    for char in letters.upper():
        if not ('A' <= char <= 'Z'):
            continue
        result = result * 26 + (ord(char) - ord('A') + 1)
    return result - 1


def _clean(value):
    """Normaliza para texto valido em XML 1.0"""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return _ILLEGAL_XML_RE.sub('', value)


def _escape(text):
    """Escapa os cinco caracteres reservados do XML"""
    return (text.replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&apos;'))


def _is_numeric(text):
    """True se o texto deve virar celula numerica no Excel"""
    return bool(_NUMERIC_RE.match(text.strip())) if text.strip() else False


def _cell_xml(ref, text):
    """XML de uma celula.

    Numero -> celula numerica (permite somar/ordenar no Excel).
    Resto   -> inlineStr, que dispensa a parte sharedStrings.xml.
    """
    if not text:
        return '<c r="{}"/>'.format(ref)

    if _is_numeric(text):
        return '<c r="{}"><v>{}</v></c>'.format(ref, _escape(text.strip()))

    return ('<c r="{}" t="inlineStr"><is><t xml:space="preserve">{}</t></is></c>'
            .format(ref, _escape(text)))


def _sheet_xml(headers, rows):
    """Monta xl/worksheets/sheet1.xml"""
    parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             '<worksheet xmlns="{}">'.format(_NS_MAIN)]

    col_count = len(headers)
    for row in rows:
        col_count = max(col_count, len(row))

    if col_count:
        # Congela a linha de cabecalho: schedules costumam ser longos
        parts.append('<sheetViews><sheetView workbookViewId="0">'
                     '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
                     '</sheetView></sheetViews>')

    parts.append('<sheetData>')

    all_rows = [headers] + list(rows) if headers else list(rows)
    for row_idx, row in enumerate(all_rows, start=1):
        cells = []
        for col_idx, value in enumerate(row):
            text = _clean(value)
            ref = "{}{}".format(column_letter(col_idx), row_idx)
            cells.append(_cell_xml(ref, text))
        parts.append('<row r="{}">{}</row>'.format(row_idx, "".join(cells)))

    parts.append('</sheetData></worksheet>')
    return "".join(parts)


def _workbook_xml(sheet_name):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="{}" xmlns:r="{}">'
            '<sheets><sheet name="{}" sheetId="1" r:id="rId1"/></sheets>'
            '</workbook>'.format(_NS_MAIN, _NS_REL_DOC, _escape(sheet_name)))


def _sanitize_sheet_name(name):
    """Nome de aba valido: sem : \\ / ? * [ ] e no maximo 31 caracteres"""
    clean = _clean(name) or "Dados"
    for char in ':\\/?*[]':
        clean = clean.replace(char, '_')
    clean = clean.strip("'")
    return clean[:31] or "Dados"


def write_xlsx(file_path, headers, rows, sheet_name="Dados"):
    """Escreve um .xlsx com uma aba.

    headers: lista de titulos (pode ser vazia)
    rows:    lista de listas; linhas de tamanhos diferentes sao aceitas
    """
    headers = [_clean(h) for h in (headers or [])]
    rows = rows or []
    sheet_name = _sanitize_sheet_name(sheet_name)

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="{}">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'.format(_NS_CONTENT_TYPES))

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="{}">'
        '<Relationship Id="rId1" Type="{}/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'.format(_NS_REL_PKG, _NS_REL_DOC))

    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="{}">'
        '<Relationship Id="rId1" Type="{}/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'.format(_NS_REL_PKG, _NS_REL_DOC))

    folder = os.path.dirname(file_path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder)

    with zipfile.ZipFile(file_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', content_types)
        archive.writestr('_rels/.rels', root_rels)
        archive.writestr('xl/workbook.xml', _workbook_xml(sheet_name))
        archive.writestr('xl/_rels/workbook.xml.rels', workbook_rels)
        archive.writestr('xl/worksheets/sheet1.xml', _sheet_xml(headers, rows))

    return file_path


def _tag(name):
    return '{{{}}}{}'.format(_NS_MAIN, name)


def _read_shared_strings(archive):
    """Le xl/sharedStrings.xml (arquivos gerados pelo Excel usam essa parte)"""
    try:
        data = archive.read('xl/sharedStrings.xml')
    except KeyError:
        return []

    strings = []
    root = ET.fromstring(data)
    for si in root.findall(_tag('si')):
        # O texto pode estar quebrado em varios <t> por causa de formatacao
        # parcial (rich text); e preciso concatenar todos.
        parts = [(node.text or "") for node in si.iter(_tag('t'))]
        strings.append("".join(parts))
    return strings


def _find_first_sheet(archive):
    """Caminho da primeira planilha dentro do pacote"""
    names = archive.namelist()

    preferred = 'xl/worksheets/sheet1.xml'
    if preferred in names:
        return preferred

    sheets = sorted(n for n in names
                    if n.startswith('xl/worksheets/') and n.endswith('.xml'))
    return sheets[0] if sheets else None


def _cell_text(cell, shared_strings):
    """Extrai o texto de um <c>, conforme o tipo declarado"""
    cell_type = cell.get('t')

    if cell_type == 'inlineStr':
        node = cell.find(_tag('is'))
        if node is None:
            return ""
        return "".join((t.text or "") for t in node.iter(_tag('t')))

    value_node = cell.find(_tag('v'))
    if value_node is None:
        return ""
    raw = value_node.text or ""

    if cell_type == 's':
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError):
            return ""

    if cell_type == 'e':      # celula de erro (#REF!, #N/D...)
        return raw

    # Numerico: remover o ".0" de inteiros para nao virar "3.0" em vez de "3"
    if cell_type in (None, 'n'):
        try:
            number = float(raw)
            if number == int(number) and abs(number) < 1e15:
                return str(int(number))
        except (ValueError, OverflowError):
            pass

    return raw


def read_xlsx(file_path, first_row_is_header=True):
    """Le a primeira aba de um .xlsx.

    Retorna (headers, rows). Se first_row_is_header for False, headers vem
    vazio e todas as linhas entram em rows.

    Respeita a referencia de cada celula (A1, C3...), entao colunas puladas
    viram string vazia na posicao certa em vez de deslocar a linha.
    """
    if not os.path.exists(file_path):
        raise IOError("Arquivo nao encontrado: {}".format(file_path))

    if not zipfile.is_zipfile(file_path):
        raise ValueError(
            "Arquivo nao e um .xlsx valido: {}\n"
            "Formatos .xls antigos e .csv renomeados nao sao suportados."
            .format(os.path.basename(file_path)))

    with zipfile.ZipFile(file_path, 'r') as archive:
        sheet_path = _find_first_sheet(archive)
        if not sheet_path:
            raise ValueError("Nenhuma planilha encontrada em {}".format(file_path))

        shared_strings = _read_shared_strings(archive)
        root = ET.fromstring(archive.read(sheet_path))

    sheet_data = root.find(_tag('sheetData'))
    if sheet_data is None:
        return [], []

    parsed = []
    for row in sheet_data.findall(_tag('row')):
        values = {}
        max_col = -1

        for pos, cell in enumerate(row.findall(_tag('c'))):
            ref = cell.get('r')
            if ref:
                letters = "".join(c for c in ref if c.isalpha())
                col_idx = column_index(letters) if letters else pos
            else:
                col_idx = pos  # celula sem referencia: usar a ordem

            values[col_idx] = _cell_text(cell, shared_strings)
            max_col = max(max_col, col_idx)

        parsed.append([values.get(i, "") for i in range(max_col + 1)])

    # Normalizar largura para todas as linhas terem o mesmo numero de colunas.
    # Sem max(default=): IronPython nao aceita esse argumento.
    width = 0
    for row in parsed:
        if len(row) > width:
            width = len(row)
    for row in parsed:
        row.extend([""] * (width - len(row)))

    if first_row_is_header and parsed:
        return parsed[0], parsed[1:]

    return [], parsed
