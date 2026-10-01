# -*- coding: utf-8 -*-
"""Repositorio de relatorios do projeto: N pessoas, N perguntas, um status.

O PROBLEMA (Thiago, 30/09/2026)
-------------------------------
> "o que acontece quando dois usuarios criam um relatorio de interferencia?
>  ... nos termos um repositorio dos relatorios criados para aquele projeto"

Antes, o relatorio levava o nome do modelo aberto: dois engenheiros no mesmo
modelo se sobrescreviam, e os conflitos do primeiro viravam "sairam do
relatorio" — o mesmo sinal de "resolvido no modelo" — sem nada ter mudado.

AS TRES DECISOES (do Thiago, mesma data)
---------------------------------------
1. Um relatorio e uma PERGUNTA, nao uma execucao. A pergunta e o tipo + o
   escopo (modelos e "o que x o que"; ou lajes e regras). Refazer a MESMA
   pergunta, por qualquer pessoa, atualiza aquele relatorio e guarda o
   historico. Pergunta diferente = outro relatorio, lado a lado. Assim o
   "sairam" volta a significar "corrigido": so compara rodadas da mesma
   pergunta.
2. O status e do PAR, nao do relatorio: resolver o tubo x duto num relatorio
   resolve em todos onde ele aparece. Mora em `status_do_projeto.json`.
3. O HTML exportado pelo Revit entra no repositorio ao ser aberto — visivel
   para todos, com o espelho do LOG funcionando em qualquer maquina.

    <pasta do central>/DAT/RELATORIOS/
        clash-<hash>.json          a pergunta + a ultima rodada + historico
        clash-<hash>.status.json   presenca dos pares nesta pergunta
        passes-<hash>.json ...
        html-<hash>.json ...
        status_do_projeto.json     o status de cada PAR, para o projeto

Puro: sem `clr`, sem Revit — testado em `dev-tools/tests/test_repositorio.py`.
"""
import re

PASTA = 'RELATORIOS'
STATUS_DO_PROJETO = 'status_do_projeto.json'
MAX_HISTORICO = 30
#: o que e do PAR (vale para o projeto); presenca (no_relatorio, visto_em)
#: continua sendo de cada relatorio
CAMPOS_DE_STATUS = ('status', 'comentario', 'por', 'quando', 'log_id',
                    'reaberto_em', 'resolvido_antes_em')
FONTES = ('clash', 'passes', 'html')
#: as abas e os relatorios que cada uma mostra
FONTES_DA_ABA = {'html': ('clash', 'html'), 'passes': ('passes',)}
ANTES_DO_REPOSITORIO = u'(antes do repositório)'


# ------------------------------------------------------------ identidade

