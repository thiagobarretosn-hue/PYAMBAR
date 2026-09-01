# -*- coding: utf-8 -*-
"""
_mep_angled_junction.py — junção em ângulo (Wye 45 e afins).

``doc.Create.NewTeeFitting`` recusa ramal que nao chega a 90 graus:

    InvalidOperationException: "Fitting cannot be created between the input
    connectors because the angle between them is too small or too large."

...mesmo quando o Wye ESTA nas routing preferences do tipo. Este modulo faz o
que a API nao oferece: insere a familia de juncao adequada ao angulo, orienta
no espaco, dimensiona e liga os tres tubos.

Receita validada no Revit 2026 (ver docstring de create_angled_junction).
REQUER Transaction ativa.
"""

import math

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    ElementTransformUtils, Line, LocationCurve, LocationPoint, StorageType,
    SubTransaction, XYZ, RoutingPreferenceRuleGroupType
)
from Autodesk.Revit.DB.Plumbing import PlumbingUtils
from Autodesk.Revit.DB.Structure import StructuralType

from pyrevit import revit
from pyrevit.compat import get_elementid_value_func as _get_func

get_id_val = _get_func()

# Tolerancias
# Por que a juncao em angulo nao saiu. Toda a cadeia (find_junction_symbol ->
# branch_angle -> create_angled_junction) engolia excecoes e devolvia None, e
# o chamador so sabia dizer "nem te nem wye serviram para este angulo" —
# culpando o angulo por qualquer causa, inclusive falta de espaco ou familia
# sem parametro de tamanho. Cada recusa agora deixa a razao aqui.
MOTIVOS = []


def _nota(msg):
    MOTIVOS.append(msg)


def limpar_motivos():
    del MOTIVOS[:]


ANGLE_TOL = 0.09          # rad (~5 graus) — casar o angulo do ramal com o da familia
COLLINEAR_DOT = -0.99     # dois conectores do "run" sao opostos
CONNECT_TOL = 0.02        # ft — coincidencia para ConnectTo
END_TOL = 0.06            # ft — reconhecer a ponta do tubo no ponto de juncao
MIN_FORWARD = 0.05        # ft — o conector tem de estar A FRENTE da ponta
                          # fixa. Nao confundir com MIN_STUB do _mep_offset_jog,
                          # que e sobra de tubo: aqui e anti-inversao.

# O angulo do branch e propriedade da familia e nao muda em runtime.
_ANGLE_CACHE = {}


# ---------------------------------------------------------------------------
# Inspecao do simbolo
# ---------------------------------------------------------------------------

def _classify(connectors):
    """(run_a, run_b, branch) a partir dos conectores de uma juncao de 3 vias."""
    cons = list(connectors)
    if len(cons) < 3:
        return None, None, None
    run_a = run_b = None
    for i in range(len(cons)):
        for j in range(i + 1, len(cons)):
            try:
                dot = cons[i].CoordinateSystem.BasisZ.DotProduct(
                    cons[j].CoordinateSystem.BasisZ)
            except Exception:
                continue
            if dot < COLLINEAR_DOT:
                run_a, run_b = cons[i], cons[j]
                break
        if run_a is not None:
            break
    if run_a is None:
        return None, None, None
    branch = None
    for c in cons:
        if c is not run_a and c is not run_b:
            branch = c
            break
    return run_a, run_b, branch


def _downstream(run_a, run_b, branch):
    """O lado do run para onde o branch converge (jusante).

    No Wye o ramal se junta no sentido do fluxo: e o conector do run cujo
    dot com a direcao do branch e positivo.
    """
    try:
        bz = branch.CoordinateSystem.BasisZ
        return run_a if run_a.CoordinateSystem.BasisZ.DotProduct(bz) > 0 else run_b
    except Exception:
        return run_a


