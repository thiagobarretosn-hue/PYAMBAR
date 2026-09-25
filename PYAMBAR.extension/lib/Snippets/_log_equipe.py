# -*- coding: utf-8 -*-
"""A equipe do LOG: quem e quem, cruzando o ID do Revit com o NOME.

POR QUE ESTE ARQUIVO EXISTE (Thiago, 24/09/2026)
------------------------------------------------
> "a equipe hoje fica armazenada na obra mas isso deve ser geral para todas
>  as obras... a primeira vez que o usuario usar, perguntar o nome e ai
>  cadastrar cruzando o Revit ID com o nome para nao ficar o ID, que nao fica
>  tao organizado: meu ID e thiagonunesXNUJD mas eu escreveria Thiago Nunes"

Duas decisoes moram aqui:

1. O **ID do Revit e a chave** (nunca muda, nao repete). O **nome** e o que
   aparece na tela. Um mapa id -> nome resolve os dois.
2. A lista e de TODA a empresa, nao de uma obra. Quem esta na obra e
   consequencia (quem escreveu la), nao cadastro.

FORMATOS QUE ESTE MODULO LE
---------------------------
v1 (o que ja existe na obra): {"pessoas": ["thiagonunesXNUJD"]}
    -> vira {"id": "thiagonunesXNUJD", "nome": "thiagonunesXNUJD"}, sem
       perder ninguem; o nome se conserta quando a pessoa se cadastra.
v2 (este): {"versao": 2, "pessoas": [{"id": .., "nome": .., "em": ..}]}

MESCLAR, SEMPRE
---------------
Varios Revits gravam o mesmo arquivo em rede. Nunca sobrescrever: reler,
mesclar e gravar (o mesmo padrao dos apontamentos). Aqui a regra e por
pessoa: o cadastro MAIS NOVO manda, porque so a propria pessoa troca o
proprio nome.

Puro: sem `clr`, sem Revit — roda em CPython, testado em
`dev-tools/tests/test_log_equipe.py`.
"""

VERSAO = 2

#: o caminho da pasta corporativa, a partir da raiz do drive compartilhado
PASTA_GLOBAL = ['00 - PROCEDURES', '01 - BIM', '03 - AUTOMATION SOLUTIONS',
                'PYREVIT']
#: a pasta que marca a raiz: e ela que tem `00 - PROCEDURES` e `01 - PROJECTS`
MARCO = '00 - PROCEDURES'
ARQUIVO = 'equipe.json'


def _limpo(texto):
    return ' '.join((texto or '').split())


def normalizar(dados):
    """Qualquer formato vira {'versao': 2, 'pessoas': [{id, nome, em}]}."""
    pessoas = dados.get('pessoas') if isinstance(dados, dict) else dados
    saida = []
    vistos = set()
    for pessoa in (pessoas or []):
        if isinstance(pessoa, dict):
            ident = _limpo(pessoa.get('id') or pessoa.get('nome'))
            nome = _limpo(pessoa.get('nome')) or ident
            em = pessoa.get('em') or ''
        else:
            ident = nome = _limpo(pessoa)
            em = ''
        if not ident or ident.lower() in vistos:
            continue
        vistos.add(ident.lower())
        saida.append({'id': ident, 'nome': nome, 'em': em})
    saida.sort(key=lambda p: p['nome'].lower())
    return {'versao': VERSAO, 'pessoas': saida}


def mesclar(*equipes):
    """A uniao de varias listas — por ID, o cadastro mais novo ganha.

    O nome vazio nunca derruba um nome preenchido: quem foi importado do
    formato antigo (nome == id) perde para quem se cadastrou de verdade.
    """
    por_id = {}
    for equipe in equipes:
        for pessoa in normalizar(equipe)['pessoas']:
            chave = pessoa['id'].lower()
            atual = por_id.get(chave)
            if atual is None or _ganha(pessoa, atual):
                por_id[chave] = pessoa
    return normalizar({'pessoas': list(por_id.values())})


