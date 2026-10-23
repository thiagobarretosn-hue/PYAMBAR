# -*- coding: utf-8 -*-
"""
Tag Slab Passes — a Tags Organizadas com o template Slab Passes, num menu
curto: so o TIPO de tag de cada elemento, a seta e Executar.

Codigo comum com a Tag Installation Plans e a Tag Wall FAC:
TagsOrganizadas.pushbutton/menu_template.py. Regras do template (CIQ nivel 2,
06-09/10/2026): tag perto do elemento, chamada a 90/45, pente de Smurfs nos
conduites, passes, caixas e stubs.

VERSAO: 1.0 (23/10/2026)
AUTOR: Thiago Barreto Sobral Nunes
"""
__title__ = "Tag\nSlab Passes"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "1.0"

import os
import sys

from Autodesk.Revit.DB import ViewPlan

from pyrevit import revit

PASTA_TAGS = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'TagsOrganizadas.pushbutton'))
if PASTA_TAGS not in sys.path:
    sys.path.insert(0, PASTA_TAGS)
sys.modules.pop('menu_template', None)      # reler do disco a cada clique
import menu_template  # noqa: E402

BOTAO = menu_template.Botao(u'Tag Slab Passes', 'TagSlabPasses')


def main():
    menu_template.rodar(BOTAO, revit.doc, u'Slab Passes',
                        lambda v: isinstance(v, ViewPlan), u'Abra uma planta para etiquetar.', globals())


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        BOTAO.falhou(e)