def branch_angle(symbol, level_id):
    """Angulo (rad) entre o branch e o jusante do run da familia.

    Mede instanciando de verdade — nao ha como ler isso do simbolo. A
    instancia nasce e morre dentro de uma SubTransaction revertida.
    """
    key = get_id_val(symbol.Id)
    if key in _ANGLE_CACHE:
        return _ANGLE_CACHE[key]

    doc = revit.doc
    ang = None
    sub = SubTransaction(doc)
    sub.Start()
    try:
        if not symbol.IsActive:
            symbol.Activate()
            doc.Regenerate()
        inst = doc.Create.NewFamilyInstance(
            XYZ(0, 0, 0), symbol, StructuralType.NonStructural)
        doc.Regenerate()
        run_a, run_b, branch = _classify(
            inst.MEPModel.ConnectorManager.Connectors)
        if branch is None:
            _nota("'{}' nao tem tres conectores em T (run/run/branch)".format(
                symbol.Family.Name))
        else:
            jus = _downstream(run_a, run_b, branch)
            ang = branch.CoordinateSystem.BasisZ.AngleTo(
                jus.CoordinateSystem.BasisZ)
    except Exception as erro:
        _nota("nao consegui instanciar '{}' para medir: {}".format(
            getattr(symbol.Family, 'Name', '?'), erro))
        ang = None
    sub.RollBack()

    _ANGLE_CACHE[key] = ang
    return ang


def find_junction_symbol(pipe, wanted_angle, level_id):
    """FamilySymbol de junção cujo branch faz ``wanted_angle`` com o run.

    Varre as regras de Junctions das routing preferences do tipo do tubo —
    assim a escolha respeita o que o projeto configurou, sem depender do nome
    da familia. None se nenhuma bate.
    """
    doc = revit.doc
    try:
        rpm = pipe.PipeType.RoutingPreferenceManager
    except Exception as erro:
        _nota("tipo de tubo sem routing preferences: {}".format(erro))
        return None

    melhor, melhor_dif = None, ANGLE_TOL
    try:
        n = rpm.GetNumberOfRules(RoutingPreferenceRuleGroupType.Junctions)
    except Exception as erro:
        _nota("nao consegui ler as regras de juncao: {}".format(erro))
        return None

    vistos = []
    for i in range(n):
        try:
            rule = rpm.GetRule(RoutingPreferenceRuleGroupType.Junctions, i)
            symbol = doc.GetElement(rule.MEPPartId)
        except Exception as erro:
            _nota("regra {} ilegivel: {}".format(i, erro))
            continue
        if symbol is None:
            _nota("regra {} sem familia associada".format(i))
            continue
        ang = branch_angle(symbol, level_id)
        if ang is None:
            _nota("nao consegui medir o angulo de '{}'".format(
                symbol.Family.Name))
            continue
        vistos.append((symbol.Family.Name, math.degrees(ang)))
        dif = abs(ang - wanted_angle)
        if dif < melhor_dif:
            melhor, melhor_dif = symbol, dif
    if melhor is None:
        _nota("nenhuma juncao a {:.1f} graus (tolerancia {:.1f}); "
              "disponiveis: {}".format(
                  math.degrees(wanted_angle), math.degrees(ANGLE_TOL),
                  ", ".join("{}={:.1f}".format(nome, g) for nome, g in vistos)
                  or "nenhuma"))
    return melhor


# ---------------------------------------------------------------------------
# Dimensionamento
# ---------------------------------------------------------------------------

def _set_sizes(inst, d_run, d_branch):
    """Ajusta o tamanho da juncao pelos parametros de instancia.

    Os nomes variam por familia ("Nominal Diameter 01" no P_601, "Nominal
    Radius 1" no Standard), entao casa por padrao e trata raio e diametro.
    Sufixo 3/03 = branch; os demais = run.
    """
    setados = 0
    for param in inst.Parameters:
        try:
            if param.IsReadOnly or param.StorageType != StorageType.Double:
                continue
            nome = param.Definition.Name.lower()
        except Exception:
            continue
        eh_diam = "nominal diameter" in nome
        eh_raio = "nominal radius" in nome
        if not (eh_diam or eh_raio):
            continue
        alvo = d_branch if nome.endswith("3") or nome.endswith("03") else d_run
        try:
            param.Set(alvo / 2.0 if eh_raio else alvo)
            setados += 1
        except Exception:
            pass
    return setados


