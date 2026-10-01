# -*- coding: utf-8 -*-
"""
LOG
O que está pendente na obra, com lugar no modelo: os apontamentos do time
(pasta DAT/LOG), o relatório de interferência do Revit e a verificação de
passes de laje — na mesma janela, com a mesma navegação.

Este arquivo só DISPARA. A janela modeless mora em `ifr_janela.py`: o motor
do pyRevit apaga os globais do script.py quando ele termina
([[api-pyrevit-motor]]).

VERSAO: 2.0
AUTOR: Thiago Barreto Sobral Nunes
"""
__title__ = "LOG"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "3.1"

import os
import sys

SCRIPT_DIR = os.path.dirname(__file__)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import ifr_janela

if __name__ == '__main__':
    ifr_janela.main(__revit__)