def _ganha(novo, atual):
    cadastrado = lambda p: p['nome'].lower() != p['id'].lower()  # noqa: E731
    if cadastrado(novo) != cadastrado(atual):
        return cadastrado(novo)        # nome de verdade vence o id cru
    return (novo.get('em') or '') > (atual.get('em') or '')


def registrar(equipe, ident, nome, agora=''):
    """Cadastra/renomeia alguem. -> (equipe, mudou)."""
    ident, nome = _limpo(ident), _limpo(nome)
    if not ident:
        return normalizar(equipe), False
    atual = normalizar(equipe)
    anterior = next((p for p in atual['pessoas']
                     if p['id'].lower() == ident.lower()), None)
    if anterior is not None and anterior['nome'] == (nome or ident):
        return atual, False
    nova = mesclar(atual, {'pessoas': [{'id': ident, 'nome': nome or ident,
                                        'em': agora}]})
    return nova, True


def nome_de(equipe, ident):
    """O nome de quem tem esse ID — o proprio ID se ninguem cadastrou."""
    ident = _limpo(ident)
    for pessoa in normalizar(equipe)['pessoas']:
        if pessoa['id'].lower() == ident.lower():
            return pessoa['nome']
    return ident


def id_de(equipe, nome):
    """O ID de quem se chama assim (aceita o proprio ID). '' se nao achar."""
    nome = _limpo(nome)
    for pessoa in normalizar(equipe)['pessoas']:
        if nome.lower() in (pessoa['nome'].lower(), pessoa['id'].lower()):
            return pessoa['id']
    return ''


def nomes(equipe):
    """Os nomes para o auto-completar, em ordem."""
    return [p['nome'] for p in normalizar(equipe)['pessoas']]


def esta_cadastrado(equipe, ident):
    """True se essa pessoa ja disse como se chama (nome != id)."""
    ident = _limpo(ident)
    if not ident:
        return False
    nome = nome_de(equipe, ident)
    return bool(nome) and nome.lower() != ident.lower()


def apelidos(equipe, ident):
    """Como EU apareco nos apontamentos: o ID e o nome.

    Apontamento antigo gravou o ID no `autor`/`para`; o novo grava o nome.
    Comparar com os dois e o que faz 'para mim' continuar certo.
    """
    ident = _limpo(ident)
    nome = nome_de(equipe, ident)
    saida = []
    for apelido in (ident, nome):
        if apelido and apelido.lower() not in [a.lower() for a in saida]:
            saida.append(apelido)
    return saida


# ------------------------------------------------------- onde fica o arquivo

def caminho_global(caminho_do_modelo, existe, juntar=None, partes=None):
    """O `equipe.json` da empresa, achado SUBINDO a partir do modelo.

    Sem letra de drive no codigo: `H:` e a maquina do Thiago; outro usuario
    pode ter `G:` ou o caminho do Google Drive. Sobe de pasta em pasta ate
    achar a que tem `00 - PROCEDURES` e desce pelo caminho conhecido.

    `existe` e `juntar` sao injetados (o modulo e puro): no Revit vem
    `os.path.isdir` e `os.path.join`. -> '' se nao achar.
    """
    juntar = juntar or (lambda *p: '/'.join(p))
    pasta = _pasta_de(caminho_do_modelo, partes)
    while pasta:
        if existe(juntar(pasta, MARCO)):
            return juntar(pasta, *(PASTA_GLOBAL + [ARQUIVO]))
        pai = _subir(pasta)
        if pai == pasta:
            return ''
        pasta = pai
    return ''


def _pasta_de(caminho, partes=None):
    if partes:
        return partes(caminho)[0]
    caminho = (caminho or '').replace('\\', '/').rstrip('/')
    return caminho.rsplit('/', 1)[0] if '/' in caminho else ''


def _subir(pasta):
    pasta = pasta.replace('\\', '/').rstrip('/')
    return pasta.rsplit('/', 1)[0] if '/' in pasta else pasta
