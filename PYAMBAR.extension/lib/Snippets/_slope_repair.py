# -*- coding: utf-8 -*-
"""
Nome do arquivo: _slope_repair.py
Localizacao: PYAMBAR(lab).extension/lib/Snippets/

Descricao:
Reinclinacao dos trechos que uma operacao de conexao estragou.

Fecha o ciclo aberto por Snippets._mep_connector_utils: la o snapshot/diff
descobre QUAIS tubos perderam inclinacao; aqui os trechos desses tubos sao
recolocados no alvo por bitola.

Motivacao (log ModelLogger session_20260814_150732): 5 minutos, 29 transacoes
e 58 toques em 17 tubos para inclinar uma rede, terminando com 11 tubos
achatados. O estrago nasce na conexao e era corrigido a mao, um a um.

REQUER Transaction ativa em reinclinar_trechos(). A pergunta ao usuario deve
acontecer FORA da transacao — coletar, perguntar, depois abrir a transacao.

Autor: Thiago Barreto Sobral Nunes
Data: 14.08.2026
Versao: 1.0
"""

import clr
clr.AddReference('RevitAPI')

from System import Int64
from Autodesk.Revit.DB import ElementId

from Snippets._prumada_utils import is_pipe
from Snippets._pipe_scanner_engine import config_interna
from Snippets._slope_geometry import DESVIO_OK, classificar_desvio
from Snippets._trecho_slope_utils import (
    encontrar_trecho, escolher_ancora, alvo_para_bitola, inclinacao_atual,
    aplicar_inclinacao
)


def _pol_pe(razao):
    """Razao (dz/dxy) para polegadas por pe, que e como o projetista le."""
    return razao * 12.0


def coletar_trechos_afetados(doc, ids_alterados, cfg_mm=None,
                             somente_fora_do_alvo=False):
    """Trechos UNICOS que contem os tubos alterados.

    Varios tubos alterados costumam pertencer ao mesmo trecho — corrigir o
    trecho uma vez ja resolve todos. A deduplicacao e pelo conjunto de ids do
    trecho, nao pelo tubo que o encontrou.

    Args:
        doc: documento
        ids_alterados: ids (int) dos tubos que mudaram de inclinacao
        cfg_mm: config do Pipe Doctor (alvos por bitola)
        somente_fora_do_alvo: descarta trechos que ja estao dentro da
            tolerancia. Use no LOTE por regiao — sem isso, uma selecao com 20
            trechos reescreveria os 20, inclusive os corretos. No reparo pos-
            conexao deixe False: ali ja se sabe que o trecho foi estragado.

    Returns:
        lista de dicts: trecho, elem_por_id, atual, alvo, ancora_idx, motivo,
        travado (bool), desvio. Trechos que nao dao para inclinar entram com
        ancora_idx None e motivo preenchido.
    """
    tol_pct = config_interna(cfg_mm)['inclinacao_tolerancia_pct']
    achados = []
    vistos = set()
    for eid in (ids_alterados or []):
        try:
            pipe = doc.GetElement(ElementId(Int64(eid)))
        except Exception:
            continue
        if not is_pipe(pipe):
            continue
        try:
            trecho, elem_por_id = encontrar_trecho(pipe, cfg_mm)
        except Exception:
            continue
        if trecho is None:
            continue

        chave = frozenset(trecho['ids'])
        if chave in vistos:
            continue
        vistos.add(chave)

        atual = inclinacao_atual(trecho)
        alvo = alvo_para_bitola(trecho, cfg_mm)
        desvio = classificar_desvio(atual, alvo, tol_pct)
        if somente_fora_do_alvo and desvio == DESVIO_OK:
            continue

        ancora_idx, motivo = escolher_ancora(trecho, elem_por_id)
        travado = ancora_idx is None
        if travado:
            # Mesma decisao do InclinarTrecho: preso nas duas pontas ainda da
            # para resolver ancorando na jusante e empurrando a montante.
            ancora_idx, motivo = escolher_ancora(trecho, elem_por_id,
                                                 permitir_travado=True)
        achados.append({
            'trecho': trecho,
            'elem_por_id': elem_por_id,
            'atual': atual,
            'alvo': alvo,
            'ancora_idx': ancora_idx,
            'motivo': motivo,
            'travado': travado,
            'desvio': desvio,
        })
    return achados


def descrever_trechos(achados, cabecalho=None):
    """Texto da pergunta ao usuario. '' quando nao ha nada a corrigir.

    cabecalho: primeira linha, com '{}' para o numero de trechos. O padrao fala
    da conexao; o lote por regiao passa o seu proprio.
    """
    if cabecalho is None:
        cabecalho = "A conexao mexeu na inclinacao de {} trecho(s):"
    corrigiveis = [a for a in achados if a['ancora_idx'] is not None]
    if not corrigiveis:
        return ""

    linhas = []
    for a in corrigiveis[:8]:
        linhas.append('  - {} tubo(s): {:.3f}"/ft -> {:.3f}"/ft{}'.format(
            len(a['trecho']['ids']), _pol_pe(a['atual']), _pol_pe(a['alvo']),
            "  [travado nas duas pontas]" if a['travado'] else ""))
    if len(corrigiveis) > 8:
        linhas.append("  - (+{} outro(s))".format(len(corrigiveis) - 8))

    travados = sum(1 for a in corrigiveis if a['travado'])
    aviso = ""
    if travados:
        aviso = ("\n{} trecho(s) estao presos nas duas pontas: a jusante fica "
                 "parada e a rede a montante sera arrastada.\n".format(travados))

    return ("{}\n\n{}\n{}"
            "\nRecolocar no alvo da bitola?".format(
                cabecalho.format(len(corrigiveis)),
                "\n".join(linhas), aviso))


def reinclinar_trechos(achados):
    """Aplica o alvo por bitola nos trechos. REQUER Transaction ativa.

    Returns:
        dict: trechos, tubos, falhas (lista de (id, motivo)), pulados
    """
    trechos_ok = 0
    tubos = 0
    falhas = []
    pulados = 0
    for a in (achados or []):
        if a['ancora_idx'] is None:
            pulados += 1
            continue
        try:
            ajustados, erros = aplicar_inclinacao(
                a['trecho'], a['ancora_idx'], a['alvo'], a['elem_por_id'])
        except Exception as erro:
            falhas.append((a['trecho']['ids'][0], str(erro)))
            continue
        if ajustados:
            trechos_ok += 1
            tubos += ajustados
        falhas.extend(erros)
    return {'trechos': trechos_ok, 'tubos': tubos,
            'falhas': falhas, 'pulados': pulados}


def formatar_resultado(res):
    """Linha curta para balao/output."""
    partes = ['{} trecho(s), {} tubo(s) reinclinado(s)'.format(
        res['trechos'], res['tubos'])]
    if res['pulados']:
        partes.append('{} sem ancora possivel'.format(res['pulados']))
    if res['falhas']:
        partes.append('{} falha(s)'.format(len(res['falhas'])))
    return ' | '.join(partes)
