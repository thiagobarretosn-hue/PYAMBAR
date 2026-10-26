# -*- coding: utf-8 -*-
"""Templates de atuacao da Tags Organizadas — um padrao fixo por tipo de projeto.

Logica pura (sem clr/Autodesk). Um template e o MESMO dicionario que a janela
devolve ('categorias' + 'arranjo'), com nome. Os de fabrica nascem do que foi
medido nas vistas do Thiago; os do usuario ficam em APPDATA e, com o mesmo
nome, substituem o de fabrica.

Combinado com o Thiago (09/10/2026): templates por tipo de projeto (cortes
water supply, slab passes, installation plans, depois 3D e underground),
editaveis — a pessoa etiqueta o que quiser e grava o padrao. Nomes provisorios.
"""
import copy
import io
import json
import os

#: arranjo comum (mm de papel; o que a janela guarda)
_ARRANJO_BASE = {
    'angulos': [90, 45],
    'refazer': False,
    'alcance_mm': 22.0,
    'folga_mm': 0.8,
    'raio_mm': 8.0,
    'max_pente': 8,
    'max_uniao': 12,
    'estilo_uniao': 'ramos',
    'estilo_arranjo': 'perto',
}


def _cat(ativo, unir=True, x_pes=None):
    return {'ativo': ativo, 'tipo': None, 'seta': u'__manter__', 'unir': unir, 'x_pes': x_pes}


FABRICA = {
    # CIQ nivel 2 (06-09/10/2026): tag perto do elemento, 45/90, pente de Smurfs
    u'Slab Passes': {
        'categorias': {
            'passe': _cat(True), 'caixa': _cat(True), 'stub': _cat(True),
            'conduite': _cat(True, x_pes=25.0),
            'tubo': _cat(False, unir=False), 'conexao_tubo': _cat(False),
            'peca_sanitaria': _cat(False),
        },
        'arranjo': dict(_ARRANJO_BASE),
    },
    # MOTION cortes 04/07/DEM (08-09/10/2026): texto fora do desenho, quente a
    # esquerda e fria a direita, todo tubo reto, te/plug/cotovelo ProPEX
    u'Cortes Water Supply': {
        'categorias': {
            'passe': _cat(True), 'caixa': _cat(False), 'stub': _cat(False),
            'conduite': _cat(False, x_pes=25.0),
            'tubo': _cat(True, unir=False), 'conexao_tubo': _cat(True),
            # caixa de ligacao (ice maker) com seta — DEM 104, 09/10/2026
            'peca_sanitaria': _cat(True),
        },
        # F10 (46 cortes): o projeto une texto igual a 9-15 mm, cotovelos na
        # mesma altura (ramos). Raio 15 unia 35 tags; 10 une 13 (projeto: 14)
        'arranjo': dict(_ARRANJO_BASE, estilo_arranjo='margem', angulos=[90, 60],
                        estilo_uniao='ramos', raio_mm=10.0),
    },
    # MOTION planta IP001 (08/10/2026): um tubo por trecho entre tes, so tes —
    # A VALIDAR (regra codada, ainda nao conferida contra a planta dele)
    u'Installation Plans': {
        'categorias': {
            'passe': _cat(False), 'caixa': _cat(False), 'stub': _cat(False),
            'conduite': _cat(False, x_pes=25.0),
            # tag de tubo alinhada sem chamada; conexao segue a tag de sempre.
            # Familia nova corrigida (Thiago, PH3 B8, 26/10/2026;
            # antes 2026 : 1,5 mm, PH3 B5 23/10). A calibracao do texto do
            # arranjo (alinhada_centro_mm) e DESTA familia
            'tubo': dict(_cat(True, unir=False), tipo=u'Ambar_US_Tag_Pipe_Segment 2026- : PIPE - DIAMETRO (1,5 mm)'),
            # te de MESMO texto a ate 10 mm vira uma tag com duas chamadas (o
            # ajuste manual do Thiago associou assim, 23/10/2026)
            'conexao_tubo': dict(_cat(True), tipo=u'Ambar_US_Tag_Pipe_Fittings : Tag Pipe Fittings'),
            # planta: peca, caixa e acessorio ficam na parede — sao dos cortes
            # (Thiago, IP001 7 PAV, 14/10/2026; antes ligado pelo DEM 104)
            'peca_sanitaria': _cat(False),
            # parede WALL_ com descida (PH3 UNIT B5, 23/10/2026)
            'parede': _cat(True, unir=False),
        },
        # so_trama: so recebe tag o que corre na trama (cota dominante dos
        # tubos horizontais +- 300 mm); o que desce nas paredes fica de fora
        # planta (PH3 UNIT B5, 23/10/2026): texto PERTO do tubo; a tag de tubo
        # corre alinhada ao lado dele e so leva chamada onde nao cabe. Chamada a
        # 90 graus primeiro, 45 so no caso especial; texto nunca sobre parede
        # (Thiago, 23/10/2026)
        'arranjo': dict(_ARRANJO_BASE, estilo_arranjo='perto', angulos=[90, 45],
                        estilo_uniao='leque', so_trama=True, trama_tol_mm=300.0,
                        tubo_alinhado=True, evitar_parede=True, folga_linha_mm=0.6,
                        # texto da tag de tubo: o motor calcula pela altura da
                        # letra do tipo escolhido (centro_do_texto, _tag_regras),
                        # igual nos 4 lados, sem o usuario escolher (Thiago,
                        # 26/10/2026). Estes sao so o FALLBACK quando a familia
                        # nao deixa ler o label: tipo 1,5 mm com Coord 0 —
                        # centro 0,825h / 0,775h, distancia 0,95h. O ajuste
                        # manual por lado fica recolhido no menu
                        altura_texto_tubo_mm=1.5, alinhada_centro_mm=1.24, alinhada_centro_v_mm=1.16,
                        alinhada_dist_mm=1.43, par_max_mm=3.0, par_sobre_mm=4.0, fila_max_mm=30.0,
                        respiro_mm=3.0, raio_mm=10.0, polir=True,
                        # chamada correndo DENTRO do tubo some (9840640/642)
                        pesos={'dobra': 1.0, 'dobra45': 4.0, 'chamada_sobre_linha': 30.0}),
        # a janela mostra a nota ao escolher (auditoria 12/10/2026: o usuario
        # nao tinha como saber que este template nao foi conferido)
        'nota': u'A validar: regra ainda não conferida contra a planta do projeto.',
    },
}


