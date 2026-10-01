# -*- coding: utf-8 -*-
"""Conflito de relatorio <-> apontamento do LOG: um e ESPELHO do outro.

O PEDIDO (Thiago, 30/09/2026)
-----------------------------
> "o que for feito no log referente a esse apontamento que foi feito la no
>  interferencias deve ser um espelho... tanto faz onde ele for mexer, um e
>  o outro devem ser iguais"

COMO
----
Os dois lados guardam o endereco do outro:

    conflito (no .status.json do relatorio)   ->  'log_id': <id do apontamento>
    apontamento (DAT/LOG/<id>.json)           ->  'origem': {'arquivo', 'caminho',
                                                              'chave'}

Mexer de um lado ESCREVE nos dois na hora (a janela faz). Isto aqui cobre o
que escapa disso — outra pessoa mexeu no LOG enquanto o relatorio estava
fechado: ao abrir, `puxar` traz o que e mais novo. A marca mais recente
vence, pela data, dos dois lados.

O status tem nomes diferentes nos dois vocabularios (o LOG fala 'aberta',
o relatorio fala 'pendente'); a traducao mora em `_log_ocorrencias`.

Puro: sem `clr`, sem Revit — testado em `dev-tools/tests/test_espelho.py`.
"""
import os

from Snippets._log_ocorrencias import DA_JANELA, PARA_JANELA

ABERTA_NO_LOG = 'aberta'
#: o repositorio de relatorios do projeto (`_repositorio.PASTA`)
PASTA_RELATORIOS = 'RELATORIOS'


def origem_do_conflito(caminho_relatorio, chave):
    """O endereco do conflito, gravado no apontamento que nasceu dele.

    O caminho absoluto vale na maquina de quem criou; na de outro engenheiro
    o drive pode ter outra letra. Por isso vai o NOME do arquivo junto: o
    relatorio mora na mesma DAT que o LOG, e `achar_relatorio` resolve.
    """
    return {'arquivo': os.path.basename(caminho_relatorio or ''),
            'caminho': caminho_relatorio or '', 'chave': chave}


def achar_relatorio(origem, pasta_log, existe=os.path.exists):
    """O caminho do relatorio de onde o apontamento veio. '' se sumiu.

    1. o caminho gravado (mesma maquina);
    2. o mesmo nome na DAT do projeto (a pasta-mae de `DAT/LOG`).
    """
    if not origem or not origem.get('chave'):
        return ''
    gravado = origem.get('caminho') or ''
    if gravado and existe(gravado):
        return gravado
    nome = origem.get('arquivo') or os.path.basename(gravado)
    if not nome or not pasta_log:
        return ''
    dat = os.path.dirname(pasta_log.rstrip('/\\'))
    # 3. o repositorio (`DAT/RELATORIOS`, 30/09/2026) — onde o relatorio
    # mora desde entao
    for pasta in (dat, os.path.join(dat, PASTA_RELATORIOS)):
        candidato = os.path.join(pasta, nome)
        if existe(candidato):
            return candidato
    return ''


def status_do_log_no_relatorio(status_log):
    return PARA_JANELA.get(status_log or ABERTA_NO_LOG, 'pendente')


def status_do_relatorio_no_log(status_relatorio):
    return DA_JANELA.get(status_relatorio or 'pendente', ABERTA_NO_LOG)


def ultima_fala(item_log):
    """O texto que o relatorio mostra na coluna de comentario."""
    mensagens = item_log.get('mensagens') or []
    if mensagens:
        return mensagens[-1].get('texto') or ''
    return item_log.get('texto') or ''


def _quando_do_log(item_log):
    datas = [item_log.get('status_em') or '', item_log.get('criado_em') or '']
    datas += [m.get('quando') or '' for m in item_log.get('mensagens') or []]
    return max(datas)


def puxar(conflito, item_log):
    """Traz do LOG o que e mais novo que a marca do conflito. -> True se mudou.

    Status, comentario (a ultima fala), quem e quando. So muda se o LOG
    mexeu DEPOIS da ultima marca do relatorio — senao quem acabou de marcar
    no relatorio perderia a marca para uma versao velha do apontamento.
    """
    if not conflito or not item_log:
        return False
    quando_log = _quando_do_log(item_log)
    if quando_log <= (conflito.get('quando') or ''):
        return False
    novo_status = status_do_log_no_relatorio(item_log.get('status'))
    fala = ultima_fala(item_log)
    quem = item_log.get('status_por') if (item_log.get('status_em') or '') \
        == quando_log else _autor_da_ultima(item_log)
    mudou = (conflito.get('status') != novo_status or
             (conflito.get('comentario') or '') != fala)
    conflito['status'] = novo_status
    conflito['comentario'] = fala
    conflito['por'] = quem or conflito.get('por') or ''
    conflito['quando'] = quando_log
    return mudou


def _autor_da_ultima(item_log):
    mensagens = item_log.get('mensagens') or []
    if mensagens:
        return mensagens[-1].get('autor') or ''
    return item_log.get('autor') or ''


def conflitos_ligados(registro):
    """{log_id: chave} — os conflitos que ja viraram apontamento."""
    ligados = {}
    for chave, item in (registro.get('conflitos') or {}).items():
        if item.get('log_id'):
            ligados[item['log_id']] = chave
    return ligados


def sincronizar_registro(registro, itens_log):
    """Aplica `puxar` em todos os conflitos ligados. -> [chaves que mudaram].

    `itens_log` = {id: apontamento}. Apontamento apagado nao desliga o
    conflito: o `log_id` fica, e a janela avisa que o outro lado sumiu.
    """
    mudaram = []
    for log_id, chave in conflitos_ligados(registro).items():
        item_log = itens_log.get(log_id)
        if item_log is None:
            continue
        if puxar(registro['conflitos'][chave], item_log):
            mudaram.append(chave)
    return sorted(mudaram)
