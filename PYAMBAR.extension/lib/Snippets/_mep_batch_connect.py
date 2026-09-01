# -*- coding: utf-8 -*-
"""
_mep_batch_connect.py — motor de conexao MEP em lote.

===========================================================================
DIRETRIZES  (decisoes do Thiago; mudar qualquer uma quebra um caso real)
===========================================================================

1. CONECTAR O QUE EXISTE VEM ANTES DE CRIAR.
   As fases que criam fitting rodavam primeiro e enchiam de tes e joelhos
   novos uma rede que so precisava ter os conectores fechados. Por isso o
   pareamento roda DUAS vezes: antes (prioridade a quem ja esta la) e depois
   (fechar o que a criacao deixou solto).

2. CONECTAR E PUXAR, nao so ligar logicamente.
   Ligar conectores afastados deixa a geometria torta. A ordem de tentativas
   vai do menos ao mais invasivo: elongar o tubo -> elongar o outro lado ->
   PUXAR sem girar (translacao) -> mover e girar. Quem se move e sempre quem
   tem menos rede atras de si.

3. NAO SALTAR POR CIMA de quem esta no meio.
   O alcance ampliado (PULL_DIST) serve para usar a conexao que ja existe;
   sem a guarda _ha_intermediario ele pulava um segmento e o deixava orfao.

4. DESVIO E DERIVACAO SAO ULTIMO RECURSO.
   Rodam depois de todo o pareamento, so no que sobrou. Rodando antes, o
   desvio consumia pontas livres que a proximidade resolveria melhor.

5. CADA FASE PROTEGIDA POR SI.
   Uma excecao isolada nao pode derrubar a Transaction e apagar o que as
   outras fases ja fizeram. As que abortam aparecem nomeadas no output.

6. DIALOGO SEMPRE FORA DA TRANSACTION (erro fatal no Revit 2026).
   Por isso a escolha de estrategia acontece antes, e o motor recebe o
   angulo pronto — nenhum snippet daqui abre janela.

7. QUANDO RECUSAR, DIZER POR QUE.
   Todo criterio que barra um par tem mensagem com a medida e o limite. Sem
   isso nao ha como distinguir "nao se aplica" de "esta quebrado".

FASES, na ordem em que rodam
---------------------------------------------------------------------------
  1/2  pairing_loop  proximidade (<1"; 150 mm com fitting) e eixo (ate 10 ft)
  0    split_pass    te/cruzeta livre sobre o eixo de um tubo: divide e liga
  0c   series_pass   conjunto montado SOBRE o tubo: dois cortes, APAGA o miolo
  0b   junction_pass ponta livre cruzando outro tubo: te, wye ou joelho
  1/2  pairing_loop  de novo, fechando o que a criacao deixou
  0d   jog_pass      tubos paralelos desalinhados: desvio de dois joelhos
  0e   takeoff_pass  ramal ao lado de tronco continuo: joelho + wye/te
  --   merge_pass    funde colineares ja ligados (respeita luva/uniao)

Ponto de entrada: ``connect_batch(elements, required, jog_angle,
takeoff_angle)``. REQUER Transaction ativa — as fases usam SubTransaction
para reverter tentativas isoladas sem perder o resto.

Geometria pura testada em dev-tools/tests/test_mep_connect_geometry.py.

NOTA: ``revit.doc`` e lido dentro das funcoes, nunca cacheado no modulo —
com __persistentengine__ o modulo sobrevive entre execucoes e um ``doc``
de modulo apontaria para um documento ja fechado.
"""

import math

import clr
clr.AddReference("System")

from Autodesk.Revit.DB import (
    BoundingBoxIntersectsFilter, BuiltInCategory, ElementId,
    ElementTransformUtils, FilteredElementCollector, Line, LocationCurve,
    Outline, SubTransaction, XYZ
)
from Autodesk.Revit.DB.Plumbing import Pipe, PlumbingUtils
from Autodesk.Revit.DB.Mechanical import MechanicalUtils

from pyrevit import revit
from pyrevit.compat import get_elementid_value_func as _get_func

from Snippets._mep_angled_junction import create_angled_junction
from Snippets._mep_common import system_type_id as _tipo_de_sistema
from Snippets._mep_branch_takeoff import takeoff_pass
from Snippets._mep_offset_jog import jog_pass
from Snippets._mep_connector_utils import (
    get_connector_manager,
    connect_elements,
    connect_elements_no_rotate,
    validate_connectors_compatible,
    apply_and_verify_slope,
    describe_network_change,
    describe_slope_report,
    diff_network_slopes,
    measure_pipe_slope,
    snapshot_network_slopes
)

get_id_val = _get_func()

MAX_DIST = 1.0 / 12.0  # ft — 1" (raio maximo para considerar par candidato)

# Frente a frente: abaixo disso os conectores ja se olham e basta PUXAR
# (translacao). -0.9999 era estrito demais — 0.8 grau de desvio ja obrigava
# rotacao, que e barrada em elemento ancorado, e o par acabava so ligado
# logicamente, torto.
FACING_TOL = -0.999    # ~2.5 graus

# Alcance para PUXAR uma conexao existente ate o tubo (ou vice-versa). Maior
# que MAX_DIST porque a prioridade e usar o fitting que ja esta la, em vez de
# criar outro: so vale quando ha fitting no par — pipe-pipe continua em 1".
PULL_DIST = 0.5        # ft (~150 mm)

# Passadas de pareamento: mover um elemento pode trazer para dentro do alcance
# conectores que estavam de fora. Para quando uma passada nao conecta nada.
MAX_PASSES = 3

# Pareamento por eixo (fase 2): tubo livre alinhado com conector livre distante
AXIAL_MAX = 10.0        # ft — alcance maximo ao longo do eixo do tubo
AXIAL_PERP_TOL = 0.01   # ft — desvio lateral maximo do eixo (~3 mm)
AXIAL_ANGLE_TOL = 0.05  # rad — desvio maximo entre eixos opostos (~3 graus)

# Fusao pipe-pipe colinear (pos-conexao): sobrevive o segmento MAIOR
# Quanto um tubo pode ENCURTAR para alcancar um conector que esta dentro dele.
#
# Antes o limite era "ate sobrar 0.05 ft", ou seja, 99% do tubo: um tubo de
# 8 ft foi comido nas duas pontas ate 2.59 ft para encaixar entre dois tes que
# estavam no meio dele. Sobreposicao pequena e acidente de modelagem e vale
# aparar; conector no MEIO do tubo nao e caso de encurtar, e de DIVIDIR — o
# que a fase 0 faz, preservando os tres segmentos.
MAX_ENCURTAR = 0.5       # ft (152 mm)

MERGE_JUNC_TOL = 0.002   # ft — coincidencia dos endpoints na juncao
MERGE_PERP_TOL = 0.0016  # ft — desvio lateral maximo do eixo (~0.5 mm)

# Fase 0 — dividir tubo em te/cruzeta com passagem reta livre
SPLIT_PULL_MAX = 1.0     # ft — desalinhamento lateral maximo para puxar o fitting
SPLIT_AXIS_DOT = 0.999   # paralelismo minimo entre eixo do fitting e do tubo
# Vao maximo entre os dois fittings para o conjunto ser considerado "em
# serie". A fase 0c existe para conjunto COMPACTO — registro, hidrometro —
# onde nao ha tubo entre as pecas: ela apaga o trecho interno de proposito.
# Sem limite nenhum, dois fittings distantes na mesma prumada eram lidos como
# conjunto e METROS de tubo util eram deletados. Acima deste vao o certo e
# dividir o tubo em cada fitting e preservar o trecho do meio.
SERIES_MAX_SPAN = 2.0    # ft (610 mm)

SPLIT_END_MARGIN = 0.25  # ft — nao dividir a menos disso de uma extremidade
                         # (metade menor que o proprio fitting nao sobreviveria
                         # ao encurtamento; ali a Fase 1/2 ja resolve na ponta)

# Fase 0b — ramal cruzando o meio de um tubo: apara/estende, divide e cria o te
TEE_PULL_MAX = 1.0       # ft — desalinhamento maximo para puxar o ramal ao plano
TEE_PARALLEL_DOT = 0.999 # acima disso os eixos sao paralelos (nao ha cruzamento)

# Metades geradas por um mesmo split: nunca podem casar entre si (desfaria o
# split, religando a prumada e deixando o fitting de fora).
SPLIT_SIBLINGS = set()

# Escopo obrigatorio: quando definido, toda ligacao precisa envolver ao menos
# um elemento deste conjunto. Serve para quem passa vizinhos so como CONTEXTO
# (ex: insercao de kit) e nao quer que dois vizinhos se conectem entre si.
_REQUIRED_IDS = None


def _in_scope(*elements):
    """True se a operacao pode acontecer no escopo atual."""
    if _REQUIRED_IDS is None:
        return True
    for elem in elements:
        try:
            if get_id_val(elem.Id) in _REQUIRED_IDS:
                return True
        except Exception:
            pass
    return False


def is_pipe(elem):
    if not elem.Category:
        return False
    return get_id_val(elem.Category.Id) == int(BuiltInCategory.OST_PipeCurves)


def get_free_connectors(elem):
    try:
        cm = get_connector_manager(elem)
        return [c for c in cm.Connectors if not c.IsConnected]
    except Exception:
        return []


def count_free(elem):
    return len(get_free_connectors(elem))


def count_connected(elem):
    """Quantos conectores do elemento ja estao na rede."""
    try:
        cm = get_connector_manager(elem)
        return len([c for c in cm.Connectors if c.IsConnected])
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Elongacao (copiado do Move Connect Pro — preserva inclinacao do tubo)
# ---------------------------------------------------------------------------

def _get_endpoint_conn(pipe, point, tol=0.01):
    try:
        for c in pipe.ConnectorManager.Connectors:
            if c.Origin.DistanceTo(point) < tol:
                return c
    except Exception:
        pass
    return None


def _get_connected_ref(conn, pipe_id):
    try:
        for ref in conn.AllRefs:
            if ref.Owner.Id != pipe_id:
                return ref
    except Exception:
        pass
    return None


def _forward_ok(pipe, free_conn, target_origin, tol=0.01):
    """True se conectar free_conn ao target NAO reverte o tubo.

    O alvo precisa estar do lado da direcao de saida da ponta livre — ou seja,
    alem do ponto fixo ao longo do eixo fixo->livre. Se estiver atras do ponto
    fixo, a conexao so seria possivel invertendo o tubo (proibido).
    """
    loc = pipe.Location
    if not isinstance(loc, LocationCurve):
        return True  # sem curva (fitting): sem restricao direcional
    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)
    if free_conn.Origin.DistanceTo(p0) < tol:
        fixed_pt = p1
    elif free_conn.Origin.DistanceTo(p1) < tol:
        fixed_pt = p0
    else:
        return True
    axis = free_conn.Origin - fixed_pt
    if axis.GetLength() < 1e-6:
        return True
    axis = axis.Normalize()
    t = (target_origin - fixed_pt).DotProduct(axis)
    return t > 0.001


def _facing_dot(conn_a, conn_b):
    """Dot entre as direcoes dos conectores. ~-1 = frente a frente (correto),
    ~+1 = mesma direcao (lado errado de um fitting coaxial)."""
    try:
        return conn_a.CoordinateSystem.BasisZ.DotProduct(
            conn_b.CoordinateSystem.BasisZ)
    except Exception:
        return 0.0


def _is_anchored(elem):
    """True se o elemento tem ALGUM conector ja conectado a rede.

    Elemento ancorado nao pode ser rotacionado pelo fallback: o Revit nao
    consegue manter a conectividade ("Desconectar a familia da rede?").
    """
    try:
        cm = get_connector_manager(elem)
        for c in cm.Connectors:
            if c.IsConnected:
                return True
    except Exception:
        pass
    return False


def _pair_safe_direction(elem_a, conn_a, elem_b, conn_b):
    """Rejeita pares que so conectariam invertendo um tubo.

    pipe-pipe: exige que ao menos um lado consiga elongar pra frente.
    pipe-fitting / fitting-fitting: sem restricao (o fitting e quem se move).
    """
    a_pipe = is_pipe(elem_a)
    b_pipe = is_pipe(elem_b)
    if a_pipe and b_pipe:
        return (_forward_ok(elem_a, conn_a, conn_b.Origin) or
                _forward_ok(elem_b, conn_b, conn_a.Origin))
    return True


def elongate_and_connect(pipe, moved_conn, target_conn, require_anchored=True):
    """Move a ponta livre do tubo ao longo do proprio eixo ate o alvo.

    ``require_anchored=False`` permite tubo com a ponta oposta solta — usado
    pela Fase 0, onde as metades recem-divididas podem nao estar na rede.
    """
    loc = pipe.Location
    if not isinstance(loc, LocationCurve):
        return False

    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)

    tol_end = 0.002
    if moved_conn.Origin.DistanceTo(p0) < tol_end:
        p_moving, fixed_pt = p0, p1
    elif moved_conn.Origin.DistanceTo(p1) < tol_end:
        p_moving, fixed_pt = p1, p0
    else:
        return False

    fixed_conn = _get_endpoint_conn(pipe, fixed_pt)
    if require_anchored and (not fixed_conn or not fixed_conn.IsConnected):
        return False

    fixed_ref = _get_connected_ref(fixed_conn, pipe.Id) if fixed_conn else None

    pipe_vec = XYZ(p_moving.X - fixed_pt.X, p_moving.Y - fixed_pt.Y, p_moving.Z - fixed_pt.Z)
    pipe_len = math.sqrt(pipe_vec.X**2 + pipe_vec.Y**2 + pipe_vec.Z**2)
    if pipe_len < 0.001:
        return False
    pipe_dir = XYZ(pipe_vec.X/pipe_len, pipe_vec.Y/pipe_len, pipe_vec.Z/pipe_len)

    to_target = target_conn.Origin - fixed_pt
    t = to_target.X*pipe_dir.X + to_target.Y*pipe_dir.Y + to_target.Z*pipe_dir.Z
    if t < 0.001:
        return False

    # Alvo deve estar FRENTE A FRENTE com a ponta do tubo. Conectar em
    # conector de mesma direcao (lado errado de fitting coaxial) faz o Revit
    # inverter o tubo: "modificado para estar na direcao oposta".
    try:
        if target_conn.CoordinateSystem.BasisZ.DotProduct(pipe_dir) > -0.9:
            return False
    except Exception:
        pass

    new_pt = XYZ(fixed_pt.X + pipe_dir.X*t, fixed_pt.Y + pipe_dir.Y*t, fixed_pt.Z + pipe_dir.Z*t)
    if fixed_pt.DistanceTo(new_pt) < 0.001:
        return False

    # Alvo FORA do eixo: elongar so chega na projecao dele, e o ConnectTo
    # aceitaria a conexao torta (tubo entrando no fitting de esguelha). Quem
    # resolve desalinhamento e o fallback, movendo o elemento ate o alvo.
    if target_conn.Origin.DistanceTo(new_pt) > AXIAL_PERP_TOL:
        return False

    # Desconectar moved
    if moved_conn.IsConnected:
        try:
            for ref in list(moved_conn.AllRefs):
                if ref.Owner.Id != pipe.Id:
                    moved_conn.DisconnectFrom(ref)
        except Exception:
            pass

    # Desconectar fixed antes de modificar curva
    if fixed_ref:
        try:
            fixed_conn.DisconnectFrom(fixed_ref)
        except Exception:
            fixed_ref = None

    try:
        loc.Curve = Line.CreateBound(fixed_pt, new_pt)
    except Exception:
        return False

    # Reconectar fixed
    if fixed_ref:
        new_fixed = _get_endpoint_conn(pipe, fixed_pt)
        if new_fixed:
            try:
                new_fixed.ConnectTo(fixed_ref)
            except Exception:
                pass

    # Conectar novo moving end ao target
    new_moved = _get_endpoint_conn(pipe, new_pt)
    if new_moved:
        try:
            new_moved.ConnectTo(target_conn)
            return True
        except Exception:
            pass

    return False


