# -*- coding: utf-8 -*-
"""Para que serve o passe — o papel do tubo que cruza a laje, sem Revit.

Sem clr/Autodesk: testado em CPython (`dev-tools/tests/test_passes_papel.py`).
Quem coleta os fatos (system type, peca no pe) e o SlabPasses.

O QUE O MODELO MOSTROU (CIQ-PLB-SLAB PASSES, MCP 05/10/2026)
-----------------------------------------------------------
121 tubos cruzam o L2 = 121 passes. Aranha = system type
`10.03.02-KIT ARN Sewer` em 37 de 37. Os outros sinais FALHAM: PHASE (Kits
34, Typical 2, vazio 1), nome do system (`SEWER ...` em 78 dos 137 KIT do
vinculo), ARN Type (preenchido tambem em risers).

O ponto da aranha e a peca no conector de BAIXO do vertical (12 aranhas x 3):
    Closet bend  4"  -> toilet
    P-Trap       2"  -> tub / shower      (o usuario escolhe o nome)
    Elbow        2"  -> vanity / laundry  (Long Turn 9, comum 3)
Nenhum vent cruza a laje dentro da aranha: vent e riser (`10.03.01-Vent Sewer`).

A REGRA DA BITOLA (Thiago, 05/10/2026)
-------------------------------------
    riser   +1 tamanho WPS      aranha  +2 tamanhos WPS
    minimo WPS-1 1/2 (o menor do mercado) — em `_passes_laje.passe_para_tubo`

COMMENTS (Thiago, 05/10/2026): todo passe leva. Riser = `Riser <valor>`, o
valor de um parametro escolhido do tubo (padrao: o system type sem o codigo,
porque o TRADE do vent e SEWER e o confundiria com o esgoto).
"""
import re

RISER = 'riser'
TOILET = 'toilet'
TUB = 'tub'
VANITY = 'vanity'
CONFERIR = 'conferir'          # aranha sem peca reconhecida no pe

PONTOS_DA_ARANHA = (TOILET, TUB, VANITY)

#: tamanhos WPS acima do tubo, por papel
PASSOS = {RISER: 1, TOILET: 2, TUB: 2, VANITY: 2, CONFERIR: 2}

SYSTEM_ARANHA = u'KIT ARN'

NOMES_TUB = (u'Tub', u'Shower')
NOMES_VANITY = (u'Vanity', u'Laundry')
NOME_TOILET = u'Toilet'

#: o que vale para o grupo da janela (uma bitola por grupo)
FAMILIA_RISER = u'Riser'
FAMILIA_ARANHA = u'Aranha'

_CODIGO = re.compile(r'^\s*[\d.]+\s*-\s*')


def eh_aranha(system_type):
    return SYSTEM_ARANHA.lower() in (system_type or u'').lower()


def ponto_pela_peca(familia_no_pe):
    """FamilyName da peca no pe do vertical -> TOILET / TUB / VANITY / None.

    Por substring: o modelo tem duas familias de P-Trap
    (`...-4885` e `...PVC_DWV1`) e dois cotovelos (Long Turn e comum).
    """
    nome = (familia_no_pe or u'').lower().replace(u'-', u'_')
    if u'closet' in nome:
        return TOILET
    if u'p_trap' in nome or u'ptrap' in nome:
        return TUB
    if u'elbow' in nome:
        return VANITY
    return None


def classificar(system_type, familia_no_pe):
    """-> papel. Aranha sem peca reconhecida e CONFERIR, nunca um chute."""
    if not eh_aranha(system_type):
        return RISER
    return ponto_pela_peca(familia_no_pe) or CONFERIR


def familia_do_papel(papel):
    return FAMILIA_RISER if papel == RISER else FAMILIA_ARANHA


def passos_do_papel(papel):
    return PASSOS.get(papel, PASSOS[RISER])


def sem_codigo(system_type):
    """'10.04-Storm Drain' -> 'Storm Drain'; '10.03.01-Vent Sewer' -> 'Vent Sewer'."""
    return _CODIGO.sub(u'', system_type or u'').strip()


def comentario(papel, valor_riser=u'', nome_tub=NOMES_TUB[0],
               nome_vanity=NOMES_VANITY[0]):
    """O texto do Comments do passe. CONFERIR -> None (nao se grava chute)."""
    if papel == RISER:
        valor = (valor_riser or u'').strip()
        return u'Riser {}'.format(valor) if valor else u'Riser'
    if papel == TOILET:
        return NOME_TOILET
    if papel == TUB:
        return nome_tub
    if papel == VANITY:
        return nome_vanity
    return None
