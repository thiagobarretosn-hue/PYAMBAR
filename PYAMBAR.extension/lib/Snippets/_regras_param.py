# -*- coding: utf-8 -*-
"""Regras de parametros do Unit Mapper — o motor, puro (sem clr).

Pedido do Thiago em 14/09/2026: "regras como temos no Fluxo ARN — tubos
horizontais PHASE Colgante, verticais PHASE Riser — grupos nomeados com ARN
TYP o PHASE Typical — tudo inteligente, limpo, pratico".

UMA REGRA
---------
    {'nome': 'Tubo horizontal', 'ativa': True,
     'quando': [{'campo': 'orientacao', 'operador': 'e', 'valor': 'horizontal'}],
     'entao':  [{'parametro': 'PHASE', 'acao': 'fixo', 'valor': 'Colgante'}],
     'onde': 'ambos', 'so_vazio': False, 'combinar': 'todas'}

`combinar` 'todas' (E, o padrao) exige todas as condicoes; 'qualquer' (OU,
16/09/2026) basta uma. Lista sem condicao casa com
tudo — serve para "todo elemento recebe X". Para cada parametro, a primeira
regra que casa vence — e desde 15/09/2026 (decisao do Thiago) a regra com
condicao AFIRMATIVA sobre o grupo vem antes das outras, seja qual for a
posicao: tubo horizontal dentro da aranha e Typical, nao Colgante. Dentro de
cada faixa, a ordem da lista.

PRIORIDADE (decisao do Thiago): Regra > Membros > Ambiente > Fixo. Cada fonte
so preenche o parametro que as anteriores nao decidiram. "Membros" so existe
na instancia do Model Group: o valor dominante dos elementos de dentro.

ONDE (decisao dele: por regra): 'grupo' grava na instancia do Model Group,
'membros' nos elementos dentro de grupos, 'ambos' nos dois. Elemento solto
(fora de grupo) sempre recebe.

OS FATOS de um elemento (montados pelo lado Revit, `um_fatos`):
    {'papel': 'solto' | 'grupo' | 'membro',
     'orientacao': 'horizontal' | 'vertical' | 'inclinado' | '',
     'grupos': ['ARN TYP#A', ...],     # do mais interno ao mais externo
     'system': '...', 'classificacao': '...',
     'categoria': '...', 'familia': '...', 'tipo': '...',
     'nivel': '...', 'room': '...', 'room_numero': '...',
     'diametro': 2.0,                  # polegadas, ou None
     'comprimento': 10.5,              # pes (so tubo), ou None
     'floors': ['1st', '2nd', ...],    # aba Floors, de baixo para cima
     'params': {'PHASE': 'Typical', ...},   # valores ATUAIS
     'calculados': {'Floor': '2nd', 'Unit ID': '207', 'Type': '...'},
     'ambiente': {'Room': 'Bath', ...}}     # do room que contem o elemento
"""
import json
import math

from Snippets._comprimento_texto import texto_para_pes

# -------------------------------------------------------------- orientacao

#: Medido no MIIQLUX-SEW-RSR em 14/09/2026, 1569 tubos: 662 verticais (XY
#: parado), 325 planos, 530 ate 1,5 graus (caimento de esgoto), 22 ate 5,
#: 1 ate 30 e 29 entre 30 e 80 (descidas a 45). Horizontal ate 5 graus
#: cobre o caimento; a partir de 80, vertical.
TOL_XY_VERTICAL = 0.01      # pes
DZ_MINIMO = 0.01            # pes
ANGULO_HORIZONTAL = 5.0     # graus
ANGULO_VERTICAL = 80.0      # graus


def classificar_orientacao(p0, p1):
    """'horizontal', 'vertical', 'inclinado' — ou '' se nao tem comprimento."""
    dxy = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    dz = abs(p1[2] - p0[2])
    if dxy <= TOL_XY_VERTICAL:
        return 'vertical' if dz >= DZ_MINIMO else ''
    angulo = math.degrees(math.atan2(dz, dxy))
    if angulo <= ANGULO_HORIZONTAL:
        return 'horizontal'
    if angulo >= ANGULO_VERTICAL:
        return 'vertical'
    return 'inclinado'


def orientacao_herdada(orientacoes):
    """A orientacao de uma conexao ou acessorio, pelas dos tubos ligados.

    Liga em tubo vertical: 'vertical' (e a subida ou a descida). Senao
    horizontal, senao inclinado. Decisao do Thiago em 15/09/2026 — antes so
    tubo tinha orientacao, e Colgante/Riser nunca pegavam conexao.
    """
    presentes = set(o for o in orientacoes or [] if o)
    for candidata in ('vertical', 'horizontal', 'inclinado'):
        if candidata in presentes:
            return candidata
    return ''

# ------------------------------------------------------------------ campos

