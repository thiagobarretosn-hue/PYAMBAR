# -*- coding: utf-8 -*-
"""O LOG da obra no disco: a pasta `DAT\\LOG` do projeto.

Só caminho e arquivo — a regra está em `Snippets._log_ocorrencias` (puro,
testado). Substitui o transporte por web app do Apps Script do
LogOcorrencias: abrir a janela era duas chamadas HTTP síncronas, agora é
listar uma pasta.

ONDE (decisão do Thiago, 24/09/2026)
-----------------------------------
    <pasta do CENTRAL>\\DAT\\LOG\\<id>.json      uma ocorrência por arquivo
    <pasta do CENTRAL>\\DAT\\LOG\\img\\<id>.jpg   o recorte de tela
    <pasta do CENTRAL>\\DAT\\LOG\\equipe.json     a lista que se completa

Todos os modelos da obra (de todos os trades) vivem no mesmo `03-MODELING`,
então a pasta do central dá a MESMA DAT para todo mundo. Sem modelo salvo,
cai no APPDATA e vira um log só seu — melhor que perder o recado.

UM ARQUIVO POR OCORRÊNCIA
-------------------------
Duas pessoas escrevendo ao mesmo tempo não disputam o mesmo arquivo.
`gravar` ainda relê o arquivo e mescla antes de escrever (`mesclar` une as
mensagens por id), porque duas respostas na MESMA ocorrência acontecem.
Troca atômica com `File.Move(.., True)` — `os.replace` não existe no
IronPython ([[ironpython-os-replace-nao-existe]]).
"""
import codecs
import json
import os

from System.IO import File

from Snippets._log_equipe import (
    caminho_global as caminho_global_da_equipe,
    esta_cadastrado,
    mesclar as mesclar_equipe,
    nome_de,
    registrar,
)
from Snippets._log_ocorrencias import (
    arquivo_do_item,
    mesclar,
    normalizar,
)

PASTA_DAT = 'DAT'
PASTA_LOG = 'LOG'
PASTA_IMG = 'img'
EQUIPE = 'equipe.json'
_APPDATA = os.path.join(os.getenv('APPDATA', ''), 'pyRevit', 'PYAMBAR',
                        'Interferencias')
_VISTOS = os.path.join(_APPDATA, 'log_vistos.json')
#: cópia local da equipe: abre rápido e sobrevive ao servidor fora do ar
_CACHE_EQUIPE = os.path.join(_APPDATA, EQUIPE)


# ------------------------------------------------------------------ caminhos

def pasta_do_log(caminho_do_modelo):
    """`<pasta do central>\\DAT\\LOG` — a pasta da OBRA, não do modelo."""
    pasta = os.path.dirname(caminho_do_modelo or '')
    if not pasta or not os.path.isdir(pasta):
        return os.path.join(_APPDATA, PASTA_LOG)
    return os.path.join(pasta, PASTA_DAT, PASTA_LOG)


def pasta_das_imagens(pasta):
    return os.path.join(pasta, PASTA_IMG)


def caminho_da_imagem(pasta, nome):
    return os.path.join(pasta_das_imagens(pasta), nome) if nome else ''


def garantir_imagens(pasta):
    """A pasta das imagens, criada — o recorte grava aqui, não no Drive."""
    return _garantir(pasta_das_imagens(pasta))


def _garantir(pasta):
    if pasta and not os.path.isdir(pasta):
        os.makedirs(pasta)
    return pasta


# -------------------------------------------------------------------- json

def _ler_json(caminho):
    with codecs.open(caminho, 'r', encoding='utf-8') as arquivo:
        return json.load(arquivo)


def _gravar_json(caminho, dados):
    _garantir(os.path.dirname(caminho))
    temporario = caminho + '.tmp'
    with codecs.open(temporario, 'w', encoding='utf-8') as arquivo:
        json.dump(dados, arquivo, indent=1, ensure_ascii=False,
                  sort_keys=True)
    File.Move(temporario, caminho, True)


# ------------------------------------------------------------------ leitura

def ler(pasta):
    """(itens, avisos). Arquivo ilegível não derruba a lista: entra no aviso
    e os outros seguem — o LogOcorrencias ensinou isso com a fila."""
    itens, avisos = [], []
    if not os.path.isdir(pasta):
        return itens, avisos
    for nome in sorted(os.listdir(pasta)):
        if not nome.lower().endswith('.json') or nome == EQUIPE:
            continue
        caminho = os.path.join(pasta, nome)
        try:
            item = normalizar(_ler_json(caminho))
        except Exception as erro:
            avisos.append(u'{}: {}'.format(nome, erro))
            continue
        if item is None:
            avisos.append(u'{}: não parece uma ocorrência'.format(nome))
            continue
        itens.append(item)
    return itens, avisos