# ---------------------------------------------------------------------------
# Fusao de tubos colineares (pipe-pipe)
# ---------------------------------------------------------------------------

def try_merge_collinear(pipe_a, pipe_b):
    """Funde dois tubos colineares conectados de ponta a ponta em um so.

    Sobrevive o segmento MAIOR (mantem os parametros dele); o menor e
    deletado e a curva do maior e estendida ate a extremidade distante.
    A conexao da extremidade distante do deletado e transferida.
    Retorna True se fundiu; False se criterios nao batem ou falhou
    (nesse caso os dois tubos permanecem conectados como estavam).
    """
    if not (is_pipe(pipe_a) and is_pipe(pipe_b)):
        return False
    if pipe_a.GetTypeId() != pipe_b.GetTypeId():
        return False
    try:
        if abs(pipe_a.Diameter - pipe_b.Diameter) > 1e-6:
            return False
    except Exception:
        return False

    loc_a, loc_b = pipe_a.Location, pipe_b.Location
    if not isinstance(loc_a, LocationCurve) or not isinstance(loc_b, LocationCurve):
        return False

    a0, a1 = loc_a.Curve.GetEndPoint(0), loc_a.Curve.GetEndPoint(1)
    b0, b1 = loc_b.Curve.GetEndPoint(0), loc_b.Curve.GetEndPoint(1)

    # Juncao: par de endpoints coincidentes
    junction = None
    for ja, fa in ((a0, a1), (a1, a0)):
        for jb, fb in ((b0, b1), (b1, b0)):
            if ja.DistanceTo(jb) < MERGE_JUNC_TOL:
                junction = (ja, fa, fb)
                break
        if junction:
            break
    if not junction:
        return False
    ja, far_a, far_b = junction

    # Colinearidade real: extremidade distante de B deve estar no eixo de A,
    # alem da juncao (nao dobrado sobre A)
    axis = ja - far_a
    if axis.GetLength() < 0.001:
        return False
    axis = axis.Normalize()
    v = far_b - far_a
    t = v.DotProduct(axis)
    if t <= loc_a.Curve.Length + 0.001:
        return False
    perp = (v - axis.Multiply(t)).GetLength()
    if perp > MERGE_PERP_TOL:
        return False

    # Sobrevivente = maior segmento (mantem os parametros dele)
    if loc_a.Curve.Length >= loc_b.Curve.Length:
        survivor, victim = pipe_a, pipe_b
        surv_far, vict_far = far_a, far_b
    else:
        survivor, victim = pipe_b, pipe_a
        surv_far, vict_far = far_b, far_a

    st = SubTransaction(revit.doc)
    st.Start()
    try:
        # Guardar e soltar a conexao distante do victim (sera transferida)
        far_ref = None
        vict_conn = _get_endpoint_conn(victim, vict_far)
        if vict_conn and vict_conn.IsConnected:
            far_ref = _get_connected_ref(vict_conn, victim.Id)
            if far_ref:
                vict_conn.DisconnectFrom(far_ref)

        # Soltar a conexao distante do survivor antes de mexer na curva
        surv_ref = None
        surv_conn = _get_endpoint_conn(survivor, surv_far)
        if surv_conn and surv_conn.IsConnected:
            surv_ref = _get_connected_ref(surv_conn, survivor.Id)
            if surv_ref:
                surv_conn.DisconnectFrom(surv_ref)

        revit.doc.Delete(victim.Id)
        # Preservar a orientacao original do survivor (endpoint 0 -> 1):
        # comecar a nova curva pelo lado errado reverteria o tubo.
        sc = survivor.Location.Curve
        if sc.GetEndPoint(0).DistanceTo(surv_far) <= sc.GetEndPoint(1).DistanceTo(surv_far):
            survivor.Location.Curve = Line.CreateBound(surv_far, vict_far)
        else:
            survivor.Location.Curve = Line.CreateBound(vict_far, surv_far)

        if surv_ref:
            c = _get_endpoint_conn(survivor, surv_far)
            if not c:
                raise Exception("conector distante do survivor nao encontrado")
            c.ConnectTo(surv_ref)
        if far_ref:
            c = _get_endpoint_conn(survivor, vict_far)
            if not c:
                raise Exception("conector estendido nao encontrado")
            c.ConnectTo(far_ref)

        st.Commit()
        return True
    except Exception:
        st.RollBack()
        return False


def merge_pass(elements):
    """Funde todo par colinear ligado ponta a ponta entre os selecionados.

    O merge do laco de conexao so alcanca o par que a ferramenta acabou de
    ligar. Uma prumada que ja chegou partida em varios pedacos nunca passava
    por ali — nao tem conector livre, entao nao vira par. Esta passada varre a
    selecao inteira e resolve tambem esses casos.

    Tubo separado por luva/uniao NAO funde: o fitting no meio afasta os
    endpoints, e o criterio de juncao exige coincidencia de MERGE_JUNC_TOL.

    Repete enquanto houver progresso: fundir A+B pode deixar o resultado
    colinear com C.
    """
    fundidos = 0
    recusas = {}
    for _ in range(MAX_PASSES):
        vivos = [e for e in elements
                 if e is not None and e.IsValidObject and is_pipe(e)]
        se_fundiu = False
        for i in range(len(vivos)):
            pipe_a = vivos[i]
            if not pipe_a.IsValidObject:
                continue
            for j in range(i + 1, len(vivos)):
                pipe_b = vivos[j]
                if not pipe_b.IsValidObject or not pipe_a.IsValidObject:
                    continue
                if _are_split_siblings(pipe_a, pipe_b):
                    continue
                if not _in_scope(pipe_a, pipe_b):
                    continue
                if not _sao_vizinhos_ligados(pipe_a, pipe_b):
                    continue
                # Chave e id ANTES de fundir: a fusao deleta um dos dois, e
                # ler .Id de elemento deletado levanta InvalidObjectException
                # — que aborta a Transaction inteira e desfaz todo o trabalho.
                chave = _par_chave(pipe_a, pipe_b)
                id_a = get_id_val(pipe_a.Id)
                try:
                    fundiu = try_merge_collinear(pipe_a, pipe_b)
                except Exception:
                    fundiu = False
                if fundiu:
                    fundidos += 1
                    se_fundiu = True
                    recusas.pop(chave, None)
                else:
                    try:
                        motivo = _motivo_nao_fundiu(pipe_a, pipe_b)
                    except Exception:
                        motivo = "nao consegui avaliar"
                    recusas[chave] = (id_a, motivo)
        if not se_fundiu:
            break
    elements = [e for e in elements if e is not None and e.IsValidObject]
    # um tubo recusado numa passada pode ter sido fundido na seguinte: so
    # reportar quem ainda existe
    vivos_ids = set(get_id_val(e.Id) for e in elements)
    restantes = [(eid, motivo) for eid, motivo in recusas.values()
                 if eid in vivos_ids]
    return elements, fundidos, restantes


def _par_chave(pipe_a, pipe_b):
    return frozenset((get_id_val(pipe_a.Id), get_id_val(pipe_b.Id)))


def _motivo_nao_fundiu(pipe_a, pipe_b):
    """Por que dois tubos ligados nao viraram um so.

    Refaz as checagens de try_merge_collinear na mesma ordem e devolve a
    primeira que barra — assim o relatorio diz o motivo real em vez de so
    informar que nao fundiu.
    """
    try:
        if pipe_a.GetTypeId() != pipe_b.GetTypeId():
            return "tipos de tubo diferentes"
        if abs(pipe_a.Diameter - pipe_b.Diameter) > 1e-6:
            return "diametros diferentes ({:.0f} mm x {:.0f} mm)".format(
                pipe_a.Diameter * 304.8, pipe_b.Diameter * 304.8)
    except Exception:
        return "nao consegui comparar tipo/diametro"

    loc_a, loc_b = pipe_a.Location, pipe_b.Location
    if not isinstance(loc_a, LocationCurve) or not isinstance(loc_b, LocationCurve):
        return "algum dos dois nao tem curva"

    a0, a1 = loc_a.Curve.GetEndPoint(0), loc_a.Curve.GetEndPoint(1)
    b0, b1 = loc_b.Curve.GetEndPoint(0), loc_b.Curve.GetEndPoint(1)
    melhor = None
    for ja, fa in ((a0, a1), (a1, a0)):
        for jb, fb in ((b0, b1), (b1, b0)):
            d = ja.DistanceTo(jb)
            if melhor is None or d < melhor[0]:
                melhor = (d, ja, fa, fb)
    if melhor is None:
        return "sem extremidades para comparar"
    dist, ja, far_a, far_b = melhor
    if dist >= MERGE_JUNC_TOL:
        return ("extremidades a {:.1f} mm uma da outra (limite {:.1f} mm) — "
                "provavelmente ha uma luva/uniao entre os dois".format(
                    dist * 304.8, MERGE_JUNC_TOL * 304.8))

    axis = ja - far_a
    if axis.GetLength() < 0.001:
        return "tubo degenerado"
    axis = axis.Normalize()
    v = far_b - far_a
    t = v.DotProduct(axis)
    if t <= loc_a.Curve.Length + 0.001:
        return "o segundo tubo dobra sobre o primeiro (nao segue em frente)"
    perp = (v - axis.Multiply(t)).GetLength()
    if perp > MERGE_PERP_TOL:
        return ("nao sao colineares: desvio de {:.1f} mm (limite {:.1f} mm)"
                .format(perp * 304.8, MERGE_PERP_TOL * 304.8))
    if _are_split_siblings(pipe_a, pipe_b):
        return "sao as duas metades de uma divisao desta execucao"
    return "o Revit recusou a fusao"


def _sao_vizinhos_ligados(pipe_a, pipe_b):
    """True se os dois tubos estao conectados um ao outro diretamente."""
    id_b = pipe_b.Id
    try:
        for conn in pipe_a.ConnectorManager.Connectors:
            if not conn.IsConnected:
                continue
            for ref in conn.AllRefs:
                owner = ref.Owner
                if owner is not None and owner.Id == id_b:
                    return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Fase 0 — dividir tubo sob te/cruzeta livre
# ---------------------------------------------------------------------------

def _break_curve(elem, pt):
    """Divide tubo/duto no ponto. Retorna o elemento novo ou None."""
    try:
        cat = get_id_val(elem.Category.Id)
    except Exception:
        return None
    try:
        if cat == int(BuiltInCategory.OST_PipeCurves):
            new_id = PlumbingUtils.BreakCurve(revit.doc, elem.Id, pt)
        elif cat == int(BuiltInCategory.OST_DuctCurves):
            new_id = MechanicalUtils.BreakCurve(revit.doc, elem.Id, pt)
        else:
            return None
    except Exception:
        return None
    if new_id is None or new_id == ElementId.InvalidElementId:
        return None
    return revit.doc.GetElement(new_id)


def _through_axis(fitting):
    """(centro, eixo, conn_a, conn_b) do maior par de conectores livres OPOSTOS.

    E a "passagem reta" de um te/cruzeta copiado fora da rede: os dois
    conectores que deveriam receber o tubo principal. None se nao houver.
    """
    frees = get_free_connectors(fitting)
    if len(frees) < 2:
        return None

    best = None
    for i, ca in enumerate(frees):
        for cb in frees[i + 1:]:
            try:
                za = ca.CoordinateSystem.BasisZ
                zb = cb.CoordinateSystem.BasisZ
            except Exception:
                continue
            if za.DotProduct(zb) > -0.999:
                continue  # nao sao opostos
            v = cb.Origin - ca.Origin
            length = v.GetLength()
            if length < 1e-6:
                continue
            axis = v.Normalize()
            if abs(axis.DotProduct(za)) < 0.999:
                continue  # opostos, mas fora da reta que os liga
            if best is None or length > best[0]:
                mid = XYZ((ca.Origin.X + cb.Origin.X) / 2.0,
                          (ca.Origin.Y + cb.Origin.Y) / 2.0,
                          (ca.Origin.Z + cb.Origin.Z) / 2.0)
                best = (length, mid, axis, ca, cb)

    if best is None:
        return None
    return best[1], best[2], best[3], best[4]


def _find_host_pipe(center, axis, pipes):
    """(perp, tubo, projecao) do tubo paralelo ao eixo que o fitting atravessa.

    Exige que a projecao do centro caia DENTRO do tubo (com margem nas pontas)
    e que o desalinhamento lateral seja no maximo SPLIT_PULL_MAX.
    """
    best = None
    for pipe in pipes:
        loc = pipe.Location
        if not isinstance(loc, LocationCurve):
            continue
        p0 = loc.Curve.GetEndPoint(0)
        p1 = loc.Curve.GetEndPoint(1)
        v = p1 - p0
        length = v.GetLength()
        if length < 1e-6:
            continue
        direction = v.Normalize()
        if abs(direction.DotProduct(axis)) < SPLIT_AXIS_DOT:
            continue
        t = (center - p0).DotProduct(direction)
        if t < SPLIT_END_MARGIN or t > length - SPLIT_END_MARGIN:
            continue
        proj = p0 + direction.Multiply(t)
        perp = center.DistanceTo(proj)
        if perp > SPLIT_PULL_MAX:
            continue
        if best is None or perp < best[0]:
            best = (perp, pipe, proj)
    return best


def _vivos(elements):
    """So os elementos que ainda existem no modelo.

    Fases que fundem tubos APAGAM elementos, e a lista continua com as
    referencias mortas. Tocar numa delas levanta InvalidObjectException, o
    `except` da fase engole e a fase inteira e dada como abortada — foi o que
    derrubou a bucha e a divisao no cenario da cadeia de 5 segmentos, onde a
    fusao apaga quatro tubos. Validar SEMPRE antes de qualquer outra checagem:
    `is_pipe(e)` num elemento apagado ja levanta.
    """
    return [e for e in elements if e is not None and e.IsValidObject]


REDUCER_FACING = -0.9    # conectores praticamente de frente um para o outro