ORIENTACAO = 'orientacao'
GRUPO = 'grupo'
SYSTEM = 'system'
CLASSIFICACAO = 'classificacao'
CATEGORIA = 'categoria'
FAMILIA = 'familia'
TIPO = 'tipo'
NIVEL = 'nivel'
#: 24/09/2026: o Floor CALCULADO da linha (pela geometria), que nao e o mesmo
#: que NIVEL — este le o Level de referencia da peca. Medido no
#: CIQ-PLB-WATER SUPPLY: 246 pecas referenciam "00 - FOUNDATION" e so 10 estao
#: de fato abaixo de 0'; as 13 do underground sao as que tem Floor "0th".
FLOOR = 'floor'
ROOM = 'room'
ROOM_NUMERO = 'room_numero'
DIAMETRO = 'diametro'
COMPRIMENTO = 'comprimento'   # 16/09/2026, pes; valor digitado em pes/polegadas
#: trecho horizontal (Snippets._trecho_horizontal): a conexao herda os numeros
#: do trecho, entao a regra do desvio nao deixa mais conexao em branco
TRECHO_COMPRIMENTO = 'trecho_comprimento'
TRECHO_PONTAS = 'trecho_pontas'
PAPEL = 'papel'
PARAMETRO = 'parametro'     # usa o nome em cond['parametro']

#: (campo, rotulo para a tela) — na ordem da lista
CAMPOS = (
    (ORIENTACAO, u'Orientação (tubo, conexão)'),
    (GRUPO, u'Nome do grupo'),
    (SYSTEM, u'Nome do system'),
    (CLASSIFICACAO, u'Classificação do system'),
    (CATEGORIA, u'Categoria'),
    (FAMILIA, u'Família'),
    (TIPO, u'Tipo'),
    (NIVEL, u'Nível'),
    (FLOOR, u'Floor (calculado)'),
    (ROOM, u'Ambiente (nome)'),
    (ROOM_NUMERO, u'Ambiente (número)'),
    (DIAMETRO, u'Diâmetro (pol)'),
    (COMPRIMENTO, u'Comprimento (tubo)'),
    (TRECHO_COMPRIMENTO, u'Trecho horizontal (comprimento)'),
    (TRECHO_PONTAS, u'Trecho horizontal (pontas verticais)'),
    (PAPEL, u'Solto / grupo / membro'),
    (PARAMETRO, u'Valor de parâmetro'),
)

# --------------------------------------------------------------- operadores

E = 'e'
NAO_E = 'nao_e'
CONTEM = 'contem'
NAO_CONTEM = 'nao_contem'
COMECA = 'comeca'
TERMINA = 'termina'
ENTRE = 'entre'
VAZIO = 'vazio'
PREENCHIDO = 'preenchido'
MAIOR_IGUAL = 'maior_igual'   # 16/09/2026: comparacoes numericas
MENOR_IGUAL = 'menor_igual'
MAIOR = 'maior'
MENOR = 'menor'

OPERADORES = (
    (E, u'é'), (NAO_E, u'não é'), (CONTEM, u'contém'),
    (NAO_CONTEM, u'não contém'), (COMECA, u'começa com'),
    (TERMINA, u'termina com'), (ENTRE, u'entre'),
    (MAIOR_IGUAL, u'≥ maior ou igual'), (MENOR_IGUAL, u'≤ menor ou igual'),
    (MAIOR, u'> maior que'), (MENOR, u'< menor que'),
    (VAZIO, u'está vazio'), (PREENCHIDO, u'está preenchido'),
)
SEM_VALOR = (VAZIO, PREENCHIDO)
COMPARACOES = (MAIOR_IGUAL, MENOR_IGUAL, MAIOR, MENOR)
#: campos em que "e"/"nao e" comparam numero (2 == 2.0)
CAMPOS_NUMERICOS = (DIAMETRO, COMPRIMENTO, TRECHO_COMPRIMENTO, TRECHO_PONTAS)
#: campos cujo valor digitado e comprimento (10, 6", 1'-6")
CAMPOS_DE_COMPRIMENTO = (COMPRIMENTO, TRECHO_COMPRIMENTO)
#: campos que exigem percorrer a rede (o lado Revit so calcula se usados)
CAMPOS_DE_TRECHO = (TRECHO_COMPRIMENTO, TRECHO_PONTAS)
_TOLERANCIA = 1e-6

# -------------------------------------------------------------------- acoes

FIXO = 'fixo'           # valor digitado
COPIAR = 'copiar'       # valor de outro parametro do elemento
MODELO = 'modelo'       # texto com campos: '{Floor}-{Unit ID}', '{room}'
DO_AMBIENTE = 'ambiente'  # o mesmo parametro, lido do room
#: 16/09/2026 (aranha): o room do TOPO da peca, nao o do centro. A aranha fica
#: no forro do pavimento de baixo e atende a unidade de CIMA — Floor do nivel
#: onde esta instalada, Unit ID e Type da unidade de cima.
DO_AMBIENTE_TOPO = 'ambiente_topo'
#: 16/09/2026 (Thiago): "grupo X -> Floor do nivel de referencia +1, +2..."
#: valor = N (inteiro com sinal); anda N posicoes na lista da aba Floors
FLOOR_MAIS = 'floor_mais'

ACOES = ((FIXO, u'valor'), (COPIAR, u'copiar do parâmetro'),
         (MODELO, u'modelo com campos'), (DO_AMBIENTE, u'do ambiente'),
         (DO_AMBIENTE_TOPO, u'da unidade de cima (room do topo; sem room, pelo sufixo)'),
         (FLOOR_MAIS, u'Floor do nível + N'))

# ---------------------------------------------------------------- onde / origem