# ---------------------------------------------------------------------------
# Orientacao
# ---------------------------------------------------------------------------

def _rotate_to(inst, atual, alvo):
    """Rotaciona a instancia levando a direcao ``atual`` ate ``alvo``."""
    doc = revit.doc
    eixo = atual.CrossProduct(alvo)
    ponto = inst.Location.Point
    if eixo.GetLength() > 1e-9:
        ElementTransformUtils.RotateElement(
            doc, inst.Id, Line.CreateBound(ponto, ponto + eixo.Normalize()),
            atual.AngleTo(alvo))
        doc.Regenerate()
        return True
    if atual.DotProduct(alvo) < 0:
        # antiparalelos: girar 180 em torno de qualquer perpendicular
        base = XYZ.BasisZ if abs(atual.Z) < 0.9 else XYZ.BasisX
        perp = atual.CrossProduct(base)
        if perp.GetLength() < 1e-9:
            return False
        ElementTransformUtils.RotateElement(
            doc, inst.Id, Line.CreateBound(ponto, ponto + perp.Normalize()),
            math.pi)
        doc.Regenerate()
    return True


def _spin_around(inst, eixo, atual, alvo):
    """Gira em torno de ``eixo`` ate a projecao de ``atual`` bater com ``alvo``."""
    doc = revit.doc
    a = atual - eixo.Multiply(atual.DotProduct(eixo))
    b = alvo - eixo.Multiply(alvo.DotProduct(eixo))
    if a.GetLength() < 1e-6 or b.GetLength() < 1e-6:
        return False
    a, b = a.Normalize(), b.Normalize()
    cos = max(-1.0, min(1.0, a.DotProduct(b)))
    ang = math.acos(cos)
    if a.CrossProduct(b).DotProduct(eixo) < 0:
        ang = -ang
    if abs(ang) < 1e-6:
        return True
    ponto = inst.Location.Point
    ElementTransformUtils.RotateElement(
        doc, inst.Id, Line.CreateBound(ponto, ponto + eixo), ang)
    doc.Regenerate()
    return True


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------

