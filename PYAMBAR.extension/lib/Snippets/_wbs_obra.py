# -*- coding: utf-8 -*-
"""Config do Unit Mapper que e DA OBRA, nao do usuario.

Pedido do Thiago em 21/10/2026: os engenheiros querem regras, Type, Floors,
nomes de parametro e offsets de ambiente iguais para todo mundo. O resto
(parametros fixos, escopo, sufixo, cadeados) continua por usuario no APPDATA.

**Mora num arquivo, nao dentro do .rvt.** O Thiago derrubou a ideia do
Extensible Storage com um argumento certo: ele grava no ARQUIVO, e uma obra
tem varios modelos (medido em PRINCETON 248 PHASE 3: SEWER, WATER SUPPLY,
DRAINAGE, ARQBASE e STR na MESMA pasta `03-MODELING`). Um JSON em
`<pasta do modelo>\\DAT\\UnitMapper\\config.json` serve a obra inteira — o
mesmo lugar onde o LOG ja guarda dado por obra.

Aqui so LOGICA PURA (roda em CPython, testada em `test_wbs_obra.py`): quem
resolve a pasta e a janela, com `Snippets.project._dat_folder_manager`.

## Mesclagem

Duas pessoas mexem na mesma obra. Em vez de "o ultimo a salvar vence", a
gravacao e uma mescla de TRES vias por item (decisao do Thiago):

    base   = o que esta janela leu quando abriu
    minha  = o que esta janela tem agora
    disco  = o que esta no arquivo neste instante (pode ter mudado)

Para cada item, comparado por chave estavel (regra pelo nome, Type pela
chave, Floor pelo nome do Level, offset pelo UniqueId):

- nao mexi (minha == base)      -> fica o do disco (o outro pode ter mexido)
- mexi                          -> vence o meu
- so existe no disco            -> fica (o outro criou)
- estava na base e sumiu em mim -> apaguei de proposito, sai do disco
"""

import copy

#: subpasta dentro de DAT e nome do arquivo
SUBPASTA = 'UnitMapper'
NOME_ARQUIVO = 'config.json'

VERSAO = 1

#: (secao, campo que identifica o item) — secao sem chave e valor escalar
SECOES_DE_LISTA = (
    ('regras_param', 'nome'),      # aba Regras
    ('levels', 'name'),            # Configuracoes > Floors
)
SECOES_DE_MAPA = (
    'tipologia',                   # Configuracoes > Type
    'amb_offsets',                 # offsets de ambiente, por room
    'params',                      # nomes de Floor / Unit ID / Type
)


def vazia():
    """Config de obra sem nada — o que uma obra nova tem."""
    dados = {'version': VERSAO}
    for secao, _chave in SECOES_DE_LISTA:
        dados[secao] = []
    for secao in SECOES_DE_MAPA:
        dados[secao] = {}
    return dados


def normalizar(bruto):
    """Qualquer coisa lida do disco -> estrutura completa, sem levantar."""
    dados = vazia()
    if not isinstance(bruto, dict):
        return dados
    for secao, _chave in SECOES_DE_LISTA:
        valor = bruto.get(secao)
        if isinstance(valor, list):
            dados[secao] = [i for i in valor if isinstance(i, dict)]
    for secao in SECOES_DE_MAPA:
        valor = bruto.get(secao)
        if isinstance(valor, dict):
            dados[secao] = dict(valor)
    return dados


def esta_vazia(dados):
    """Obra que nunca foi configurada (arquivo novo ou so com a versao)."""
    dados = normalizar(dados)
    return not any(dados[secao] for secao, _ in SECOES_DE_LISTA) \
        and not any(dados[secao] for secao in SECOES_DE_MAPA)


def _por_chave(itens, chave):
    """[{...}] -> {valor da chave: item}, preservando a ordem de entrada."""
    saida = {}
    for item in itens or []:
        if not isinstance(item, dict):
            continue
        nome = item.get(chave)
        if nome:
            saida[nome] = item
    return saida


def _mesclar_lista(base, minha, disco, chave):
    """Mescla de tres vias preservando a ordem de quem esta salvando."""
    b, m, d = (_por_chave(x, chave) for x in (base, minha, disco))
    saida, usados = [], set()

    for nome, item in m.items():
        usados.add(nome)
        if nome in b and b[nome] == item and nome in d:
            saida.append(d[nome])      # nao mexi: o do disco manda
        else:
            saida.append(item)         # mexi (ou criei): o meu manda

    apagados = set(b) - set(m)         # estava na base e sumiu = apaguei
    for nome, item in d.items():
        if nome in usados or nome in apagados:
            continue
        saida.append(item)             # so existe no disco: o outro criou
    return saida


def _mesclar_mapa(base, minha, disco):
    base = base or {}
    minha = minha or {}
    resultado = dict(disco or {})

    for chave in set(base) - set(minha):
        resultado.pop(chave, None)     # apaguei de proposito

    for chave, valor in minha.items():
        if chave in base and base[chave] == valor and chave in resultado:
            continue                   # nao mexi: fica o do disco
        resultado[chave] = valor
    return resultado


def mesclar(base, minha, disco):
    """A config que deve ir para o arquivo. Nao altera os argumentos."""
    base = normalizar(base)
    minha = normalizar(minha)
    disco = normalizar(disco)

    saida = {'version': VERSAO}
    for secao, chave in SECOES_DE_LISTA:
        saida[secao] = _mesclar_lista(base[secao], minha[secao],
                                      disco[secao], chave)
    for secao in SECOES_DE_MAPA:
        saida[secao] = _mesclar_mapa(base[secao], minha[secao], disco[secao])
    return saida


def diferencas(antes, depois):
    """{secao: quantos itens mudaram} — para a janela dizer o que entrou.

    Conta item que entrou, saiu ou mudou de valor; secao igual nao aparece.
    """
    antes, depois = normalizar(antes), normalizar(depois)
    saida = {}
    for secao, chave in SECOES_DE_LISTA:
        a, d = _por_chave(antes[secao], chave), _por_chave(depois[secao], chave)
        mudou = len(set(a) ^ set(d))
        mudou += sum(1 for k in set(a) & set(d) if a[k] != d[k])
        if mudou:
            saida[secao] = mudou
    for secao in SECOES_DE_MAPA:
        a, d = antes[secao], depois[secao]
        mudou = len(set(a) ^ set(d))
        mudou += sum(1 for k in set(a) & set(d) if a[k] != d[k])
        if mudou:
            saida[secao] = mudou
    return saida


def copia(dados):
    """Foto da config para guardar como `base` enquanto a janela vive."""
    return copy.deepcopy(normalizar(dados))
