# -*- coding: utf-8 -*-
"""Log da obra: recados com lugar no modelo — a regra, sem Revit.

Sem clr/Autodesk: testado em CPython (`dev-tools/tests/test_log_ocorrencias_dat.py`).
Quem le e grava a pasta e o modulo da ferramenta; aqui so ha a forma do item,
a conversa, o filtro e a adaptacao para a janela das Pendencias.

POR QUE ISTO EXISTE (Thiago, 24/09/2026)
----------------------------------------
O LogOcorrencias (2.348 linhas) funcionava, mas ABRIR custava duas chamadas
HTTP sincronas a um web app do Apps Script (roster + inbox) e ENVIAR custava
outra, com a imagem subindo para o Drive. O usuario esperava a rede para ver
a janela. E o caminho vai morrer: a empresa migrou de workspace.

A troca: **uma pasta na DAT da obra**, no mesmo padrao do relatorio de
interferencias. Ler a pasta e disco, nao rede.

UM ARQUIVO POR OCORRENCIA
-------------------------
`DAT/LOG/<id>.json`. Duas pessoas escrevendo ao mesmo tempo nunca disputam o
mesmo arquivo — e o que um JSON unico nao garante. Responder toca so o
arquivo daquela ocorrencia, e a conversa e **so acrescentar**: mesclar une as
mensagens por id, entao ninguem sobrescreve o recado do outro.

O MESMO VOCABULARIO DAS INTERFERENCIAS
--------------------------------------
    aberta -> pendente | resolvida -> resolvido | ignorada -> ignorar
`como_registro` entrega os itens na forma que a janela ja sabe mostrar
(lista em arvore, sanfona, filtros, "proxima pendente", navegacao entre
modelos). O LOG e uma FONTE nova, nao uma janela nova.

O ALVO GUARDA UniqueId, NAO ElementId
-------------------------------------
ElementId e local ao arquivo; UniqueId sobrevive (licao do LogOcorrencias).
O `ponto` fica nas coordenadas do MODELO DO ALVO — quem abre aquele modelo
usa direto; quem o ve como vinculo aplica a transform. Elemento apagado e
refeito perde o UniqueId, mas o ponto ainda leva a regiao certa.
"""
import re

ABERTA = 'aberta'
RESOLVIDA = 'resolvida'
IGNORADA = 'ignorada'
STATUS = (ABERTA, RESOLVIDA, IGNORADA)

#: aberta/resolvida/ignorada -> o status da janela (Snippets._interferencia)
PARA_JANELA = {ABERTA: 'pendente', RESOLVIDA: 'resolvido',
               IGNORADA: 'ignorar'}
DA_JANELA = dict((v, k) for k, v in PARA_JANELA.items())

VERSAO = 1
_RE_MENCAO = re.compile(r'@([\w\.\-]+(?:\s+[\w\.\-]+)?)', re.UNICODE)
_RE_ID = re.compile(r'[^a-z0-9]+')


# -------------------------------------------------------------------- criar

def slug(texto, limite=12):
    """'Thiago Barreto' -> 'thiago-barre' — para caber no nome do arquivo."""
    limpo = _RE_ID.sub('-', (texto or '').lower()).strip('-')
    return limpo[:limite] or 'anonimo'


def novo_id(agora, usuario, sufixo):
    """'20260924-1030-thiago-barre-3f2a'. `sufixo`: 4 chars de quem chama
    (uuid) — a funcao e pura e nao inventa aleatorio."""
    compacto = re.sub(r'[^0-9]', '', (agora or ''))[:12]
    return u'{}-{}-{}'.format(compacto, slug(usuario), sufixo)


