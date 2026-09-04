# -*- coding: utf-8 -*-
"""
_mep_fill_gap.py — cria o TUBO que falta entre duas vias livres alinhadas.

Pedido do usuario (02/09/2026): "quando nao tiver tubo crie o tubo para
permitir criar as conecçoes; isso vale para conexao para conexao".

O buraco que isto tapa: as fases existentes so sabem mexer em tubo. A Fase 1
conecta conectores a menos de 1"; a Fase 2 ESTICA um tubo ate um conector
livre. Quando as duas pontas sao FITTINGS, nao ha tubo para esticar e o par
nunca era visto — o caso saia como "nada a conectar" mesmo estando a peca a
um palmo da outra, perfeitamente alinhada.

Aqui a peca que nasce e o proprio tubo, entre as duas origens:

    fitting A  |>-----------------<|  fitting B
               ^                   ^
               ca.Origin           cb.Origin

Condicoes (todas medidas, e o motivo volta quando falha):

  - conectores frente a frente (~180 graus)
  - alinhados: o desvio lateral do eixo cabe em PERP_TOL
  - mesmo diametro
  - vao entre MIN_VAO e MAX_VAO — abaixo do minimo o caso e da Fase 1
    (puxar), nao de criar tubo
  - pelo menos um lado e FITTING: com dois tubos a Fase 2 ja resolve
    esticando, e criar tubo no meio deixaria emenda a mais

REQUER Transaction ativa. Cada tentativa roda em SubTransaction: se o
Revit recusar a criacao ou a ligacao, nada sobra pela metade.
"""

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    BuiltInParameter, LocationCurve, SubTransaction
)
from Autodesk.Revit.DB.Plumbing import Pipe

from pyrevit import revit
from pyrevit.compat import get_elementid_value_func as _get_func
from Snippets._mep_common import conn_at as _conn_at
from Snippets._mep_common import system_type_id as _tipo_de_sistema

get_id_val = _get_func()

FACING_TOL = 10.0        # graus de folga em torno de 180
PERP_TOL = 0.02          # ft (6 mm) — desvio lateral tolerado
MIN_VAO = 1.0 / 12.0     # ft (25 mm) — abaixo disso e caso de PUXAR (Fase 1),
                         # e o tubo que nasceria seria uma emenda inutil
MAX_VAO = 10.0           # ft — mesmo alcance da Fase 2; alem disso nao e um
                         # vao, sao redes diferentes
DIAM_TOL = 0.01          # ft


def _conectores(elem):
    try:
        if isinstance(elem, Pipe):
            return list(elem.ConnectorManager.Connectors)
        return list(elem.MEPModel.ConnectorManager.Connectors)
    except Exception:
        return []


def _e_tubo(elem):
    return isinstance(elem, Pipe)


def _molde(elem):
    """(PipeType, ReferenceLevel, diametro) para o tubo novo.

    Um fitting nao tem PipeType. O molde vem do proprio elemento quando ele e
    tubo; se nao for, de um tubo ja ligado a ele — que e o tubo com que a
    peca foi montada, e portanto o tipo certo. Sem molde nao se inventa: a
    fase recusa e diz por que.
    """
    if _e_tubo(elem):
        return elem.PipeType, elem.ReferenceLevel, elem.Diameter
    for conn in _conectores(elem):
        try:
            for ref in conn.AllRefs:
                dono = ref.Owner
                if dono is None or not _e_tubo(dono):
                    continue
                if not dono.IsValidObject:
                    continue
                return dono.PipeType, dono.ReferenceLevel, dono.Diameter
        except Exception:
            continue
    return None, None, None


def find_gap_pairs(elements, in_scope=None):
    """Pares de vias livres que so precisam de um tubo. (pares, recusas)."""
    livres = []
    for elem in elements:
        try:
            if not elem.IsValidObject:
                continue
        except Exception:
            continue
        if in_scope is not None and not in_scope(elem):
            continue
        for conn in _conectores(elem):
            try:
                if conn.IsConnected:
                    continue
            except Exception:
                continue
            livres.append((elem, conn))

    pares, recusas, usados = [], [], set()
    for i, (ea, ca) in enumerate(livres):
        for j, (eb, cb) in enumerate(livres):
            if j <= i or ea.Id == eb.Id:
                continue
            if i in usados or j in usados:
                continue
            # dois tubos: a Fase 2 estica um ate o outro, sem emenda a mais
            if _e_tubo(ea) and _e_tubo(eb):
                continue
            try:
                if abs(ca.Radius - cb.Radius) > DIAM_TOL:
                    continue
                da = ca.CoordinateSystem.BasisZ
                db = cb.CoordinateSystem.BasisZ
                v = cb.Origin - ca.Origin
            except Exception:
                continue

            vao = v.GetLength()
            if vao < MIN_VAO or vao > MAX_VAO:
                continue
            ang = da.AngleTo(db) * 180.0 / 3.141592653589793
            if abs(ang - 180.0) > FACING_TOL:
                continue
            t = v.DotProduct(da)
            if t <= 0:
                continue                  # o alvo esta ATRAS da via livre
            perp = (v - da.Multiply(t)).GetLength()
            if perp > PERP_TOL:
                recusas.append((get_id_val(ea.Id),
                                "tubo faltando ate {}: fora do eixo por "
                                "{:.4f} ft ({:.1f} mm), limite {:.1f} mm"
                                .format(get_id_val(eb.Id), perp, perp * 304.8,
                                        PERP_TOL * 304.8)))
                continue

            tipo, nivel, diam = _molde(ea)
            if tipo is None:
                tipo, nivel, diam = _molde(eb)
            if tipo is None:
                recusas.append((get_id_val(ea.Id),
                                "tubo faltando ate {}: nenhum dos dois lados "
                                "tem tubo de onde herdar o tipo"
                                .format(get_id_val(eb.Id))))
                continue

            usados.add(i)
            usados.add(j)
            pares.append({'elem_a': ea, 'conn_a': ca,
                          'elem_b': eb, 'conn_b': cb,
                          'vao': vao, 'tipo': tipo, 'nivel': nivel,
                          'diam': diam if diam else ca.Radius * 2.0})
    return pares, recusas