def reducer_pass(elements):
    """Bucha de reducao entre pontas livres de diametros diferentes.

    A fase 1 recusa esse par de proposito: um conector de 3" nao casa com um
    de 2", e forcar a ligacao daria uma emenda invalida. Falta uma peca no
    meio — e quem sabe monta-la e o proprio Revit, por NewTransitionFitting,
    que ja encurta os dois tubos para abrir espaco para a bucha.

    Roda logo depois do primeiro pareamento: resolvido cedo, o par para de
    aparecer como candidato a te ou joelho nas fases que criam peca.

    Devolve (elements, feitas, recusas).
    """
    doc = revit.doc
    feitas = 0
    recusas = []
    tubos = [e for e in _vivos(elements) if is_pipe(e)]

    for i in range(len(tubos)):
        for j in range(i + 1, len(tubos)):
            pipe_a, pipe_b = tubos[i], tubos[j]
            if not (pipe_a.IsValidObject and pipe_b.IsValidObject):
                continue
            try:
                if abs(pipe_a.Diameter - pipe_b.Diameter) <= 1e-6:
                    continue          # mesmo diametro: e trabalho da fase 1
            except Exception:
                continue

            melhor = None
            for conn_a in get_free_connectors(pipe_a):
                for conn_b in get_free_connectors(pipe_b):
                    dist = conn_a.Origin.DistanceTo(conn_b.Origin)
                    if melhor is None or dist < melhor[0]:
                        melhor = (dist, conn_a, conn_b)
            if melhor is None or melhor[0] > MAX_DIST:
                continue
            dist, conn_a, conn_b = melhor

            # De frente e no mesmo eixo. Cruzando em angulo o certo e um te ou
            # um joelho, nao uma bucha.
            if _facing_dot(conn_a, conn_b) > REDUCER_FACING:
                recusas.append((get_id_val(pipe_a.Id),
                                "pontas nao estao de frente — nao e emenda reta"))
                continue

            ida = get_id_val(pipe_a.Id)
            sub = SubTransaction(doc)
            sub.Start()
            try:
                doc.Create.NewTransitionFitting(conn_a, conn_b)
                doc.Regenerate()
                sub.Commit()
                feitas += 1
            except Exception as erro:
                sub.RollBack()
                recusas.append((ida, "nao consegui criar a bucha: {}".format(erro)))

    elements = [e for e in elements if e is not None and e.IsValidObject]
    return elements, feitas, recusas


def split_pass(elements):
    """Divide o tubo hospedeiro sob cada te/cruzeta livre e conecta as metades.

    Para cada fitting selecionado com passagem reta livre:
      1. puxa o fitting ate o eixo do tubo (desalinhamento ate SPLIT_PULL_MAX)
      2. BreakCurve no centro do fitting
      3. encurta cada metade ate o conector livre correspondente e conecta

    Retorna (elementos + metades novas, n_divisoes, n_conexoes).
    """
    result = list(elements)
    splits = 0
    connected = 0

    fittings = [e for e in _vivos(elements)
                if not is_pipe(e) and len(get_free_connectors(e)) >= 2
                and _in_scope(e)]

    for fitting in fittings:
        info = _through_axis(fitting)
        if info is None:
            continue
        center, axis, _, _ = info

        pipes = [e for e in result if is_pipe(e) and e.IsValidObject]
        host = _find_host_pipe(center, axis, pipes)
        if host is None:
            continue
        perp, pipe, proj = host

        # Puxar + dividir numa SubTransaction: se o BreakCurve falhar, o
        # fitting volta para a posicao original.
        sub = SubTransaction(revit.doc)
        sub.Start()
        try:
            if perp > 0.001:
                ElementTransformUtils.MoveElement(revit.doc, fitting.Id, proj - center)
            moved = _through_axis(fitting)
            if moved is None:
                raise Exception("fitting perdeu os conectores livres apos mover")
            break_pt = moved[0]
            new_pipe = _break_curve(pipe, break_pt)
            if new_pipe is None:
                raise Exception("BreakCurve falhou")
            sub.Commit()
        except Exception:
            sub.RollBack()
            continue

        splits += 1
        result.append(new_pipe)
        SPLIT_SIBLINGS.add(frozenset((get_id_val(pipe.Id), get_id_val(new_pipe.Id))))

        # Encurtar cada metade ate o conector livre do fitting e conectar.
        for half in (pipe, new_pipe):
            half_conn = _get_endpoint_conn(half, break_pt)
            if half_conn is None or half_conn.IsConnected:
                continue
            outward = _outward_dir(half, half_conn)
            if outward is None:
                continue
            # Reler os conectores: a metade anterior ja pode ter alterado o estado.
            current = _through_axis(fitting)
            if current is None:
                break
            target = None
            for cand in (current[2], current[3]):
                try:
                    if cand.CoordinateSystem.BasisZ.DotProduct(outward) < -0.9:
                        target = cand
                        break
                except Exception:
                    pass
            if target is None:
                continue
            if elongate_and_connect(half, half_conn, target, require_anchored=False):
                connected += 1

    return result, splits, connected


# ---------------------------------------------------------------------------
# Fase 0c — insercao em serie: conjunto montado SOBRE um tubo continuo
# ---------------------------------------------------------------------------

def _free_ends_outward(fitting):
    """[(conector, origem, direcao)] dos conectores livres do fitting."""
    saida = []
    for conn in get_free_connectors(fitting):
        try:
            saida.append((conn, conn.Origin, conn.CoordinateSystem.BasisZ))
        except Exception:
            pass
    return saida


def _series_candidates(elements):
    """Pares (fitting_a, conn_a, fitting_b, conn_b) que abracam um trecho.

    Sao dois fittings cujos conectores livres estao na MESMA reta e apontam
    para FORA (afastando-se um do outro): e a assinatura de um conjunto —
    registro, hidrometro, reducao — montado para entrar em serie num tubo.
    """
    pontas = []
    for elem in elements:
        if is_pipe(elem) or not elem.IsValidObject:
            continue
        for conn, origin, direction in _free_ends_outward(elem):
            pontas.append((elem, conn, origin, direction))

    pares = []
    for i, (elem_a, conn_a, org_a, dir_a) in enumerate(pontas):
        for elem_b, conn_b, org_b, dir_b in pontas[i + 1:]:
            if elem_b.Id == elem_a.Id:
                continue
            if dir_a.DotProduct(dir_b) > -0.9:
                continue  # precisam ser opostos
            v = org_b - org_a
            span = v.GetLength()
            if span < 1e-6:
                continue
            eixo = v.Normalize()
            if abs(abs(eixo.DotProduct(dir_a)) - 1.0) > 0.01:
                continue  # opostos, mas fora da reta que os liga
            # Apontando para FORA: A na direcao contraria a B, e vice-versa.
            if dir_a.DotProduct(eixo) > -0.9 or dir_b.DotProduct(eixo) < 0.9:
                continue
            pares.append((elem_a, conn_a, org_a, elem_b, conn_b, org_b, eixo,
                          span))
    return pares


def _host_for_series(org_a, org_b, eixo, pipes):
    """(tubo, tA, tB) do tubo continuo que os dois pontos atravessam."""
    melhor = None
    for pipe in pipes:
        loc = pipe.Location
        if not isinstance(loc, LocationCurve):
            continue
        p0 = loc.Curve.GetEndPoint(0)
        p1 = loc.Curve.GetEndPoint(1)
        vec = p1 - p0
        mlen = vec.GetLength()
        if mlen < 1e-6:
            continue
        direction = vec.Normalize()
        if abs(direction.DotProduct(eixo)) < SPLIT_AXIS_DOT:
            continue

        ts = []
        perp_max = 0.0
        for org in (org_a, org_b):
            t = (org - p0).DotProduct(direction)
            perp = (org - (p0 + direction.Multiply(t))).GetLength()
            perp_max = max(perp_max, perp)
            ts.append(t)
        if perp_max > AXIAL_PERP_TOL:
            continue  # conjunto fora do eixo: mover a montagem inteira nao
                      # e seguro daqui, o usuario alinha antes
        t_lo, t_hi = min(ts), max(ts)
        if t_lo < SPLIT_END_MARGIN or t_hi > mlen - SPLIT_END_MARGIN:
            continue
        if melhor is None or perp_max < melhor[3]:
            melhor = (pipe, t_lo, t_hi, perp_max)

    if melhor is None:
        return None
    return melhor[0], melhor[1], melhor[2]


def _middle_piece(pieces, pt_lo, pt_hi, tol=0.02):
    """O segmento cujos dois extremos sao os pontos de corte — o miolo."""
    for piece in pieces:
        if piece is None or not piece.IsValidObject:
            continue
        loc = piece.Location
        if not isinstance(loc, LocationCurve):
            continue
        a = loc.Curve.GetEndPoint(0)
        b = loc.Curve.GetEndPoint(1)
        if ((a.DistanceTo(pt_lo) < tol and b.DistanceTo(pt_hi) < tol) or
                (a.DistanceTo(pt_hi) < tol and b.DistanceTo(pt_lo) < tol)):
            return piece
    return None


def series_pass(elements):
    """Conjunto montado SOBRE um tubo continuo: corta duas vezes e emenda.

    Dois fittings com conectores livres colineares apontando para fora, sobre
    o eixo de um tubo selecionado: divide o tubo nos dois pontos, DELETA o
    trecho que sobra dentro do conjunto e liga cada extremidade ao seu fitting.
    O conjunto passa a ser aquele pedaco do tubo.

    Retorna (elementos + partes novas, n_insercoes, n_conexoes).
    """
    result = list(elements)
    inserted = 0
    connected = 0
    recusas = []

    for (elem_a, conn_a, org_a, elem_b, conn_b, org_b,
         eixo, span) in _series_candidates(elements):
        if not (elem_a.IsValidObject and elem_b.IsValidObject):
            continue
        if not (_in_scope(elem_a) or _in_scope(elem_b)):
            continue
        if span > SERIES_MAX_SPAN:
            # Ha tubo util entre os fittings: apagar seria destruir modelagem.
            # Cada um deve dividir o tubo por conta propria (fase 0).
            recusas.append(
                (get_id_val(elem_a.Id),
                 "os fittings distam {:.2f} ft ({:.0f} mm) — acima de {:.0f} "
                 "mm ha tubo util entre eles, que nao pode ser apagado"
                 .format(span, span * 304.8, SERIES_MAX_SPAN * 304.8)))
            continue

        pipes = [e for e in result if is_pipe(e) and e.IsValidObject]
        host = _host_for_series(org_a, org_b, eixo, pipes)
        if host is None:
            continue
        pipe, t_lo, t_hi = host

        loc = pipe.Location
        p0 = loc.Curve.GetEndPoint(0)
        direction = (loc.Curve.GetEndPoint(1) - p0).Normalize()
        pt_lo = p0 + direction.Multiply(t_lo)
        pt_hi = p0 + direction.Multiply(t_hi)

        sub = SubTransaction(revit.doc)
        sub.Start()
        try:
            first = _break_curve(pipe, pt_lo)
            if first is None:
                raise Exception("primeiro corte falhou")

            # O segundo corte vai na parte que contem pt_hi.
            alvo = None
            for cand in (pipe, first):
                cloc = cand.Location
                if not isinstance(cloc, LocationCurve):
                    continue
                ca = cloc.Curve.GetEndPoint(0)
                cb = cloc.Curve.GetEndPoint(1)
                seg = cb - ca
                seg_len = seg.GetLength()
                if seg_len < 1e-6:
                    continue
                t = (pt_hi - ca).DotProduct(seg.Normalize())
                if SPLIT_END_MARGIN <= t <= seg_len - SPLIT_END_MARGIN:
                    alvo = cand
                    break
            if alvo is None:
                raise Exception("segundo ponto nao caiu em nenhuma das partes")

            second = _break_curve(alvo, pt_hi)
            if second is None:
                raise Exception("segundo corte falhou")

            miolo = _middle_piece([pipe, first, second], pt_lo, pt_hi)
            if miolo is None:
                raise Exception("nao identifiquei o trecho interno")

            # TUBO UTIL NAO SE APAGA.
            #
            # Esta fase nasceu para o conjunto compacto — registro, hidrometro
            # — onde o trecho entre as pecas nao existe fisicamente. Quando ha
            # tubo de verdade ali, apagar destroi modelagem: o certo e dividir
            # em cada fitting e MANTER os tres segmentos, que e o que a fase 0
            # (divisao sob o fitting) ja faz sozinha, uma vez por peca.
            try:
                comp_miolo = miolo.Location.Curve.Length
            except Exception:
                comp_miolo = 0.0
            if comp_miolo >= SPLIT_END_MARGIN:
                raise Exception(
                    "o trecho entre os fittings tem {:.0f} mm de tubo util — "
                    "nao pode ser apagado; cada fitting deve dividir o tubo "
                    "por conta propria".format(comp_miolo * 304.8))

            restantes = [p for p in (pipe, first, second)
                         if p.Id != miolo.Id]
            revit.doc.Delete(miolo.Id)

            # Ligar cada extremidade que sobrou ao fitting correspondente.
            feitas = 0
            for ponto, fitting in ((pt_lo, elem_a), (pt_hi, elem_b)):
                alvo_conn = None
                for cand in get_free_connectors(fitting):
                    if cand.Origin.DistanceTo(ponto) < 0.05:
                        alvo_conn = cand
                        break
                if alvo_conn is None:
                    continue
                for peca in restantes:
                    if not peca.IsValidObject:
                        continue
                    ponta = _get_endpoint_conn(peca, ponto)
                    if ponta is None or ponta.IsConnected:
                        continue
                    ponta.ConnectTo(alvo_conn)
                    feitas += 1
                    break

            if feitas == 0:
                raise Exception("nenhuma extremidade conectou ao conjunto")

            sub.Commit()
        except Exception as erro:
            sub.RollBack()
            # recusar em silencio deixava o usuario sem saber por que o
            # conjunto nao entrou — e escondia justamente os casos em que a
            # fase estava prestes a apagar tubo util
            recusas.append((get_id_val(elem_a.Id),
                            str(erro) or erro.__class__.__name__))
            continue

        inserted += 1
        connected += feitas
        for peca in (first, second):
            if peca is not None and peca.IsValidObject:
                result.append(peca)

    # O miolo deletado pode ter vindo da selecao — tirar os invalidos daqui
    # evita que as fases seguintes tropecem neles.
    result = [e for e in result if e is not None and e.IsValidObject]
    return result, inserted, connected, recusas


def _are_split_siblings(elem_a, elem_b):
    return frozenset((get_id_val(elem_a.Id), get_id_val(elem_b.Id))) in SPLIT_SIBLINGS


# ---------------------------------------------------------------------------
# Fase 0b — juncao no cruzamento: te por divisao, te no vao, joelho no canto
# ---------------------------------------------------------------------------

