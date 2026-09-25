# -*- coding: utf-8 -*-
"""O disco da ferramenta: o HTML, o registro de status e as preferencias.

REGISTRO AO LADO DO HTML (decisao do Thiago, 16/09/2026)
--------------------------------------------------------
`<relatorio>.status.json` na mesma pasta do relatorio — no drive H: o time
inteiro ve as marcas, e o modelo nao e tocado (sem Transaction, sem dono de
elemento no central).

Duas pessoas gravando: `gravar_registro` RELE o disco, mescla item a item
(`Snippets._interferencia.mesclar`) e so entao grava — num .tmp trocado por
`File.Move(.., True)` ([[ironpython-os-replace-nao-existe]]), para ninguem
ler um JSON pela metade.

PREFERENCIAS em `%APPDATA%\\pyRevit\\PYAMBAR\\Interferencias\\config.json`
(Secao 8 do CLAUDE.md): o ultimo relatorio e o que fazer ao escolher.

v1.5: o relatorio da verificacao de passes (`<modelo> - passes.json`) mora
ao lado do .rvt, com o seu `.status.json` — igual ao HTML.
v1.7: mora em `DAT\\` (pasta do projeto) — `realocar` leva os antigos.
"""
import codecs
import io
import json
import os

from System.IO import File

from Snippets._interferencia import mesclar, registro_vazio

_DIR = os.path.join(os.getenv('APPDATA', ''), 'pyRevit', 'PYAMBAR',
                    'Interferencias')
_CONFIG = os.path.join(_DIR, 'config.json')


def ler_html(caminho):
    """Os bytes do relatorio — a decodificacao e do snippet."""
    with io.open(caminho, 'rb') as arquivo:
        return arquivo.read()


def caminho_do_registro(caminho_html):
    return os.path.splitext(caminho_html)[0] + '.status.json'


def _ler_json(caminho):
    if not os.path.exists(caminho):
        return None
    with codecs.open(caminho, 'r', encoding='utf-8') as arquivo:
        return json.load(arquivo)


def _gravar_json(caminho, dados):
    temporario = caminho + '.tmp'
    with codecs.open(temporario, 'w', encoding='utf-8') as arquivo:
        json.dump(dados, arquivo, indent=1, ensure_ascii=False, sort_keys=True)
    File.Move(temporario, caminho, True)


def ler_registro(caminho_html):
    """(registro, aviso). Arquivo corrompido nao impede de navegar."""
    caminho = caminho_do_registro(caminho_html)
    try:
        dados = _ler_json(caminho)
    except Exception as erro:
        return registro_vazio(), u'não consegui ler {} ({}); começando do ' \
            u'zero — nada será gravado por cima até você marcar algo'.format(
                os.path.basename(caminho), erro)
    if not isinstance(dados, dict) or \
            not isinstance(dados.get('conflitos'), dict):
        return registro_vazio(), ''
    return dados, ''


def gravar_registro(caminho_html, registro):
    """(registro_mesclado, erro). Nao levanta: sem gravar, a lista segue util."""
    caminho = caminho_do_registro(caminho_html)
    try:
        try:
            disco = _ler_json(caminho)
        except Exception:
            disco = None    # corrompido: o da janela e o que vale
        junto = mesclar(disco, registro)
        _gravar_json(caminho, junto)
        return junto, None
    except Exception as erro:
        return registro, str(erro)


SUFIXO_PASSES = u' - passes.json'
PASTA_DAT = 'DAT'


def caminho_relatorio_passes(caminho_do_modelo, titulo=''):
    """`<pasta do modelo>\\DAT\\<modelo> - passes.json`.

    v1.7 (Thiago, 21/09/2026: "o arquivo com as configurações está dentro da
    pasta MODELING, deve ficar em DAT"): a pasta DAT do projeto, a mesma da
    Paleta. O nome vem do CENTRAL — `titulo` do documento local tem o sufixo
    do usuário e cada engenheiro gravaria o seu. Sem modelo salvo: APPDATA.
    """
    pasta = os.path.dirname(caminho_do_modelo or '')
    if not pasta or not os.path.isdir(pasta):
        pasta, nome = _DIR, titulo or 'modelo'
    else:
        pasta = os.path.join(pasta, PASTA_DAT)
        nome = os.path.splitext(os.path.basename(caminho_do_modelo))[0]
    return os.path.join(pasta, nome + SUFIXO_PASSES)


def realocar(caminho):
    """Relatório de passes gravado ao lado do .rvt (v1.5/v1.6) -> DAT.

    Leva junto o `.status.json` (os comentários do time). Se o destino já
    existe, não sobrescreve: devolve o destino e deixa o antigo onde está.
    -> (caminho a usar, aviso ou '').
    """
    if not caminho or not caminho.endswith(SUFIXO_PASSES):
        return caminho, ''
    pasta = os.path.dirname(caminho)
    if os.path.basename(pasta).upper() == PASTA_DAT:
        return caminho, ''
    destino = os.path.join(pasta, PASTA_DAT, os.path.basename(caminho))
    if os.path.exists(destino) or not os.path.exists(caminho):
        return (destino if os.path.exists(destino) else caminho), ''
    try:
        if not os.path.isdir(os.path.dirname(destino)):
            os.makedirs(os.path.dirname(destino))
        File.Move(caminho, destino)
        status = caminho_do_registro(caminho)
        if os.path.exists(status):
            File.Move(status, caminho_do_registro(destino))
        return destino, u'relatório e status movidos para {}'.format(
            os.path.dirname(destino))
    except Exception as erro:
        return caminho, u'não consegui mover para DAT ({}); segue onde ' \
            u'está'.format(erro)


def gravar_relatorio(caminho, dados):
    """Grava o relatorio de uma verificacao propria. Levanta: sem o arquivo
    a janela nao tem o que abrir, e quem chama avisa."""
    pasta = os.path.dirname(caminho)
    if pasta and not os.path.exists(pasta):
        os.makedirs(pasta)
    _gravar_json(caminho, dados)


def preferencias():
    try:
        dados = _ler_json(_CONFIG)
    except Exception:
        dados = None
    return dados if isinstance(dados, dict) else {}


def gravar_preferencias(dados):
    try:
        if not os.path.exists(_DIR):
            os.makedirs(_DIR)
        _gravar_json(_CONFIG, dados)
        return None
    except Exception as erro:
        return str(erro)
