# -*- coding: utf-8 -*-
"""
Tag Installation Plans — a Tags Organizadas com o template Installation Plans,
num menu curto: so o TIPO de tag de cada elemento e Executar.

Codigo comum com a Tag Wall FAC: TagsOrganizadas.pushbutton/menu_template.py.
Regras do template (PH3 UNIT B5, 23/10/2026): tag de tubo alinhada so na
trama, conexao com chamada (te igual a ate 10 mm vira uma tag), parede com
descida; texto a 1,4 mm do eixo, par quente/frio na mesma estacao, filas
alinhadas, respiro de 3 mm entre conexao e texto de tubo.

VERSAO: 1.0 (23/10/2026)
AUTOR: Thiago Barreto Sobral Nunes
"""
__title__ = "Tag\nInstallation Plans"
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

BOTAO = menu_template.Botao(u'Tag Installation Plans', 'TagInstallationPlans')


def main():
    menu_template.rodar(BOTAO, revit.doc, u'Installation Plans',
                        lambda v: isinstance(v, ViewPlan), u'Abra uma planta para etiquetar.', globals(),
                        texto_refazer=u'Apagar e refazer as tags que o botão coloca '
                                      u'(as de elementos da parede ficam)')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        BOTAO.falhou(e)
