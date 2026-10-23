# -*- coding: utf-8 -*-
"""Registro das categorias que a Tags Organizadas sabe etiquetar.

Para ensinar uma categoria nova (tubos, conexoes, acessorios...), acrescente
UMA entrada aqui — a janela monta a linha sozinha. Combinado com o Thiago
(08/10/2026): categorias entram aos poucos, cada uma estudada antes.

Campos:
  chave        identificador interno (vai para o config.json)
  rotulo       o que aparece na janela
  descricao    linha de apoio embaixo do rotulo
  bic          categoria do elemento
  tag_bic      categoria da tag
  modo         'ponto'  -> uma tag por elemento (passe, caixa, stub, conexao)
               'linear' -> tags ao longo do trecho, a cada X pes (conduite)
               'tubo'   -> tubulacao: corte = cada tubo reto visivel; planta =
                           um por trecho entre tes (coleta.alvos_tubos)
  ativo_padrao marcada na janela quando nao ha config salvo (padrao True)
  partes       (ponto) PartType aceitos — 'partes_planta' vale em planta
  excluir_familia  (ponto) trechos do nome que excluem (minusculas)
  filtro       trecho do nome 'Familia : Tipo' que o elemento precisa ter
               (minusculas); None = todos
  tipo_padrao  'Familia : Tipo' da tag sugerida (bancada do CIQ)
  unir         padrao da coluna "Unir": pontual = tags de texto 100% igual numa
               tag so; linear = uma tag por feixe de paralelos
  lado_livre   (ponto) a tag prefere o lado oposto ao conduite/tubo que chega
               no elemento (stub: ponta de conduite)
  lado_fraco   (margem) o lado do sistema e preferencia mais fraca: vai para o
               outro lado quando la e mais perto
  x_pes        (linear) uma tag a cada X pes, alem da primeira
  bic_conexao  (linear) categoria das conexoes que emendam os retos num trecho
"""
from Autodesk.Revit.DB import BuiltInCategory