def _closest_points(p, u, q, v):
    """Pontos mais proximos entre as retas p+s*u e q+t*v (u e v unitarios).

    Retorna (pt_na_reta_p, pt_na_reta_q, s, t) ou None se forem paralelas.
    O vetor entre os dois pontos e perpendicular a ambos os eixos — mover o
    ramal por ele faz os eixos se cruzarem sem alterar s.
    """
    uv = u.DotProduct(v)
    den = 1.0 - uv * uv
    if abs(den) < 1e-9:
        return None
    w = p - q
    wu = w.DotProduct(u)
    wv = w.DotProduct(v)
    s = (uv * wv - wu) / den
    t = (wv - uv * wu) / den
    return p + u.Multiply(s), q + v.Multiply(t), s, t


def _set_free_end(pipe, free_pt, new_pt):
    """Leva a ponta livre do tubo ate new_pt, preservando a conexao da oposta.

    Diferente de elongate_and_connect, nao conecta nada: serve para posicionar
    o ramal exatamente sobre o eixo do principal antes do NewTeeFitting.
    """
    loc = pipe.Location
    if not isinstance(loc, LocationCurve):
        return False
    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)
    if free_pt.DistanceTo(p0) < 0.01:
        fixed_pt, free_is_p0 = p1, True
    elif free_pt.DistanceTo(p1) < 0.01:
        fixed_pt, free_is_p0 = p0, False
    else:
        return False
    if fixed_pt.DistanceTo(new_pt) < 0.01:
        return False

    # O novo ponto tem de ficar A FRENTE da ponta fixa. Preservar a ordem
    # p0->p1 nao basta: se new_pt cai atras de fixed_pt o tubo aponta para o
    # lado oposto e o Revit invalida a rede ("direcao oposta"). As copias
    # desta funcao no jog e no takeoff ja tinham esta guarda; esta nao.
    orig = free_pt - fixed_pt
    novo = new_pt - fixed_pt
    if orig.GetLength() < 1e-9 or novo.GetLength() < 1e-9:
        return False
    if novo.Normalize().DotProduct(orig.Normalize()) < 0.9:
        return False

    fixed_conn = _get_endpoint_conn(pipe, fixed_pt)
    fixed_ref = _get_connected_ref(fixed_conn, pipe.Id) if fixed_conn else None
    if fixed_ref:
        try:
            fixed_conn.DisconnectFrom(fixed_ref)
        except Exception:
            fixed_ref = None

    try:
        # Preservar a orientacao original (endpoint 0 -> 1): inverter reverteria
        # o tubo e dispararia "modificado para estar na direcao oposta".
        if free_is_p0:
            loc.Curve = Line.CreateBound(new_pt, fixed_pt)
        else:
            loc.Curve = Line.CreateBound(fixed_pt, new_pt)
    except Exception:
        return False

    if fixed_ref:
        c = _get_endpoint_conn(pipe, fixed_pt)
        if c:
            try:
                c.ConnectTo(fixed_ref)
            except Exception:
                pass
    return True


def _reach_info(a, b, mlen, t):
    """(ponta_que_alcanca, ponta_oposta, resto, ajuste) para levar o tubo ate
    o parametro t do proprio eixo.

    ``resto`` e o comprimento que sobra medido da ponta OPOSTA ate o ponto —
    sempre > 0, entao o tubo nunca inverte. ``ajuste`` e quanto a ponta anda
    (estica se t esta fora do tubo, apara se esta dentro).
    """
    d_a = abs(t)
    d_b = abs(mlen - t)
    if d_a <= d_b:
        return a, b, mlen - t, d_a
    return b, a, t, d_b


def _leg_at_point(pipe, pt):
    """(ponta_livre, ponta_oposta, ajuste) se o tubo pode levar uma ponta LIVRE
    ate pt ao longo do proprio eixo. None se pt esta fora do eixo, se a ponta
    ja esta conectada, se sobraria menos que a margem ou se passa de AXIAL_MAX.
    """
    loc = pipe.Location
    if not isinstance(loc, LocationCurve):
        return None
    a = loc.Curve.GetEndPoint(0)
    b = loc.Curve.GetEndPoint(1)
    vec = b - a
    mlen = vec.GetLength()
    if mlen < 1e-6:
        return None
    axis = vec.Normalize()

    t = (pt - a).DotProduct(axis)
    perp = (pt - (a + axis.Multiply(t))).GetLength()
    if perp > AXIAL_PERP_TOL:
        return None  # pt nao esta no eixo deste tubo

    end_pt, far_pt, rest, adjust = _reach_info(a, b, mlen, t)
    if rest < SPLIT_END_MARGIN or adjust > AXIAL_MAX:
        return None
    conn = _get_endpoint_conn(pipe, end_pt)
    if conn is None or conn.IsConnected:
        return None
    return end_pt, far_pt, adjust


def _legs_at_point(pt, pipes, skip_id):
    """[(tubo, ponta, ponta_oposta, ajuste)] dos tubos que alcancam pt com uma
    ponta livre, ordenados do menor ajuste para o maior."""
    legs = []
    for pipe in pipes:
        if pipe.Id == skip_id or not pipe.IsValidObject:
            continue
        info = _leg_at_point(pipe, pt)
        if info is None:
            continue
        legs.append((pipe, info[0], info[1], info[2]))
    legs.sort(key=lambda x: x[3])
    return legs


def _far_end(pipe, pt, tol=0.01):
    """Extremidade do tubo OPOSTA a pt (a que nao esta no ponto de juncao)."""
    loc = pipe.Location
    if not isinstance(loc, LocationCurve):
        return None
    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)
    if p0.DistanceTo(pt) < tol:
        return p1
    if p1.DistanceTo(pt) < tol:
        return p0
    return None


def _make_tee(c1, c2, c3, pipes=None, point=None):
    """Cria a juncao da passagem c1-c2 com ramal c3.

    Retorna 'tee', 'wye' ou None.

    NewTeeFitting so aceita ramal perto de 90 graus — a 45 ele levanta
    "the angle between them is too small or too large", MESMO com o Wye
    configurado nas routing preferences do tipo. Nesse caso a juncao em angulo
    e montada na mao (ver Snippets._mep_angled_junction).

    Sem nenhuma das duas, religa a passagem reta e devolve None: o ramal fica
    encostado, para acabamento manual. A excecao so sobe se nem a religacao
    funcionar (a juncao inteira reverte).
    """
    try:
        revit.doc.Create.NewTeeFitting(c1, c2, c3)
        return 'tee'
    except Exception:
        pass

    if pipes and point is not None and len(pipes) == 3:
        try:
            branch_dir = c3.CoordinateSystem.BasisZ
        except Exception:
            branch_dir = None
        if branch_dir is not None:
            try:
                if create_angled_junction(pipes[0], pipes[1], pipes[2],
                                          point, branch_dir) is not None:
                    return 'wye'
            except Exception:
                pass

    c1.ConnectTo(c2)
    return None


def _collinear_pair(members):
    """(i, j, k) onde i e j sao o par colinear OPOSTO e k e o ramal.

    ``members`` e uma lista de (rotulo, direcao_para_dentro) — a direcao que o
    tubo segue a partir do ponto de juncao. Dois tubos formam a passagem reta
    do te quando essas direcoes sao opostas. None se nao houver par.
    """
    n = len(members)
    for i in range(n):
        for j in range(i + 1, n):
            if members[i][1].DotProduct(members[j][1]) < -0.9:
                for k in range(n):
                    if k != i and k != j:
                        return i, j, k
    return None


def _find_junction(branch, bconn, others):
    """Melhor juncao para a ponta livre do ramal. Retorna dict ou None.

    kind:
      'tee_split' — cruzamento no MEIO de um tubo: divide e cria te
      'junction'  — cruzamento na ponta dos tubos. ``legs`` traz os que chegam
                    ao ponto com ponta livre: 1 leg vira joelho, 2 legs viram
                    te (prumada partida em dois segmentos, por exemplo)
    """
    loc = branch.Location
    if not isinstance(loc, LocationCurve):
        return None
    u = _outward_dir(branch, bconn)
    if u is None:
        return None

    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)
    fixed_pt = p1 if bconn.Origin.DistanceTo(p0) < 0.01 else p0
    cur_len = fixed_pt.DistanceTo(bconn.Origin)

    interiors = []   # (chave, tubo, pt, pt_no_ramal, gap)
    crossings = []   # (chave, pt, pt_no_ramal, gap)

    for other in others:
        if other.Id == branch.Id or not other.IsValidObject:
            continue
        oloc = other.Location
        if not isinstance(oloc, LocationCurve):
            continue
        a = oloc.Curve.GetEndPoint(0)
        b = oloc.Curve.GetEndPoint(1)
        ovec = b - a
        mlen = ovec.GetLength()
        if mlen < 1e-6:
            continue
        v = ovec.Normalize()
        if abs(v.DotProduct(u)) > TEE_PARALLEL_DOT:
            continue

        cp = _closest_points(fixed_pt, u, a, v)
        if cp is None:
            continue
        pt_branch, pt_other, s, t = cp

        gap = pt_branch.DistanceTo(pt_other)
        if gap > TEE_PULL_MAX:
            continue
        if s < SPLIT_END_MARGIN:
            continue  # sobraria menos ramal que a margem, ou cruzamento atras
        branch_adjust = abs(s - cur_len)
        if branch_adjust > AXIAL_MAX:
            continue
        # Papel invertido: se o cruzamento cai no MEIO do proprio branch, quem
        # atravessa e o outro tubo — este aqui e o tronco. Sem esta guarda o
        # tronco se apresentava como ramal, o cruzamento caia fora do tubo
        # curto (logo nao era 'interior'), virava joelho, e o tronco era
        # encurtado ate o ponto: um tronco de 10 ft perdia 5 ft e ganhava um
        # joelho onde o certo era um te. Deixar passar so o sentido correto
        # tambem torna o resultado independente da ordem da selecao.
        if SPLIT_END_MARGIN <= s <= cur_len - SPLIT_END_MARGIN:
            continue

        if SPLIT_END_MARGIN <= t <= mlen - SPLIT_END_MARGIN:
            interiors.append(((gap, branch_adjust), other, pt_other,
                              pt_branch, gap))
        else:
            crossings.append(((gap, branch_adjust), pt_other, pt_branch, gap))

    # Te por divisao vence: se ha tubo continuando dos dois lados, e te.
    if interiors:
        interiors.sort(key=lambda x: x[0])
        _, main, pt, pt_branch, gap = interiors[0]
        return {'kind': 'tee_split', 'main': main, 'pt': pt,
                'pt_branch': pt_branch, 'gap': gap}

    if not crossings:
        return None

    # O cruzamento cai na ponta dos tubos. Quem chega ali nao depende de qual
    # tubo o laco elegeu como ramal: varrer TODOS (inclusive os colineares ao
    # ramal, que a busca por cruzamento nao ve) e montar a juncao pelos eixos.
    crossings.sort(key=lambda x: x[0])
    _, pt, pt_branch, gap = crossings[0]

    legs = _legs_at_point(pt, others, branch.Id)
    if not legs:
        return None

    return {'kind': 'junction', 'pt': pt, 'pt_branch': pt_branch, 'gap': gap,
            'legs': legs[:2]}


def _angulo_de_chegada(branch, main, pt):
    """Angulo em graus com que o ramal chega ao tronco, ou None."""
    try:
        bloc, mloc = branch.Location, main.Location
        if not (isinstance(bloc, LocationCurve) and isinstance(mloc, LocationCurve)):
            return None
        b0, b1 = bloc.Curve.GetEndPoint(0), bloc.Curve.GetEndPoint(1)
        m0, m1 = mloc.Curve.GetEndPoint(0), mloc.Curve.GetEndPoint(1)
        # direcao do ramal a partir do cruzamento, para o lado que fica
        longe = b0 if b0.DistanceTo(pt) > b1.DistanceTo(pt) else b1
        u = (longe - pt)
        v = (m1 - m0)
        if u.GetLength() < 1e-9 or v.GetLength() < 1e-9:
            return None
        cos = abs(u.Normalize().DotProduct(v.Normalize()))
        cos = max(-1.0, min(1.0, cos))
        return math.degrees(math.acos(cos))
    except Exception:
        return None


def _angulo_entre_eixos(branch, main):
    """Angulo em graus entre os eixos dos dois tubos, em [0, 90].

    Nao depende de haver cruzamento: e so a direcao de um contra a do outro.
    Medir pelo cruzamento fazia a conferencia do giro falhar exatamente
    quando ele dava certo — o tubo girava para o angulo pedido, o ponto de
    encontro saia de onde estava, e sem cruzamento nao havia o que medir.
    """
    try:
        bl, ml = branch.Location, main.Location
        if not (isinstance(bl, LocationCurve) and isinstance(ml, LocationCurve)):
            return None
        u = bl.Curve.GetEndPoint(1) - bl.Curve.GetEndPoint(0)
        v = ml.Curve.GetEndPoint(1) - ml.Curve.GetEndPoint(0)
        if u.GetLength() < 1e-9 or v.GetLength() < 1e-9:
            return None
        cos = abs(u.Normalize().DotProduct(v.Normalize()))
        return math.degrees(math.acos(max(-1.0, min(1.0, cos))))
    except Exception:
        return None


def _planos_de_angulo(branch, main, pt):
    """[(id, texto)] dizendo o que resolveria um cruzamento sem peca.

    Sem isto o usuario so via o contador `no_tee` subir: o cruzamento estava
    certo, faltava peca para aquele angulo, e nada dizia qual.
    """
    ang = _angulo_de_chegada(branch, main, pt)
    if ang is None:
        return []
    try:
        from Snippets._mep_angle_fix import explicar as explicar_angulo
        linhas = explicar_angulo(ang, branch)
    except Exception:
        return []
    return [(get_id_val(branch.Id), " ".join(l.strip() for l in linhas))]


def detectar_angulos_fora(elements):
    """Cruzamentos cujo angulo nao tem peca no catalogo.

    Devolve [{'branch','main','pt','theta','planos','id'}]. Roda FORA da
    Transaction principal para que a pergunta ao usuario possa ser feita antes
    — girar um tubo que o projetista desenhou nunca acontece sozinho.

    `angulos_de_juncao` mede as familias instanciando, o que exige uma
    Transaction ativa: quem chama abre uma so para medir (nada e alterado).
    """
    achados = []
    tubos = [e for e in _vivos(elements) if is_pipe(e)]
    for branch in tubos:
        if not _in_scope(branch):
            continue
        for bconn in get_free_connectors(branch):
            job = _find_junction(branch, bconn, tubos)
            if not job or job.get('kind') != 'tee_split':
                continue
            main, pt = job['main'], job['pt']
            theta = _angulo_de_chegada(branch, main, pt)
            if theta is None:
                continue
            try:
                from Snippets._mep_angle_fix import (
                    avaliar, angulos_de_juncao, angulos_de_joelho)
                juncoes = angulos_de_juncao(branch)
                joelhos = angulos_de_joelho(branch)
            except Exception:
                continue
            if not juncoes:
                continue
            planos = avaliar(theta, juncoes, joelhos)
            if planos and planos[0]['tipo'] == 'direto':
                continue                 # o angulo ja serve: nada a avisar
            achados.append({'branch': branch, 'main': main, 'pt': pt,
                            'theta': theta, 'planos': planos,
                            'id': get_id_val(branch.Id)})
            break
    return achados