def nova_ocorrencia(texto, autor, agora, id_=None, para=(), alvos=(),
                    modelo='', vista='', nivel='', imagem='', autor_id='',
                    origem=None):
    """O item como ele vai para o disco.

    alvo: {arquivo, uniqueId, elementId, categoria, descricao,
           ponto: {min: [x,y,z], max: [x,y,z]}}  (coordenadas do `arquivo`)

    `autor` e o NOME de gente ('Thiago Nunes') — o arquivo tambem e lido por
    humanos; `autor_id` guarda o ID do Revit, que e a chave que nunca muda
    ([[_log_equipe]], 24/09/2026).
    """
    return {
        'versao': VERSAO,
        'id': id_ or novo_id(agora, autor, '0000'),
        'criado_em': agora,
        'autor': autor,
        'autor_id': autor_id or '',
        'para': [p for p in para if p],
        'texto': texto or '',
        'status': ABERTA,
        'status_por': '',
        'status_em': '',
        'modelo': modelo,
        'vista': vista,
        'nivel': nivel,
        'imagem': imagem,
        'alvos': list(alvos),
        'mensagens': [],
        # v2.5: de onde veio (relatorio + chave do conflito). E o que faz o
        # apontamento e o conflito serem ESPELHO um do outro (_espelho.py).
        'origem': dict(origem) if origem else {},
    }


def arquivo_do_item(item):
    return u'{}.json'.format(item['id'])


def normalizar(item):
    """Item vindo do disco com as chaves garantidas (arquivo de versao
    antiga nao pode derrubar a janela)."""
    if not isinstance(item, dict) or not item.get('id'):
        return None
    base = nova_ocorrencia('', '', '', id_=item['id'])
    base.update(dict((k, v) for k, v in item.items() if v is not None))
    base['status'] = base['status'] if base['status'] in STATUS else ABERTA
    base['para'] = [p for p in (base.get('para') or []) if p]
    base['alvos'] = list(base.get('alvos') or [])
    base['mensagens'] = [m for m in (base.get('mensagens') or [])
                         if isinstance(m, dict) and m.get('id')]
    return base


# ------------------------------------------------------------------ conversa

def responder(item, texto, autor, agora, id_msg, imagem=''):
    """Acrescenta uma mensagem. `id_msg` vem de quem chama (uuid).

    `imagem` (v2.5): o nome do arquivo em `DAT/LOG/img` — resposta tambem
    leva print, nao so o apontamento que abriu a conversa.
    """
    mensagem = {'id': id_msg, 'quando': agora, 'autor': autor,
                'texto': texto or ''}
    if imagem:
        mensagem['imagem'] = imagem
    item.setdefault('mensagens', []).append(mensagem)
    return item


def acrescentar_para(item, nomes):
    """Soma destinatarios sem repetir. -> True se mudou.

    Encaminhar e ACRESCENTAR: quem ja estava na conversa continua nela.
    """
    atuais = list(item.get('para') or [])
    vistos = set(n.strip().lower() for n in atuais if n)
    mudou = False
    for nome in nomes or []:
        nome = (nome or '').strip()
        if nome and nome.lower() not in vistos:
            vistos.add(nome.lower())
            atuais.append(nome)
            mudou = True
    item['para'] = atuais
    return mudou


def separar_nomes(texto):
    """'Ana, Bruno Lima; @carlos' -> ['Ana', 'Bruno Lima', 'carlos']."""
    partes = []
    for bruto in (texto or '').replace(';', ',').split(','):
        nome = bruto.strip().lstrip('@').strip()
        if nome and nome.lower() not in [p.lower() for p in partes]:
            partes.append(nome)
    return partes


def mudar_status(item, status, autor, agora):
    if status not in STATUS:
        raise ValueError(u'status inválido: {}'.format(status))
    item['status'] = status
    item['status_por'] = autor
    item['status_em'] = agora
    return item