def create_gap_pipe(par):
    """Cria e liga o tubo do vao. Retorna (tubo, motivo)."""
    doc = revit.doc
    ea, ca = par['elem_a'], par['conn_a']
    eb, cb = par['elem_b'], par['conn_b']
    p1, p2 = ca.Origin, cb.Origin

    sub = SubTransaction(doc)
    sub.Start()
    try:
        molde = ea if _e_tubo(ea) else (eb if _e_tubo(eb) else None)
        sistema = _tipo_de_sistema(molde if molde is not None else ea, doc)
        novo = Pipe.Create(doc, sistema, par['tipo'].Id, par['nivel'].Id,
                           p1, p2)
        try:
            novo.get_Parameter(
                BuiltInParameter.RBS_PIPE_DIAMETER_PARAM).Set(par['diam'])
        except Exception:
            pass
        doc.Regenerate()

        c1 = _conn_at(novo, p1)
        c2 = _conn_at(novo, p2)
        if not (c1 and c2):
            raise Exception("tubo novo sem conectores nas pontas")
        ca.ConnectTo(c1)
        cb.ConnectTo(c2)
        doc.Regenerate()
        sub.Commit()
        return novo, ""
    except Exception as erro:
        sub.RollBack()
        return None, (str(erro) or erro.__class__.__name__)


def fill_pass(elements, in_scope=None):
    """Cria todos os tubos faltantes. (elementos, n_tubos, recusas)."""
    pares, recusas = find_gap_pairs(elements, in_scope)
    resultado = list(elements)
    feitos = 0
    for par in pares:
        try:
            if not (par['elem_a'].IsValidObject and par['elem_b'].IsValidObject):
                continue
        except Exception:
            continue
        novo, motivo = create_gap_pipe(par)
        if novo is None:
            recusas.append((get_id_val(par['elem_a'].Id),
                            "tubo faltando ate {}: {}".format(
                                get_id_val(par['elem_b'].Id), motivo)))
            continue
        resultado.append(novo)
        feitos += 1
    return resultado, feitos, recusas


# ---------------------------------------------------------------------------
# Modo TOCO: uma via livre de fitting que precisa virar ramal
# ---------------------------------------------------------------------------
#
# Caso real (banca de test, 02/09/2026): o te 10815230 com a via de cima
# livre (D=76, rumo +Z) precisa alcancar a prumada D=102 que passa 0.995 ft
# ao lado. A derivacao (fase 0e) sabe montar isso — mas exige um RAMAL, e
# ramal, para ela, e um TUBO. Com so o fitting ali, o par nunca aparecia.
#
# Aqui nasce o toco: um tubo curto saindo da via livre, no rumo dela. A
# derivacao roda logo depois e o encontra como ramal. O toco e deliberadamente
# curto — quem decide o comprimento final e a derivacao, que leva a ponta
# livre ate o ponto de entrada calculado.
#
# Toco que sobra sem ligar e LIXO no modelo, pior que nao ter feito nada: os
# ids criados voltam em `criados` para que connect_batch remova os que
# terminarem a execucao ainda com ponta livre.

STUB_MIN = 0.35          # ft — toco menor que isto nao sobrevive ao ajuste
STUB_MAX_OFFSET = 4.0    # ft — mesmo limite da derivacao (MAX_OFFSET)
STUB_MIN_OFFSET = 1.0 / 12.0
PARALELO_DOT = 0.999
FATOR_TRONCO = 2.0       # o tronco tem de ser bem maior que o ramal


