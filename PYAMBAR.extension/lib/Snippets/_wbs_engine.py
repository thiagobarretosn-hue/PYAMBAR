# -*- coding: utf-8 -*-
"""
_wbs_engine.py
Motor puro do pulldown WBS — deteccao de pavimento por elevacao, geracao do
numero WBS e cruzamento com a tabela de Tipologia UH.

Sem clr / sem Autodesk: roda identico em IronPython 3 (Revit) e CPython 3
(pytest). O script.py so extrai z_min/z_max dos elementos e grava parametros.

USAGE:
    from Snippets._wbs_engine import build_ranges, atribuir, auto_ordinal

    ranges = build_ranges([(0.0, '1st'), (10.5, '2nd'), (21.0, '3rd')])
    registros = [{'id': 123, 'z_min': 10.4, 'z_max': 13.0}]
    linhas = atribuir(registros, ranges, sufixo=1, incrementar=True,
                      reiniciar_por_pavimento=True, offset_ft=-0.3,
                      tipologia={'201': 'A1 - L'})

AUTHOR: Thiago Barreto Sobral Nunes
VERSION: 1.0 (03/09/2026 — extraido de WBSCompleto v1.1 + WBSFloor v1.2)
NOTES:
    - find_wbs_by_span veio do WBSFloor v1.2 (escolhe o nivel de MAIOR
      sobreposicao com o bounding box, nao o ponto medio) — cobre laje,
      parede e fundacao sketch-based, que o ponto medio errava.
"""

import re

# motivos de descarte devolvidos por atribuir()
MOTIVO_SEM_GEOMETRIA = 'sem_geometria'
MOTIVO_FORA_DAS_FAIXAS = 'fora_das_faixas'
MOTIVO_DETAIL_SEM_NUMERO = 'detail_sem_numero'

MOTIVO_TEXTO = {
    MOTIVO_SEM_GEOMETRIA: 'sem geometria (sem bounding box nem Location)',
    MOTIVO_FORA_DAS_FAIXAS: 'elevacao fora de todas as faixas de nivel',
    MOTIVO_DETAIL_SEM_NUMERO: 'texto do Floor nao contem numero',
}


# ── formatacao ────────────────────────────────────────────────────────────────

def format_elevation(elev_ft):
    """Pes decimais -> notacao imperial (ex.: 10.5 -> 10'-6\")."""
    if elev_ft is None:
        return '(sem geom)'
    negativo = elev_ft < 0
    valor = abs(elev_ft)
    feet = int(valor)
    inches = round((valor - feet) * 12, 2)
    if inches >= 12:            # arredondamento estourou a polegada
        feet += 1
        inches = 0
    sinal = '-' if negativo else ''
    if inches == 0:
        return "{}{}'-0\"".format(sinal, feet)
    if inches == int(inches):
        return "{}{}'-{}\"".format(sinal, feet, int(inches))
    return "{}{}'-{:.2f}\"".format(sinal, feet, inches)


def auto_ordinal(level_name):
    """'3rd Intermediate Floor' -> '3rd'. Sem numero, devolve o nome intacto."""
    if not level_name:
        return level_name
    m = re.search(r"(\d+)", level_name)
    if not m:
        return level_name
    n = int(m.group(1))
    if n % 100 in (11, 12, 13):
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return "{}{}".format(n, suffix)


def extrair_andar(texto):
    """Primeiro inteiro do texto ('5th' -> 5). Sem numero -> None."""
    if not texto:
        return None
    m = re.search(r"(\d+)", str(texto))
    return int(m.group(1)) if m else None


def normalizar_chave_wbs(valor):
    """Chave de lookup na tabela de tipologia: sempre str, sem espacos.

    Aceita int (915), str ('915'), str com espaco (' 915 ') e float vindo de
    parametro Double ('915.0' -> '915').
    """
    if valor is None:
        return None
    if isinstance(valor, float):
        if valor == int(valor):
            valor = int(valor)
    texto = str(valor).strip()
    if not texto:
        return None
    if texto.endswith('.0') and texto[:-2].lstrip('-').isdigit():
        texto = texto[:-2]
    return texto


# ── faixas de nivel ───────────────────────────────────────────────────────────

def build_ranges(levels):
    """[(elev_ft, wbs_value), ...] -> [(lower, upper, wbs_value), ...].

    Ordena por elevacao. A ultima faixa vai ate o infinito. Niveis com a mesma
    elevacao: o primeiro (ordem de entrada) fica com a faixa, o outro vira uma
    faixa de espessura zero — nunca casa, e nao rouba elementos do vizinho.
    """
    ordenados = sorted(enumerate(levels), key=lambda par: (par[1][0], par[0]))
    ordenados = [item for _, item in ordenados]

    ranges = []
    for i, (elev, wbs) in enumerate(ordenados):
        upper = ordenados[i + 1][0] if i + 1 < len(ordenados) else float('inf')
        ranges.append((elev, upper, wbs))
    return ranges


