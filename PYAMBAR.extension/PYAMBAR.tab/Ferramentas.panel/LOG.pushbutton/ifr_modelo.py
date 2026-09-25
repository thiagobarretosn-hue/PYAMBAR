# -*- coding: utf-8 -*-
"""Qual é o .rvt de um documento — o nome que relatórios e LOG usam.

Módulo próprio (v1.8) porque três módulos precisam disto e importar um do
outro faria ciclo (`log_novo` -> `ifr_evento` -> `log_novo`).

Sempre o CENTRAL quando houver: a cópia local tem o sufixo do usuário
(`..._thiag.rvt`) e cada engenheiro gravaria um nome diferente.
"""
from Autodesk.Revit.DB import ModelPathUtils

from Snippets._interferencia import nome_do_arquivo


def caminho_do_modelo(documento):
    try:
        if documento.IsWorkshared:
            return ModelPathUtils.ConvertModelPathToUserVisiblePath(
                documento.GetWorksharingCentralModelPath())
    except Exception as erro:
        print(u'Interferências: sem o caminho do central ({})'.format(erro))
    return documento.PathName or ''


def arquivo_do_modelo(documento):
    """'CIQ-PLB-WATER SUPPLY.rvt' — o nome que os relatórios usam."""
    return nome_do_arquivo(caminho_do_modelo(documento)) or \
        u'{}.rvt'.format(documento.Title)