def find_stub_targets(elements, in_scope=None):
    """Vias livres de fitting que viram ramal de uma derivacao.

    Devolve (alvos, recusas). Cada alvo traz o tronco medido e o comprimento
    do toco a criar.
    """
    tubos, fittings = [], []
    for elem in elements:
        try:
            if not elem.IsValidObject:
                continue
        except Exception:
            continue
        if in_scope is not None and not in_scope(elem):
            continue
        (tubos if _e_tubo(elem) else fittings).append(elem)

    alvos, recusas = [], []
    for fit in fittings:
        for conn in _conectores(fit):
            try:
                if conn.IsConnected:
                    continue
                origem = conn.Origin
                rumo = conn.CoordinateSystem.BasisZ
                raio = conn.Radius
            except Exception:
                continue

            melhor = None
            for tubo in tubos:
                try:
                    curva = tubo.Location.Curve
                    a, b = curva.GetEndPoint(0), curva.GetEndPoint(1)
                    eixo = (b - a).Normalize()
                    comp = curva.Length
                except Exception:
                    continue
                if abs(eixo.DotProduct(rumo)) < PARALELO_DOT:
                    continue

                # distancia lateral entre o eixo do tronco e o do toco
                v = origem - a
                lateral = (v - eixo.Multiply(v.DotProduct(eixo))).GetLength()
                if lateral < STUB_MIN_OFFSET or lateral > STUB_MAX_OFFSET:
                    continue

                # o tronco precisa existir A FRENTE da via livre, senao o
                # toco cresce para o lado errado
                ta = (a - origem).DotProduct(rumo)
                tb = (b - origem).DotProduct(rumo)
                frente = max(ta, tb)
                if frente < STUB_MIN:
                    continue

                if comp < STUB_MIN * FATOR_TRONCO:
                    continue
                if melhor is None or lateral < melhor[0]:
                    melhor = (lateral, tubo, comp, frente)

            if melhor is None:
                continue
            lateral, tronco, comp_t, frente = melhor

            tipo, nivel, _diam = _molde(fit)
            if tipo is None:
                recusas.append((get_id_val(fit.Id),
                                "toco para derivar em {}: nenhum tubo ligado "
                                "de onde herdar o tipo"
                                .format(get_id_val(tronco.Id))))
                continue

            # curto de proposito: a derivacao estica ate o ponto de entrada.
            # Nao pode passar do fim do tronco nem virar "ramal" grande
            # demais para a regra do fator de tronco.
            comprimento = max(STUB_MIN, min(lateral, frente,
                                            comp_t / FATOR_TRONCO))
            if comprimento < STUB_MIN:
                recusas.append((get_id_val(fit.Id),
                                "toco para derivar em {}: so caberia "
                                "{:.0f} mm, minimo {:.0f} mm"
                                .format(get_id_val(tronco.Id),
                                        comprimento * 304.8, STUB_MIN * 304.8)))
                continue

            alvos.append({'fitting': fit, 'conn': conn, 'origem': origem,
                          'rumo': rumo, 'diam': raio * 2.0, 'tipo': tipo,
                          'nivel': nivel, 'tronco': tronco,
                          'lateral': lateral, 'comprimento': comprimento})
    return alvos, recusas


def create_stub(alvo):
    """Cria o toco e o liga ao fitting. Retorna (tubo, motivo)."""
    doc = revit.doc
    p1 = alvo['origem']
    p2 = p1 + alvo['rumo'].Multiply(alvo['comprimento'])

    sub = SubTransaction(doc)
    sub.Start()
    try:
        sistema = _tipo_de_sistema(alvo['tronco'], doc)
        novo = Pipe.Create(doc, sistema, alvo['tipo'].Id, alvo['nivel'].Id,
                           p1, p2)
        try:
            novo.get_Parameter(
                BuiltInParameter.RBS_PIPE_DIAMETER_PARAM).Set(alvo['diam'])
        except Exception:
            pass
        doc.Regenerate()
        c1 = _conn_at(novo, p1)
        if c1 is None:
            raise Exception("toco sem conector na base")
        alvo['conn'].ConnectTo(c1)
        doc.Regenerate()
        sub.Commit()
        return novo, ""
    except Exception as erro:
        sub.RollBack()
        return None, (str(erro) or erro.__class__.__name__)


def stub_pass(elements, in_scope=None):
    """Cria os tocos. (elementos, n_tocos, recusas, ids_criados).

    ``ids_criados`` volta para que connect_batch apague o que a derivacao
    nao aproveitar — toco solto e lixo, pior que nao ter feito nada.
    """
    alvos, recusas = find_stub_targets(elements, in_scope)
    resultado = list(elements)
    feitos, criados = 0, []
    for alvo in alvos:
        try:
            if not alvo['fitting'].IsValidObject:
                continue
        except Exception:
            continue
        novo, motivo = create_stub(alvo)
        if novo is None:
            recusas.append((get_id_val(alvo['fitting'].Id),
                            "toco para derivar em {}: {}".format(
                                get_id_val(alvo['tronco'].Id), motivo)))
            continue
        resultado.append(novo)
        criados.append(get_id_val(novo.Id))
        feitos += 1
    return resultado, feitos, recusas, criados
