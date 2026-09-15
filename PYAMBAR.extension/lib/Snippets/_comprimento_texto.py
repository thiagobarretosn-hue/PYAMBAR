# -*- coding: utf-8 -*-
"""Comprimento digitado -> pes. Puro (sem clr), com testes.

Pedido do Thiago em 15/09/2026: o offset do Unit Mapper nao aceitava 0.1" nem
0.1'. Antes de escrever, as tres implementacoes do lab foram medidas (nenhuma
tinha teste): o `_parse_length_ft` do SyncFromRoom errava `1'-6"` (0,5 em vez
de 1,5), `-1'6"` e `0'-4"` — justo o formato que o Revit mostra; os outros dois
dependem do `doc`/TryParse e leem numero puro como polegada ou recusam negativo.

ACEITA
    0.1'   0.1"   4"   4'   .5"   0,5
    1'6"   1'-6"   1' 6"   1'-6 1/2"   -1'6"   0'-4"
    1/2"   1 1/2"   1-1/2"   4''  (duas aspas simples = polegada)
    3 in   12 inches   0.1 ft   2 pol   1 pé   2 pés
    numero sem unidade -> `padrao` (PES: a config antiga guarda pes)

DEVOLVE pes (float), ou None se nao entender. Vazio -> None.
O sinal vale para o valor inteiro: -1'6" e -1,5 ft.
"""
import re

PES = 'pes'
POLEGADAS = 'polegadas'

# unidade por extenso so logo depois de numero ("3 in", "0.1ft") — "in" solto
# no meio de uma palavra nao vira polegada
_PALAVRAS_POL = re.compile(
    r'(?<=[\d.])\s*(polegadas|polegada|pol|inches|inch|in)(?![^\W\d_])\.?',
    re.IGNORECASE | re.UNICODE)
_PALAVRAS_PES = re.compile(
    u'(?<=[\\d.])\\s*(p[eé]s|p[eé]|feet|foot|ft)(?![^\\W\\d_])\\.?',
    re.IGNORECASE | re.UNICODE)

_NUM = r'(?:\d+(?:\.\d*)?|\.\d+)'
_FRAC = r'(?:\d+\s*/\s*\d+)'
_QTD = r'(?:\d+(?:\s+|-){f}|{f}|{n})'.format(f=_FRAC, n=_NUM)

_SO_NUMERO = re.compile(r'^(?P<qtd>{q})$'.format(q=_QTD))
# o traco entre pes e polegadas e SEPARADOR (formato do Revit), nunca sinal
_PES_POL = re.compile(
    r'^(?:(?P<pes>{q})\s*\')?\s*-?\s*(?:(?P<pol>{q})\s*")?$'.format(q=_QTD))

_MISTO = re.compile(r'^(\d+)(?:\s+|-)(\d+)\s*/\s*(\d+)$')
_FRACAO = re.compile(r'^(\d+)\s*/\s*(\d+)$')


def _quantidade(texto):
    """'6', '0.5', '1/2', '1 1/2', '1-1/2' -> float, ou None (divisao por 0)."""
    texto = texto.strip()
    misto = _MISTO.match(texto)
    if misto:
        inteiro, num, den = (int(g) for g in misto.groups())
        return None if den == 0 else inteiro + float(num) / den
    fracao = _FRACAO.match(texto)
    if fracao:
        num, den = (int(g) for g in fracao.groups())
        return None if den == 0 else float(num) / den
    try:
        return float(texto)
    except ValueError:
        return None


def _normalizar(texto):
    s = u'{}'.format(texto).strip()
    for de, para in ((u'′', "'"), (u'’', "'"), (u'″', '"'),
                     (u'”', '"'), ("''", '"'), (',', '.')):
        s = s.replace(de, para)
    s = _PALAVRAS_POL.sub('"', s)
    s = _PALAVRAS_PES.sub("'", s)
    return s.strip()


def texto_para_pes(texto, padrao=PES):
    if texto is None:
        return None
    s = _normalizar(texto)
    if not s:
        return None

    sinal = 1.0
    if s[0] in '+-':
        sinal = -1.0 if s[0] == '-' else 1.0
        s = s[1:].strip()
        if not s:
            return None

    so_numero = _SO_NUMERO.match(s)
    if so_numero:
        valor = _quantidade(so_numero.group('qtd'))
        if valor is None:
            return None
        return sinal * (valor / 12.0 if padrao == POLEGADAS else valor)

    partes = _PES_POL.match(s)
    if not partes or (partes.group('pes') is None and partes.group('pol') is None):
        return None
    pes = _quantidade(partes.group('pes')) if partes.group('pes') else 0.0
    pol = _quantidade(partes.group('pol')) if partes.group('pol') else 0.0
    if pes is None or pol is None:
        return None
    return sinal * (pes + pol / 12.0)
