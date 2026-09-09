# -*- coding: utf-8 -*-
"""Ordenacao natural (humana) de textos - logica pura.

Ordem alfabetica pura coloca "Nivel 10" antes de "Nivel 2" e "101" antes de
"99", porque compara caractere a caractere. Aqui os trechos de digito viram
numero na comparacao, entao a lista sai na ordem que o engenheiro espera:

    alfabetica : ['1st', '10th', '2nd']      101, 1000, 99
    natural    : ['1st', '2nd', '10th']       99, 101, 1000

Puro Python (sem clr/Autodesk) - roda em CPython e IronPython 3.
"""


def chave_natural(texto):
    """Chave de ordenacao natural para `sorted(lista, key=chave_natural)`.

    Nao diferencia maiusculas de minusculas. Devolve uma tupla de pares
    (tipo, valor) para que numero e texto nunca sejam comparados entre si
    (comparar int com str e TypeError no Python 3).

    Args:
        texto: valor a ordenar (convertido para str; None vira '').

    Returns:
        tuple: chave comparavel.
    """
    if texto is None:
        return ()
    bruto = u'{}'.format(texto).strip().lower()

    partes = []
    digitos = []
    letras = []

    def fechar_letras():
        if letras:
            partes.append((1, u''.join(letras)))
            del letras[:]

    def fechar_digitos():
        if digitos:
            partes.append((0, int(u''.join(digitos))))
            del digitos[:]

    for char in bruto:
        if char.isdigit():
            fechar_letras()
            digitos.append(char)
        else:
            fechar_digitos()
            letras.append(char)

    fechar_digitos()
    fechar_letras()
    return tuple(partes)


def ordenar_natural(valores):
    """Devolve uma NOVA lista ordenada naturalmente."""
    return sorted(valores, key=chave_natural)
