# -*- coding: utf-8 -*-
"""Para que nivel a aranha inteira deve ir — puro, sem Revit.

A REGRA, dita pelo Thiago (09/09/2026)
--------------------------------------
> "Troque o nivel de todos os elementos da aranha para o nivel onde a maior
>  parte dos elementos esta. Por exemplo: a aranha esta abaixo do nivel 2 mas
>  os tubos do kit e caps estao no nivel 3 — todo mundo deve estar no nivel 2."

O QUE O MODELO MOSTRA
---------------------
**10 das 13 aranhas** do MIIQLUX estavam com o nivel misturado, sempre no mesmo
formato: a grande maioria num nivel e uma sobra pequena noutro.

    #A  21 no GROUND FLOOR  +  4 no LEVEL 2
    #B  20 no LEVEL 2       +  4 no LEVEL 3
    #J  15 no LEVEL 2       +  6 no LEVEL 3  + 1 no GROUND
    #T  21 no LEVEL 2       +  1 no LEVEL 3   <- era o proprio Plywood Frame

As tres que estavam limpas (`#D`, `#H`, `#V`) mostram o estado desejado.

TROCAR O NIVEL NAO MOVE O ELEMENTO — medido, nao suposto
--------------------------------------------------------
Probe com rollback no MIIQLUX, conferindo o nivel DE VOLTA antes de olhar o Z:

    tubo 9561575   LEVEL 6 (51,1667) -> FOUNDATION (-3,0)   trocou: True
                   z0/z1 identicos, delta 0,000000
                   offset 10,8381 -> 65,0047  (+54,166667 = a diferenca exata)

    fitting 9521383 (FAMILY_LEVEL_PARAM)
                   FOUNDATION -> GROUND FLOOR                trocou: True
                   z -373,1776 -> -373,1776, delta 0,000000

O Revit joga a diferenca toda no offset e a geometria nao anda. Por isso esta
operacao e segura e nao precisa mexer em cota nenhuma.

A ORDEM DA CONFERENCIA IMPORTA
------------------------------
Uma versao anterior deste probe reportou "nao moveu" sem que nada tivesse sido
aplicado — os parametros eram read-only e o loop pulou os dois, entao eu estava
medindo a ausencia de movimento de uma troca que nunca aconteceu. Confirmar
primeiro que o nivel MUDOU; so depois o Z quer dizer alguma coisa.

E ha familia que troca e NAO compensa: a chapa de plywood solta (logo depois
da Inserir Plywood) aceita o nivel novo e o Revit MANTEM o offset — medido,
ela desce 12,5 ft do LEVEL 2 ao GROUND. `offset_compensado` desfaz isso. O
read-only que eu tinha atribuido a familia em 09/09/2026 vinha do Model
Group: agrupada, qualquer chapa fica com o nivel read-only.
"""


def contar_por_nivel(elementos):
    """{id_do_nivel: quantos}. `elementos` e [(qualquer_coisa, id_do_nivel)].

    Elemento sem nivel nao entra na conta: ele nao vota em nada, e incluir um
    "sem nivel" como se fosse candidato faria a maioria mudar de dono.
    """
    contagem = {}
    for _, nivel in elementos or []:
        if nivel is None:
            continue
        contagem[nivel] = contagem.get(nivel, 0) + 1
    return contagem


def esta_misturado(contagem):
    """True quando ha mais de um nivel em jogo."""
    return len(contagem or {}) > 1


def nivel_alvo(contagem, elevacoes):
    """O nivel da maioria. `elevacoes` e `{id_do_nivel: cota}`.

    Empate fica com o **mais baixo** — a aranha mora abaixo da laje que a
    referencia, entao na duvida ela desce em vez de subir. Sem a tabela de
    elevacoes, desempata pelo menor id: arbitrario, mas estavel, que e o que
    impede a escolha de mudar entre duas execucoes iguais.
    """
    if not contagem:
        return None

    maior = max(contagem.values())
    empatados = [nivel for nivel, n in contagem.items() if n == maior]
    if len(empatados) == 1:
        return empatados[0]

    elevacoes = elevacoes or {}
    return sorted(empatados,
                  key=lambda nivel: (elevacoes.get(nivel, 0.0), nivel))[0]


def nivel_do_piso(elevacoes, z_referencia):
    """O nivel do PISO que a aranha serve: o de elevacao mais proxima dela.

    `elevacoes` e `{id_do_nivel: cota}`. Isto NAO e a mesma pergunta que
    `nivel_alvo`: la a maioria dos elementos decide para onde o conjunto vai;
    aqui a GEOMETRIA decide qual laje a aranha esta servindo — util para quem
    precisa nascer no lugar certo (a chapa de plywood) e nao pode confiar no
    `ReferenceLevel` dos tubos, que e justamente o dado que costuma estar
    bagunçado.

    Empate resolve pelo menor id: arbitrario, mas estavel.
    """
    if not elevacoes:
        return None
    return sorted(elevacoes.items(),
                  key=lambda kv: (abs(kv[1] - z_referencia), kv[0]))[0][0]


def margem_do_piso(elevacoes, z_referencia):
    """(dist_do_escolhido, dist_do_segundo_colocado) — em pes.

    Serve para a ferramenta poder DUVIDAR em voz alta: se as duas distancias
    forem parecidas, a aranha esta a meio caminho entre dois niveis e a escolha
    merece confirmacao humana. Sem segundo colocado, devolve None no lugar.
    """
    if not elevacoes:
        return (None, None)
    distancias = sorted(abs(cota - z_referencia) for cota in elevacoes.values())
    return (distancias[0], distancias[1] if len(distancias) > 1 else None)


# ------------------------------------------------------ compensar a cota

#: ~0,3 mm. Abaixo disso e ruido de ponto flutuante, nao deslocamento.
TOLERANCIA_Z = 0.001


def andou(z_antes, z_depois, tolerancia=TOLERANCIA_Z):
    """True quando a troca de nivel moveu o elemento de verdade."""
    if z_antes is None or z_depois is None:
        return False
    return abs(z_depois - z_antes) > tolerancia


def offset_compensado(offset_atual, z_antes, z_depois):
    """O offset que devolve o elemento a cota onde estava.

    Ao trocar o nivel de uma familia com offset proprio (a chapa de plywood),
    o Revit MANTEM o offset e o elemento anda junto com o nivel. Somar ao
    offset o quanto ele andou desfaz exatamente isso. Medido em 10/09/2026:
    chapa no LEVEL 2 (12,5) trocada para o GROUND desce 12,5; offset
    0 + 12,5 a devolve a z=12,5 com delta 0.

    Nao depende de qual e o nivel novo, so do quanto andou — por isso vale
    tambem para quem ja tinha offset ajustado a mao (a chapa da `#M` esta em
    -0,438).
    """
    return offset_atual + (z_antes - z_depois)
