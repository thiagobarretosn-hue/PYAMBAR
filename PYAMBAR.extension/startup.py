# -*- coding: utf-8 -*-
"""Roda quando o pyRevit carrega a extensao (abrir o Revit e Reload).

Liga o vigia dos avisos do LOG (v3.2, 05/10/2026): quem foi chamado num
apontamento ve um balao no Revit, em qualquer projeto aberto
([[_vigia_caixa]], [[_caixa_entrada]]).

So chama o modulo: o pyRevit apaga os globais deste script quando ele
termina, e o vigia precisa continuar vivo ([[api-pyrevit-motor]]).
Nada aqui pode impedir o carregamento da extensao: o que acontecer vai
para `startup.log` no APPDATA, nunca para uma janela na cara do usuario.
"""
import io
import os
import sys
import time
import traceback

_LOG = os.path.join(os.getenv('APPDATA', ''), 'pyRevit', 'PYAMBAR',
                    'Interferencias', 'startup.log')


def _anotar(texto):
    try:
        pasta = os.path.dirname(_LOG)
        if not os.path.isdir(pasta):
            os.makedirs(pasta)
        with io.open(_LOG, 'a', encoding='utf-8') as arquivo:
            arquivo.write(u'{} {}\n'.format(time.strftime('%Y-%m-%d %H:%M:%S'),
                                            texto))
    except Exception:
        return


try:
    _EXTENSAO = os.path.dirname(os.path.abspath(__file__))
    _LIB = os.path.join(_EXTENSAO, 'lib')
    if _LIB not in sys.path:
        sys.path.append(_LIB)
    from pyrevit import HOST_APP
    from Snippets import _vigia_caixa

    _ABA = os.path.basename(_EXTENSAO).replace('.extension', '')
    _VIGIA = _vigia_caixa.ligar(HOST_APP.uiapp, [
        'CustomCtrl_%CustomCtrl_%{}%Ferramentas%LOG'.format(_ABA),
        'CustomCtrl_%CustomCtrl_%PYAMBAR%Ferramentas%LOG',
        'CustomCtrl_%CustomCtrl_%PYAMBAR(lab)%Ferramentas%LOG'],
        assumir=True)
    _anotar(u'{}: avisos do LOG {}'.format(
        _ABA, u'vigiando ' + _VIGIA.pasta if _VIGIA is not None
        else u'em espera (o LOG ainda nao abriu numa obra do servidor)'))
except Exception:
    _anotar(u'avisos do LOG nao ligaram:\n' + traceback.format_exc())
