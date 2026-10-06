# -*- coding: utf-8 -*-
"""Caixa de entrada do LOG: o aviso que chega no Revit de quem foi chamado.

O PEDIDO (Thiago, 05/10/2026)
-----------------------------
> "que avise aos usuarios que tem uma nova notificacao, mesmo que o usuario
>  esteja com a aplicacao fechada... independente de qual projeto ele esteja
>  aberto... algo rapido, transicional, que nao trave a tela"

COMO (proposta validada pelo Thiago no mesmo dia)
--------------------------------------------------
Quem aponta "para Ana" grava, alem do apontamento na DAT da obra, um
arquivo pequeno na CAIXA da Ana, na pasta da empresa:

    <PYREVIT>/LOG/caixa/<id do Revit da Ana>/<quando>__<tipo>__<id>__<suf>.json

O Revit da Ana vigia so essa pasta (nao as obras) e mostra um balao.
Um arquivo por aviso: duas pessoas avisando ao mesmo tempo nao disputam o
mesmo arquivo — o padrao dos apontamentos ([[win-logocorrencias-fila]]).

QUEM E AVISADO (decisao do Thiago, 05/10/2026)
----------------------------------------------
- apontamento NOVO: quem esta no "Para";
- RESPOSTA: quem criou o apontamento e quem esta no "Para";
- ENCAMINHADO: so quem acabou de entrar no "Para".
Mudanca de status nao avisa (fica no contador da aba). Ninguem e avisado
do que ele mesmo fez.

Puro: sem `clr`, sem Revit — testado em `dev-tools/tests/test_caixa_entrada.py`.
"""
import re

from Snippets._log_equipe import id_de

NOVO = 'novo'
RESPOSTA = 'resposta'
ENCAMINHADO = 'encaminhado'
TIPOS = (NOVO, RESPOSTA, ENCAMINHADO)
#: dentro da pasta PYREVIT da empresa (onde mora o equipe.json)
PASTA = ('LOG', 'caixa')
DIAS_GUARDAR = 30
LIMITE_TEXTO = 140
VERSAO = 1
#: no APPDATA (`pyRevit/PYAMBAR/Interferencias`): ao abrir o Revit ainda nao
#: ha modelo para achar a pasta da empresa — o LOG anota onde ela fica
ARQUIVO_RAIZ = 'caixa_raiz.txt'
#: os avisos que ja viraram balao nesta maquina
ARQUIVO_VISTOS = 'caixa_vistos.json'
#: o clique no balao deixa aqui o apontamento a abrir; o LOG le e apaga
ARQUIVO_ABRIR = 'caixa_abrir.json'
#: os avisos que a pessoa ja ABRIU (viu o apontamento) — o contador do
#: botao LOG e o destaque em "Avisos recebidos" saem daqui (06/10/2026)
ARQUIVO_LIDOS = 'caixa_lidos.json'


def nome_de_pasta(ident):
    """O ID do Revit como nome de pasta: so letra, numero, - e _.

    Mesma forma do `HOST_APP.username` do pyRevit (antes do @, sem ponto),
    que e o ID gravado na equipe e no apontamento. O vigia da faixa le o
    `Application.Username` cru ('thiago.nunesXNUJD'): sem isto, a janela e
    quem avisa usavam 'thiagonunesXNUJD' e o vigia olhava outra pasta
    (06/10/2026).
    """
    ident = (ident or '').strip().split('@')[0].replace('.', '')
    limpo = re.sub(r'[^0-9A-Za-z_-]', '_', ident)
    return limpo.strip('_') or '_sem_id'


def _compacto(quando):
    """'2026-10-05T18:00:47' -> '20261005T180047' (ordena pelo nome)."""
    digitos = re.sub(r'[^0-9]', '', quando or '')
    return u'{}T{}'.format(digitos[:8], digitos[8:14]) if digitos else u'0'


def nome_do_arquivo(aviso, sufixo):
    return u'{}__{}__{}__{}.json'.format(
        _compacto(aviso['quando']), aviso['tipo'],
        re.sub(r'[^0-9A-Za-z_-]', '_', aviso['id'] or u'sem-id'), sufixo)


def trecho(texto, limite=LIMITE_TEXTO):
    texto = u' '.join((texto or u'').split())
    return texto if len(texto) <= limite else texto[:limite - 1] + u'…'


def aviso(tipo, item, de, de_id, obra, pasta_log, quando, texto=None):
    """O que vai para a caixa. `texto`: a resposta (no novo, o apontamento)."""
    if tipo not in TIPOS:
        raise ValueError('tipo invalido: {}'.format(tipo))
    return {'versao': VERSAO, 'tipo': tipo, 'id': item.get('id') or '',
            'de': de or '', 'de_id': de_id or '', 'obra': obra or '',
            'pasta_log': pasta_log or '', 'quando': quando or '',
            'texto': trecho(item.get('texto') if texto is None else texto)}


def _ids(nomes, equipe):
    """Nomes do "Para" -> (IDs do Revit, nomes sem cadastro)."""
    ids, sem = [], []
    for nome in nomes or []:
        nome = (nome or u'').strip()
        if not nome:
            continue
        ident = id_de(equipe, nome)
        if not ident:
            sem.append(nome)
        elif ident.lower() not in [i.lower() for i in ids]:
            ids.append(ident)
    return ids, sem