def ler_um(pasta, id_):
    """UM apontamento pelo id. None se nao existe mais (ou nao da para ler).

    Usado quando o conflito de um relatorio ja gerou apontamento e o
    comentario novo tem de virar RESPOSTA nele (v2.5).
    """
    if not id_:
        return None
    caminho = os.path.join(pasta, u'{}.json'.format(id_))
    if not os.path.exists(caminho):
        return None
    try:
        return normalizar(_ler_json(caminho))
    except Exception as erro:
        print(u'LOG: apontamento {} ilegivel ({})'.format(id_, erro))
        return None


def gravar(pasta, item):
    """Relê, mescla e grava. -> (item gravado, erro ou None)."""
    caminho = os.path.join(pasta, arquivo_do_item(item))
    try:
        disco = None
        if os.path.exists(caminho):
            try:
                disco = normalizar(_ler_json(caminho))
            except Exception:
                disco = None    # corrompido: o meu é o que vale
        junto = mesclar(disco, item)
        _gravar_json(caminho, junto)
        return junto, None
    except Exception as erro:
        return item, str(erro)


def apagar(pasta, item):
    """Só o autor apaga, e a janela confirma — aqui é só o arquivo."""
    caminho = os.path.join(pasta, arquivo_do_item(item))
    try:
        if os.path.exists(caminho):
            File.Delete(caminho)
        imagem = caminho_da_imagem(pasta, item.get('imagem'))
        if imagem and os.path.exists(imagem):
            File.Delete(imagem)
        return None
    except Exception as erro:
        return str(erro)


# ------------------------------------------------------------------- equipe
#
# A LISTA É DA EMPRESA, NÃO DA OBRA (Thiago, 24/09/2026)
# ------------------------------------------------------
# > "a equipe hoje fica armazenada na obra mas isso deve ser geral para todas
# >  as obras"
#
# Três lugares, sempre unidos na leitura:
#   GLOBAL  ...\00 - PROCEDURES\01 - BIM\03 - AUTOMATION SOLUTIONS\PYREVIT\
#           achado SUBINDO a partir do modelo — `H:` é a letra do Thiago, na
#           máquina do colega pode ser outra
#   OBRA    a `DAT\LOG` do projeto — o que já existe, e o que sobra quando o
#           servidor da empresa não responde
#   CACHE   %APPDATA% — abrir rápido e funcionar sem rede
#
# Escrever nos três, sempre relendo e mesclando: são vários Revits no mesmo
# arquivo em rede.

def _caminho_global(pasta_log):
    """O equipe.json da empresa. '' quando a pasta não é do servidor."""
    try:
        # a função sobe a partir do ARQUIVO, então entrego o da obra
        return caminho_global_da_equipe(os.path.join(pasta_log, EQUIPE),
                                        os.path.isdir, os.path.join)
    except Exception:
        return ''


def _ler_equipe_de(caminho):
    if not caminho or not os.path.exists(caminho):
        return {}
    try:
        return _ler_json(caminho) or {}
    except Exception:
        return {}


def ler_equipe(pasta):
    """A equipe inteira: global + obra + cache. -> formato v2 (id/nome)."""
    return mesclar_equipe(_ler_equipe_de(_caminho_global(pasta)),
                          _ler_equipe_de(os.path.join(pasta, EQUIPE)),
                          _ler_equipe_de(_CACHE_EQUIPE))


def registrar_pessoa(pasta, ident, nome='', agora=''):
    """Cadastra/atualiza alguém — o ID do Revit cruzado com o nome.

    Grava no global, na obra e no cache; um lugar que falhe (servidor fora,
    pasta só leitura) não impede os outros. -> True se mudou alguma coisa.
    """
    equipe, mudou = registrar(ler_equipe(pasta), ident, nome or ident, agora)
    if not mudou:
        return False
    gravou = False
    for caminho in (_caminho_global(pasta), os.path.join(pasta, EQUIPE),
                    _CACHE_EQUIPE):
        if not caminho:
            continue
        try:
            # relê e mescla: outro Revit pode ter cadastrado alguém agora
            _gravar_json(caminho, mesclar_equipe(_ler_equipe_de(caminho),
                                                 equipe))
            gravou = True
        except Exception:
            continue
    return gravou


def nome_do_usuario(pasta, ident):
    """Como essa pessoa assina — o próprio ID se ainda não se cadastrou."""
    return nome_de(ler_equipe(pasta), ident)


def precisa_se_apresentar(pasta, ident):
    """True na PRIMEIRA vez: ninguém cruzou esse ID com um nome ainda."""
    return not esta_cadastrado(ler_equipe(pasta), ident)


# ------------------------------------------------------------------- vistos

def visto_em(pasta):
    """Quando EU olhei esta obra pela última vez (fica no meu APPDATA)."""
    try:
        return (_ler_json(_VISTOS) or {}).get(_chave(pasta), '')
    except Exception:
        return ''


def marcar_visto(pasta, agora):
    try:
        dados = _ler_json(_VISTOS) if os.path.exists(_VISTOS) else {}
    except Exception:
        dados = {}
    dados[_chave(pasta)] = agora
    try:
        _gravar_json(_VISTOS, dados)
        return None
    except Exception as erro:
        return str(erro)


def _chave(pasta):
    return os.path.normpath(pasta or '').lower()