def create_angled_junction(run_pipe_a, run_pipe_b, branch_pipe, point,
                           branch_conn_dir, level_id=None):
    """Insere e liga uma juncao em angulo (Wye) no ponto dado.

    Sequencia validada no Revit 2026:
      1. escolhe da routing preference a familia cujo branch bate com o angulo
      2. instancia, dimensiona pelos parametros de instancia
      3. rotacao 1: alinha o jusante do run com o eixo do tubo principal
      4. rotacao 2: gira em torno do run ate o branch apontar para o ramal
      5. move o ponto de insercao para o cruzamento
      6. encosta cada um dos tres tubos no seu conector e liga

    ``branch_conn_dir`` e a direcao do conector LIVRE do ramal (aponta do tubo
    para a juncao). O sentido do run sai dai: o Wye converge no jusante.

    Retorna a FamilyInstance criada, ou None (revertendo tudo) se falhar.
    """
    doc = revit.doc

    loc = run_pipe_a.Location
    if not isinstance(loc, LocationCurve):
        _nota("o tubo do run nao tem curva")
        return None
    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)
    run_vec = p1 - p0
    if run_vec.GetLength() < 1e-9:
        _nota("tubo do run degenerado")
        return None
    run_axis = run_vec.Normalize()

    # Direcao do conector do branch da juncao = oposta a do conector do ramal
    branch_dir = branch_conn_dir.Negate()
    # Jusante: o lado do run para onde o branch converge
    jusante = run_axis if branch_dir.DotProduct(run_axis) > 0 else run_axis.Negate()

    angulo = branch_dir.AngleTo(jusante)
    if level_id is None:
        try:
            level_id = run_pipe_a.ReferenceLevel.Id
        except Exception:
            level_id = None

    _nota("juncao pedida: ramal a {:.1f} graus do run".format(
        math.degrees(angulo)))
    symbol = find_junction_symbol(run_pipe_a, angulo, level_id)
    if symbol is None:
        return None            # find_junction_symbol ja anotou o motivo

    try:
        d_run = run_pipe_a.Diameter
    except Exception:
        d_run = None
    try:
        d_branch = branch_pipe.Diameter
    except Exception:
        d_branch = d_run

    sub = SubTransaction(doc)
    sub.Start()
    try:
        if not symbol.IsActive:
            symbol.Activate()
            doc.Regenerate()
        inst = doc.Create.NewFamilyInstance(
            point, symbol, StructuralType.NonStructural)
        doc.Regenerate()

        if d_run:
            _set_sizes(inst, d_run, d_branch or d_run)
            doc.Regenerate()

        run_a, run_b, branch = _classify(inst.MEPModel.ConnectorManager.Connectors)
        if branch is None:
            raise Exception("juncao sem passagem reta identificavel")
        jus_local = _downstream(run_a, run_b, branch)

        if not _rotate_to(inst, jus_local.CoordinateSystem.BasisZ, jusante):
            raise Exception("nao consegui alinhar o run")

        # reler: os conectores mudaram de lugar
        run_a, run_b, branch = _classify(inst.MEPModel.ConnectorManager.Connectors)
        if branch is None:
            raise Exception("perdi o branch apos a primeira rotacao")
        if not _spin_around(inst, jusante,
                            branch.CoordinateSystem.BasisZ, branch_dir):
            raise Exception("nao consegui girar o branch ate o ramal")

        atual = inst.Location.Point
        delta = point - atual
        if delta.GetLength() > 1e-9:
            ElementTransformUtils.MoveElement(doc, inst.Id, delta)
            doc.Regenerate()

        # ---- conferir a orientacao ANTES de tentar ligar
        #
        # O Wye e DIRECIONAL e assimetrico: um conector do run fica a 0.156 ft
        # do centro e o outro a 0.532. Montado com o run invertido, o branch
        # aponta para o lado oposto ao do ramal (medido: [0.71,0,0.71] contra
        # [0.71,0,-0.71]) e o tubo do ramal nunca alcanca seu conector — o
        # sintoma era "so 2 de 3 ligacoes fecharam", sem dizer o porque.
        #
        # Em vez de confiar que a conta do jusante acertou, mede-se o
        # resultado: se o branch ficou virado, gira 180 graus em torno do eixo
        # perpendicular ao run, o que troca os dois lados do run de lugar.
        _ra, _rb, br_conf = _classify(inst.MEPModel.ConnectorManager.Connectors)
        if br_conf is not None:
            desvio = br_conf.CoordinateSystem.BasisZ.DotProduct(branch_dir)
            if desvio < 0.9:
                _nota("branch ficou a {:.2f} da direcao do ramal; "
                      "invertendo o run".format(desvio))
                perp = jusante.CrossProduct(branch_dir)
                if perp.GetLength() > 1e-9:
                    ElementTransformUtils.RotateElement(
                        doc, inst.Id,
                        Line.CreateUnbound(inst.Location.Point,
                                           perp.Normalize()),
                        math.pi)
                    doc.Regenerate()
                    _ra, _rb, br2 = _classify(
                        inst.MEPModel.ConnectorManager.Connectors)
                    if br2 is not None:
                        novo_desvio = br2.CoordinateSystem.BasisZ.DotProduct(
                            branch_dir)
                        _nota("apos inverter, branch a {:.2f}".format(
                            novo_desvio))
                        if novo_desvio < desvio:
                            raise Exception(
                                "nao consegui orientar o branch para o ramal "
                                "(melhor alinhamento {:.2f})".format(desvio))

        # ---- ligar os tres tubos
        run_a, run_b, branch = _classify(inst.MEPModel.ConnectorManager.Connectors)
        alvos = [c for c in (run_a, run_b, branch) if c is not None]
        tubos = [t for t in (run_pipe_a, run_pipe_b, branch_pipe)
                 if t is not None and t.IsValidObject]

        ligados = 0
        usados = set()
        for i_alvo, alvo in enumerate(alvos):
            fechou = False
            recusas = []
            for tubo in tubos:
                if not tubo.IsValidObject:
                    continue
                if get_id_val(tubo.Id) in usados:
                    continue  # um tubo por conector
                tloc = tubo.Location
                if not isinstance(tloc, LocationCurve):
                    continue
                q0 = tloc.Curve.GetEndPoint(0)
                q1 = tloc.Curve.GetEndPoint(1)
                if q0.DistanceTo(point) < END_TOL:
                    movel, fixo = q0, q1
                elif q1.DistanceTo(point) < END_TOL:
                    movel, fixo = q1, q0
                else:
                    continue
                eixo_t = (movel - fixo)
                if eixo_t.GetLength() < 1e-9:
                    continue
                eixo_t = eixo_t.Normalize()
                # Coaxial NAO basta: o tubo tem de chegar pelo lado certo.
                # eixo_t sai do tubo em direcao a juncao e o conector do
                # fitting aponta para fora, entao os dois sao OPOSTOS. Testar
                # com abs() aceitaria o tubo do outro lado do fitting — foi o
                # que puxou a metade de cima da prumada ate o conector de
                # baixo, atravessando o Wye e invertendo o tubo.
                if eixo_t.DotProduct(alvo.CoordinateSystem.BasisZ) > -0.95:
                    recusas.append("{}: chega pelo lado errado (dot {:.2f})"
                                   .format(get_id_val(tubo.Id),
                                           eixo_t.DotProduct(
                                               alvo.CoordinateSystem.BasisZ)))
                    continue
                t = (alvo.Origin - fixo).DotProduct(eixo_t)
                # t <= 0 significa que o conector esta ATRAS da ponta fixa:
                # reconstruir a curva assim inverteria o tubo e o Revit
                # responde "modificado para estar na direcao oposta",
                # invalidando as conexoes da rede inteira.
                if t < MIN_FORWARD:
                    recusas.append("{}: conector atras da ponta fixa "
                                   "(t={:.3f})".format(get_id_val(tubo.Id), t))
                    continue
                novo = fixo + eixo_t.Multiply(t)
                if fixo.DistanceTo(novo) < 0.05:
                    continue
                # preservar a orientacao endpoint 0 -> 1 (inverter reverteria o tubo)
                if q0.DistanceTo(movel) < 1e-3:
                    tloc.Curve = Line.CreateBound(novo, fixo)
                else:
                    tloc.Curve = Line.CreateBound(fixo, novo)
                doc.Regenerate()
                mais_perto = None
                for conn in tubo.ConnectorManager.Connectors:
                    d = conn.Origin.DistanceTo(alvo.Origin)
                    if mais_perto is None or d < mais_perto:
                        mais_perto = d
                    if (d < CONNECT_TOL and not conn.IsConnected
                            and not alvo.IsConnected):
                        conn.ConnectTo(alvo)
                        ligados += 1
                        fechou = True
                        usados.add(get_id_val(tubo.Id))
                        break
                if not fechou:
                    recusas.append(
                        "{}: encostou a {:.4f} ft do conector (limite {:.4f}); "
                        "alvo ja ligado? {}".format(
                            get_id_val(tubo.Id),
                            mais_perto if mais_perto is not None else -1.0,
                            CONNECT_TOL, alvo.IsConnected))
                break
            if not fechou:
                _nota("conector {} do fitting ficou solto — {}".format(
                    i_alvo, "; ".join(recusas[:3]) or "nenhum tubo candidato"))

        if ligados < 3:
            raise Exception("so {} de 3 ligacoes fecharam".format(ligados))

        sub.Commit()
        return inst
    except Exception as erro:
        sub.RollBack()
        _nota("montagem da juncao em angulo falhou: {}".format(
            erro or erro.__class__.__name__))
        return None