ONDE_GRUPO = 'grupo'
ONDE_MEMBROS = 'membros'
ONDE_AMBOS = 'ambos'
ONDES = ((ONDE_AMBOS, u'grupo e membros'), (ONDE_GRUPO, u'só no grupo'),
         (ONDE_MEMBROS, u'só nos membros'))

#: Como as condicoes se somam — uma escolha por regra (Thiago, 16/09/2026).
#: Regra antiga, sem a chave, e "todas" (o unico comportamento ate a v3.3).
COMBINAR_TODAS = 'todas'
COMBINAR_QUALQUER = 'qualquer'
COMBINACOES = ((COMBINAR_TODAS, u'Todas as condições (E)'),
               (COMBINAR_QUALQUER, u'Qualquer condição (OU)'))

PAPEL_SOLTO = 'solto'
PAPEL_GRUPO = 'grupo'
PAPEL_MEMBRO = 'membro'

ORIGEM_REGRA = 'R'
ORIGEM_AMBIENTE = 'A'
ORIGEM_FIXO = 'F'
ORIGEM_MEMBROS = 'G'    # valor dominante dos membros, na instancia do grupo

FORMATO_EXPORTACAO = 'PYAMBAR-regras-parametros'
VERSAO_EXPORTACAO = 1

_CAMPOS_VALIDOS = set(c for c, _ in CAMPOS)
_OPERADORES_VALIDOS = set(o for o, _ in OPERADORES)
_ACOES_VALIDAS = set(a for a, _ in ACOES)
_ONDES_VALIDOS = set(o for o, _ in ONDES)


def _texto(valor):
    if valor is None:
        return ''
    return u'{}'.format(valor).strip()


def _numero(valor):
    try:
        return float(_texto(valor).replace(',', '.'))
    except (TypeError, ValueError):
        return None


def _numero_da_condicao(condicao, chave='valor'):
    """Comprimento aceita pes/polegadas (10, 6", 1'-6"); o resto, numero."""
    if condicao['campo'] in CAMPOS_DE_COMPRIMENTO:
        return texto_para_pes(condicao[chave])
    return _numero(condicao[chave])


def _passos(valor):
    """'+2' -> 2, '-1' -> -1; None se nao for inteiro."""
    try:
        return int(_texto(valor))
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------ normalizacao

def normalizar_condicao(bruta):
    """Condicao limpa, ou None se nao der para avaliar."""
    if not isinstance(bruta, dict):
        return None
    campo = _texto(bruta.get('campo'))
    operador = _texto(bruta.get('operador')) or E
    if campo not in _CAMPOS_VALIDOS or operador not in _OPERADORES_VALIDOS:
        return None
    condicao = {'campo': campo, 'operador': operador,
                'valor': _texto(bruta.get('valor')),
                'ate': _texto(bruta.get('ate')),
                'parametro': _texto(bruta.get('parametro'))}
    if campo == PARAMETRO and not condicao['parametro']:
        return None
    if operador == ENTRE and (_numero_da_condicao(condicao) is None
                              or _numero_da_condicao(condicao, 'ate') is None):
        return None
    if operador in COMPARACOES and _numero_da_condicao(condicao) is None:
        return None
    return condicao


def normalizar_acao(bruta):
    if not isinstance(bruta, dict):
        return None
    parametro = _texto(bruta.get('parametro'))
    acao = _texto(bruta.get('acao')) or FIXO
    if not parametro or acao not in _ACOES_VALIDAS:
        return None
    valor = _texto(bruta.get('valor'))
    if acao in (COPIAR, MODELO) and not valor:
        return None
    if acao == FLOOR_MAIS:
        passos = _passos(valor)
        if passos is None:
            return None
        valor = u'{:+d}'.format(passos)
    return {'parametro': parametro, 'acao': acao, 'valor': valor}


def normalizar_regra(bruta):
    """Regra limpa, ou None. Sem nenhuma acao valida ela nao faria nada."""
    if not isinstance(bruta, dict):
        return None
    entao = [a for a in (normalizar_acao(b) for b in bruta.get('entao') or [])
             if a is not None]
    if not entao:
        return None
    quando = [c for c in (normalizar_condicao(b)
                          for b in bruta.get('quando') or []) if c is not None]
    onde = _texto(bruta.get('onde')) or ONDE_AMBOS
    combinar = _texto(bruta.get('combinar'))
    return {'nome': _texto(bruta.get('nome')),
            'ativa': bool(bruta.get('ativa', True)),
            'quando': quando, 'entao': entao,
            'combinar': (COMBINAR_QUALQUER if combinar == COMBINAR_QUALQUER
                         else COMBINAR_TODAS),
            'onde': onde if onde in _ONDES_VALIDOS else ONDE_AMBOS,
            'so_vazio': bool(bruta.get('so_vazio', False))}


def normalizar_regras(brutas):
    return [r for r in (normalizar_regra(b) for b in brutas or [])
            if r is not None]


# --------------------------------------------------------------- avaliacao

def _valores_do_campo(condicao, fatos):
    """Lista de textos: o grupo pode ter varios nomes (aninhado)."""
    campo = condicao['campo']
    if campo == PARAMETRO:
        nome = condicao['parametro']
        valor = (fatos.get('params') or {}).get(nome)
        if valor in (None, ''):
            valor = (fatos.get('calculados') or {}).get(nome)
        return [_texto(valor)]
    if campo == GRUPO:
        return [_texto(g) for g in fatos.get('grupos') or []] or ['']
    return [_texto(fatos.get(campo))]


