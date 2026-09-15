# -*- coding: utf-8 -*-
# Unit Mapper — este arquivo so DISPARA.
#
# 3.0.1 (14/09/2026): o Unit Mapper 3.0 da distribuicao com a janela NAO MODAL
# (pedido de um usuario). O codigo da janela mora em `um_janela.py` e roda como
# modulo (`Snippets._janela_modeless`): uma janela modeless definida no
# script.py perde os globais quando o pyRevit limpa o escopo do botao.
# Ver [[api-pyrevit-motor]].
__title__ = "Unit\nMapper"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "3.0.2"

import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_LIB = os.path.normpath(os.path.join(_AQUI, '..', '..', '..', 'lib'))
if _LIB not in sys.path:
    sys.path.append(_LIB)

from Snippets._janela_modeless import rodar_como_modulo

if __name__ == '__main__':
    rodar_como_modulo(os.path.join(_AQUI, 'um_janela.py'),
                      'PYAMBAR_UnitMapper', globals())