def _sistema_valido(pipe):
    """Tipo de sistema para os trechos novos. Ver _mep_common.system_type_id."""
    return _tipo_de_sistema(pipe, revit.doc)


def _inserir_joelho_de_ajuste(branch, main, pt, plano):
    """Recua o ramal e emenda um trecho que chega ao tronco no angulo certo.

    Em vez de girar o tubo que o projetista desenhou, mete-se uma curva: o
    ramal e encurtado ate J e de J sai um trecho ate P' no tronco, fazendo com
    ele o angulo que a juncao exige. O joelho em J tem dobra ``|theta-alvo|``.

        J  = pt + d*u                        (recuo pelo eixo do ramal)
        t  = d * sin(theta) / sin(alvo)      (comprimento do trecho)
        P' = J - t*w,  w = cos(alvo)*v + sin(alvo)*n

    O trecho novo fica com a ponta livre em P' cruzando o tronco no angulo
    bom — quem monta o wye/te ali e a fase 0b, logo em seguida.

    Retorna o tubo novo, ou None.
    """
    doc = revit.doc
    alvo = plano.get('alvo')
    theta = plano.get('theta')
    if not alvo or not theta:
        return None

    try:
        bloc, mloc = branch.Location, main.Location
        b0, b1 = bloc.Curve.GetEndPoint(0), bloc.Curve.GetEndPoint(1)
        m0, m1 = mloc.Curve.GetEndPoint(0), mloc.Curve.GetEndPoint(1)
    except Exception:
        return None

    ancora = b0 if b0.DistanceTo(pt) > b1.DistanceTo(pt) else b1
    u = ancora - pt
    v = m1 - m0
    if u.GetLength() < 1e-9 or v.GetLength() < 1e-9:
        return None
    u = u.Normalize()
    v = v.Normalize()

    # v no mesmo semiplano de u, para o angulo medido bater com theta
    if u.DotProduct(v) < 0:
        v = v.Negate()
    n = u - v.Multiply(u.DotProduct(v))
    if n.GetLength() < 1e-9:
        return None
    n = n.Normalize()

    t_rad = math.radians(theta)
    a_rad = math.radians(alvo)
    if abs(math.sin(a_rad)) < 1e-9 or abs(math.sin(t_rad)) < 1e-9:
        return None

    # recuo escolhido para o trecho nascer com folga para as pecas
    folga = max(0.25, 2.0 * branch.Diameter)
    recuo = folga * math.sin(a_rad) / math.sin(t_rad)
    if recuo + folga > ancora.DistanceTo(pt):
        return None                    # ramal curto demais para recuar

    ponto_j = pt + u.Multiply(recuo)
    comp_trecho = recuo * math.sin(t_rad) / math.sin(a_rad)
    w = v.Multiply(math.cos(a_rad)) + n.Multiply(math.sin(a_rad))
    ponto_p = ponto_j - w.Multiply(comp_trecho)

    sistema = _sistema_valido(branch)
    if sistema is None:
        return None

    sub = SubTransaction(doc)
    sub.Start()
    try:
        if not _set_free_end(branch, pt, ponto_j):
            raise Exception("nao consegui recuar o ramal")
        doc.Regenerate()

        novo = Pipe.Create(doc, sistema, branch.PipeType.Id,
                           branch.ReferenceLevel.Id, ponto_p, ponto_j)
        try:
            from Autodesk.Revit.DB import BuiltInParameter
            novo.get_Parameter(
                BuiltInParameter.RBS_PIPE_DIAMETER_PARAM).Set(branch.Diameter)
        except Exception:
            pass
        doc.Regenerate()

        c_ramal = _get_endpoint_conn(branch, ponto_j)
        c_novo = _get_endpoint_conn(novo, ponto_j)
        if not (c_ramal and c_novo):
            raise Exception("conectores do joelho de ajuste nao encontrados")
        doc.Create.NewElbowFitting(c_ramal, c_novo)
        doc.Regenerate()

        sub.Commit()
        return novo
    except Exception:
        sub.RollBack()
        return None


def angle_fix_pass(elements, autorizados, ja_avisados=None):
    """Ajusta os ramais que o usuario autorizou, ate um angulo que tenha peca.

    ``autorizados``: {id_do_ramal: plano}, onde plano vem de
    _mep_angle_fix.avaliar e traz 'tipo' ('joelho' ou 'rotacao') e 'alvo'.
    Sem entrada aqui nada e tocado — a fase inteira e um no-op.

    'joelho' e sempre preferido: mete uma curva e o tubo desenhado fica onde
    esta. 'rotacao' gira o proprio tubo e so acontece com autorizacao, quando
    nenhuma dobra do catalogo resolve.

    O giro e em torno da normal ao plano dos dois tubos, passando pela ponta
    ANCORADA do ramal, para a ponta livre varrer ate o angulo pedido. O
    sentido do giro sai da medicao: gira, mede de novo e, se piorou, desfaz e
    gira para o outro lado.
    """
    if not autorizados:
        return elements, 0, []

    doc = revit.doc
    feitos = 0
    novos = []
    recusas = []
    for branch in [e for e in _vivos(elements) if is_pipe(e)]:
        bid = get_id_val(branch.Id)
        plano = autorizados.get(bid)
        if not plano:
            continue
        if isinstance(plano, dict):
            alvo = plano.get('alvo')
        else:
            alvo = plano                    # compatibilidade: so o angulo
            plano = {'tipo': 'rotacao', 'alvo': alvo}
        if not alvo:
            continue
        alvos = [e for e in _vivos(elements) if is_pipe(e) and
                 get_id_val(e.Id) != bid]
        job = None
        for bconn in get_free_connectors(branch):
            job = _find_junction(branch, bconn, alvos)
            if job and job.get('kind') == 'tee_split':
                break
            job = None
        if job is None:
            recusas.append((bid, "nao achei cruzamento no meio de outro tubo "
                                 "para este ramal"))
            continue

        main, pt = job['main'], job['pt']
        theta = _angulo_de_chegada(branch, main, pt)
        if theta is None:
            recusas.append((bid, "nao consegui medir o angulo de chegada"))
            continue

        # Preferencia: curva antes de mexer no tubo desenhado.
        if plano.get('tipo') == 'joelho':
            plano_completo = dict(plano)
            plano_completo['theta'] = theta
            novo = _inserir_joelho_de_ajuste(branch, main, pt, plano_completo)
            if novo is not None:
                novos.append(novo)
                feitos += 1
                if ja_avisados is not None:
                    ja_avisados.add(bid)
                continue
            recusas.append((bid, "joelho de ajuste nao coube; tentando girar"))
            # nao coube: segue para o giro, que o usuario tambem autorizou

        try:
            bloc = branch.Location
            mloc = main.Location
            b0, b1 = bloc.Curve.GetEndPoint(0), bloc.Curve.GetEndPoint(1)
            m0, m1 = mloc.Curve.GetEndPoint(0), mloc.Curve.GetEndPoint(1)
            # Onde pivotar:
            #
            # Girar pela ponta distante faz a ponta livre varrer um arco e
            # DEIXAR de cruzar o tronco — com 22,5 graus isso ja basta para
            # perder o encontro. Pivotar no proprio ponto de cruzamento
            # preserva o encontro e so muda o angulo, que e o que se quer.
            #
            # So que isso move a ponta oposta: se ela estiver ligada na rede,
            # o giro tem de ser em torno dela, ou a ligacao se rompe.
            distante = b0 if b0.DistanceTo(pt) > b1.DistanceTo(pt) else b1
            oposta = _get_endpoint_conn(branch, distante)
            presa = bool(oposta is not None and oposta.IsConnected)
            pivo = distante if presa else pt
            u = (distante - pt)
            v = (m1 - m0)
            normal = u.CrossProduct(v)
            if normal.GetLength() < 1e-9:
                continue
            eixo = Line.CreateUnbound(pivo, normal.Normalize())
        except Exception:
            continue

        delta = math.radians(alvo - theta)
        sub = SubTransaction(doc)
        sub.Start()
        try:
            ElementTransformUtils.RotateElement(doc, branch.Id, eixo, delta)
            doc.Regenerate()
            novo_ang = _angulo_entre_eixos(branch, main)
            if novo_ang is not None and abs(novo_ang - alvo) <= 0.5:
                sub.Commit()
                feitos += 1
                if ja_avisados is not None:
                    ja_avisados.add(bid)   # o giro foi pedido; nao e desvio
                continue
            recusas.append((bid, "girei {:+.1f} e o angulo virou {} (queria "
                                 "{:g})".format(
                                     math.degrees(delta),
                                     "{:.1f}".format(novo_ang)
                                     if novo_ang is not None
                                     else "indefinido (ficou paralelo?)",
                                     alvo)))
            # sentido errado: volta e gira para o outro lado
            sub.RollBack()
            sub2 = SubTransaction(doc)
            sub2.Start()
            try:
                ElementTransformUtils.RotateElement(doc, branch.Id, eixo, -delta)
                doc.Regenerate()
                ang2 = _angulo_entre_eixos(branch, main)
                if ang2 is not None and abs(ang2 - alvo) <= 0.5:
                    sub2.Commit()
                    feitos += 1
                    if ja_avisados is not None:
                        ja_avisados.add(bid)
                else:
                    sub2.RollBack()
                    recusas.append((bid, "no outro sentido virou {}".format(
                        "{:.1f}".format(ang2) if ang2 is not None
                        else "indefinido")))
            except Exception as erro:
                sub2.RollBack()
                recusas.append((bid, "giro reverso falhou: {}".format(erro)))
        except Exception as erro:
            sub.RollBack()
            recusas.append((bid, "giro falhou: {}".format(erro)))

    elements = _vivos(list(elements) + novos)
    return elements, feitos, recusas


def junction_pass(elements):
    """Fase 0b — cria a conexao no cruzamento da ponta livre de um ramal.

    Cobre as tres formas do "Aparar/Estender" nativo:
      te por divisao (cruzamento no meio de um tubo),
      te no vao (prumada partida em dois segmentos),
      joelho no canto (dois tubos nao paralelos terminando no mesmo ponto).

    Retorna (elementos + metades novas, n_tes, n_joelhos, n_sem_te).
    """
    result = list(elements)
    tees = 0
    wyes = 0
    elbows = 0
    no_tee = 0
    no_tee_planos = []

    for branch in [e for e in _vivos(elements) if is_pipe(e) and _in_scope(e)]:
        if not branch.IsValidObject:
            continue
        # Uma ponta por vez: cada juncao altera a geometria do ramal.
        for _ in range(2):
            frees = get_free_connectors(branch)
            if not frees:
                break

            found = None
            for bconn in frees:
                others = [e for e in result if is_pipe(e) and e.IsValidObject]
                job = _find_junction(branch, bconn, others)
                if job:
                    found = (bconn, job)
                    break
            if not found:
                break

            bconn, job = found
            pt = job['pt']
            free_origin = bconn.Origin
            new_main = None

            sub = SubTransaction(revit.doc)
            sub.Start()
            try:
                if job['gap'] > 0.001:
                    delta = pt - job['pt_branch']
                    ElementTransformUtils.MoveElement(revit.doc, branch.Id, delta)
                    free_origin = free_origin + delta

                if not _set_free_end(branch, free_origin, pt):
                    raise Exception("nao foi possivel aparar/estender o ramal")

                if job['kind'] == 'tee_split':
                    main = job['main']
                    new_main = _break_curve(main, pt)
                    if new_main is None:
                        raise Exception("BreakCurve falhou no tubo principal")
                    c1 = _get_endpoint_conn(main, pt)
                    c2 = _get_endpoint_conn(new_main, pt)
                    c3 = _get_endpoint_conn(branch, pt)
                    if not (c1 and c2 and c3):
                        raise Exception("conectores do cruzamento nao achados")
                    feito = _make_tee(c1, c2, c3,
                                      pipes=(main, new_main, branch), point=pt)
                    if feito == 'wye':
                        wyes += 1
                    elif feito:
                        tees += 1
                    else:
                        no_tee += 1
                        no_tee_planos.extend(
                            _planos_de_angulo(branch, main, pt))

                else:
                    # Direcao que cada tubo segue A PARTIR do ponto: e ela que
                    # diz quem forma a passagem reta do te.
                    far = _far_end(branch, pt)
                    if far is None:
                        raise Exception("ramal nao termina no ponto de juncao")
                    members = [(branch, (far - pt).Normalize())]

                    for leg_pipe, end_pt, far_pt, _adj in job['legs']:
                        if not _set_free_end(leg_pipe, end_pt, pt):
                            raise Exception("nao foi possivel ajustar o tubo")
                        members.append((leg_pipe, (far_pt - pt).Normalize()))

                    conns = []
                    for member, _dir in members:
                        c = _get_endpoint_conn(member, pt)
                        if c is None:
                            raise Exception("conector da juncao nao encontrado")
                        conns.append(c)

                    if len(members) == 2:
                        if members[0][1].DotProduct(members[1][1]) < -0.9:
                            # Colineares e opostos: nao e canto, e emenda reta.
                            # A Fase 2 conecta melhor (sem inventar joelho).
                            raise Exception("tubos colineares — nao e canto")
                        # Dois tubos nao paralelos terminando no ponto: joelho.
                        # Sem fallback — perpendiculares nao se ligam sem fitting.
                        revit.doc.Create.NewElbowFitting(conns[0], conns[1])
                        elbows += 1
                    else:
                        pair = _collinear_pair(members)
                        if pair is None:
                            raise Exception("sem passagem reta para o te")
                        i, j, k = pair
                        trio = (members[i][0], members[j][0], members[k][0])
                        feito = _make_tee(conns[i], conns[j], conns[k],
                                          pipes=trio, point=pt)
                        if feito == 'wye':
                            wyes += 1
                        elif feito:
                            tees += 1
                        else:
                            no_tee += 1

                sub.Commit()
            except Exception:
                sub.RollBack()
                break

            if new_main is not None:
                result.append(new_main)

    return result, tees, wyes, elbows, no_tee, no_tee_planos


# ---------------------------------------------------------------------------
# Pareamento por proximidade
# ---------------------------------------------------------------------------

def _outward_dir(pipe, conn):
    """Direcao unitaria do tubo apontando para fora na extremidade do conector."""
    loc = pipe.Location
    if not isinstance(loc, LocationCurve):
        return None
    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)
    if conn.Origin.DistanceTo(p0) < 0.01:
        v = p0 - p1
    elif conn.Origin.DistanceTo(p1) < 0.01:
        v = p1 - p0
    else:
        return None
    if v.GetLength() < 0.001:
        return None
    return v.Normalize()


