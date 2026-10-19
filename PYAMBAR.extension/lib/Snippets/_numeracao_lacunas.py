# -*- coding: utf-8 -*-
"""Numeracao de marcas que reaproveita as lacunas — puro, sem Revit.

A REGRA, dita pelo Thiago (19/10/2026)
--------------------------------------
> "Se eu deletar passes SP-101, SP-102 e acrescentar novos, quero que esses
>  novos ocupem os numeros disponiveis; se nao tiver disponiveis, usa o ultimo
>  numero: o ultimo foi SP-200, o proximo e SP-201."

O ESCOPO E O NIVEL
------------------
O "Reiniciar" da Coordenadas XYZ recomeca em 001 a cada pavimento, entao o
mesmo SP-001 existe uma vez por nivel. Lacuna e ultimo numero so fazem sentido
dentro do nivel do elemento: no modelo inteiro, o passe do LEVEL 3 iria tapar
um buraco do LEVEL 2.

POR QUE A LACUNA COMECA NO MENOR NUMERO USADO, NAO NO 1
-------------------------------------------------------
Um pavimento numerado de 101 a 200 nao tem "lacuna" de 1 a 100 — aquilo e
outra faixa. Comecar no menor numero usado protege esse caso; o custo e nao
reaproveitar o SP-001 quando ele mesmo foi o apagado.
"""
import re


def numero_da_marca(marca, prefixo):
    """O numero de `PREFIXO-NNN`, ou None se a marca nao segue o padrao."""
    if not marca or not prefixo:
        return None
    m = re.match(r"^{}-(\d+)$".format(re.escape(prefixo)), marca.strip())
    return int(m.group(1)) if m else None


def numeros_livres(usados, quantidade):
    """`quantidade` numeros: primeiro as lacunas entre o menor e o maior
    usado, em ordem crescente; depois maior+1, maior+2...

    Sem nenhum usado, comeca em 1.
    """
    if quantidade <= 0:
        return []
    usados = set(n for n in usados or [] if n is not None and n > 0)
    if not usados:
        return list(range(1, quantidade + 1))

    livres = []
    for n in range(min(usados), max(usados)):
        if n not in usados:
            livres.append(n)
            if len(livres) == quantidade:
                return livres
    proximo = max(usados) + 1
    while len(livres) < quantidade:
        livres.append(proximo)
        proximo += 1
    return livres


def distribuir_por_nivel(pendentes, usados_por_nivel):
    """Numero para cada pendente, tirado da reserva do proprio nivel.

    Args:
        pendentes: [(chave, nivel)] JA na ordem de numeracao. `nivel` pode
            ser None (elemento sem nivel forma um grupo proprio).
        usados_por_nivel: {nivel: iteravel de numeros ja ocupados}.

    Returns:
        {chave: numero}
    """
    quantos = {}
    for _, nivel in pendentes:
        quantos[nivel] = quantos.get(nivel, 0) + 1

    reserva = {}
    for nivel, qtd in quantos.items():
        reserva[nivel] = numeros_livres(usados_por_nivel.get(nivel, ()), qtd)

    resultado = {}
    cursor = {}
    for chave, nivel in pendentes:
        i = cursor.get(nivel, 0)
        resultado[chave] = reserva[nivel][i]
        cursor[nivel] = i + 1
    return resultado
