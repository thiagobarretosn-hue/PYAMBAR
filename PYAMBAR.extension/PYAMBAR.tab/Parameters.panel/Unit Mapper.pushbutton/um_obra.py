# -*- coding: utf-8 -*-
"""Ida e volta da config DA OBRA com o disco.

A decisao de mesclar e pura e mora em `Snippets._wbs_obra`; aqui so se resolve
a pasta e se le/grava o arquivo.

Onde: `<pasta do modelo>\\DAT\\UnitMapper\\config.json`. Medido em 21/10/2026
(PRINCETON 248 PHASE 3): os modelos da obra — SEWER, WATER SUPPLY, DRAINAGE,
ARQBASE, STR — ficam na MESMA pasta `03-MODELING`, entao um arquivo serve a
obra inteira e todos os engenheiros. E o mesmo `DAT` que o LOG ja usa.

A pasta costuma ser um Drive compartilhado: a gravacao pode falhar por sync ou
permissao. Nenhuma funcao daqui levanta — devolvem (ok, erro) e a janela avisa.
"""
import os

from Snippets import _wbs_obra as obra
from Snippets._wbs_config import escrever_json, ler_json
from Snippets.project._dat_folder_manager import get_dat_folder


def caminho(doc, criar=False):
    """Caminho do config.json da obra, ou None se nao der para determinar.

    Modelo nunca salvo nao tem pasta — nesse caso a janela fica so com o
    APPDATA, como era antes.
    """
    try:
        pasta = get_dat_folder(doc, subfolder=obra.SUBPASTA, create=criar)
    except Exception:
        return None
    if not pasta:
        return None
    return os.path.join(pasta, obra.NOME_ARQUIVO)


def ler(doc):
    """(config da obra, caminho). Config vazia quando nao ha arquivo."""
    alvo = caminho(doc, criar=False)
    if not alvo:
        return obra.vazia(), None
    return obra.normalizar(ler_json(alvo)), alvo


def gravar(doc, base, minha):
    """Mescla com o que esta no disco AGORA e grava.

    Devolve (ok, erro, gravada). `gravada` e o que ficou no arquivo — vira a
    nova base da janela, senao a proxima gravacao acha que o outro mexeu.
    """
    alvo = caminho(doc, criar=True)
    if not alvo:
        return False, u'modelo sem pasta no disco (nunca foi salvo?)', None
    disco = obra.normalizar(ler_json(alvo))
    final = obra.mesclar(base, minha, disco)
    ok, erro = escrever_json(alvo, final)
    if not ok:
        return False, erro, None
    return True, None, final
