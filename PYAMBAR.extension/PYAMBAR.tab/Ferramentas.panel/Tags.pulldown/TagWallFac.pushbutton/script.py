# -*- coding: utf-8 -*-
"""
Tag Wall FAC — a Tags Organizadas com o template Cortes Water Supply, num
menu curto: so o TIPO de tag de cada elemento e Executar.

Codigo comum com a Tag Installation Plans:
TagsOrganizadas.pushbutton/menu_template.py. Regras do template (MOTION
cortes 04/07/DEM e F10, 08-09/10/2026): texto fora do desenho, agua quente a
esquerda e fria a direita, chamada a 90 graus (60 so quando a reta cortaria
um tubo), texto igual unido em ramos.

VERSAO: 1.0 (23/10/2026)
AUTOR: Thiago Barreto Sobral Nunes
"""
__title__ = "Tag\nWall FAC"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "1.0"

import os
import sys

from Autodesk.Revit.DB import ViewSection

from pyrevit import revit

PASTA_TAGS = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'TagsOrganizadas.pushbutton'))
if PASTA_TAGS not in sys.path:
    sys.path.insert(0, PASTA_TAGS)
sys.modules.pop('menu_template', None)      # reler do disco a cada clique
import menu_template  # noqa: E402

BOTAO = menu_template.Botao(u'Tag Wall FAC', 'TagWallFac')


def main():
    menu_template.rodar(BOTAO, revit.doc, u'Cortes Water Supply',
                        lambda v: isinstance(v, ViewSection), u'Abra um corte ou elevação para etiquetar.',
                        globals(), rotulos={'passe': u'Acessórios de tubo'})


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        BOTAO.falhou(e)
