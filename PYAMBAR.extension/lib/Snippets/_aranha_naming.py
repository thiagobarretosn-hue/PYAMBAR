# -*- coding: utf-8 -*-
"""Nomenclatura sequencial das aranhas — pura, sem Revit.

A REGRA, dita pelo Thiago
-------------------------
"O kit vai se chamar KIT ARN TYP#V pois a ultima criada foi KIT ARN TYP#U.
Consequentemente a aranha vai se chamar ARN TYP#V."

Ou seja: **continua da maior letra usada**, nao preenche buraco. O buraco e
reportado (`letras_livres`) para o usuario decidir, nunca consumido sozinho —
reaproveitar uma letra vaga renomearia uma tipologia que ja foi para obra.

O QUE O MODELO REAL ENSINOU (24 sistemas ARN + 54 KIT, lidos em 08/09/2026)
---------------------------------------------------------------------------
A contagem tem de aguentar a bagunca que existe de verdade:

  `ARN TYP #A`      formato predominante (23 de 24)
  `ARN TYP#V`       o ultimo criado saiu SEM espaco
  `ARN TYP #T (2)`  parenteses que o Revit poe ao duplicar
  `KIT ARN TYP #U 1` sufixo do DivideSystem (1, 2, 3 — uma rede por subida)
  `KIT ARN TYP #P 1 1` o "1" vazou para o nome base
  `ARN TYP#I-M` / `#I2` variantes espelhadas: contam como a MESMA letra

Se qualquer uma dessas escapasse da contagem, a proxima aranha nasceria com uma
letra ja usada — e nome de system duplicado o Revit rejeita.

**A letra K esta livre no projeto** (a sequencia pula de J para L). Isso e
reportado, nao corrigido.

Formato de saida: **com espaco** (`ARN TYP #W`), que e o predominante. A
ferramenta normaliza em vez de propagar o escorregao do ultimo.
"""
import re

PREFIXO_ARN = 'ARN TYP #'
PREFIXO_KIT = 'KIT ARN TYP #'

#: Captura a letra logo apos o '#', tolerando ausencia de espaco antes dele.
#: O que vier depois (sufixo do DivideSystem, parenteses, -M, digito) e
#: descartado de proposito: e a mesma tipologia.
_RE_LETRA = re.compile(r'ARN\s+TYP\s*#\s*([A-Z]{1,2})', re.IGNORECASE)


def letra_do_nome(nome):
    """A letra da tipologia, ou None se o nome nao for de uma aranha."""
    if not nome:
        return None
    achado = _RE_LETRA.search(nome)
    if not achado:
        return None
    return achado.group(1).upper()


def letras_usadas(nomes):
    """Conjunto de letras ja ocupadas, varrendo systems e/ou grupos."""
    usadas = set()
    for nome in nomes or []:
        letra = letra_do_nome(nome)
        if letra:
            usadas.add(letra)
    return usadas


def _para_indice(letra):
    """'A' -> 1, 'Z' -> 26, 'AA' -> 27 — ordem de planilha."""
    valor = 0
    for c in letra:
        valor = valor * 26 + (ord(c) - ord('A') + 1)
    return valor


def _para_letra(indice):
    """O inverso de `_para_indice`."""
    letra = ''
    while indice > 0:
        indice, resto = divmod(indice - 1, 26)
        letra = chr(ord('A') + resto) + letra
    return letra


def proxima_letra(nomes):
    """A letra seguinte a MAIOR ja usada. Sem nada usado, comeca em 'A'."""
    usadas = letras_usadas(nomes)
    if not usadas:
        return 'A'
    maior = max(_para_indice(l) for l in usadas)
    return _para_letra(maior + 1)


def letras_livres(nomes):
    """Buracos na sequencia — para AVISAR, nunca para consumir.

    Reusar uma letra vaga renomearia uma tipologia que ja pode ter ido para
    obra; quem decide isso e o usuario.
    """
    usadas = letras_usadas(nomes)
    if not usadas:
        return []
    maior = max(_para_indice(l) for l in usadas)
    return [_para_letra(i) for i in range(1, maior)
            if _para_letra(i) not in usadas]


def nome_aranha(letra):
    """'ARN TYP #W' — o system dos trechos HORIZONTAIS."""
    return '{}{}'.format(PREFIXO_ARN, (letra or '').upper())


def nome_kit(letra):
    """'KIT ARN TYP #W' — o system dos tubos VERTICAIS (as subidas)."""
    return '{}{}'.format(PREFIXO_KIT, (letra or '').upper())