def mesclar(disco, meu):
    """Junta duas versoes do MESMO arquivo.

    Mensagens: uniao por id, na ordem do `quando` (ninguem perde recado).
    Status: o mais recente pelo `status_em`. O texto original nao muda.
    """
    if not disco:
        return meu
    if not meu:
        return disco
    junto = dict(disco)
    junto.update(dict((k, v) for k, v in meu.items() if k not in
                      ('mensagens', 'status', 'status_por', 'status_em')))
    vistas = {}
    for mensagem in (disco.get('mensagens') or []) + \
            (meu.get('mensagens') or []):
        vistas[mensagem['id']] = mensagem
    junto['mensagens'] = sorted(vistas.values(),
                                key=lambda m: (m.get('quando') or '',
                                               m.get('id') or ''))
    mais_novo = disco if (disco.get('status_em') or '') > \
        (meu.get('status_em') or '') else meu
    for campo in ('status', 'status_por', 'status_em'):
        junto[campo] = mais_novo.get(campo, junto.get(campo))
    # destinatarios: UNIAO — dois encaminhando ao mesmo tempo nao se apagam
    para = {'para': list(disco.get('para') or [])}
    acrescentar_para(para, meu.get('para') or [])
    junto['para'] = para['para']
    return junto


# -------------------------------------------------------------------- gente

def mencoes(texto, conhecidos=()):
    """['Thiago', 'ana.paula'] — @nome no texto, sem repetir.

    UMA palavra por padrao: em "@thiago confere isso", "confere" nao e
    sobrenome. Nome composto so quando bate com alguem de `conhecidos`
    (o LogOcorrencias fazia igual, com o roster).
    """
    texto = texto or ''
    achados = []
    por_tamanho = sorted([c for c in conhecidos if c],
                         key=lambda c: -len(c))
    for casado in _RE_MENCAO.finditer(texto):
        nome = casado.group(1).strip()
        resto = texto[casado.start(1):]
        for conhecido in por_tamanho:
            if resto.lower().startswith(conhecido.lower()):
                nome = resto[:len(conhecido)]
                break
        else:
            nome = nome.split()[0] if nome.split() else ''
        if nome and nome.lower() not in [a.lower() for a in achados]:
            achados.append(nome)
    return achados


def pessoas(itens, equipe=()):
    """A lista que auto-completa: a equipe do `equipe.json` mais todo mundo
    que ja escreveu ou foi mencionado (decisao do Thiago, 24/09/2026)."""
    nomes = []
    vistos = set()
    for nome in list(equipe) + [n for item in itens
                                for n in _gente_do_item(item, equipe)]:
        nome = (nome or '').strip()
        chave = nome.lower()
        if nome and chave not in vistos:
            vistos.add(chave)
            nomes.append(nome)
    return sorted(nomes, key=lambda n: n.lower())


def _gente_do_item(item, conhecidos=()):
    """Autor, destinatários, quem respondeu e quem foi mencionado — no texto
    do recado E no das respostas."""
    mensagens = item.get('mensagens') or []
    nomes = [item.get('autor', '')] + list(item.get('para') or [])
    nomes += [m.get('autor', '') for m in mensagens]
    for texto in [item.get('texto', '')] + [m.get('texto', '')
                                            for m in mensagens]:
        nomes += mencoes(texto, conhecidos)
    return nomes


def _eu(usuario):
    """Como EU apareco nos apontamentos.

    `usuario` pode ser o nome ('Thiago Nunes'), o ID do Revit
    ('thiagonunesXNUJD') ou os dois (`_log_equipe.apelidos`): o apontamento
    de ontem gravou o ID, o de hoje grava o nome (24/09/2026).
    """
    if usuario is None:
        return set()
    if isinstance(usuario, (list, tuple, set)):
        return set((u or '').strip().lower() for u in usuario if u)
    return set([usuario.strip().lower()]) if usuario.strip() else set()


def responder_a(item, usuario):
    """Quem recebe a minha resposta — o 'Para' ja preenchido (06/10/2026).

    Quem falou por ULTIMO e nao sou eu; sem resposta de outra pessoa, quem
    criou o apontamento; apontamento meu sem resposta de ninguem: ''.
    Devolve o nome como gravado (o autor pode ter o ID do Revit: a janela
    traduz para o nome).
    """
    eu = _eu(usuario)
    for mensagem in reversed(item.get('mensagens') or []):
        quem = (mensagem.get('autor') or '').strip()
        if quem and quem.lower() not in eu:
            return quem
    autor = (item.get('autor') or '').strip()
    ids = set(i.strip().lower() for i in (autor, item.get('autor_id') or '')
              if i and i.strip())
    if not autor or ids & eu:
        return ''
    return autor