def _casa_texto(operador, atual, alvo):
    a, b = atual.lower(), alvo.lower()
    if operador == E:
        return a == b
    if operador == NAO_E:
        return a != b
    if operador == CONTEM:
        return b in a
    if operador == NAO_CONTEM:
        return b not in a
    if operador == COMECA:
        return a.startswith(b)
    if operador == TERMINA:
        return a.endswith(b)
    if operador == VAZIO:
        return a == ''
    if operador == PREENCHIDO:
        return a != ''
    return False


def _compara(operador, numero, alvo):
    if operador == MAIOR_IGUAL:
        return numero >= alvo - _TOLERANCIA
    if operador == MENOR_IGUAL:
        return numero <= alvo + _TOLERANCIA
    if operador == MAIOR:
        return numero > alvo + _TOLERANCIA
    if operador == MENOR:
        return numero < alvo - _TOLERANCIA
    if operador == E:
        return abs(numero - alvo) <= _TOLERANCIA
    return abs(numero - alvo) > _TOLERANCIA     # NAO_E


def casa_condicao(condicao, fatos):
    operador = condicao['operador']
    valores = _valores_do_campo(condicao, fatos or {})
    numerico = operador in COMPARACOES or (
        operador in (E, NAO_E) and condicao['campo'] in CAMPOS_NUMERICOS)
    if numerico:
        alvo = _numero_da_condicao(condicao)
        if alvo is None:
            return False
        numeros = [n for n in (_numero(v) for v in valores) if n is not None]
        if not numeros:             # conexao nao tem comprimento: nao casa
            return False
        return any(_compara(operador, n, alvo) for n in numeros)
    if operador == ENTRE:
        minimo = _numero_da_condicao(condicao)
        maximo = _numero_da_condicao(condicao, 'ate')
        if minimo > maximo:
            minimo, maximo = maximo, minimo
        for valor in valores:
            numero = _numero(valor)
            if numero is not None and minimo <= numero <= maximo:
                return True
        return False
    if operador in (NAO_E, NAO_CONTEM, VAZIO):
        # negativo: TODOS os nomes precisam passar (nenhum grupo contem X)
        return all(_casa_texto(operador, v, condicao['valor']) for v in valores)
    return any(_casa_texto(operador, v, condicao['valor']) for v in valores)


def casa(regra, fatos):
    """Sem condicao vale para todo elemento, nas duas combinacoes."""
    condicoes = regra['quando']
    if not condicoes:
        return True
    if regra.get('combinar') == COMBINAR_QUALQUER:
        return any(casa_condicao(c, fatos) for c in condicoes)
    return all(casa_condicao(c, fatos) for c in condicoes)


def vale_para_o_papel(onde, papel):
    if papel == PAPEL_GRUPO:
        return onde in (ONDE_GRUPO, ONDE_AMBOS)
    if papel == PAPEL_MEMBRO:
        return onde in (ONDE_MEMBROS, ONDE_AMBOS)
    return True


def _campo_do_modelo(nome, fatos):
    """{Floor}, {Unit ID}, {room}... — parametro, calculado, ambiente ou fato."""
    for fonte in (fatos.get('calculados') or {}, fatos.get('params') or {},
                  fatos.get('ambiente') or {}):
        if _texto(fonte.get(nome)):
            return _texto(fonte.get(nome))
    return _texto(fatos.get(nome))


def preencher_modelo(modelo, fatos):
    """'{Floor}-{Unit ID}' -> '2nd-207'. Campo sem valor fica vazio."""
    saida, i = [], 0
    while i < len(modelo):
        inicio = modelo.find('{', i)
        fim = modelo.find('}', inicio + 1) if inicio >= 0 else -1
        if inicio < 0 or fim < 0:
            saida.append(modelo[i:])
            break
        saida.append(modelo[i:inicio])
        saida.append(_campo_do_modelo(modelo[inicio + 1:fim].strip(), fatos))
        i = fim + 1
    return u''.join(saida)


def valor_da_acao(acao, fatos):
    """Texto a gravar, ou None se a acao nao tem de onde tirar o valor."""
    tipo = acao['acao']
    if tipo == FIXO:
        return acao['valor']
    if tipo == COPIAR:
        valor = _campo_do_modelo(acao['valor'], fatos)
        return valor or None
    if tipo == MODELO:
        valor = preencher_modelo(acao['valor'], fatos).strip()
        return valor or None
    if tipo == DO_AMBIENTE:
        nome = acao['valor'] or acao['parametro']
        valor = _texto((fatos.get('ambiente') or {}).get(nome))
        return valor or None
    if tipo == DO_AMBIENTE_TOPO:
        nome = acao['valor'] or acao['parametro']
        valor = _texto((fatos.get('ambiente_topo') or {}).get(nome))
        return valor or None
    if tipo == FLOOR_MAIS:
        return floor_mais(_campo_do_modelo(u'Floor', fatos),
                          fatos.get('floors'), _passos(acao['valor']))
    return None