def find_wbs_by_span(z_min, z_max, ranges, offset_ft=0.0):
    """Cruza a faixa vertical do elemento [z_min, z_max] com as faixas de nivel.

    Vence o nivel de MAIOR sobreposicao; em empate, o mais baixo (ranges ja vem
    ordenado). Span de espessura ~zero ou fora de todas as faixas cai no ponto
    medio. Devolve None se nem o ponto medio casar.
    """
    if z_min is None or z_max is None or not ranges:
        return None

    lo = min(z_min, z_max) + offset_ft
    hi = max(z_min, z_max) + offset_ft

    best_wbs = None
    best_overlap = 0.0
    for lower, upper, wbs in ranges:
        ov = min(hi, upper) - max(lo, lower)
        if ov > best_overlap:
            best_overlap = ov
            best_wbs = wbs
    if best_wbs is not None:
        return best_wbs

    mid = (lo + hi) / 2.0
    for lower, upper, wbs in ranges:
        if lower <= mid < upper:
            return wbs
    return None


# ── motor ─────────────────────────────────────────────────────────────────────

def normalizar_regras(brutas):
    """Regras especiais -> lista limpa, na ordem (a primeira que casa vence).

    Cada regra: {'pavimento', 'wbs_min', 'wbs_max', 'wbs', 'tipologia'}.
    Criterio: pavimento (texto do WBS Detail) e/ou faixa de WBS — os dois
    preenchidos exigem que AMBOS casem. Acao: os campos 'wbs' e 'tipologia'
    preenchidos substituem o calculado; em branco nao mexem em nada.

    Regra sem criterio ou sem acao e descartada: casaria com tudo ou nao faria
    nada, e nos dois casos so confundiria o resultado.
    """
    limpas = []
    for bruta in brutas or []:
        if not isinstance(bruta, dict):
            continue
        pavimento = str(bruta.get('pavimento') or '').strip()
        wbs_min = _para_inteiro(bruta.get('wbs_min'))
        wbs_max = _para_inteiro(bruta.get('wbs_max'))
        wbs = str(bruta.get('wbs') or '').strip()
        tipo = str(bruta.get('tipologia') or '').strip()

        if not pavimento and wbs_min is None and wbs_max is None:
            continue
        if not wbs and not tipo:
            continue
        if wbs_min is not None and wbs_max is not None and wbs_min > wbs_max:
            wbs_min, wbs_max = wbs_max, wbs_min

        limpas.append({
            'pavimento': pavimento,
            'wbs_min': wbs_min,
            'wbs_max': wbs_max,
            'wbs': wbs,
            'tipologia': tipo,
        })
    return limpas


def _para_inteiro(valor):
    if valor is None or valor == '':
        return None
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


def casar_regra(regras, detail, wbs_num):
    """Primeira regra que casa com o pavimento e/ou a faixa. None se nenhuma."""
    if not regras:
        return None
    alvo_pav = str(detail or '').strip().lower()

    for regra in regras:
        pavimento = regra.get('pavimento')
        if pavimento and alvo_pav != pavimento.strip().lower():
            continue

        wbs_min = regra.get('wbs_min')
        wbs_max = regra.get('wbs_max')
        if wbs_min is not None or wbs_max is not None:
            if wbs_num is None:
                continue
            if wbs_min is not None and wbs_num < wbs_min:
                continue
            if wbs_max is not None and wbs_num > wbs_max:
                continue

        return regra
    return None


def descrever_regra(regra):
    """Texto curto da regra, para a coluna Situacao."""
    if not regra:
        return ''
    criterios = []
    if regra.get('pavimento'):
        criterios.append(regra['pavimento'])
    wbs_min, wbs_max = regra.get('wbs_min'), regra.get('wbs_max')
    if wbs_min is not None or wbs_max is not None:
        criterios.append("{}..{}".format(
            wbs_min if wbs_min is not None else '',
            wbs_max if wbs_max is not None else ''))

    acoes = []
    if regra.get('wbs'):
        acoes.append("Unit ID={}".format(regra['wbs']))
    if regra.get('tipologia'):
        acoes.append("Type={}".format(regra['tipologia']))

    return "regra {} → {}".format(' e '.join(criterios), ', '.join(acoes))


