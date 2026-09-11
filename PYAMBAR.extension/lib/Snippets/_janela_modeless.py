# -*- coding: utf-8 -*-
"""Roda o codigo de uma janela modeless num MODULO, fora do escopo do botao.

Puro (sys, types, codecs). Criado em 11/09/2026 para as quatro janelas que
tinham o defeito do Fluxo ARN v2.5: DetalheAmbiente, Paleta de Parametros,
SyncFromRoom e ZoneSync.

O DEFEITO
---------
O pyRevit divide UM motor IronPython entre todos os botoes da extensao e, ao
fim de cada execucao, apaga do escopo do comando todo global que nao comeca
com `__` — a menos que o motor em cache seja "persistent", e o config do
cache e o do PRIMEIRO botao rodado depois do Reload, nao o deste
([[api-pyrevit-motor]]). Uma janela modeless definida no script.py fica na
tela com as funcoes apontando para um escopo esvaziado: o primeiro clique da
`NameError`. `__persistentengine__ = True` so protegia quando a ferramenta
era a primeira do lab a rodar — por isso "funcionava".

A CORRECAO
----------
O codigo da janela mora num arquivo irmao do script.py; o script.py so chama
`rodar_como_modulo`. O arquivo e executado num modulo NOVO a cada clique:

  - os globais ficam no dicionario do modulo, que o pyRevit nao toca —
    so o escopo do comando e limpo;
  - cada clique rele o arquivo e reavalia `revit.doc`, exatamente como o
    script.py fazia; nada muda para quem usa;
  - `__name__` e `'__main__'`, entao o `if __name__ == '__main__': main()`
    do arquivo continua valendo;
  - as variaveis `__...__` que o pyRevit poe no escopo do botao
    (`__revit__`, `__shiftclick__`...) sao copiadas para o modulo.

O modulo fica em `sys.modules[chave]` (o ultimo de cada ferramenta), para
depuracao. As funcoes de uma janela antiga seguram o proprio dicionario —
nada o apaga.
"""
import codecs
import sys
import types

#: dunders que pertencem ao modulo novo, nao ao botao
_PROPRIOS = ('__name__', '__file__', '__doc__', '__package__', '__loader__',
             '__spec__', '__cached__')


def rodar_como_modulo(caminho, chave, globais_do_botao=None):
    """Executa `caminho` num modulo novo e devolve o modulo.

    Excecao no arquivo sobe para quem chamou (o script.py): o pyRevit a
    mostra como mostraria antes.
    """
    with codecs.open(caminho, 'r', encoding='utf-8') as arquivo:
        fonte = arquivo.read()
    if fonte.startswith(u'﻿'):
        fonte = fonte[1:]

    modulo = types.ModuleType(chave)
    espaco = modulo.__dict__
    for nome, valor in (globais_do_botao or {}).items():
        if (nome.startswith('__') and nome.endswith('__')
                and nome not in _PROPRIOS):
            espaco[nome] = valor
    espaco['__name__'] = '__main__'
    espaco['__file__'] = caminho

    sys.modules[chave] = modulo
    exec(compile(fonte, caminho, 'exec'), espaco)
    return modulo
