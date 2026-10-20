# -*- coding: utf-8 -*-
"""Log de sessao do Unit Mapper — o formato, puro (sem clr).

Pedido do Thiago em 15/09/2026: "adicione um log para vc poder analisar
posteriormente e acompanhar todas as escolhas e tudo que vai acontecer".

UMA LINHA JSON POR EVENTO
-------------------------
    {"quando": "2026-09-15 08:30:00", "sessao": "20260915-083000",
     "tipo": "aplicar_resultado", ...dados do evento}

JSON por linha e nao texto livre: quem analisa (o Claude, depois) filtra por
`tipo`, por `sessao` e por id de elemento sem adivinhar formato. Os campos
`quando`, `sessao` e `tipo` nunca sao sobrescritos pelos dados.

A camada que grava no disco e `um_log.py` no pushbutton.
"""
import json
import time

#: passou disso, o arquivo vira `.1` (o anterior e apagado)
LIMITE_BYTES = 20 * 1024 * 1024

_FIXOS = ('quando', 'sessao', 'tipo')


def agora():
    return time.strftime('%Y-%m-%d %H:%M:%S')


def novo_id_de_sessao(relogio=None):
    """'20260915-083000' — uma abertura da janela."""
    return (relogio or agora)().replace('-', '').replace(':', '').replace(' ', '-')


def para_json(valor):
    """Copia serializavel: set vira lista ordenada, tupla vira lista, objeto
    do Revit (ElementId, Element) vira texto. Nunca levanta."""
    if valor is None or isinstance(valor, (bool, int, float, str)):
        return valor
    if isinstance(valor, dict):
        return dict((u'{}'.format(k), para_json(v)) for k, v in valor.items())
    if isinstance(valor, (list, tuple)):
        return [para_json(v) for v in valor]
    if isinstance(valor, (set, frozenset)):
        return sorted((para_json(v) for v in valor), key=lambda x: u'{}'.format(x))
    try:
        return u'{}'.format(valor)
    except Exception:
        return repr(valor)


def linha(sessao, tipo, dados=None, relogio=None):
    """O texto de uma linha do log (sem o '\\n')."""
    registro = {'quando': (relogio or agora)(), 'sessao': sessao, 'tipo': tipo}
    for chave, valor in (dados or {}).items():
        if chave not in _FIXOS:
            registro[chave] = para_json(valor)
    return json.dumps(registro, ensure_ascii=False, sort_keys=True)


def assinatura(valor):
    """Texto estavel para comparar dois estados (dedupe de eventos repetidos)."""
    return json.dumps(para_json(valor), ensure_ascii=False, sort_keys=True)


def diferencas(antes, depois):
    """{chave: {'de', 'para'}} do que mudou — chave nova ou removida tambem."""
    antes, depois = antes or {}, depois or {}
    saida = {}
    for chave in sorted(set(antes) | set(depois)):
        de, para = para_json(antes.get(chave)), para_json(depois.get(chave))
        if assinatura(de) != assinatura(para):
            saida[chave] = {'de': de, 'para': para}
    return saida


def _somar(contagem, chave):
    contagem[chave] = contagem.get(chave, 0) + 1


def resumo_da_preview(descritos):
    """Contagens de uma preview inteira, sem listar elemento por elemento.

    `descritos`: [{'papel', 'categoria', 'orientacao', 'decisoes',
    'bloqueios', 'problemas'}] — o que a janela sabe de cada linha.
    """
    perfis, decisoes, bloqueios = {}, {}, {}
    for item in descritos or []:
        _somar(perfis, u'{} | {} | {}'.format(item.get('papel') or '-',
                                              item.get('categoria') or '-',
                                              item.get('orientacao') or '-'))
        for nome, decisao in sorted((item.get('decisoes') or {}).items()):
            _somar(decisoes, u'{} = {} ({}: {})'.format(
                nome, decisao.get('valor'), decisao.get('origem'),
                decisao.get('regra')))
        for nome, motivo in sorted((item.get('bloqueios') or {}).items()):
            _somar(bloqueios, u'{}: {}'.format(nome, motivo))
        for motivo in item.get('problemas') or []:
            _somar(bloqueios, motivo)
    return {'perfis': perfis, 'decisoes': decisoes, 'bloqueios': bloqueios}


def precisa_girar(tamanho_atual, limite=LIMITE_BYTES):
    return tamanho_atual > limite