def floor_mais(atual, floors, passos):
    """'1st' + 1 em ['1st', '2nd', '3rd'] -> '2nd'. None se o Floor atual nao
    esta na lista ou se passar do primeiro/ultimo (nao inventa andar)."""
    floors = list(floors or [])
    if passos is None or not atual or atual not in floors:
        return None
    posicao = floors.index(atual) + passos
    return floors[posicao] if 0 <= posicao < len(floors) else None


#: Operadores que AFIRMAM algo sobre o grupo. "grupo nao contem KIT" nao e
#: regra de aranha e nao ganha prioridade.
_AFIRMATIVOS = (E, CONTEM, COMECA, TERMINA, PREENCHIDO)


#: Campos que dizem a QUE CONJUNTO a peca pertence. Regra sobre eles vence a
#: regra de orientacao. O system entrou em 16/09/2026: a regra do KIT ("system
#: comeca com KIT ou grupo comeca com KIT") ficava atras da aranha e a peca de
#: KIT dentro da aranha virava Typical em vez de Kits.
CAMPOS_DE_CONJUNTO = (GRUPO, SYSTEM)


def prioridade_da_regra(regra):
    """0 para regra com condicao afirmativa sobre grupo/system, 1 para as outras.

    Decisao do Thiago (15/09/2026): no MIIQLUX o tubo horizontal dentro da
    aranha virava Colgante porque a regra de orientacao vinha antes da de
    ARN TYP na lista. A regra de grupo vence; dentro de cada faixa, a ordem.

    Com "qualquer condicao" (OU) o grupo so esta garantido quando TODAS as
    condicoes afirmam o grupo: "grupo ARN ou vertical" casa tubo solto.
    """
    condicoes = regra.get('quando') or []
    de_conjunto = [c['campo'] in CAMPOS_DE_CONJUNTO
                   and c['operador'] in _AFIRMATIVOS for c in condicoes]
    if regra.get('combinar') == COMBINAR_QUALQUER:
        return 0 if de_conjunto and all(de_conjunto) else 1
    return 0 if any(de_conjunto) else 1


def dominante(valores):
    """{'valor', 'qtd', 'total'} do valor mais frequente, sem contar vazios.

    Empate: o que apareceu primeiro. None sem valor nenhum. Usado para a
    instancia do Model Group receber o que os membros tem (15/09/2026).
    """
    contagem = {}
    ordem = []
    for valor in valores or []:
        texto = _texto(valor)
        if not texto:
            continue
        if texto not in contagem:
            contagem[texto] = 0
            ordem.append(texto)
        contagem[texto] += 1
    if not ordem:
        return None
    melhor = ordem[0]
    for texto in ordem[1:]:
        if contagem[texto] > contagem[melhor]:
            melhor = texto
    return {'valor': melhor, 'qtd': contagem[melhor],
            'total': sum(contagem.values())}


def decidir(regras, fatos, ambiente_params=None, fixos=None, membros=None,
            perdidas=None):
    """{parametro: {'valor', 'origem', 'regra'}} para UM elemento.

    `regras` ja normalizadas. `ambiente_params`: nomes que a aba Ambientes
    copia do room. `fixos`: {parametro: valor} ja filtrado para o papel.
    `membros`: {parametro: valor dominante dos membros} — so na instancia do
    grupo; entra depois das regras e antes do ambiente.

    `perdidas` (opcional): dict que recebe {nome da regra: nome da regra que
    ja tinha decidido}. E a regra que CASOU e nao gravou porque outra veio
    antes — na tela isso aparecia como "nenhuma peca" e enganava (16/09/2026).
    """
    fatos = fatos or {}
    papel = fatos.get('papel') or PAPEL_SOLTO
    atuais = fatos.get('params') or {}
    decisoes = {}

    # sorted e estavel: dentro da mesma prioridade, vale a ordem da lista
    ordenadas = sorted(enumerate(regras or []),
                       key=lambda par: prioridade_da_regra(par[1]))
    for posicao, regra in ordenadas:
        if not regra['ativa'] or not vale_para_o_papel(regra['onde'], papel):
            continue
        if not casa(regra, fatos):
            continue
        for acao in regra['entao']:
            nome = acao['parametro']
            if nome in decisoes:
                if perdidas is not None:
                    chave = regra['nome'] or u'regra {}'.format(posicao + 1)
                    perdidas.setdefault(chave, decisoes[nome]['regra'])
                continue
            if regra['so_vazio'] and _texto(atuais.get(nome)):
                continue
            valor = valor_da_acao(acao, fatos)
            if valor is None:
                continue
            decisoes[nome] = {'valor': valor, 'origem': ORIGEM_REGRA,
                              'regra': regra['nome'] or
                              u'regra {}'.format(posicao + 1)}
            if acao['acao'] == FLOOR_MAIS:
                # a janela troca o Floor CALCULADO (reservado) por este
                decisoes[nome]['floor_mais'] = acao['valor']
            elif acao['acao'] == DO_AMBIENTE_TOPO:
                # idem para Unit ID / Type quando "Calcular" esta ligado
                decisoes[nome]['do_topo'] = True

    for nome, valor in sorted((membros or {}).items()):
        valor = _texto(valor)
        if nome not in decisoes and valor:
            decisoes[nome] = {'valor': valor, 'origem': ORIGEM_MEMBROS,
                              'regra': u'dos membros'}

    ambiente = fatos.get('ambiente') or {}
    for nome in ambiente_params or []:
        valor = _texto(ambiente.get(nome))
        if nome not in decisoes and valor:
            decisoes[nome] = {'valor': valor, 'origem': ORIGEM_AMBIENTE,
                              'regra': _texto(fatos.get(ROOM)) or u'ambiente'}

    for nome, valor in sorted((fixos or {}).items()):
        valor = _texto(valor)
        if nome not in decisoes and valor:
            decisoes[nome] = {'valor': valor, 'origem': ORIGEM_FIXO,
                              'regra': u'fixo'}
    return decisoes