def e_do_autor(item, nome):
    """True se `nome` e quem criou o apontamento (pelo nome ou pelo ID)."""
    nome = (nome or '').strip().lower()
    return bool(nome) and nome in set(
        (i or '').strip().lower()
        for i in (item.get('autor'), item.get('autor_id')) if i)


def e_para(item, usuario):
    """True se o recado e para mim (ou para qualquer um)."""
    eu = _eu(usuario)
    destinos = set((p or '').strip().lower() for p in item.get('para') or []
                   if p)
    return not destinos or bool(destinos & eu)


# ------------------------------------------------------------------ leitura

def ultima_atividade(item):
    """A data que conta para 'novidade': a ultima mensagem, o status ou a
    criacao."""
    datas = [item.get('criado_em') or '', item.get('status_em') or '']
    datas += [m.get('quando') or '' for m in item.get('mensagens') or []]
    return max(datas)


def me_interessa(item, usuario):
    """Para mim, sem dono, ou MEU — resposta no recado que eu criei tambem
    e novidade, mesmo que ele seja endereçado a outra pessoa."""
    eu = _eu(usuario)
    meus = set(a.strip().lower() for a in
               (item.get('autor') or '', item.get('autor_id') or '') if a)
    return e_para(item, usuario) or bool(meus & eu)


def novidades(itens, usuario, visto_em):
    """Os itens com movimento depois de `visto_em` que interessam a mim e
    que nao fui eu quem mexeu."""
    novos = []
    for item in itens:
        quando = ultima_atividade(item)
        if quando <= (visto_em or '') or not me_interessa(item, usuario):
            continue
        if (_quem_mexeu(item, quando) or '').strip().lower() in _eu(usuario):
            continue
        novos.append(item)
    return novos


def _quem_mexeu(item, quando):
    for mensagem in item.get('mensagens') or []:
        if (mensagem.get('quando') or '') == quando:
            return mensagem.get('autor', '')
    if (item.get('status_em') or '') == quando:
        return item.get('status_por', '')
    return item.get('autor', '')