def padrao_para(tipo_vista):
    """Template sugerido pelo tipo de vista ('planta', 'corte')."""
    return u'Cortes Water Supply' if tipo_vista == 'corte' else u'Slab Passes'


def ler_usuario(caminho):
    """{nome: template} gravados pelo usuario; arquivo ausente ou ruim = {}."""
    if not caminho or not os.path.exists(caminho):
        return {}
    try:
        with io.open(caminho, 'r', encoding='utf-8') as f:
            dados = json.load(f)
    except (IOError, OSError, ValueError):
        return {}
    if not isinstance(dados, dict):
        return {}
    return dict((n, t) for n, t in dados.items() if valido(t))


def valido(t):
    return (isinstance(t, dict) and isinstance(t.get('categorias'), dict)
            and isinstance(t.get('arranjo'), dict))


def todos(caminho_usuario):
    """Fabrica + usuario (usuario com o mesmo nome substitui o de fabrica)."""
    saida = copy.deepcopy(FABRICA)
    saida.update(copy.deepcopy(ler_usuario(caminho_usuario)))
    return saida


def gravar(caminho_usuario, nome, template):
    """Grava/substitui um template do usuario. Devolve o dict completo gravado."""
    nome = (nome or u'').strip()
    if not nome:
        raise ValueError(u'nome vazio')
    if not valido(template):
        raise ValueError(u'template sem categorias/arranjo')
    dados = ler_usuario(caminho_usuario)
    limpo = copy.deepcopy(template)
    limpo['arranjo'] = dict(limpo['arranjo'], refazer=False)    # nunca grava "apagar"
    dados[nome] = limpo
    pasta = os.path.dirname(caminho_usuario)
    if pasta and not os.path.exists(pasta):
        os.makedirs(pasta)
    with io.open(caminho_usuario, 'w', encoding='utf-8') as f:
        f.write(json.dumps(dados, indent=2, ensure_ascii=False))
    return dados


def apagar(caminho_usuario, nome):
    """Apaga um template do usuario (os de fabrica nao se apagam)."""
    dados = ler_usuario(caminho_usuario)
    if nome in dados:
        del dados[nome]
        with io.open(caminho_usuario, 'w', encoding='utf-8') as f:
            f.write(json.dumps(dados, indent=2, ensure_ascii=False))
        return True
    return False