def campos_do_modelo(modelo):
    """['Floor', 'Unit ID'] de '{Floor}-{Unit ID}'."""
    nomes, i = [], 0
    while True:
        inicio = (modelo or '').find('{', i)
        fim = modelo.find('}', inicio + 1) if inicio >= 0 else -1
        if inicio < 0 or fim < 0:
            return nomes
        nome = modelo[inicio + 1:fim].strip()
        if nome:
            nomes.append(nome)
        i = fim + 1


def parametros_usados(regras):
    """Nomes de parametro que as regras leem ou gravam — o lado Revit so le
    esses (no projeto inteiro, ler todos seria caro a toa)."""
    nomes = set()
    for regra in regras or []:
        for condicao in regra['quando']:
            if condicao['campo'] == PARAMETRO:
                nomes.add(condicao['parametro'])
        for acao in regra['entao']:
            nomes.add(acao['parametro'])
            if acao['acao'] == COPIAR:
                nomes.add(acao['valor'])
            elif acao['acao'] == MODELO:
                nomes.update(campos_do_modelo(acao['valor']))
    return nomes


CAMPOS_DE_AMBIENTE = (ROOM, ROOM_NUMERO)


def precisa_de_ambiente(regras):
    """True se alguma regra ATIVA pergunta pelo room (condicao, acao 'do
    ambiente' ou campo {room} num modelo). Sem casar os rooms, essa regra
    nunca acertaria — e ninguem saberia por que (achado da auditoria)."""
    for regra in regras or []:
        if not regra.get('ativa', True):
            continue
        if any(c['campo'] in CAMPOS_DE_AMBIENTE for c in regra['quando']):
            return True
        for acao in regra['entao']:
            if acao['acao'] == DO_AMBIENTE:
                return True
            if acao['acao'] == MODELO and any(
                    nome.lower() in CAMPOS_DE_AMBIENTE
                    for nome in campos_do_modelo(acao['valor'])):
                return True
    return False


def avisos_da_regra(regra):
    """Avisos de regra que NUNCA vai casar ou que vai deixar peça de fora.

    Achados do 1o uso (auditoria 16/09/2026): o Thiago escreveu "Categoria é
    Acessório E é Conexão E é Tubulação" (nenhuma peça tem tres categorias) e
    "Comprimento > 1'" (conexao nao tem comprimento e ficou tudo em branco).
    """
    avisos = []
    if regra is None:
        return avisos
    condicoes = regra.get('quando') or []
    if regra.get('combinar') != COMBINAR_QUALQUER:
        vistos = {}
        for condicao in condicoes:
            if condicao['operador'] not in (E, VAZIO):
                continue
            chave = condicao['parametro'] if condicao['campo'] == PARAMETRO \
                else condicao['campo']
            vistos.setdefault(chave, []).append(condicao['valor'])
        for chave, valores in sorted(vistos.items()):
            if len(set(valores)) > 1:
                avisos.append(
                    u'"{}" não pode ser {} ao mesmo tempo: nenhuma peça casa. '
                    u'Troque para "Qualquer condição (OU)".'.format(
                        _rotulo(CAMPOS, chave),
                        u' e '.join(u'"{}"'.format(v) for v in valores)))
    usa_comprimento = any(c['campo'] == COMPRIMENTO for c in condicoes)
    if usa_comprimento and not any(c['campo'] in CAMPOS_DE_TRECHO
                                   for c in condicoes):
        avisos.append(
            u'Só tubo tem comprimento: as conexões e os acessórios ficam de '
            u'fora. Para pegar o desvio inteiro use "Trecho horizontal '
            u'(comprimento)".')
    return avisos


def precisa_de_ambiente_topo(regras):
    """True se alguma regra ATIVA le o room do TOPO (custa uma sondagem a mais
    por elemento — so vale quando alguem usa)."""
    for regra in regras or []:
        if not regra.get('ativa', True):
            continue
        if any(a['acao'] == DO_AMBIENTE_TOPO for a in regra['entao']):
            return True
    return False


def precisa_de_trecho(regras):
    """True se alguma regra ATIVA pergunta pelo trecho horizontal — percorrer a
    rede custa caro e so vale a pena quando alguem usa (16/09/2026)."""
    for regra in regras or []:
        if not regra.get('ativa', True):
            continue
        if any(c['campo'] in CAMPOS_DE_TRECHO for c in regra['quando']):
            return True
    return False


def so_o_que_muda(decisoes, atuais):
    """As decisoes cujo valor difere do que o elemento ja tem."""
    atuais = atuais or {}
    return dict((nome, d) for nome, d in (decisoes or {}).items()
                if _texto(atuais.get(nome)) != d['valor'])