def destinatarios(tipo, item, quem_fez_id, equipe, novos_para=()):
    """Quem recebe o aviso. -> (IDs do Revit, nomes que nao tem ID).

    O autor do apontamento entra pelo `autor_id` (o nome pode ter mudado);
    apontamento antigo sem `autor_id` cai no nome.
    """
    if tipo == NOVO:
        nomes = list(item.get('para') or [])
    elif tipo == ENCAMINHADO:
        nomes = list(novos_para or [])
    else:
        nomes = list(item.get('para') or []) + list(novos_para or [])
        nomes.append(item.get('autor_id') or item.get('autor') or '')
    ids, sem = _ids(nomes, equipe)
    eu = (quem_fez_id or u'').lower()
    return [i for i in ids if i.lower() != eu], sem


def pendentes(nomes_de_arquivo, vistos):
    """Os avisos que ainda nao viraram balao, do mais velho ao mais novo."""
    ja = set(n.lower() for n in vistos or [])
    return sorted(n for n in nomes_de_arquivo
                  if n.lower().endswith('.json') and n.lower() not in ja)


def vencidos(nomes_de_arquivo, agora, dias=DIAS_GUARDAR):
    """Avisos mais velhos que `dias` (pela data no nome). `agora` ISO."""
    limite = _compacto(agora)[:8]
    if len(limite) < 8:
        return []
    ano, mes, dia = int(limite[:4]), int(limite[4:6]), int(limite[6:8])
    corte = _dias_absolutos(ano, mes, dia) - dias
    saida = []
    for nome in nomes_de_arquivo:
        data = nome[:8]
        if not data.isdigit():
            continue
        if _dias_absolutos(int(data[:4]), int(data[4:6]),
                           int(data[6:8])) < corte:
            saida.append(nome)
    return saida


def _dias_absolutos(ano, mes, dia):
    """Dias desde uma data fixa — sem datetime (snippet puro e simples)."""
    a = ano - (1 if mes < 3 else 0)
    m = mes + (12 if mes < 3 else 0)
    return 365 * a + a // 4 - a // 100 + a // 400 + (153 * (m - 3) + 2) // 5 \
        + dia


ROTULO = {NOVO: u'Novo apontamento para você',
          RESPOSTA: u'Resposta no apontamento',
          ENCAMINHADO: u'Apontamento encaminhado para você'}


def balao(avisos):
    """(categoria, titulo) do balao. Varios de uma vez viram um resumo."""
    if not avisos:
        return None
    if len(avisos) == 1:
        a = avisos[0]
        obra = u' · {}'.format(a['obra']) if a.get('obra') else u''
        return (u'PYAMBAR · LOG{}'.format(obra),
                u'{} — {}: {}'.format(ROTULO.get(a['tipo'], a['tipo']),
                                      a.get('de') or u'alguém',
                                      a.get('texto') or u''))
    obras = []
    for a in avisos:
        if a.get('obra') and a['obra'] not in obras:
            obras.append(a['obra'])
    return (u'PYAMBAR · LOG',
            u'{} avisos novos para você{}'.format(
                len(avisos), u' — ' + u', '.join(obras[:3]) if obras else u''))


# --------------------------------------- avisos recebidos e contador (v3.4)
# Thiago, 06/10/2026: "se eu nao conseguir clicar na notificacao, eu perco".
# O aviso nao se perde (fica na caixa 30 dias); falta MOSTRAR: o botao LOG
# conta os nao lidos e o LOG lista todos. Lido = a pessoa abriu o apontamento.

def nao_lidos(nomes_de_arquivo, lidos):
    """Os avisos ainda nao abertos, do mais novo ao mais velho."""
    ja = set(n.lower() for n in lidos or [])
    return sorted((n for n in nomes_de_arquivo
                   if n.lower().endswith('.json') and n.lower() not in ja),
                  reverse=True)


def avisos_do_apontamento(avisos_por_nome, id_apontamento):
    """Os arquivos de aviso que falam deste apontamento (abrir um apontamento
    da como lidos todos os avisos dele: novo, respostas, encaminhado)."""
    if not id_apontamento:
        return []
    return sorted(nome for nome, aviso in avisos_por_nome.items()
                  if (aviso or {}).get('id') == id_apontamento)


def manter_lidos(lidos, nomes_existentes):
    """Esquece os lidos que ja sairam da caixa (limpeza de 30 dias)."""
    existem = set(n.lower() for n in nomes_existentes)
    return [n for n in lidos or [] if n.lower() in existem]


def rotulo_do_botao(base, quantos):
    """'LOG' -> 'LOG · 2' enquanto houver aviso nao lido."""
    return u'{} · {}'.format(base, quantos) if quantos else base


def resumo_do_aviso(aviso):
    """(titulo, detalhe sem o 'quando') para a lista 'Avisos recebidos'."""
    titulo = u'{} — {}'.format(ROTULO.get(aviso.get('tipo'), u'Aviso'),
                               aviso.get('de') or u'alguém')
    return titulo, aviso.get('obra') or u''