def hash_estavel(texto):
    """FNV-1a 64 bits em hex. Igual em CPython e IronPython, sem hashlib."""
    valor = 0xcbf29ce484222325
    for byte in bytearray((texto or u'').encode('utf-8')):
        valor ^= byte
        valor = (valor * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
    return '{:016x}'.format(valor)[:12]


def _lista(valores):
    return u';'.join(sorted(set((v or u'').strip().lower()
                                for v in (valores or []) if v)))


def assinatura(fonte, escopo):
    """A pergunta em texto canonico: a ordem das caixas marcadas nao importa."""
    escopo = escopo or {}
    if fonte == 'clash':
        return u'clash|m:{}|a:{}|b:{}|mm:{}'.format(
            _lista(escopo.get('modelos')), _lista(escopo.get('categorias')),
            _lista(escopo.get('contra')), bool(escopo.get('mesmo_modelo')))
    if fonte == 'passes':
        return u'passes|l:{}|v:{}|r:{}'.format(
            _lista(escopo.get('lajes')), _lista(escopo.get('vinculos')),
            _lista(escopo.get('regras')))
    return u'html|{}'.format((escopo.get('arquivo') or u'').strip().lower())


def id_do_relatorio(fonte, escopo):
    return u'{}-{}'.format(fonte, hash_estavel(assinatura(fonte, escopo)))


#: categoria -> familia: o nome do relatorio fala a lingua da obra
#: ("Tubo x Duto"), nao a lista de caixas marcadas (Thiago, 30/09/2026:
#: "o nome pode ser algo mais curto e inteligente")
FAMILIA = {
    u'tubulação': u'Tubo', u'conexões de tubo': u'Tubo',
    u'acessórios de tubo': u'Tubo', u'isolamento de tubo': u'Tubo',
    u'dutos': u'Duto', u'conexões de duto': u'Duto',
    u'acessórios de duto': u'Duto', u'terminais de ar': u'Duto',
    u'eletrocalhas': u'Eletrocalha', u'conduítes': u'Conduíte',
    u'equipamento mecânico': u'Equipamento',
    u'peças sanitárias': u'Louça',
    u'pilares estruturais': u'Estrutura', u'vigas e treliças': u'Estrutura',
    u'paredes': u'Parede', u'pisos': u'Piso', u'forros': u'Forro',
}


def familias(categorias):
    """['Tubulação', 'Conexões de tubo', 'Dutos'] -> 'Tubo + Duto'."""
    vistas = []
    for categoria in categorias or []:
        nome = FAMILIA.get((categoria or u'').strip().lower(),
                           (categoria or u'').strip())
        if nome and nome not in vistas:
            vistas.append(nome)
    return u' + '.join(vistas) or u'?'


def _nivel_curto(nivel):
    """'02 - LEVEL 2' -> 'L2'; 'Térreo' fica 'Térreo'."""
    achou = re.search(r'(?:level|nível|nivel|piso|pav\w*)\s*(\d+)',
                      nivel or u'', re.I)
    return u'L{}'.format(achou.group(1)) if achou else (nivel or u'').strip()


def titulo(fonte, escopo):
    """O NOME curto do relatorio: 'Tubo × Duto', 'Passes L2', 'Revit · X'."""
    escopo = escopo or {}
    if fonte == 'clash':
        de = familias(escopo.get('categorias'))
        contra = escopo.get('contra') or []
        if contra:
            return u'{} × {}'.format(de, familias(contra))
        return u'{} (todos)'.format(de)
    if fonte == 'passes':
        lajes = [_nivel_curto(n) for n in escopo.get('lajes') or []]
        return u'Passes {}'.format(u', '.join(lajes) or u'?')
    nome = re.sub(r'\.html?$', u'', escopo.get('arquivo') or u'relatório',
                  flags=re.I)
    return u'Revit · {}'.format(nome if len(nome) <= 28 else nome[:27] + u'…')


def descricao(fonte, escopo):
    """O escopo inteiro, para o tooltip — o nome curto nao perde nada."""
    escopo = escopo or {}
    if fonte == 'clash':
        linhas = [u'Verificar: ' + (u', '.join(escopo.get('categorias') or [])
                                    or u'?'),
                  u'Contra: ' + (u', '.join(escopo.get('contra') or [])
                                 or u'as mesmas (tudo contra tudo)'),
                  u'Modelos ({}): {}'.format(
                      len(escopo.get('modelos') or []),
                      u', '.join(escopo.get('modelos') or []))]
        if escopo.get('mesmo_modelo'):
            linhas.append(u'Inclui pares dentro do mesmo modelo')
        return u'\n'.join(linhas)
    if fonte == 'passes':
        return u'\n'.join([
            u'Lajes: ' + u', '.join(escopo.get('lajes') or []),
            u'Tubos de: ' + u', '.join(escopo.get('vinculos') or []),
            u'Regras: ' + u', '.join(escopo.get('regras') or [])])
    return u'HTML exportado pelo Revit: {}'.format(escopo.get('arquivo') or '')


def nomes_unicos(metas):
    """Dois relatorios com o mesmo nome curto ganham o que os diferencia:
    primeiro o numero de modelos, depois quem gerou."""
    contagem = {}
    for m in metas:
        contagem[m['titulo']] = contagem.get(m['titulo'], 0) + 1
    for m in metas:
        m['nome'] = m['titulo']
        if contagem[m['titulo']] > 1:
            m['nome'] = u'{} · {} modelo(s)'.format(m['titulo'],
                                                   m.get('n_modelos', 0))
    contagem = {}
    for m in metas:
        contagem[m['nome']] = contagem.get(m['nome'], 0) + 1
    for m in metas:
        if contagem[m['nome']] > 1:
            m['nome'] = u'{} · {}'.format(m['nome'], m['autor'])
    return metas


# ------------------------------------------------------------- execucoes

def registrar_execucao(anterior, novo, autor, autor_id, agora):
    """O relatorio novo com a identidade e o historico da mesma pergunta.

    Quem criou a pergunta fica; cada rodada entra no topo do historico.
    """
    anterior = anterior or {}
    novo = dict(novo)
    novo['criado_por'] = anterior.get('criado_por') or autor
    novo['criado_em'] = anterior.get('criado_em') or agora
    novo['autor'] = autor
    novo['autor_id'] = autor_id or ''
    novo['gerado_em'] = agora
    rodada = {'autor': autor, 'gerado_em': agora,
              'achados': len(novo.get('achados') or [])}
    novo['historico'] = ([rodada] + list(anterior.get('historico') or
                                         []))[:MAX_HISTORICO]
    return novo


def meta(relatorio, caminho):
    """O pouco que o dropdown precisa — sem carregar os achados na tela."""
    fonte = relatorio.get('fonte') or 'clash'
    escopo = relatorio.get('escopo') or {}
    return {'id': relatorio.get('id') or '', 'fonte': fonte,
            'titulo': titulo(fonte, escopo),
            'descricao': descricao(fonte, escopo),
            'n_modelos': len(escopo.get('modelos') or
                             escopo.get('vinculos') or []),
            'autor': relatorio.get('autor') or ANTES_DO_REPOSITORIO,
            'gerado_em': relatorio.get('gerado_em') or '',
            'projeto': relatorio.get('projeto') or '',
            'achados': len(relatorio.get('achados') or []),
            'rodadas': len(relatorio.get('historico') or []) or 1,
            'caminho': caminho}


def ordenar(metas):
    """O mais recente primeiro."""
    return sorted(metas, key=lambda m: m.get('gerado_em') or '', reverse=True)


def detalhe(m, quando_relativo=None):
    """A segunda linha do dropdown: 'Thiago Nunes · há 2 h · 43 achados'."""
    quando = m.get('gerado_em') or ''
    if quando_relativo is not None:
        quando = quando_relativo(quando)
    else:
        quando = quando.replace('T', ' ')[:16]
    rodadas = m.get('rodadas') or 1
    return u'{} · {} · {} achado(s){}'.format(
        m['autor'], quando, m['achados'],
        u' · {} rodadas'.format(rodadas) if rodadas > 1 else u'')


def da_aba(metas, aba):
    fontes = FONTES_DA_ABA.get(aba, (aba,))
    return ordenar([m for m in metas if m['fonte'] in fontes])


def escolher(metas, aba, meu_ultimo=None, pedido=None):
    """Qual relatorio abrir numa aba. -> meta ou None.

    1. o PEDIDO (veio de um apontamento que nasceu naquele relatorio);
    2. o ultimo que EU gerei ou abri nesta aba;
    3. o mais recente do projeto.
    """
    da = da_aba(metas, aba)
    por_id = dict((m['id'], m) for m in da)
    for escolha in (pedido, meu_ultimo):
        if escolha and escolha in por_id:
            return por_id[escolha]
    return da[0] if da else None


# ------------------------------------------------------ status do projeto

def status_vazio():
    return {'versao': 1, 'pares': {}}


def campos_de_status(item):
    return dict((c, item[c]) for c in CAMPOS_DE_STATUS if c in item)


def mesclar_status(disco, meu):
    """Duas versoes do status do projeto: por par, a marca mais nova vence."""
    junto = status_vazio()
    pares_d = (disco or {}).get('pares') or {}
    pares_m = (meu or {}).get('pares') or {}
    for chave in set(pares_d) | set(pares_m):
        d, m = pares_d.get(chave), pares_m.get(chave)
        if d is None or m is None:
            junto['pares'][chave] = dict(d or m)
        elif (d.get('quando') or '') > (m.get('quando') or ''):
            junto['pares'][chave] = dict(d)
        else:
            junto['pares'][chave] = dict(m)
    return junto


def puxar_status(registro, projeto):
    """Traz do projeto o que e mais novo que a marca local. -> chaves."""
    pares = (projeto or {}).get('pares') or {}
    mudaram = []
    for chave, item in (registro.get('conflitos') or {}).items():
        do_projeto = pares.get(chave)
        if not do_projeto:
            continue
        if (do_projeto.get('quando') or '') <= (item.get('quando') or ''):
            continue
        item.update(campos_de_status(do_projeto))
        mudaram.append(chave)
    return sorted(mudaram)


def empurrar_status(projeto, registro, chaves=None):
    """Leva ao projeto o que o relatorio marcou. -> chaves que mudaram.

    So quem tem marca (`quando`) sobe: par nunca tocado nao cria linha.
    """
    projeto = projeto if projeto is not None else status_vazio()
    pares = projeto.setdefault('pares', {})
    itens = registro.get('conflitos') or {}
    mudaram = []
    for chave in (chaves if chaves is not None else list(itens)):
        item = itens.get(chave)
        if not item or not item.get('quando'):
            continue
        atual = pares.get(chave) or {}
        if (atual.get('quando') or '') >= item['quando'] and atual:
            if (atual.get('quando') or '') > item['quando']:
                continue
            if campos_de_status(atual) == campos_de_status(item):
                continue
        pares[chave] = campos_de_status(item)
        mudaram.append(chave)
    return sorted(mudaram)


# ----------------------------------------------------------- HTML do Revit

def _lado_com_projeto(lado, projeto):
    if lado and not lado.get('vinculo'):
        return dict(lado, vinculo=projeto)
    return lado


def chave_com_projeto(chave, projeto):
    """'#123|link.rvt#9' -> 'modelo.rvt#123|link.rvt#9', na ordem canonica.

    No HTML do Revit o lado do modelo aberto vem SEM arquivo; no nosso clash
    vem com ele. Sem isto o mesmo par teria duas chaves e o status nao seria
    do projeto.
    """
    lados = []
    for lado in (chave or '').split('|'):
        vinculo, _, ident = lado.rpartition('#')
        lados.append(u'{}#{}'.format(vinculo or (projeto or '').lower(), ident))
    return u'|'.join(sorted(lados))


def html_para_relatorio(lido, arquivo_html, projeto_nome):
    """O HTML ja lido (`ler_relatorio`) no formato do repositorio.

    O lado do modelo aberto ganha o nome do projeto; as chaves sao refeitas.
    """
    projeto = projeto_nome or u''
    achados = []
    for conflito in lido.get('conflitos') or []:
        a = _lado_com_projeto(conflito['a'], projeto)
        b = _lado_com_projeto(conflito.get('b'), projeto)
        achado = {'a': a, 'b': b,
                  'chave': chave_com_projeto(conflito['chave'], projeto)}
        for extra in ('regra', 'medida', 'nivel', 'gravidade', 'valor'):
            if extra in conflito:
                achado[extra] = conflito[extra]
        achados.append(achado)
    escopo = {'arquivo': arquivo_html}
    return {'fonte': 'html', 'versao': 1,
            'id': id_do_relatorio('html', escopo), 'escopo': escopo,
            'titulo': titulo('html', escopo), 'projeto': lido.get('projeto')
            or projeto, 'lajes': [], 'parametros': {'arquivo': arquivo_html},
            'achados': achados}


def registro_com_projeto(registro, projeto):
    """O .status.json antigo de um HTML, com as chaves refeitas."""
    novo = {'conflitos': {}}
    for chave, item in ((registro or {}).get('conflitos') or {}).items():
        item = dict(item)
        item['a'] = _lado_com_projeto(item.get('a'), projeto)
        item['b'] = _lado_com_projeto(item.get('b'), projeto)
        novo['conflitos'][chave_com_projeto(chave, projeto)] = item
    return novo


# -------------------------------------------------- relatorios de antes

_NOME_ANTIGO = re.compile(r'^(?P<modelo>.+) - (?P<tipo>interferencias|passes)'
                          r'\.json$', re.I)


def relatorio_antigo(nome_arquivo):
    """'CIQ - interferencias.json' -> ('clash', 'CIQ'). None se nao for."""
    achou = _NOME_ANTIGO.match(nome_arquivo or '')
    if not achou:
        return None
    tipo = 'clash' if achou.group('tipo').lower() == 'interferencias' \
        else 'passes'
    return tipo, achou.group('modelo')


def escopo_de_relatorio(relatorio):
    """O escopo de um relatorio gravado antes do repositorio (parametros)."""
    fonte = relatorio.get('fonte') or 'clash'
    p = relatorio.get('parametros') or {}
    if fonte == 'passes':
        return {'lajes': list(relatorio.get('lajes') or []),
                'vinculos': list(p.get('vinculos') or []),
                'regras': list(p.get('regras') or [])}
    return {'modelos': list(p.get('modelos') or relatorio.get('lajes') or []),
            'categorias': list(p.get('categorias') or []),
            'contra': list(p.get('contra') or []),
            'mesmo_modelo': bool(p.get('mesmo_modelo', True))}


def migrar(relatorio):
    """Um relatorio de antes vira uma pergunta do repositorio (sem autor)."""
    fonte = relatorio.get('fonte') or 'clash'
    escopo = escopo_de_relatorio(relatorio)
    novo = dict(relatorio)
    novo['escopo'] = escopo
    novo['id'] = id_do_relatorio(fonte, escopo)
    novo['titulo'] = titulo(fonte, escopo)
    novo.setdefault('autor', ANTES_DO_REPOSITORIO)
    novo.setdefault('criado_por', ANTES_DO_REPOSITORIO)
    novo.setdefault('historico', [{'autor': ANTES_DO_REPOSITORIO,
                                   'gerado_em': relatorio.get('gerado_em')
                                   or '', 'achados': len(
                                       relatorio.get('achados') or [])}])
    return novo