CATEGORIAS = [
    {
        'chave': 'passe',
        'rotulo': u'Passes',
        'descricao': u'Acessórios de tubo — sleeves de laje (peça aninhada não ganha tag própria)',
        'bic': BuiltInCategory.OST_PipeAccessory,
        'tag_bic': BuiltInCategory.OST_PipeAccessoryTags,
        'modo': 'ponto',
        'filtro': None,
        'tipo_padrao': u'Ambar_US_Tag_Pipe_Acessory : Tag Pipe Fittings',
        'unir': True,
    },
    {
        'chave': 'caixa',
        'rotulo': u'Caixas',
        'descricao': u'Dispositivos elétricos — slab box, floor box',
        'bic': BuiltInCategory.OST_ElectricalFixtures,
        'tag_bic': BuiltInCategory.OST_ElectricalFixtureTags,
        'modo': 'ponto',
        'filtro': None,
        'tipo_padrao': u'Ambar_Tag_FP_Electrical_Fixtures_A2 : Description and Comments',
        'unir': True,
    },
    {
        'chave': 'stub',
        'rotulo': u'Stubs',
        'descricao': u'Conexões de conduíte cuja família tem "stub" no nome',
        'bic': BuiltInCategory.OST_ConduitFitting,
        'tag_bic': BuiltInCategory.OST_ConduitFittingTags,
        'modo': 'ponto',
        'filtro': u'stub',
        'tipo_padrao': u'Ambar_Tag_FP_Conduit_Fitting_A2 : Type Name, Comments e Mark',
        # unidos em RAMIFICACOES ortogonais (ajuste manual do Thiago, 08/10/2026);
        # o leque de cotovelo comum ficava confuso no aglomerado de stubs
        'unir': True,
        # tag preferencialmente ALEM da ponta, do lado oposto ao conduite
        'lado_livre': True,
    },
    {
        'chave': 'conduite',
        'rotulo': u'Conduítes',
        'descricao': u'Smurfs e demais conduítes — no mínimo uma tag por trecho',
        'bic': BuiltInCategory.OST_Conduit,
        'tag_bic': BuiltInCategory.OST_ConduitTags,
        'modo': 'linear',
        'filtro': None,
        'tipo_padrao': u'AmbarUS_Tag_Conduit : Tag completa',
        'unir': True,          # no linear, "unir" = uma tag por feixe de paralelos
        'x_pes': 25.0,
        'bic_conexao': BuiltInCategory.OST_ConduitFitting,   # liga os retos num trecho
    },
    # ---- installation plans (MOTION, 08/10/2026) — estilo Margem nos cortes
    {
        'chave': 'tubo',
        'rotulo': u'Tubos',
        'descricao': u'Tubulação — corte: todo tubo reto visível; planta: um por trecho entre tês',
        'bic': BuiltInCategory.OST_PipeCurves,
        'tag_bic': BuiltInCategory.OST_PipeTags,
        'modo': 'tubo',
        'ativo_padrao': False,
        'filtro': None,
        'tipo_padrao': u'Ambar_US_Tag_Pipe_Segment(06.17) : PIPE - Desc/Size/Segment - ( 4mm)',
        'unir': False,
        # comprimento VISIVEL minimo no papel: tubo perpendicular a vista vira
        # ponto e nao ganha tag (corte 07: os 2 que viram ponto ficaram sem)
        'comp_min_mm': 1.0,
        # no F10 o projeto poe 31% das tags de tubo do lado oposto ao sistema
        # quando la ha espaco (Blue a esquerda com a esquerda vazia) — "a
        # inversao resolve muitas organizacoes" (Thiago, 10/10/2026)
        'lado_fraco': True,
    },
    {
        'chave': 'conexao_tubo',
        'ativo_padrao': False,
        'rotulo': u'Conexões de tubo',
        'descricao': u'Tê, cotovelo e plug (ProPEX); curva "Bend" e anel ficam de fora',
        'bic': BuiltInCategory.OST_PipeFitting,
        'tag_bic': BuiltInCategory.OST_PipeFittingTags,
        'modo': 'ponto',
        'filtro': None,
        # medido nos 6 cortes do MOTION: tag em 100% dos Tee/Cap/Elbow ProPEX,
        # em 0% das curvas "Bend-Uponor-AquaPEX" (PartType Elbow) e dos anéis
        'partes': ('Tee', 'Cap', 'Elbow'),
        'partes_planta': ('Tee',),
        'excluir_familia': (u'bend',),
        'tipo_padrao': u'Ambar_US_Tag_Pipe_Fittings(06.17) : Tag Pipe Fittings (4,0mm-TPY 1)',
        'unir': True,
        # margem: o lado do sistema pesa menos que no tubo (manuais do MOTION:
        # tubo 19/19, conexao 13/16 — Pex Plug na ponta oposta fica do lado
        # mais perto, DEM 98, 09/10/2026)
        'lado_fraco': True,
    },
    {
        'chave': 'peca_sanitaria',
        'ativo_padrao': False,
        'rotulo': u'Peças hidrossanitárias',
        'descricao': u'Caixas de ligação (ice maker, máquina de lavar) e demais peças',
        'bic': BuiltInCategory.OST_PlumbingFixtures,
        'tag_bic': BuiltInCategory.OST_PlumbingFixtureTags,
        'modo': 'ponto',
        'filtro': None,
        # DEM 104 do MOTION (09/10/2026): Fire Rated Supply Box com esta tag
        'tipo_padrao': u'Ambar_US_Tag_Plumbing_Fixtures : Tag Plumbing Fixtures',
        'unir': True,
        'lado_fraco': True,
    },
    # ---- installation plans em PLANTA (PH3 UNIT B5, 23/10/2026)
    {
        'chave': 'parede',
        'ativo_padrao': False,
        'rotulo': u'Paredes',
        'descricao': u'Paredes WALL_ com descida de tubo — o número é o "Stage" da parede',
        'bic': BuiltInCategory.OST_Walls,
        'tag_bic': BuiltInCategory.OST_WallTags,
        'modo': 'ponto',
        'coletor': 'paredes_com_descida',
        'prefixo_tipo': u'wall_',
        'filtro': None,
        'tipo_padrao': u'Identificador de parede : 12mm',
        'unir': False,
    },
]


def por_chave(chave):
    for c in CATEGORIAS:
        if c['chave'] == chave:
            return c
    return None