# ===================================================================
# NOME DO GRUPO — outro formato, e nao e descuido
# ===================================================================
#
# Medido em 09/09/2026: os dois dominios divergem, e cada um e consistente
# dentro de si.
#
#     systems      `ARN TYP #A`   com espaco     23 de 24
#     GroupTypes   `ARN TYP#A`    SEM espaco     15 de 15
#
# Por isso `nome_aranha` (system) e `nome_grupo` (grupo) devolvem coisas
# diferentes de proposito. Normalizar os dois para o mesmo formato renomearia
# tipologias que ja foram para obra.

PREFIXO_GRUPO = 'ARN TYP#'

#: Nome do grupo de detalhe anexado — as cotas e tags da aranha.
#: O modelo tem tres grafias (COTA 2x, Cotas 2x, COTAS 8x) porque o Revit
#: **aceita GroupTypes com nome repetido** — ao contrario do system, que
#: rejeita. Cada aranha agrupada criou o seu. O Thiago escolheu `Cotas` em
#: 09/09/2026.
NOME_DETALHE = 'Cotas'


def nome_grupo(letra):
    """`ARN TYP#A` — o formato dos GroupTypes, sem espaco antes do '#'."""
    return PREFIXO_GRUPO + (letra or '').upper()


# ===================================================================
# NOME DA VISTA DE DETALHE — a aranha primeiro, depois o piso
# ===================================================================
#
# Pedido do Thiago em 10/09/2026: a vista criada pela chamada de detalhe se
# chama "<nome da aranha> - <piso em que ela foi criada>":
#
#     ARN TYP #N - 04 - LEVEL 4
#
# As 16 vistas que existiam estavam ao contrario ("04 - LEVEL 4 - ARN TYP#N"),
# duas com espaco duplo antes do hifen, e ele pediu para padronizar todas.
#
# O separador " - " COM espacos e o que torna o nome inequivoco: a variante
# cola o hifen na letra (`#I-M`), entao `ARN TYP #I - ...` nao e prefixo de
# `ARN TYP #I-M - ...` — o casamento por prefixo que ja mordeu em `#I`/`#I2`.

SEPARADOR_VISTA = ' - '

#: A aranha dentro de qualquer nome — system, grupo ou vista, formato velho ou
#: novo. A variante so conta se vier COLADA na letra: com espaco, o hifen e o
#: separador do nivel.
_RE_ARANHA = re.compile(r'ARN\s+TYP\s*#\s*([A-Z]{1,2})(-[A-Z0-9]+)?',
                        re.IGNORECASE)


def aranha_do_nome(nome):
    """'ARN TYP #I-M' a partir de qualquer grafia, ou None.

    Normaliza para o formato do system (espaco antes do '#'), o mesmo de
    `nome_aranha`: o nome da vista sai igual venha a letra do painel, do
    system ou de um grupo antigo sem espaco.
    """
    if not nome:
        return None
    achado = _RE_ARANHA.search(nome)
    if not achado:
        return None
    return nome_aranha(achado.group(1)) + (achado.group(2) or '').upper()


def nome_vista_detalhe(aranha, nivel):
    """'ARN TYP #N - 04 - LEVEL 4'."""
    return '{}{}{}'.format(aranha, SEPARADOR_VISTA, (nivel or '').strip())


def nome_vista_padronizado(nome_atual, nivel):
    """O nome novo de uma vista antiga, ou None se ela nao for de aranha.

    O nivel vem da VISTA (`GenLevel`), nao do texto: dois nomes antigos
    tinham espaco duplo antes do hifen, e reaproveitar o texto propagaria o
    escorregao.
    """
    aranha = aranha_do_nome(nome_atual)
    if aranha is None or not (nivel or '').strip():
        return None
    return nome_vista_detalhe(aranha, nivel)


def eh_vista_da_aranha(nome_vista, letra):
    """True quando a vista e da aranha `letra` — e NAO de uma variante dela.

    `#I-M` e variante de `#I` mas tem vista propria. Confundir as duas faria o
    painel dar a chamada da `#I` por feita so porque a espelhada tem a sua.
    """
    if not letra:
        return False
    return aranha_do_nome(nome_vista) == nome_aranha(letra)


