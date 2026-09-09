# -*- coding: utf-8 -*-
"""Parser e serializador CSV no formato RFC 4180 - logica pura.

Motivo de existir: o parser antigo do lab fazia `linha.split(',')` e
`valor.strip('"')`. Isso corrompe em silencio dois casos comuns em MEP:

    Tamanho;  1/2"        -> aspas de polegada eram comidas
    Descricao; A, B e C   -> a virgula partia o valor em duas colunas

Aqui as aspas delimitam o campo, `""` e uma aspa literal e a virgula dentro
de aspas nao separa. Puro Python (sem clr/Autodesk) - roda em CPython e
IronPython 3, e e testado em `dev-tools/tests/test_csv_rfc.py`.
"""


def parse_csv_text(text):
    """Converte texto CSV em (headers, rows).

    Linhas totalmente vazias sao descartadas. Campos sem aspas tem espacos
    das pontas removidos; campos entre aspas sao preservados como estao.

    Args:
        text (str): conteudo do arquivo (ja sem BOM).

    Returns:
        tuple: (headers, rows) - headers e list[str], rows e list[list[str]].
    """
    if not text:
        return [], []

    rows = []
    row = []
    field = []
    field_quoted = False
    in_quotes = False
    i = 0
    total = len(text)

    def close_field():
        value = u''.join(field)
        if not field_quoted:
            value = value.strip()
        row.append(value)

    while i < total:
        char = text[i]

        if in_quotes:
            if char == u'"':
                # Aspa dupla dentro do campo = aspa literal
                if i + 1 < total and text[i + 1] == u'"':
                    field.append(u'"')
                    i += 2
                    continue
                in_quotes = False
                i += 1
                continue
            field.append(char)
            i += 1
            continue

        if char == u'"':
            in_quotes = True
            field_quoted = True
            i += 1
            continue

        if char == u',':
            close_field()
            field = []
            field_quoted = False
            i += 1
            continue

        if char == u'\r' or char == u'\n':
            if char == u'\r' and i + 1 < total and text[i + 1] == u'\n':
                i += 1
            close_field()
            rows.append(row)
            row = []
            field = []
            field_quoted = False
            i += 1
            continue

        field.append(char)
        i += 1

    close_field()
    rows.append(row)

    rows = [r for r in rows if any(v.strip() for v in r)]
    if not rows:
        return [], []
    return rows[0], rows[1:]


def format_csv_text(headers, rows):
    """Converte (headers, rows) em texto CSV com todos os campos entre aspas.

    Nao modifica `rows`: linhas curtas sao completadas em copias.

    Args:
        headers (list): nomes das colunas.
        rows (list): lista de listas com os valores.

    Returns:
        str: texto CSV terminado em quebra de linha.
    """
    largura = len(headers)
    linhas = [_join_row(headers, largura)]
    for row in rows:
        linhas.append(_join_row(row, largura))
    return u''.join(linhas)


def _join_row(values, largura):
    campos = [_escape(v) for v in values]
    while len(campos) < largura:
        campos.append(u'""')
    return u','.join(campos) + u'\n'


def _escape(value):
    if value is None:
        texto = u''
    else:
        texto = u'{}'.format(value)
    return u'"{}"'.format(texto.replace(u'"', u'""'))
