# -*- coding: utf-8 -*-
"""Configuracao da documentacao da aranha — pura, sem Revit.

Pedido do Thiago em 10/09/2026: "uma aba de configuracao que la vai ter ja
pre-estabelecido modelo de vista, o tipo de cota, o tipo de tag, para nao
precisar selecionar".

OS PADROES FORAM MEDIDOS, NAO ESCOLHIDOS
----------------------------------------
No MIIQLUX-SEW-RSR - 2026, em 10/09/2026:

    modelo de vista   ARN TYP                            16 vistas de aranha
    tipo de cota      4.0mm (in)                         93 de 93 cotas
    tipo de tag       PIPE - Desc/Size/Segment - ( 4mm)  96 tags

Quem le: Chamada de Detalhe, Cotar Aranha e Tag Tubos Horizontais, rodando
pelo Fluxo ARN ou soltas — por isso a config nao mora no painel.

O arquivo fica em APPDATA (Secao 8 do CLAUDE.md): a pasta do botao e
sobrescrita a cada atualizacao do lab.
"""
import codecs
import json
import os

MODELO = 'modelo_vista'
COTA = 'tipo_cota'
TAG = 'tipo_tag'
#: 14/09/2026: o nome da planta do nivel que o botao "Planta" abre;
#: `{nivel}` vira o nome do nivel (`Snippets._aranha_vistas`)
PLANTA = 'padrao_planta'
#: 14/09/2026: o modelo de vista que a "ARN 3D" do botao 3D recebe
MODELO_3D = 'modelo_vista_3d'
CHAVES = (MODELO, COTA, TAG, PLANTA, MODELO_3D)

#: Separa familia e tipo no nome da tag, como o Revit mostra na lista.
SEP_TAG = ' : '

PADROES = {
    MODELO: 'ARN TYP',
    COTA: '4.0mm (in)',
    TAG: 'Ambar_US_Tag_Pipe_Segment : PIPE - Desc/Size/Segment - ( 4mm)',
    # medido: a planta de piso tem o nome do nivel (02 - LEVEL 2)
    PLANTA: '{nivel}',
    # pedido do Thiago: "vista 3D deve aplicar o modelo de vista ARN TYP 3D"
    MODELO_3D: 'ARN TYP 3D',
}

#: O modelo que, se faltar no projeto, vem do arquivo semente.
MODELO_DA_SEMENTE = 'ARN TYP'

#: O .rvt com o `ARN TYP` do MIIQLUX: 1:12, Fine, os 4 filtros `Pre Fab`.
#: Mora ao lado da Chamada de Detalhe, que e quem o usa. Copiar o modelo leva
#: os filtros E os dois system types que eles referenciam — os ids sao
#: remapeados na copia (medido em 10/09/2026).
ARQUIVO_SEMENTE = 'ARN_TYP_modelo.rvt'


def caminho_padrao():
    return os.path.join(os.getenv('APPDATA', ''), 'pyRevit', 'PYAMBAR',
                        'ARNFlow', 'config.json')


def mesclar(salvo):
    """Os padroes, cobertos pelo que foi salvo.

    Chave desconhecida e valor que nao e texto sao ignorados. Texto vazio e
    valido e significa "nao usar": no modelo de vista, criar a vista sem
    modelo; na cota e na tag, voltar ao comportamento de antes (o tipo
    corrente do Revit / perguntar).
    """
    config = dict(PADROES)
    for chave in CHAVES:
        valor = (salvo or {}).get(chave)
        if isinstance(valor, str):
            config[chave] = valor.strip()
    return config


def carregar(caminho=None):
    """(config, erro). Sem arquivo e sem erro: os padroes.

    O erro volta em vez de ser engolido: uma config ilegivel que vira padrao
    em silencio faria a ferramenta aplicar outro modelo sem ninguem saber
    por que.
    """
    caminho = caminho or caminho_padrao()
    if not os.path.exists(caminho):
        return dict(PADROES), None
    try:
        with codecs.open(caminho, 'r', encoding='utf-8') as arquivo:
            return mesclar(json.loads(arquivo.read())), None
    except Exception as erro:
        return dict(PADROES), 'config ilegível em {} ({}) — usei os ' \
            'padroes'.format(caminho, erro)


def salvar(config, caminho=None):
    """(ok, erro). Escreve direto: `os.replace` nao existe no IronPython."""
    caminho = caminho or caminho_padrao()
    try:
        pasta = os.path.dirname(caminho)
        if pasta and not os.path.isdir(pasta):
            os.makedirs(pasta)
        with codecs.open(caminho, 'w', encoding='utf-8') as arquivo:
            arquivo.write(json.dumps(mesclar(config), indent=2,
                                     ensure_ascii=False, sort_keys=True))
        return True, None
    except Exception as erro:
        return False, str(erro)


def rotulo_tag(familia, tipo):
    """'Familia : Tipo' — o nome que a lista mostra e que a config guarda."""
    if familia:
        return '{}{}{}'.format(familia, SEP_TAG, tipo)
    return tipo or ''


def casa_tag(familia, tipo, configurado):
    """True se o FamilySymbol (familia, tipo) e o da config.

    A config guarda 'Familia : Tipo' porque o nome do tipo sozinho pode
    repetir entre familias. Sem o separador, compara so o tipo — e o que a
    Tag Tubos Horizontais guardava antes.
    """
    configurado = (configurado or '').strip()
    if not configurado:
        return False
    if SEP_TAG in configurado:
        return configurado == rotulo_tag(familia, tipo)
    return configurado == (tipo or '')