def atribuir(registros, ranges, sufixo=1, incrementar=False,
             reiniciar_por_pavimento=False, offset_ft=0.0, tipologia=None,
             regras=None):
    """Calcula WBS Detail, WBS e Tipologia UH para cada registro.

    Args:
        registros: [{'id': int, 'z_min': float|None, 'z_max': float|None}, ...]
                   z_min/z_max None = elemento sem geometria.
        ranges: saida de build_ranges().
        sufixo: numero inicial somado a (andar * 100).
        incrementar: True soma 1 ao sufixo a cada elemento resolvido.
        reiniciar_por_pavimento: com incrementar=True, cada pavimento recomeca
                   no sufixo inicial (101,102... / 201,202...). Sem isso o
                   contador corre pela selecao inteira, atravessando andares.
        offset_ft: deslocamento aplicado ao Z antes de comparar com as faixas
                   (positivo = aceita elemento abaixo do Level).
        tipologia: {chave_wbs: 'Tipologia UH'}.

    Returns:
        Lista na MESMA ordem de entrada, cada item:
        {'id', 'z_min', 'z_max', 'z_meio', 'elev_display',
         'detail', 'wbs', 'tipologia', 'motivo'}
        motivo e None quando o pavimento foi resolvido.
    """
    tipologia = tipologia or {}
    regras = normalizar_regras(regras)
    contador_global = sufixo
    contadores_por_pavimento = {}
    linhas = []

    for reg in registros:
        z_min = reg.get('z_min')
        z_max = reg.get('z_max')
        z_meio = None
        if z_min is not None and z_max is not None:
            z_meio = (z_min + z_max) / 2.0

        linha = {
            'id': reg.get('id'),
            'z_min': z_min,
            'z_max': z_max,
            'z_meio': z_meio,
            'elev_display': format_elevation(z_meio),
            'detail': None,
            'wbs': None,
            'tipologia': None,
            'motivo': None,
            'regra': '',
        }

        if z_min is None or z_max is None:
            linha['motivo'] = MOTIVO_SEM_GEOMETRIA
            linhas.append(linha)
            continue

        detail = find_wbs_by_span(z_min, z_max, ranges, offset_ft)
        if detail is None:
            linha['motivo'] = MOTIVO_FORA_DAS_FAIXAS
            linhas.append(linha)
            continue

        linha['detail'] = detail

        andar = extrair_andar(detail)
        if andar is None:
            linha['motivo'] = MOTIVO_DETAIL_SEM_NUMERO
            linhas.append(linha)
            continue

        if reiniciar_por_pavimento:
            atual = contadores_por_pavimento.get(detail, sufixo)
        else:
            atual = contador_global

        # numero candidato: a faixa das regras precisa dele para casar, mas o
        # contador so anda se a regra NAO substituir o WBS
        candidato = (andar * 100) + atual
        regra = casar_regra(regras, detail, candidato)

        if regra and regra.get('wbs'):
            linha['wbs'] = regra['wbs']
            linha['regra'] = descrever_regra(regra)
        else:
            linha['wbs'] = candidato
            if regra:
                linha['regra'] = descrever_regra(regra)
            if incrementar:
                if reiniciar_por_pavimento:
                    contadores_por_pavimento[detail] = atual + 1
                else:
                    contador_global = atual + 1

        if regra and regra.get('tipologia'):
            linha['tipologia'] = regra['tipologia']
        else:
            linha['tipologia'] = tipologia.get(normalizar_chave_wbs(linha['wbs']))

        linhas.append(linha)

    return linhas


def colunas_para_parametros(headers, rows, limite_opcoes=200):
    """CSV no formato da Paleta de Parametros -> [(nome, [opcoes])].

    Cada COLUNA e um parametro; os valores distintos da coluna viram as opcoes
    do combo, na ordem em que aparecem. Coluna sem nome e ignorada; valor vazio
    nao vira opcao.

    Args:
        headers: primeira linha do CSV (nomes dos parametros).
        rows: demais linhas.
        limite_opcoes: teto por coluna, para um CSV enorme nao travar a UI.

    Returns:
        [(nome_do_parametro, [opcao, ...]), ...] na ordem das colunas.
    """
    if not headers:
        return []

    nomes = [str(h).strip() for h in headers]
    colunas = [[] for _ in nomes]
    vistos = [set() for _ in nomes]

    for row in rows or []:
        for i in range(len(nomes)):
            if i >= len(row):
                continue
            valor = str(row[i]).strip()
            if not valor or valor in vistos[i]:
                continue
            if len(colunas[i]) >= limite_opcoes:
                continue
            vistos[i].add(valor)
            colunas[i].append(valor)

    return [(nome, colunas[i]) for i, nome in enumerate(nomes) if nome]


def resumir(linhas):
    """Contagens para a barra de status: resolvidos, por motivo, sem tipologia."""
    resumo = {
        'total': len(linhas),
        'com_pavimento': 0,
        'sem_tipologia': 0,
        MOTIVO_SEM_GEOMETRIA: 0,
        MOTIVO_FORA_DAS_FAIXAS: 0,
        MOTIVO_DETAIL_SEM_NUMERO: 0,
    }
    for linha in linhas:
        motivo = linha.get('motivo')
        if motivo:
            resumo[motivo] = resumo.get(motivo, 0) + 1
            continue
        resumo['com_pavimento'] += 1
        if not linha.get('tipologia'):
            resumo['sem_tipologia'] += 1
    return resumo