# ===================================================================
# A LETRA ESCOLHIDA NUMA LISTA — e valendo para tudo
# ===================================================================
#
# Pedido do Thiago em 10/09/2026, depois de o Agrupar batizar a `#Q` com uma
# letra nova: "ele deve nomear de acordo com o que ja foi nomeado e nao buscar
# um nome novo". E o caso inverso: "ja nomeamos o system e temos que
# configurar um nome que nao esta disponivel". A lista oferece os dois, e a
# letra escolhida nela e a referencia de system, parametros, vista e grupo.

MOTIVO_ATUAL = 'atual'
MOTIVO_DA_ARANHA = 'já no system desta aranha'
MOTIVO_PROXIMA = 'próxima da sequência'
MOTIVO_VAGA = 'vaga na sequência'
MOTIVO_EM_USO = 'em uso'

#: Entre a letra e o motivo na lista. Dois espacos de cada lado: a variante
#: cola o hifen na letra (`I-M`) e nunca e confundida com o separador.
SEP_OPCAO = '  -  '

_RE_LETRA_SOLTA = re.compile(r'^([A-Z]{1,2})(-[A-Z0-9]+)?$')


def normalizar_letra(texto):
    """'q' -> 'Q', 'i-m' -> 'I-M', 'ARN TYP #Q' -> 'Q'; o que nao serve -> None."""
    if not texto:
        return None
    texto = texto.strip().upper()
    aranha = aranha_do_nome(texto)
    if aranha:
        return aranha[len(PREFIXO_ARN):]
    if _RE_LETRA_SOLTA.match(texto):
        return texto
    return None


def _ordem(letra):
    base = letra.split('-')[0]
    return (_para_indice(base), letra)


def letras_por_dominancia(nomes):
    """Letras (com variante) dos nomes, da mais frequente para a menos.

    Dominante, nunca a primeira encontrada ([[feedback-medir-pelo-dominante]]):
    a aranha tem um system ARN e varios KIT, todos da mesma letra — mas um
    tubo vizinho de outra aranha na selecao nao pode decidir o nome.
    """
    contagem = {}
    for nome in nomes or []:
        aranha = aranha_do_nome(nome)
        if aranha:
            letra = aranha[len(PREFIXO_ARN):]
            contagem[letra] = contagem.get(letra, 0) + 1
    return sorted(contagem, key=lambda l: (-contagem[l], _ordem(l)))


def letra_dominante(nomes):
    letras = letras_por_dominancia(nomes)
    return letras[0] if letras else None


def opcoes_de_letra(nomes_usados, letras_da_aranha=None, atual=None):
    """[(letra, motivo)] sem repetir, na ordem em que a lista mostra.

    atual -> as do system desta aranha -> a proxima -> as vagas -> as em uso.
    As "em uso" ficam na lista de proposito: e o caso do system ja nomeado,
    ou de refazer uma tipologia.
    """
    opcoes = []
    vistas = set()

    def por(letra, motivo):
        letra = normalizar_letra(letra)
        if letra and letra not in vistas:
            vistas.add(letra)
            opcoes.append((letra, motivo))

    por(atual, MOTIVO_ATUAL)
    for letra in letras_da_aranha or []:
        por(letra, MOTIVO_DA_ARANHA)
    por(proxima_letra(nomes_usados), MOTIVO_PROXIMA)
    for letra in letras_livres(nomes_usados):
        por(letra, MOTIVO_VAGA)
    for letra in sorted(letras_usadas(nomes_usados), key=_para_indice):
        por(letra, MOTIVO_EM_USO)
    return opcoes


def rotulo_opcao(letra, motivo):
    """'ARN TYP #R  -  ja no system desta aranha'.

    O nome inteiro, nao so a letra — pedido do Thiago em 10/09/2026: "fica
    mais organizado". `letra_do_rotulo` le os dois formatos.
    """
    return '{}{}{}'.format(nome_aranha(letra), SEP_OPCAO, motivo)


def letra_a_adotar(atual, letras_da_aranha):
    """A letra que o painel assume sem perguntar: a atual, senao a do system.

    O Thiago, 10/09/2026: "se a gente ja sabe que o R ja esta no sistema, ja e
    o nome que muito possivelmente iremos usar" — vale para aranha nova que
    ja passou pela Separar e para as que ja foram feitas. A lista continua la
    para trocar; aqui so se decide o ponto de partida.
    """
    if atual:
        return normalizar_letra(atual)
    for letra in letras_da_aranha or []:
        letra = normalizar_letra(letra)
        if letra:
            return letra
    return None


def letra_do_rotulo(texto):
    """A letra de um item da lista — ou do que foi digitado no campo."""
    if not texto:
        return None
    return normalizar_letra(texto.split(SEP_OPCAO)[0])
