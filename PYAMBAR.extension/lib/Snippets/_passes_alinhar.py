# -*- coding: utf-8 -*-
"""Alinhar passes de uma laje pelos passes de outra — sem Revit.

Sem clr/Autodesk: testado em CPython (`dev-tools/tests/test_passes_alinhar.py`).
Quem coleta (passes de cada nivel) e o `slp_sync` do SlabPasses.

O CASO (Thiago, 22/10/2026 — PH3-PLB-SLAB PASSES)
------------------------------------------------
Os passes do 3rd Floor foram modelados depois dos do 2nd e ficaram um pouco
fora; o tubo nao serve de guia. Medido: 287 passes no 3o x 290 no 2o —
mediana 0,1", 284 ate 4", 3 a mais de 12" (posicao diferente, nao desvio).
Nenhum passe do 3o disputando o mesmo do 2o. O 4o era copia exata do 3o.

A REGRA
-------
- Referencia: o nivel de BAIXO, o de CIMA, ou o mais PERTO dos dois (passe
  a passe, o vizinho mais proximo entre os dois niveis).
- Um passe de referencia atende um passe so (guloso pela menor distancia,
  como o `casar` do LOG).
- So puxa ate `raio` (padrao 4"): alem disso nao e desvio, nao se mexe.
- Tipo diferente nao impede: vale o ponto central (o eixo do passe).
"""
import math

TUBO = 'tubo'
BAIXO = 'baixo'
CIMA = 'cima'
PERTO = 'perto'
REFERENCIAS = (TUBO, BAIXO, CIMA, PERTO)

PUXAR_PADRAO = 4.0      # pol — decisao do Thiago, 22/10/2026


def casar_por_xy(origem, referencia, raio_pol):
    """{id da origem: (passe de referencia, distancia em pol)}.

    origem / referencia: [{'id', 'x', 'y', ...}] em pes. Guloso pela menor
    distancia no conjunto todo: cada passe de referencia casa com um so.
    """
    pares = []
    for i, a in enumerate(origem):
        for j, b in enumerate(referencia):
            d = math.hypot(a['x'] - b['x'], a['y'] - b['y']) * 12.0
            if d <= raio_pol:
                pares.append((d, i, j))
    pares.sort()
    casados, usados = {}, set()
    for d, i, j in pares:
        if origem[i]['id'] in casados or j in usados:
            continue
        casados[origem[i]['id']] = (referencia[j], d)
        usados.add(j)
    return casados


def alvos(origem, abaixo, acima, referencia, raio_pol=PUXAR_PADRAO):
    """{id: (x, y, distancia pol, 'baixo'|'cima')} — para onde cada passe vai.

    Quem nao aparece ficou fora do raio (ou o nivel de referencia nao existe).
    """
    candidatos = []
    if referencia in (BAIXO, PERTO):
        candidatos.extend(dict(p, _lado=BAIXO) for p in abaixo or [])
    if referencia in (CIMA, PERTO):
        candidatos.extend(dict(p, _lado=CIMA) for p in acima or [])
    resultado = {}
    for pid, (ref, d) in casar_por_xy(origem, candidatos, raio_pol).items():
        resultado[pid] = (ref['x'], ref['y'], d, ref['_lado'])
    return resultado


def niveis_vizinhos(cotas, cota):
    """(cota de baixo, cota de cima) entre as cotas que TEM passe; None se nao ha."""
    abaixo = [c for c in cotas if c < cota - 1e-6]
    acima = [c for c in cotas if c > cota + 1e-6]
    return (max(abaixo) if abaixo else None, min(acima) if acima else None)


def ler_polegadas(texto, padrao=PUXAR_PADRAO):
    """'4' / '4,5' / '4.5"' / ' 6 in ' -> float; vazio ou invalido -> padrao."""
    limpo = (texto or u'').strip().lower().replace(u',', u'.')
    for sufixo in (u'"', u'in', u'pol'):
        if limpo.endswith(sufixo):
            limpo = limpo[:-len(sufixo)].strip()
    try:
        valor = float(limpo)
    except ValueError:
        return padrao
    return valor if valor > 0 else padrao


def mais_proximo(passe, abaixo, acima, referencia):
    """(passe de referencia, distancia pol, 'baixo'|'cima') mais perto, SEM raio —
    para o relatorio dizer quanto falta ao que ficou fora. None sem referencia."""
    candidatos = []
    if referencia in (BAIXO, PERTO):
        candidatos.extend((p, BAIXO) for p in abaixo or [])
    if referencia in (CIMA, PERTO):
        candidatos.extend((p, CIMA) for p in acima or [])
    melhor = None
    for ref, lado in candidatos:
        d = math.hypot(passe['x'] - ref['x'], passe['y'] - ref['y']) * 12.0
        if melhor is None or d < melhor[1]:
            melhor = (ref, d, lado)
    return melhor
