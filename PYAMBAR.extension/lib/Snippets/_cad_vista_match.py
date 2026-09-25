# -*- coding: utf-8 -*-
"""Sugere a vista de destino de um CAD pelo nome do arquivo.

Logica pura (sem clr/Autodesk) — testada em dev-tools/tests/test_cad_vista_match.py.
Usada pelo VincularCADs.
"""
import os
import re

_NAO_ALFANUM = re.compile(r'[^0-9a-z]+')


def tokens(texto):
    """'LEVEL-1_Plumbing.dwg' -> ['level', '1', 'plumbing'] (sem extensao)."""
    base = os.path.splitext(texto or '')[0] if (texto or '').lower().endswith('.dwg') else (texto or '')
    return [t for t in _NAO_ALFANUM.split(base.lower()) if t]


def contem_tokens(maior, menor):
    """True se a sequencia `menor` aparece contigua dentro de `maior`.

    Compara token a token, entao 'level 1' NAO esta contido em 'level 10'.
    """
    if not menor or len(menor) > len(maior):
        return False
    n = len(menor)
    for i in range(len(maior) - n + 1):
        if maior[i:i + n] == menor:
            return True
    return False


def sugerir_vista(nome_arquivo, nomes_vistas):
    """Indice da vista mais provavel para o arquivo, ou None.

    Ordem: nome igual > nome da vista contido no arquivo (vence a vista de nome
    mais longo) > nome do arquivo contido na vista (vence a de nome mais curto).
    Empate no mesmo criterio = ambiguo = None (o usuario escolhe).
    """
    alvo = tokens(nome_arquivo)
    if not alvo:
        return None

    candidatos = [tokens(n) for n in nomes_vistas]

    iguais = [i for i, c in enumerate(candidatos) if c and c == alvo]
    if len(iguais) == 1:
        return iguais[0]
    if iguais:
        return None

    vista_no_arquivo = [i for i, c in enumerate(candidatos) if contem_tokens(alvo, c)]
    if vista_no_arquivo:
        maior = max(len(candidatos[i]) for i in vista_no_arquivo)
        melhores = [i for i in vista_no_arquivo if len(candidatos[i]) == maior]
        return melhores[0] if len(melhores) == 1 else None

    arquivo_na_vista = [i for i, c in enumerate(candidatos) if contem_tokens(c, alvo)]
    if arquivo_na_vista:
        menor = min(len(candidatos[i]) for i in arquivo_na_vista)
        melhores = [i for i in arquivo_na_vista if len(candidatos[i]) == menor]
        return melhores[0] if len(melhores) == 1 else None

    return None