def _order_pipe_fitting(pipe, pipe_conn, fitting, fitting_conn):
    """Par (movido, conn, alvo, conn, long_range) para tubo x fitting.

    Move quem esta MENOS ancorado: um tubo solto desce ate o fitting da rede,
    em vez de arrastar o fitting (e o que estiver atras dele) ate o tubo.
    Empate mantem o fitting como movel — e o caso do tubo que acabou de ser
    ancorado por um te nesta mesma execucao, onde mexer no tubo desfaria a
    conexao recem-criada.
    """
    if count_connected(pipe) < count_connected(fitting):
        return (pipe, pipe_conn, fitting, fitting_conn, False)
    return (fitting, fitting_conn, pipe, pipe_conn, False)


def _ha_intermediario(conn_a, conn_b, all_free, i, j):
    """True se ha conector livre de OUTRO elemento no caminho entre os dois.

    Sem esta guarda o pareamento SALTA POR CIMA de um segmento existente:
    com o alcance ampliado para puxar conexoes (PULL_DIST), um fitting
    alcancava o tubo do outro lado e ligava direto, deixando o tubo do meio
    duplicado e orfao.

    Criterio: k esta no caminho quando ir de A ate B passando por k custa
    praticamente o mesmo que ir direto (desigualdade triangular quase
    degenerada) — vale para qualquer direcao, sem precisar projetar.
    """
    origem_a, origem_b = conn_a.Origin, conn_b.Origin
    direto = origem_a.DistanceTo(origem_b)
    if direto < 1e-6:
        return False
    id_a = get_id_val(all_free[i][0].Id)
    id_b = get_id_val(all_free[j][0].Id)
    for k, (elem_k, conn_k) in enumerate(all_free):
        if k == i or k == j:
            continue
        id_k = get_id_val(elem_k.Id)
        if id_k == id_a or id_k == id_b:
            continue
        d_ak = origem_a.DistanceTo(conn_k.Origin)
        d_kb = conn_k.Origin.DistanceTo(origem_b)
        if d_ak < 1e-6 or d_kb < 1e-6:
            continue
        if d_ak + d_kb <= direto * 1.05:
            return True
    return False


def _proximity_pass(all_free, used, pairs, accept):
    """Uma passada de pareamento por proximidade (< MAX_DIST).

    So forma pares em que ``accept(elem_a, elem_b)`` retorna True. Compartilha
    ``used`` e ``pairs`` entre passadas para dar prioridade a certos tipos de
    par (ex: fittings antes de pipe-pipe).
    """
    for i, (elem_a, conn_a) in enumerate(all_free):
        if i in used:
            continue
        # best_key = (0 se antiparalelo / 1 se nao, distancia): conector
        # FRENTE A FRENTE vence mesmo mais distante — evita casar com o lado
        # errado de um fitting coaxial (ex: clamp com tubo atravessando: o
        # conector coincidente aponta na MESMA direcao e reverteria o tubo).
        best_j, best_key = None, (2, PULL_DIST)

        for j, (elem_b, conn_b) in enumerate(all_free):
            if j <= i or j in used:
                continue
            if elem_b.Id == elem_a.Id:
                continue
            if not accept(elem_a, elem_b):
                continue
            if _are_split_siblings(elem_a, elem_b):
                continue  # religaria a prumada, deixando o fitting de fora
            if not _in_scope(elem_a, elem_b):
                continue  # dois vizinhos de contexto: nao e para mexer neles
            dist = conn_a.Origin.DistanceTo(conn_b.Origin)
            # Com fitting no par vale puxar de mais longe: usar a conexao que
            # ja existe tem prioridade sobre criar uma nova. Entre dois tubos
            # o limite continua 1" — ali criar fitting e a resposta certa.
            limite = MAX_DIST if (is_pipe(elem_a) and is_pipe(elem_b)) else PULL_DIST
            if dist >= limite:
                continue
            # nao saltar por cima de quem esta no meio do caminho
            if _ha_intermediario(conn_a, conn_b, all_free, i, j):
                continue
            dot = _facing_dot(conn_a, conn_b)
            anti = dot < -0.9
            # Par NAO frente a frente exige rotacao de um dos lados.
            # Tubo nao rotaciona; fitting so rotaciona se estiver LIVRE.
            # Rejeitar aqui deixa os conectores para a Fase 2 (eixo), que
            # encontra o conector CERTO do outro lado do fitting.
            if not anti:
                a_pipe = is_pipe(elem_a)
                b_pipe = is_pipe(elem_b)
                if a_pipe and b_pipe:
                    continue
                if a_pipe or b_pipe:
                    fitting = elem_b if a_pipe else elem_a
                    if _is_anchored(fitting):
                        continue
            key = (0 if anti else 1, dist)
            if key < best_key:
                # sentido: nao casar com conector do lado errado (reverteria tubo)
                if not _pair_safe_direction(elem_a, conn_a, elem_b, conn_b):
                    continue
                ok, _ = validate_connectors_compatible(conn_a, conn_b, allow_connected=False)
                if ok:
                    best_key = key
                    best_j = j

        if best_j is None:
            continue

        used.add(i)
        used.add(best_j)
        elem_b, conn_b = all_free[best_j]

        a_pipe = is_pipe(elem_a)
        b_pipe = is_pipe(elem_b)

        if a_pipe and not b_pipe:
            pairs.append(_order_pipe_fitting(elem_a, conn_a, elem_b, conn_b))
        elif b_pipe and not a_pipe:
            pairs.append(_order_pipe_fitting(elem_b, conn_b, elem_a, conn_a))
        elif a_pipe and b_pipe:
            # pipe-pipe: moved = A, target = B (execution tenta elongar ambas direcoes)
            pairs.append((elem_a, conn_a, elem_b, conn_b, False))
        else:
            # fitting-fitting: move o menos ancorado (mais conectores livres)
            if count_free(elem_a) >= count_free(elem_b):
                pairs.append((elem_a, conn_a, elem_b, conn_b, False))
            else:
                pairs.append((elem_b, conn_b, elem_a, conn_a, False))


def find_pairs(elements):
    """Retorna pares (moved_elem, moved_conn, target_elem, target_conn, long_range).

    Fase 1 — proximidade: conectores livres a menos de 1" um do outro.
    Prioridade: primeiro pares que envolvem fitting (conector de conexao),
    depois pipe-pipe — assim um fitting desconectado nao fica de fora porque
    dois tubos proximos casaram entre si antes.
    Fase 2 — eixo: conector livre de tubo alinhado com outro conector livre
    distante (ate AXIAL_MAX ft) na direcao do proprio eixo — ex: prumada com
    vao ate o fitting acima. Esses pares conectam por elongacao do tubo.
    """
    all_free = []
    for elem in elements:
        for conn in get_free_connectors(elem):
            all_free.append((elem, conn))

    used = set()
    pairs = []

    # ---- Fase 1a: proximidade envolvendo fitting (prioridade) ----
    _proximity_pass(all_free, used, pairs,
                    lambda a, b: not (is_pipe(a) and is_pipe(b)))

    # ---- Fase 1b: proximidade pipe-pipe (o que sobrou) ----
    _proximity_pass(all_free, used, pairs,
                    lambda a, b: is_pipe(a) and is_pipe(b))

    # ---- Fase 2: alinhamento por eixo (so tubos como origem) ----
    for i, (elem_a, conn_a) in enumerate(all_free):
        if i in used or not is_pipe(elem_a):
            continue
        axis = _outward_dir(elem_a, conn_a)
        if axis is None:
            continue

        # Aparar sobreposicao pequena, sim; comer o tubo, nao. Alem deste
        # limite o conector esta no meio do tubo e o caso e de divisao.
        try:
            comprimento = elem_a.Location.Curve.Length
            max_overlap = max(0.0, min(MAX_ENCURTAR, comprimento - 0.05))
        except Exception:
            max_overlap = 0.0

        best_j, best_abs = None, AXIAL_MAX
        for j, (elem_b, conn_b) in enumerate(all_free):
            if j == i or j in used:
                continue
            if elem_b.Id == elem_a.Id:
                continue
            if _are_split_siblings(elem_a, elem_b):
                continue
            if not _in_scope(elem_a, elem_b):
                continue
            # a Fase 2 alcanca ate 10 ft: sem esta guarda ela salta por cima
            # de segmentos inteiros que estao no meio do caminho
            if _ha_intermediario(conn_a, conn_b, all_free, i, j):
                continue
            v = conn_b.Origin - conn_a.Origin
            t = v.DotProduct(axis)
            # t > 0: vao a frente da ponta livre (tubo estica)
            # t < 0: conector DENTRO do tubo (sobreposto — tubo encurta ate ele)
            if t > AXIAL_MAX or t < -max_overlap:
                continue
            if abs(t) >= best_abs:
                continue
            perp = (v - axis.Multiply(t)).GetLength()
            if perp > AXIAL_PERP_TOL:
                continue
            try:
                ang = conn_b.CoordinateSystem.BasisZ.AngleTo(axis)
            except Exception:
                continue
            if abs(ang - math.pi) > AXIAL_ANGLE_TOL:
                continue
            ok, _ = validate_connectors_compatible(conn_a, conn_b, allow_connected=False)
            if not ok:
                continue
            best_abs = abs(t)
            best_j = j

        if best_j is None:
            continue

        used.add(i)
        used.add(best_j)
        elem_b, conn_b = all_free[best_j]
        # tubo sempre como moved — conexao por elongacao, sem mover o alvo
        pairs.append((elem_a, conn_a, elem_b, conn_b, True))

    return pairs


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------

def has_connectors(elem):
    """True se o elemento expoe ConnectorManager (e candidato a conexao)."""
    if elem is None:
        return False
    try:
        get_connector_manager(elem)
        return True
    except AttributeError:
        return False


def pairing_loop(elements, slope_avisos, slope_ja_avisado):
    """Fases 1 e 2: conecta o que JA existe, do mais proximo para o resto.

    Extraido de connect_batch para poder rodar DUAS vezes: antes das fases
    que criam fitting (prioridade a quem ja esta encostado) e de novo depois
    delas (fechar o que a criacao deixou solto).

    Retorna (elements, conectados, fundidos, falhas).
    """
    connected = 0
    merged = 0
    failed = 0

    for _ in range(MAX_PASSES):
        elements = [e for e in elements if e.IsValidObject]
        pairs = find_pairs(elements)
        if not pairs:
            break

        round_connected = 0
        round_merged = 0
        round_failed = 0

        for moved_elem, moved_conn, target_elem, target_conn, long_range in pairs:
            try:
                # Tentativa 1: elongar tubo (preserva rede)
                #
                # Em par de LONGO ALCANCE mover esta proibido (arrastaria o
                # tubo pelo vao em vez de estica-lo), entao esticar e a unica
                # saida — e ali nao se pode exigir que a ponta oposta esteja
                # na rede: dois tubos soltos separados por um vao tinham as
                # quatro tentativas recusadas e o par virava falha.
                ok = False
                anchor = not long_range
                if is_pipe(moved_elem):
                    ok = elongate_and_connect(moved_elem, moved_conn, target_conn,
                                              require_anchored=anchor)

                # Tentativa 2: elongar o OUTRO lado — inclusive quando o movel
                # e um fitting. Elongar mexe so num tubo; mover o fitting
                # arrasta a cadeia atras dele e come o tubo da ancora. Entre as
                # duas, elongar sempre perturba menos o modelo.
                #
                # So e seguro porque elongate_and_connect recusa alvo FORA do
                # eixo: com desalinhamento perpendicular, elongar nao alinharia
                # nada e a conexao sairia torta — ali mover e a resposta certa.
                if not ok and is_pipe(target_elem):
                    ok = elongate_and_connect(target_elem, target_conn,
                                              moved_conn,
                                              require_anchored=anchor)

                # Tentativa 3 — PUXAR sem girar. Quando os conectores ja estao
                # frente a frente e so falta encostar, translacao pura resolve:
                # arrasta junto o que estiver conectado atras, preserva a
                # inclinacao e nao esbarra na trava de rotacao. Sem este passo
                # a ferramenta apenas ligava logicamente conectores afastados,
                # deixando a rede torta.
                if not ok and not long_range:
                    if _facing_dot(moved_conn, target_conn) <= FACING_TOL:
                        movel, m_conn, alvo_conn = moved_elem, moved_conn, target_conn
                        # puxa quem tem menos rede atras de si
                        if count_connected(target_elem) < count_connected(moved_elem):
                            movel, m_conn, alvo_conn = target_elem, target_conn, moved_conn
                        original_slope = 0.0
                        if is_pipe(movel):
                            original_slope = measure_pipe_slope(movel, m_conn.Origin)
                        ok = connect_elements_no_rotate(movel, m_conn, alvo_conn,
                                                        auto_disconnect=True)
                        if ok:
                            rel = apply_and_verify_slope(movel, alvo_conn,
                                                         original_slope)
                            aviso = describe_slope_report(rel)
                            mid = get_id_val(movel.Id)
                            slope_ja_avisado.add(mid)
                            if aviso:
                                slope_avisos.append("id {}: {}".format(mid, aviso))

                # Fallback: mover + rotacionar — NUNCA em par de longo
                # alcance (arrastaria o elemento pelo vao em vez de esticar
                # o tubo). Rotacao so em elemento LIVRE: rotacionar elemento
                # ancorado quebra a rede ("nao e possivel manter a
                # conectividade") ou inverte tubo ("direcao oposta").
                if not ok and not long_range:
                    needs_rotation = _facing_dot(moved_conn,
                                                 target_conn) > FACING_TOL
                    if needs_rotation and _is_anchored(moved_elem):
                        pass  # sem rotacao segura; deixa como falha
                    else:
                        # Medir ANTES: connect_elements rotaciona o tubo ate
                        # o eixo do alvo e achataria um tubo inclinado.
                        original_slope = 0.0
                        if is_pipe(moved_elem):
                            original_slope = measure_pipe_slope(
                                moved_elem, moved_conn.Origin)
                        ok = connect_elements(moved_elem, moved_conn,
                                              target_conn,
                                              auto_disconnect=True)
                        if ok:
                            rel = apply_and_verify_slope(
                                moved_elem, target_conn, original_slope)
                            aviso = describe_slope_report(rel)
                            mid = get_id_val(moved_elem.Id)
                            slope_ja_avisado.add(mid)
                            if aviso:
                                slope_avisos.append(
                                    "id {}: {}".format(mid, aviso))

                if ok:
                    round_connected += 1
                    # Pipe-pipe colinear mesmo tipo/diametro: fundir em um so
                    if try_merge_collinear(moved_elem, target_elem):
                        round_merged += 1
                else:
                    round_failed += 1
            except Exception:
                round_failed += 1

        connected += round_connected
        merged += round_merged
        # So a ultima passada conta como falha: o que falhou numa passada e
        # foi resolvido na seguinte nao e falha, e o que falha sempre seria
        # contado varias vezes.
        failed = round_failed

        if round_connected == 0:
            break

    return elements, connected, merged, failed


