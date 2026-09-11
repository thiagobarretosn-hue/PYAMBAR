# -*- coding: utf-8 -*-
# Paleta de Parametros — este arquivo so DISPARA.
#
# O codigo da paleta mora em `paleta_janela.py` e roda como modulo
# (`Snippets._janela_modeless`). Uma janela modeless definida no script.py
# perde os globais quando o pyRevit limpa o escopo do botao — o que acontece
# sempre que esta ferramenta nao e a primeira do lab rodada depois do Reload.
# Ver [[api-pyrevit-motor]]. Corrigido em 11/09/2026 (v5.6.1); o historico
# de versoes esta no cabecalho do `paleta_janela.py` e no CHANGELOG.md.
__title__ = "Paleta de\nParametros"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "5.6.1"

import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_LIB = os.path.normpath(os.path.join(_AQUI, '..', '..', '..', 'lib'))
if _LIB not in sys.path:
    sys.path.append(_LIB)

from Snippets._janela_modeless import rodar_como_modulo

if __name__ == '__main__':
    rodar_como_modulo(os.path.join(_AQUI, 'paleta_janela.py'),
                      'PYAMBAR_ParameterPalette', globals())