# ---------------------------------------------------------------- descricao

def _rotulo(pares, chave):
    return dict(pares).get(chave, chave)


def descrever_condicao(condicao):
    campo = (condicao['parametro'] if condicao['campo'] == PARAMETRO
             else _rotulo(CAMPOS, condicao['campo']))
    operador = _rotulo(OPERADORES, condicao['operador'])
    if condicao['operador'] in SEM_VALOR:
        return u'{} {}'.format(campo, operador)
    if condicao['operador'] == ENTRE:
        return u'{} entre {} e {}'.format(campo, condicao['valor'],
                                          condicao['ate'])
    return u'{} {} "{}"'.format(campo, operador, condicao['valor'])


def descrever_acao(acao):
    if acao['acao'] == FIXO:
        return u'{} = "{}"'.format(acao['parametro'], acao['valor'])
    if acao['acao'] == COPIAR:
        return u'{} ← {}'.format(acao['parametro'], acao['valor'])
    if acao['acao'] == MODELO:
        return u'{} = {}'.format(acao['parametro'], acao['valor'])
    if acao['acao'] == FLOOR_MAIS:
        return u'{} = Floor do nível {}'.format(acao['parametro'], acao['valor'])
    if acao['acao'] == DO_AMBIENTE_TOPO:
        return u'{} ← unidade de cima'.format(acao['parametro'])
    return u'{} ← ambiente'.format(acao['parametro'])


def descrever_regra(regra):
    juncao = u' ou ' if regra.get('combinar') == COMBINAR_QUALQUER else u' e '
    quando = juncao.join(descrever_condicao(c) for c in regra['quando'])
    entao = u', '.join(descrever_acao(a) for a in regra['entao'])
    texto = u'se {} → {}'.format(quando, entao) if quando else \
        u'sempre → {}'.format(entao)
    if regra['onde'] != ONDE_AMBOS:
        texto += u' ({})'.format(_rotulo(ONDES, regra['onde']))
    if regra['so_vazio']:
        texto += u' · só se vazio'
    return texto


# ---------------------------------------------------- exportar / importar

def exportar(regras, projeto=''):
    """Texto JSON para arquivo — com formato e versao para reconhecer depois."""
    return json.dumps({'formato': FORMATO_EXPORTACAO,
                       'versao': VERSAO_EXPORTACAO,
                       'projeto': projeto or '',
                       'regras': normalizar_regras(regras)},
                      indent=2, ensure_ascii=False)


def fundir_regras(atuais, novas):
    """(regras, trocadas). A nova com o MESMO nome troca a antiga NO LUGAR —
    e entra como veio, ativa.

    16/09/2026: o banco de regras PULAVA a de mesmo nome. O Thiago tinha uma
    "Aranha (grupo ARN TYP)" desativada, a do banco nao entrou, e as regras de
    riser passaram a pegar as pecas da aranha.
    """
    resultado = [dict(r) for r in normalizar_regras(atuais)]
    por_nome = dict((r['nome'], i) for i, r in enumerate(resultado) if r['nome'])
    trocadas = 0
    for regra in normalizar_regras(novas):
        if regra['nome'] and regra['nome'] in por_nome:
            resultado[por_nome[regra['nome']]] = regra
            trocadas += 1
        else:
            resultado.append(regra)
    return resultado, trocadas


def importar(texto, atuais=None, substituir=False):
    """(regras, mensagem). Soma por padrao: regra com o MESMO nome e
    substituida no lugar; as novas vao para o fim.

    ValueError com o motivo se o arquivo nao for de regras.
    """
    try:
        dados = json.loads(texto)
    except (TypeError, ValueError):
        raise ValueError(u'o arquivo não é JSON')
    if isinstance(dados, list):
        brutas = dados
    elif isinstance(dados, dict) and dados.get('formato') == FORMATO_EXPORTACAO:
        brutas = dados.get('regras') or []
    else:
        raise ValueError(u'o arquivo não é uma exportação de regras do Unit '
                         u'Mapper')
    novas = normalizar_regras(brutas)
    descartadas = len(brutas) - len(novas)
    if substituir:
        resultado = novas
        acao = u'{} regra(s) importada(s), substituindo as do modelo'.format(
            len(novas))
    else:
        resultado, trocadas = fundir_regras(atuais, novas)
        acao = u'{} regra(s) importada(s) ({} atualizada(s) pelo nome)'.format(
            len(novas), trocadas)
    if descartadas:
        acao += u' · {} inválida(s) ignorada(s)'.format(descartadas)
    return resultado, acao


# --------------------------------------------------------- modelos prontos

def _regra(nome, quando, entao, onde=ONDE_AMBOS):
    return normalizar_regra({'nome': nome, 'quando': quando, 'entao': entao,
                             'onde': onde})


#: Corte do desvio de riser — decisao do Thiago em 16/09/2026, com os numeros
#: da auditoria (trechos soltos entre 2 verticais: <2 ft 696 pecas, <4 761,
#: <6 962, <8 996) e os exemplos dele (1,5 ft e 4,9 ft).
DESVIO_ATE = u"6'"