def _foto_dos_tubos(elements):
    """{id: comprimento} dos tubos vivos — para saber quem some e onde."""
    foto = {}
    for elem in elements:
        try:
            if elem is None or not elem.IsValidObject or not is_pipe(elem):
                continue
            loc = elem.Location
            if isinstance(loc, LocationCurve):
                foto[get_id_val(elem.Id)] = round(loc.Curve.Length, 3)
        except Exception:
            pass
    return foto


def _perdas(antes, depois, fase, registro):
    """Anota os tubos que existiam antes da fase e sumiram depois.

    Um segmento apagado e a falha mais cara desta ferramenta: o usuario perde
    modelagem e so descobre olhando o modelo. Saber QUAL fase comeu o tubo e a
    diferenca entre corrigir em minutos e passar rodadas adivinhando.
    """
    for pid, comp in antes.items():
        if pid not in depois:
            registro.append((pid, "{}: sumiu um tubo de {:.0f} mm".format(
                fase, comp * 304.8)))


def connect_batch(elements, required=None, jog_angle=None,
                  takeoff_angle=None, rotacoes=None):
    """Resolve as ligacoes entre os elementos dados. REQUER Transaction ativa.

    Roda as quatro fases na ordem (0, 0b, 1, 2) e repete o pareamento ate
    MAX_PASSES enquanto houver progresso — mover um elemento pode trazer para
    dentro do alcance conectores que estavam de fora.

    ``jog_angle``: quando dado (graus), tubos paralelos desalinhados frente a
    frente recebem um desvio de dois joelhos nesse angulo. A escolha vem de
    fora — o motor nao abre dialogo.

    ``takeoff_angle``: quando dado (graus), ramal paralelo com ponta solta ao
    lado de um tronco continuo recebe derivacao — joelho no ramal e Wye/Te no
    tronco. Tambem escolhido de fora.

    ``required``: lista/set de elementos (ou de ids) que precisam participar de
    toda ligacao. Os demais entram apenas como CONTEXTO — util para quem passa
    a vizinhanca junto e nao quer que dois vizinhos se conectem entre si. None
    (padrao) trata todos como iguais.

    Retorna dict com: tees, elbows, splits, connected, merged, failed, no_tee,
    elements (a lista original mais as metades criadas por divisao).
    """
    global _REQUIRED_IDS

    SPLIT_SIBLINGS.clear()

    if required is None:
        _REQUIRED_IDS = None
    else:
        ids = set()
        for item in required:
            try:
                ids.add(get_id_val(item.Id))
            except AttributeError:
                try:
                    ids.add(get_id_val(item))
                except Exception:
                    pass
        _REQUIRED_IDS = ids

    elements = [e for e in elements if has_connectors(e)]

    connected = 0
    merged = 0
    failed = 0
    fases_com_erro = []
    tubos_perdidos = []     # segmentos que sumiram, e em qual fase
    slope_avisos = []       # conexoes onde o Revit nao respeitou a inclinacao
    slope_ja_avisado = set()   # ids com aviso pontual, para o diff nao repetir

    # Foto da inclinacao de tudo que pode ser arrastado, antes de comecar.
    # Uma unica foto no inicio e um diff no fim cobrem TODAS as fases, inclusive
    # as que nao tem verificacao pontual (split, tee, elongacao).
    snap_inicial = snapshot_network_slopes(elements, max_elements=200)

    # PRIORIDADE 1 — ligar o que JA existe e esta encostado. Isto vem antes de
    # qualquer fase que CRIE fitting: com a ordem invertida, uma rede colada
    # com dezenas de conectores coincidentes (distancia zero) ganhava tes e
    # joelhos novos em cima de conexoes que so precisavam ser fechadas.
    # Cada fase protegida por si: uma falha isolada nao pode derrubar a
    # Transaction e apagar o que as outras ja fizeram.
    try:
        _antes = _foto_dos_tubos(elements)
        elements, c1, m1, f1 = pairing_loop(elements, slope_avisos, slope_ja_avisado)
        _perdas(_antes, _foto_dos_tubos(elements), "fase 1 (pareamento)", tubos_perdidos)
        connected += c1
        merged += m1
        failed = f1
    except Exception:
        fases_com_erro.append("pareamento (1a passada)")

    # Fase 1r: pontas ja encostadas, mas de diametros diferentes — falta a
    # bucha. Vem logo apos o pareamento para que o par nao chegue as fases de
    # criacao e vire te ou joelho.
    try:
        _antes = _foto_dos_tubos(elements)
        elements, reducers, reducer_recusas = reducer_pass(elements)
        _perdas(_antes, _foto_dos_tubos(elements), "fase 1r (bucha)", tubos_perdidos)
    except Exception:
        reducers = 0
        reducer_recusas = []
        fases_com_erro.append("bucha de reducao (fase 1r)")

    # Fase 0: te/cruzeta livre sobre o eixo de um tubo — divide e conecta.
    try:
        _antes = _foto_dos_tubos(elements)
        elements, splits, split_connected = split_pass(elements)
        _perdas(_antes, _foto_dos_tubos(elements), "fase 0 (divisao sob fitting)", tubos_perdidos)
        connected += split_connected
    except Exception:
        splits = 0
        fases_com_erro.append("divisao sob te/cruzeta (fase 0)")

    # Fase 0c: conjunto montado SOBRE um tubo continuo — dois cortes, remove o
    # trecho interno e emenda.
    try:
        _antes = _foto_dos_tubos(elements)
        (elements, series, series_connected,
         series_recusas) = series_pass(elements)
        _perdas(_antes, _foto_dos_tubos(elements), "fase 0c (serie)", tubos_perdidos)
        connected += series_connected
    except Exception:
        series = 0
        series_recusas = []
        fases_com_erro.append("insercao em serie (fase 0c)")

    # Fase 0a: girar os ramais que o usuario AUTORIZOU girar. Vem antes da
    # 0b para que o cruzamento ja chegue la num angulo que tenha peca.
    try:
        elements, girados, girar_recusas = angle_fix_pass(
            elements, rotacoes, ja_avisados=slope_ja_avisado)
    except Exception:
        girados = 0
        girar_recusas = []
        fases_com_erro.append("ajuste de angulo (fase 0a)")

    # Fase 0b: ponta livre de ramal cruzando outro tubo — te, wye ou joelho.
    try:
        _antes = _foto_dos_tubos(elements)
        (elements, tees, wyes, elbows, no_tee,
         no_tee_planos) = junction_pass(elements)
        _perdas(_antes, _foto_dos_tubos(elements), "fase 0b (juncao)", tubos_perdidos)
    except Exception:
        tees = wyes = elbows = no_tee = 0
        no_tee_planos = []
        fases_com_erro.append("juncao no cruzamento (fase 0b)")

    # PRIORIDADE 2 — de novo o pareamento, agora fechando o que as fases de
    # criacao deixaram solto.
    try:
        elements, c2, m2, f2 = pairing_loop(elements, slope_avisos, slope_ja_avisado)
        connected += c2
        merged += m2
        failed = f2
    except Exception:
        fases_com_erro.append("pareamento (2a passada)")

    # Fase 0d: desvio de dois joelhos — POR ULTIMO, so nas pontas que
    # sobraram. Rodando antes, ele consumia pontas livres que as fases de
    # proximidade resolveriam melhor, e saia ligando tubos distantes com um
    # trecho atravessando a montagem inteira.
    try:
        elements, jogs, jog_skips = jog_pass(elements, jog_angle,
                                            in_scope=_in_scope)
    except Exception:
        jogs, jog_skips = 0, []
        fases_com_erro.append("desvio de dois joelhos (fase 0d)")

    # Fase 0e: derivacao para tronco continuo — joelho no ramal, Wye/Te no
    # tronco. Ultimo recurso, junto com o desvio: so no que sobrou.
    try:
        elements, takeoffs, takeoff_skips = takeoff_pass(
            elements, takeoff_angle, in_scope=_in_scope)
    except Exception:
        takeoffs, takeoff_skips = 0, []
        fases_com_erro.append("derivacao para tronco (fase 0e)")

    # Fusao final: pares colineares JA ligados, que nunca viravam par no laco
    # acima por nao terem conector livre (prumada que chegou partida).
    try:
        _antes = _foto_dos_tubos(elements)
        elements, merged_extra, merge_recusas = merge_pass(elements)
        _perdas(_antes, _foto_dos_tubos(elements), "fusao final", tubos_perdidos)
        merged += merged_extra
    except Exception:
        # fusao e limpeza: se falhar, o que ja foi conectado tem de sobreviver
        merge_recusas = []
        fases_com_erro.append("fusao de colineares")

    _REQUIRED_IDS = None  # nao vazar o escopo para a proxima chamada

    # Diff final da vizinhanca. Os avisos pontuais ja cobrem os tubos movidos
    # de proposito; aqui aparece quem foi arrastado sem ninguem pedir.
    slope_ids = []
    for alterado in diff_network_slopes(revit.doc, snap_inicial,
                                        ignore_ids=slope_ja_avisado):
        texto = describe_network_change(alterado)
        if texto:
            slope_avisos.append(texto)
            slope_ids.append(alterado['id'])

    return {
        'tees': tees,
        'wyes': wyes,
        'jogs': jogs,
        'takeoffs': takeoffs,
        'takeoff_skips': takeoff_skips,
        'merge_recusas': merge_recusas,
        'fases_com_erro': fases_com_erro,
        'tubos_perdidos': tubos_perdidos,
        'jog_skips': jog_skips,
        'elbows': elbows,
        'splits': splits,
        'reducers': reducers,
        'reducer_recusas': reducer_recusas,
        'series': series,
        'series_recusas': series_recusas,
        'connected': connected,
        'merged': merged,
        'failed': failed,
        'no_tee': no_tee,
        'no_tee_planos': no_tee_planos,
        'girados': girados,
        'girar_recusas': girar_recusas,
        'slope_avisos': slope_avisos,
        'slope_ids': slope_ids,      # para reinclinar depois, fora da Transaction
        'elements': elements,
    }


def format_summary(res):
    """Linha unica de resumo para balao/output."""
    # `no_tee` era so contado: o cruzamento certo, mas sem peca no catalogo
    # para aquele angulo (22.5 e 60 graus, por exemplo, quando as routing
    # preferences so trazem te de 90 e wye de 45). A ferramenta recusava em
    # silencio e o usuario ficava sem saber por que nada aconteceu.
    linha = ("{} te(s) | {} wye(s) | {} joelho(s) | {} bucha(s) | "
             "{} desvio(s) | "
             "{} derivacao(oes) | {} dividido(s) | {} em serie | "
             "{} conectado(s) | {} fundido(s) | {} falha(s)").format(
        res['tees'], res.get('wyes', 0), res['elbows'],
        res.get('reducers', 0), res.get('jogs', 0),
        res.get('takeoffs', 0),
        res['splits'], res.get('series', 0), res['connected'],
        res['merged'], res['failed'])
    n = len(res.get('slope_avisos') or [])
    if n:
        linha += " | {} com inclinacao alterada".format(n)
    if res.get('no_tee'):
        linha += (" | {} cruzamento(s) sem peca para o angulo".format(
            res['no_tee']))
    if res.get('girados'):
        linha += " | {} tubo(s) girado(s)".format(res['girados'])
    return linha


def did_anything(res):
    """False quando nenhuma fase encontrou nada para fazer."""
    return bool(res['splits'] or res.get('series') or res['tees'] or
                res['elbows'] or res['no_tee'] or res['connected'] or
                res['failed'] or res.get('wyes') or res.get('jogs') or
                res.get('takeoffs') or res.get('reducers') or
                res.get('girados'))


def vizinhos_fora_da_selecao(elements, raio=MAX_DIST):
    """Conectores livres encostados em elementos que NAO foram selecionados.

    Sem isto, esquecer um tubo na selecao produz exatamente o mesmo sintoma
    de um bug: conectores coincidentes que ficam soltos, sem nenhuma
    explicacao. Aqui a ferramenta olha em volta e diz o que faltou pegar.
    """
    doc = revit.doc
    dentro = set()
    for e in elements:
        try:
            dentro.add(get_id_val(e.Id))
        except Exception:
            pass

    achados = []
    for elem in elements:
        if elem is None or not elem.IsValidObject:
            continue
        for conn in get_free_connectors(elem):
            origem = conn.Origin
            try:
                outline = Outline(
                    XYZ(origem.X - raio, origem.Y - raio, origem.Z - raio),
                    XYZ(origem.X + raio, origem.Y + raio, origem.Z + raio))
                perto = (FilteredElementCollector(doc)
                         .WherePasses(BoundingBoxIntersectsFilter(outline))
                         .WhereElementIsNotElementType().ToElements())
            except Exception:
                continue
            for viz in perto:
                try:
                    vid = get_id_val(viz.Id)
                except Exception:
                    continue
                if vid in dentro:
                    continue
                for cv in get_free_connectors(viz):
                    dist = cv.Origin.DistanceTo(origem)
                    if dist > raio:
                        continue
                    ok, _msg = validate_connectors_compatible(
                        conn, cv, allow_connected=False)
                    if not ok:
                        continue
                    achados.append((get_id_val(elem.Id), vid, dist))
                    break
    # um aviso por vizinho, o mais proximo
    melhor = {}
    for meu, dele, dist in achados:
        if dele not in melhor or dist < melhor[dele][1]:
            melhor[dele] = (meu, dist)
    return [(meu, dele, dist) for dele, (meu, dist) in melhor.items()]


def _fmt_pt(p):
    return "[{:.3f}, {:.3f}, {:.3f}]".format(p.X, p.Y, p.Z)