def quando_relativo(quando, agora):
    """'há 2 h', 'ontem 10:37', '24/09 10:37' — ISO que vira tempo humano.

    A lista precisa responder "isto é de agora ou de semana passada?" sem o
    usuário ler uma data inteira.
    """
    if not quando:
        return ''
    try:
        dia, hora = quando.split('T')[0], quando.split('T')[1][:5]
        ano, mes, dia_ = [int(p) for p in dia.split('-')]
    except (ValueError, IndexError):
        return quando
    minutos = _minutos_entre(quando, agora)
    dias = _dias_entre(quando, agora)
    if minutos is None or dias is None:
        return u'{:02d}/{:02d} {}'.format(dia_, mes, hora)
    if dias == 0:
        # o dia do calendário decide: 16 h atrás pode ser "ontem"
        if minutos < 1:
            return u'agora'
        if minutos < 60:
            return u'há {} min'.format(int(minutos))
        return u'há {} h'.format(int(minutos // 60))
    if dias == 1:
        return u'ontem {}'.format(hora)
    if dias < 7:
        return u'há {} dias'.format(dias)
    return u'{:02d}/{:02d} {}'.format(dia_, mes, hora)


def _dias_entre(quando, agora):
    try:
        a, b = _em_dias(quando), _em_dias(agora)
    except (ValueError, IndexError, TypeError):
        return None
    return None if b < a else b - a


def _em_dias(quando):
    ano, mes, dia = [int(p) for p in quando.split('T')[0].split('-')]
    return (ano * 12 + mes) * 31 + dia


def _minutos_entre(quando, agora):
    """Minutos entre dois ISO, sem datetime (o snippet é puro e o IronPython
    não tem `fromisoformat`). None quando não dá para comparar."""
    try:
        a, b = _em_minutos(quando), _em_minutos(agora)
    except (ValueError, IndexError, TypeError):
        return None
    return None if a is None or b is None or b < a else b - a


def _em_minutos(quando):
    dia, hora = quando.split('T')
    ano, mes, dia_ = [int(p) for p in dia.split('-')]
    h, m = int(hora[:2]), int(hora[3:5])
    # dias corridos aproximados: serve para "há N dias", não para calendário
    return (((ano * 12 + mes) * 31 + dia_) * 24 + h) * 60 + m


def so_para(registro, chaves, usuario):
    """As chaves de quem me interessa — o 'atribuídas a mim' de um clique."""
    itens = registro.get('conflitos', {})
    return [k for k in chaves
            if not itens[k].get('log') or
            me_interessa(itens[k]['log'], usuario)]


def resumo_do_item(item, limite=110):
    texto = ' '.join((item.get('texto') or '').split())
    return texto if len(texto) <= limite else texto[:limite - 1] + u'…'


def modelos(itens):
    """Os .rvt citados pelos alvos — o 'Agrupar por: Modelo' da janela."""
    achados = set()
    for item in itens:
        for alvo in item.get('alvos') or []:
            if alvo.get('arquivo'):
                achados.add(alvo['arquivo'])
        if item.get('modelo'):
            achados.add(item['modelo'])
    return sorted(achados, key=lambda n: n.lower())


# ------------------------------------------------- adaptacao para a janela

def _lado(alvo):
    return {'vinculo': '', 'arquivo': alvo.get('arquivo', ''),
            'categoria': alvo.get('categoria') or u'Elemento',
            'descricao': alvo.get('descricao') or '',
            'id': alvo.get('elementId') or 0,
            'uniqueId': alvo.get('uniqueId') or '',
            'ponto': alvo.get('ponto')}


def _lado_do_recado(item):
    """Recado sem elemento: o lado e o proprio modelo (ainda navegavel pelo
    ponto, se houver)."""
    return {'vinculo': '', 'arquivo': item.get('modelo', ''),
            'categoria': u'Recado', 'descricao': resumo_do_item(item, 60),
            'id': 0, 'uniqueId': '', 'ponto': item.get('ponto')}


def como_registro(itens, usuario=''):
    """Os itens na forma que a janela das Pendencias ja sabe mostrar.

    `regra` = para quem e; `nivel` = o modelo (o 'Agrupar por' do LOG);
    `medida` = o texto; `comentario` = a ultima resposta.
    """
    conflitos = {}
    for item in itens:
        alvos = item.get('alvos') or []
        # TODOS os alvos, não só dois (24/09/2026): a interferência nasce de
        # um PAR (a × b), mas o apontamento aponta N elementos — gravar 12 e
        # navegar para 2 era perder 10 em silêncio.
        lados = [_lado(alvo) for alvo in alvos] or [_lado_do_recado(item)]
        a = lados[0]
        b = lados[1] if len(lados) > 1 else None
        mensagens = item.get('mensagens') or []
        destino = u', '.join(item.get('para') or []) or u'(toda a equipe)'
        conflitos[item['id']] = {
            'a': a, 'b': b, 'lados': lados,
            'status': PARA_JANELA[item.get('status', ABERTA)],
            'comentario': (mensagens[-1].get('texto', '') if mensagens
                           else ''),
            'por': item.get('status_por') or item.get('autor', ''),
            'quando': item.get('status_em') or item.get('criado_em', ''),
            'no_relatorio': True,
            'visto_em': item.get('criado_em', ''),
            'regra': u'Para {}'.format(destino),
            'medida': resumo_do_item(item),
            'nivel': item.get('modelo') or (a.get('arquivo') or u'(sem modelo)'),
            'gravidade': 'atencao' if item.get('status') == ABERTA else 'ok',
            'log': item,
        }
    return {'versao': VERSAO, 'conflitos': conflitos}


def ordem_do_log(itens):
    """As chaves na ordem de criacao — o equivalente a ordem do HTML."""
    return [item['id'] for item in
            sorted(itens, key=lambda i: (i.get('criado_em') or '', i['id']))]