def banco_de_regras():
    """[(pacote, [regras])] — o banco que a tela oferece por disciplina.

    A ordem importa: o KIT vem antes da aranha (decisao do Thiago em
    16/09/2026 — a peca de KIT DENTRO da aranha e "Kits", nao "Typical"; as
    duas tem prioridade de grupo, entao quem decide e a ordem da lista), e o
    desvio vem antes do colgante, senao todo horizontal ja seria Colgante.
    """
    return [
        (u'KIT', [
            _combinar(_regra(u'KIT', [
                {'campo': SYSTEM, 'operador': COMECA, 'valor': 'KIT'},
                {'campo': GRUPO, 'operador': COMECA, 'valor': 'KIT'}],
                [{'parametro': 'PHASE', 'acao': FIXO, 'valor': 'Kits'},
                 {'parametro': 'Stage', 'acao': FIXO, 'valor': 'Job Site'}]),
                COMBINAR_QUALQUER)]),
        (u'Aranha (grupo ARN TYP)', [
            _regra(u'Aranha (grupo ARN TYP)', [
                {'campo': GRUPO, 'operador': COMECA, 'valor': 'ARN TYP'}],
                [{'parametro': 'PHASE', 'acao': FIXO, 'valor': 'Typical'},
                 {'parametro': 'Stage', 'acao': FIXO, 'valor': 'Pre-Fab'},
                 # a aranha mora no forro de baixo e atende a unidade de cima:
                 # Floor fica o do nivel onde ela esta (natural, sem offset)
                 {'parametro': 'Unit ID', 'acao': DO_AMBIENTE_TOPO,
                  'valor': 'Unit ID'},
                 {'parametro': 'Type', 'acao': DO_AMBIENTE_TOPO,
                  'valor': 'Type'}])]),
        (u'Riser e desvio (esgoto e ventilação)', [
            _regra(u'Desvio de riser (trecho curto)', [
                {'campo': ORIENTACAO, 'operador': E, 'valor': 'horizontal'},
                {'campo': TRECHO_COMPRIMENTO, 'operador': MENOR,
                 'valor': DESVIO_ATE},
                {'campo': TRECHO_PONTAS, 'operador': MAIOR_IGUAL, 'valor': '2'}],
                [{'parametro': 'PHASE', 'acao': FIXO, 'valor': 'Riser'}]),
            _combinar(_regra(u'Riser (vertical ou inclinado)', [
                {'campo': ORIENTACAO, 'operador': E, 'valor': 'vertical'},
                {'campo': ORIENTACAO, 'operador': E, 'valor': 'inclinado'}],
                [{'parametro': 'PHASE', 'acao': FIXO, 'valor': 'Riser'}]),
                COMBINAR_QUALQUER)]),
        (u'Colgante', [
            _regra(u'Colgante (horizontal)', [
                {'campo': ORIENTACAO, 'operador': E, 'valor': 'horizontal'}],
                [{'parametro': 'PHASE', 'acao': FIXO, 'valor': 'Colgante'}])]),
    ]


def ordenar_pelo_banco(regras):
    """As regras que vieram do banco voltam para a ORDEM do banco, sem sair
    das posicoes que ocupam (as regras proprias do usuario ficam onde estao).

    16/09/2026: o KIT entrou no fim da lista, depois da aranha, e nao pegava
    peca nenhuma — as duas tem prioridade de conjunto, entao vale a ordem.
    """
    do_banco = [r['nome'] for _pacote, rs in banco_de_regras() for r in rs]
    posicoes = [i for i, r in enumerate(regras or []) if r['nome'] in do_banco]
    if len(posicoes) < 2:
        return list(regras or [])
    ordenadas = sorted((regras[i] for i in posicoes),
                       key=lambda r: do_banco.index(r['nome']))
    saida = list(regras)
    for posicao, regra in zip(posicoes, ordenadas):
        saida[posicao] = regra
    return saida


def _combinar(regra, combinar):
    regra['combinar'] = combinar
    return regra


def modelos_prontos():
    """Regras de partida — carregadas pela tela, editaveis. A ordem importa:
    o KIT da aranha antes da aranha, a aranha antes da orientacao."""
    return [
        _regra(u'KIT da aranha', [
            {'campo': GRUPO, 'operador': COMECA, 'valor': 'ARN TYP'},
            {'campo': SYSTEM, 'operador': CONTEM, 'valor': 'KIT'}],
            [{'parametro': 'PHASE', 'acao': FIXO, 'valor': 'Kits'},
             {'parametro': 'Stage', 'acao': FIXO, 'valor': 'Job Site'}]),
        _regra(u'Aranha (grupo ARN TYP)', [
            {'campo': GRUPO, 'operador': COMECA, 'valor': 'ARN TYP'}],
            [{'parametro': 'PHASE', 'acao': FIXO, 'valor': 'Typical'},
             {'parametro': 'Stage', 'acao': FIXO, 'valor': 'Pre-Fab'}]),
        _regra(u'Tubo horizontal', [
            {'campo': ORIENTACAO, 'operador': E, 'valor': 'horizontal'}],
            [{'parametro': 'PHASE', 'acao': FIXO, 'valor': 'Colgante'}]),
        _regra(u'Tubo vertical', [
            {'campo': ORIENTACAO, 'operador': E, 'valor': 'vertical'}],
            [{'parametro': 'PHASE', 'acao': FIXO, 'valor': 'Riser'}]),
    ]