def diagnose(elements):
    """Linhas explicando por que NADA foi conectado.

    Nao reimplementa as regras: mede as mesmas grandezas que as fases usam
    (distancia entre conectores, desvio do eixo, posicao do cruzamento) e
    mostra cada uma contra o seu limite, para dar para ver qual estourou.
    """
    linhas = []
    elements = [e for e in elements if e is not None and e.IsValidObject]

    livres = []
    for elem in elements:
        frees = get_free_connectors(elem)
        try:
            cat = elem.Category.Name if elem.Category else "?"
        except Exception:
            cat = "?"
        linhas.append("- `{}` {} — {} conector(es) livre(s){}".format(
            get_id_val(elem.Id), cat, len(frees),
            "" if not frees else ": " + ", ".join(
                _fmt_pt(c.Origin) for c in frees)))
        for conn in frees:
            livres.append((elem, conn))

    if not livres:
        linhas.append("")
        linhas.append("**Nenhum conector livre em nada que foi selecionado** — "
                      "nao ha o que conectar.")
        # Fase 0d: tubos paralelos desalinhados (desvio de dois joelhos)
    try:
        from Snippets._mep_offset_jog import (
            find_offset_pairs, MIN_OFFSET as JOG_MIN, MAX_OFFSET as JOG_MAX,
            MAX_GAP as JOG_GAP)
        pares_jog = find_offset_pairs([e for e in _vivos(elements) if is_pipe(e)])
    except Exception:
        pares_jog = []
    if pares_jog:
        try:
            from Snippets._mep_offset_jog import (
                feasibility as jog_feas, advance_for as jog_adv,
                available_angles as jog_angs)
        except Exception:
            jog_feas = None
        linhas.append("")
        linhas.append("**Fase 0d:** {} par(es) paralelo(s) desalinhado(s) — "
                      "caso de desvio com dois joelhos:".format(len(pares_jog)))
        for par in pares_jog:
            linhas.append("  - `{}` + `{}`: offset {:.1f} mm, vao {:.1f} mm, "
                          "tubos de {:.2f} e {:.2f} ft"
                          .format(get_id_val(par['pipe_a'].Id),
                                  get_id_val(par['pipe_b'].Id),
                                  par['offset'] * 304.8, par['vao'] * 304.8,
                                  par['len_a'], par['len_b']))
            if jog_feas is None:
                continue
            for ang in jog_angs(par['pipe_a']):
                cabe, falta, motivo = jog_feas(par, ang)
                linhas.append("      {:g} graus (avanca {:.0f} mm): {}".format(
                    ang, jog_adv(par['offset'], ang) * 304.8,
                    "cabe" if cabe else ("NAO cabe — " + (motivo or "?"))))

    # Fase 0e: derivacao para tronco
    try:
        from Snippets._mep_branch_takeoff import explicar as explicar_takeoff
        linhas.append("")
        linhas.extend(explicar_takeoff([e for e in _vivos(elements) if is_pipe(e)]))
    except Exception:
        pass

    # Fusao: pares ligados que poderiam virar um tubo so
    pares_lig = []
    tubos_todos2 = [e for e in _vivos(elements) if is_pipe(e)]
    for i in range(len(tubos_todos2)):
        for j in range(i + 1, len(tubos_todos2)):
            a, b = tubos_todos2[i], tubos_todos2[j]
            try:
                if _sao_vizinhos_ligados(a, b):
                    pares_lig.append((a, b))
            except Exception:
                pass
    if pares_lig:
        linhas.append("")
        linhas.append("**Fusao:** {} par(es) ligado(s) ponta a ponta:".format(
            len(pares_lig)))
        for a, b in pares_lig:
            try:
                motivo = _motivo_nao_fundiu(a, b)
            except Exception:
                motivo = "nao consegui avaliar"
            linhas.append("  - `{}` + `{}`: {}".format(
                get_id_val(a.Id), get_id_val(b.Id), motivo))

    # Fase 1: menor distancia entre conectores livres de elementos diferentes
    melhor = None
    for i, (elem_a, conn_a) in enumerate(livres):
        for elem_b, conn_b in livres[i + 1:]:
            if elem_b.Id == elem_a.Id:
                continue
            dist = conn_a.Origin.DistanceTo(conn_b.Origin)
            if melhor is None or dist < melhor[0]:
                melhor = (dist, elem_a, elem_b)

    linhas.append("")
    if melhor is None:
        linhas.append("**Fase 1:** os conectores livres sao todos do mesmo "
                      "elemento — nao ha par possivel.")
    else:
        dist, elem_a, elem_b = melhor
        linhas.append(
            "**Fase 1** (conectores a menos de 1\"): menor distancia = "
            "**{:.4f} ft ({:.1f} mm)** entre `{}` e `{}` — limite {:.4f} ft. {}"
            .format(dist, dist * 304.8, get_id_val(elem_a.Id),
                    get_id_val(elem_b.Id), MAX_DIST,
                    "Dentro." if dist < MAX_DIST else "**Fora por {:.1f} mm.**"
                    .format((dist - MAX_DIST) * 304.8)))

    # Fase 0b: cruzamento entre a ponta livre de um tubo e outro tubo
    tubos = [e for e in _vivos(elements) if is_pipe(e)]
    achou_cruzamento = False
    for branch in tubos:
        for bconn in get_free_connectors(branch):
            u = _outward_dir(branch, bconn)
            if u is None:
                continue
            loc = branch.Location
            if not isinstance(loc, LocationCurve):
                continue
            p0 = loc.Curve.GetEndPoint(0)
            p1 = loc.Curve.GetEndPoint(1)
            fixed_pt = p1 if bconn.Origin.DistanceTo(p0) < 0.01 else p0
            cur_len = fixed_pt.DistanceTo(bconn.Origin)

            for other in tubos:
                if other.Id == branch.Id:
                    continue
                oloc = other.Location
                if not isinstance(oloc, LocationCurve):
                    continue
                a = oloc.Curve.GetEndPoint(0)
                b = oloc.Curve.GetEndPoint(1)
                ovec = b - a
                mlen = ovec.GetLength()
                if mlen < 1e-6:
                    continue
                v = ovec.Normalize()

                cabeca = "`{}` x `{}`".format(get_id_val(branch.Id),
                                              get_id_val(other.Id))
                if abs(v.DotProduct(u)) > TEE_PARALLEL_DOT:
                    continue  # paralelos: nao ha cruzamento a reportar
                cp = _closest_points(fixed_pt, u, a, v)
                if cp is None:
                    continue
                pt_branch, pt_other, s, t = cp
                gap = pt_branch.DistanceTo(pt_other)
                ajuste = abs(s - cur_len)
                achou_cruzamento = True

                motivos = []
                if gap > TEE_PULL_MAX:
                    motivos.append(
                        "eixos passam a **{:.3f} ft um do outro** (limite "
                        "{:.1f} ft) — estao em planos diferentes".format(
                            gap, TEE_PULL_MAX))
                if s < SPLIT_END_MARGIN:
                    motivos.append(
                        "cruzamento cai atras da ponta fixa do ramal "
                        "(s={:.3f})".format(s))
                if ajuste > AXIAL_MAX:
                    motivos.append(
                        "o ramal teria de andar **{:.2f} ft** (limite "
                        "{:.0f} ft)".format(ajuste, AXIAL_MAX))
                if not (SPLIT_END_MARGIN <= t <= mlen - SPLIT_END_MARGIN):
                    fora = -t if t < 0 else t - mlen
                    motivos.append(
                        "cruzamento cai **{:.3f} ft fora** do outro tubo "
                        "(comprimento {:.3f} ft) — seria te no vao ou "
                        "joelho".format(fora, mlen))

                linhas.append("")
                linhas.append("**Fase 0b** {}: gap {:.4f} ft | ajuste do ramal "
                              "{:.3f} ft | cruzamento em t={:.3f} de {:.3f}"
                              .format(cabeca, gap, ajuste, t, mlen))
                if motivos:
                    for m in motivos:
                        linhas.append("  - " + m)
                else:
                    linhas.append("  - dentro de todos os limites — deveria "
                                  "ter criado te; verificar conectores livres "
                                  "e compatibilidade de diametro")

    if not achou_cruzamento and tubos:
        linhas.append("")
        linhas.append("**Fase 0b:** nenhum par de tubos selecionados se cruza "
                      "(todos paralelos entre si, ou sem ponta livre).")

    # Fase 0: exige fitting com DOIS conectores livres opostos (passagem reta)
    fittings = [e for e in _vivos(elements) if not is_pipe(e)]
    for fitting in fittings:
        n_livres = len(get_free_connectors(fitting))
        linhas.append("")
        if n_livres < 2:
            linhas.append(
                "**Fase 0** `{}`: tem {} conector(es) livre(s) — precisa de 2 "
                "opostos (passagem reta) para dividir um tubo. Nao se aplica."
                .format(get_id_val(fitting.Id), n_livres))
            continue

        info = _through_axis(fitting)
        if info is None:
            linhas.append(
                "**Fase 0** `{}`: tem {} conectores livres, mas **nenhum par "
                "deles e oposto e colinear** — nao ha passagem reta para "
                "atravessar um tubo. Saidas em angulo (joelho/te ja usado) nao "
                "servem para dividir.".format(get_id_val(fitting.Id), n_livres))
            continue

        centro, eixo, _ca, _cb = info
        host = _find_host_pipe(centro, eixo, [e for e in elements
                                              if is_pipe(e)])
        if host is None:
            linhas.append(
                "**Fase 0** `{}`: tem passagem reta livre, mas nenhum tubo "
                "selecionado e paralelo a ela e a atravessa dentro das "
                "margens.".format(get_id_val(fitting.Id)))
        else:
            perp, pipe, _proj = host
            linhas.append(
                "**Fase 0** `{}`: passagem reta sobre `{}` a {:.4f} ft do eixo "
                "— dentro dos limites, deveria ter dividido.".format(
                    get_id_val(fitting.Id), get_id_val(pipe.Id), perp))

    # Fase 0c: conjunto em serie (dois fittings abracando um trecho)
    tubos_todos = [e for e in _vivos(elements) if is_pipe(e)]
    for (elem_a, _ca, org_a, elem_b, _cb, org_b, eixo,
         span) in _series_candidates(elements):
        cabeca = "`{}` + `{}`".format(get_id_val(elem_a.Id),
                                      get_id_val(elem_b.Id))
        host = _host_for_series(org_a, org_b, eixo, tubos_todos)
        linhas.append("")
        if host is not None:
            pipe, t_lo, t_hi = host
            linhas.append(
                "**Fase 0c** {}: conjunto de {:.3f} ft sobre `{}` — cortes em "
                "t={:.3f} e t={:.3f}. Dentro dos limites.".format(
                    cabeca, span, get_id_val(pipe.Id), t_lo, t_hi))
            continue

        linhas.append("**Fase 0c** {}: par de conectores livres opostos "
                      "(conjunto de {:.3f} ft), mas nenhum tubo selecionado "
                      "serve de hospedeiro:".format(cabeca, span))
        for pipe in tubos_todos:
            loc = pipe.Location
            if not isinstance(loc, LocationCurve):
                continue
            p0 = loc.Curve.GetEndPoint(0)
            p1 = loc.Curve.GetEndPoint(1)
            vec = p1 - p0
            mlen = vec.GetLength()
            if mlen < 1e-6:
                continue
            direction = vec.Normalize()
            if abs(direction.DotProduct(eixo)) < SPLIT_AXIS_DOT:
                linhas.append("  - `{}`: nao e paralelo ao conjunto".format(
                    get_id_val(pipe.Id)))
                continue
            ts, perp_max = [], 0.0
            for org in (org_a, org_b):
                t = (org - p0).DotProduct(direction)
                perp_max = max(perp_max, (org - (p0 + direction.Multiply(t)))
                               .GetLength())
                ts.append(t)
            t_lo, t_hi = min(ts), max(ts)
            if perp_max > AXIAL_PERP_TOL:
                linhas.append(
                    "  - `{}`: conjunto **{:.4f} ft ({:.1f} mm) fora do eixo** "
                    "(limite {:.1f} mm) — alinhe o conjunto ao tubo antes"
                    .format(get_id_val(pipe.Id), perp_max, perp_max * 304.8,
                            AXIAL_PERP_TOL * 304.8))
            elif t_lo < SPLIT_END_MARGIN or t_hi > mlen - SPLIT_END_MARGIN:
                linhas.append(
                    "  - `{}`: cortes em t={:.3f}/{:.3f} caem fora do tubo "
                    "(0 a {:.3f}, margem {:.2f})".format(
                        get_id_val(pipe.Id), t_lo, t_hi, mlen,
                        SPLIT_END_MARGIN))

    # Fase 2: tubo com ponta livre alinhado com um conector livre distante
    for elem_a, conn_a in livres:
        if not is_pipe(elem_a):
            continue
        axis = _outward_dir(elem_a, conn_a)
        if axis is None:
            continue
        try:
            max_overlap = max(0.0, min(MAX_ENCURTAR,
                                       elem_a.Location.Curve.Length - 0.05))
        except Exception:
            max_overlap = 0.0

        for elem_b, conn_b in livres:
            if elem_b.Id == elem_a.Id:
                continue
            v = conn_b.Origin - conn_a.Origin
            t = v.DotProduct(axis)
            perp = (v - axis.Multiply(t)).GetLength()
            try:
                ang = conn_b.CoordinateSystem.BasisZ.AngleTo(axis)
            except Exception:
                ang = None

            motivos = []
            if t > AXIAL_MAX:
                motivos.append("alvo a **{:.2f} ft** a frente (limite {:.0f} ft)"
                               .format(t, AXIAL_MAX))
            if t < -max_overlap:
                motivos.append(
                    "alvo {:.3f} ft DENTRO do tubo — encurtar no maximo "
                    "{:.2f} ft; alem disso o conector esta no meio do tubo e "
                    "o caso e de DIVISAO (fase 0), nao de encurtar"
                    .format(-t, MAX_ENCURTAR))
            if perp > AXIAL_PERP_TOL:
                motivos.append(
                    "desvio do eixo **{:.4f} ft ({:.1f} mm)** — limite {:.4f} ft "
                    "({:.1f} mm). Elongar so alcanca a projecao; o alvo ficaria "
                    "de lado".format(perp, perp * 304.8, AXIAL_PERP_TOL,
                                     AXIAL_PERP_TOL * 304.8))
            if ang is not None and abs(ang - math.pi) > AXIAL_ANGLE_TOL:
                motivos.append("conectores nao estao frente a frente "
                               "({:.1f} graus, precisa ~180)".format(
                                   ang * 180.0 / math.pi))

            linhas.append("")
            linhas.append("**Fase 2** `{}` -> `{}`: distancia no eixo {:.3f} ft "
                          "| desvio {:.4f} ft".format(
                              get_id_val(elem_a.Id), get_id_val(elem_b.Id),
                              t, perp))
            if motivos:
                for m in motivos:
                    linhas.append("  - " + m)
            else:
                linhas.append("  - dentro de todos os limites — deveria ter "
                              "conectado; verificar diametro/compatibilidade")

    return linhas


def sum_results(acc, res):
    """Acumula o retorno de varias chamadas de connect_batch."""
    if acc is None:
        return dict(res)
    for key in ('tees', 'wyes', 'jogs', 'takeoffs', 'elbows', 'splits',
                'reducers', 'girados', 'series', 'connected', 'merged',
                'failed', 'no_tee'):
        acc[key] = acc.get(key, 0) + res.get(key, 0)
    acc['slope_avisos'] = (list(acc.get('slope_avisos') or []) +
                           list(res.get('slope_avisos') or []))
    acc['slope_ids'] = (list(acc.get('slope_ids') or []) +
                        list(res.get('slope_ids') or []))
    # listas de relatorio: sem acumular, o InsertKitBatch perdia os motivos
    # de cada alvo e so mostrava os do ultimo kit inserido.
    for key in ('merge_recusas', 'jog_skips', 'takeoff_skips',
                'reducer_recusas', 'fases_com_erro'):
        acc[key] = list(acc.get(key) or []) + list(res.get(key) or [])
    acc['elements'] = list(acc['elements']) + list(res['elements'])
    return acc
