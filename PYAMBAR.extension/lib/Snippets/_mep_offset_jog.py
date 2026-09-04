# -*- coding: utf-8 -*-
"""
_mep_offset_jog.py — desvio (jog) entre dois tubos paralelos desalinhados.

Duas pontas livres frente a frente, eixos paralelos mas deslocados
lateralmente: nao da para emendar reto. A solucao de obra e um desvio com
DOIS joelhos e um trecho entre eles.

O avanco que o desvio consome ao longo do eixo depende do angulo:

    avanco = offset / tan(angulo)

    90 graus -> 0            (trecho perpendicular)
    60 graus -> offset*0.577
    45 graus -> offset
    22.5     -> offset*2.414

O ``Bend Angle`` do joelho e read-only: o Revit deduz da geometria. Entao
basta criar o trecho na inclinacao certa e chamar NewElbowFitting.

REQUER Transaction ativa. A escolha do angulo e feita FORA daqui (o snippet
nao abre dialogo) e chega como parametro.
"""

import math
import re

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    BuiltInParameter, ElementId, Line, LocationCurve, RoutingPreferenceRuleGroupType,
    SubTransaction, XYZ
)
from Autodesk.Revit.DB.Plumbing import Pipe, PipingSystemType

from pyrevit import revit
from pyrevit.compat import get_elementid_value_func as _get_func
from Snippets._mep_common import advance_for, conn_at as _conn_at
from Snippets._mep_common import system_type_id as _tipo_de_sistema

get_id_val = _get_func()

PARALLEL_DOT = 0.999     # eixos paralelos
FACING_DOT = -0.9        # pontas livres frente a frente
MIN_OFFSET = 1.0 / 12.0  # ft (25 mm) — abaixo disso NAO e desvio: nenhum
                         # joelho de obra tem essa dimensao, e o que o Revit
                         # montaria seria geometria degenerada. Caso de
                         # alinhar (a Fase 1 puxa), nao de dois joelhos.
MAX_OFFSET = 2.0         # ft (~600 mm) — acima disso nao e um desvio de obra,
                         # sao redes distintas. Com 10 ft a ferramenta chegou a
                         # ligar pontas a 1.18 m atravessando a montagem toda.
MAX_GAP = 4.0            # ft — distancia maxima entre as duas pontas livres
MIN_STUB = 0.25          # ft — sobra minima de tubo depois de encurtar
CONNECT_TOL = 0.02       # ft
PERP_DOT = 0.05          # |dA . dB| — pontas perpendiculares (~90 graus)
CORNER_MIN_TRECHO = 0.5  # ft (152 mm) — vao minimo entre os dois joelhos
                         # do canto. Medido no modelo real: um canto de
                         # 0.813 ft deixou 0.443 ft (135 mm) de tubo entre
                         # joelhos de 51 mm — ~56 mm por joelho.
CORNER_MAX_ESTICAR = 6.0 # ft — esticar mais que isso nao e fechar canto,
                         # e inventar rede
ANGULOS_PADRAO = [90.0, 45.0, 22.5]
# Angulos de conexao usados na pratica — a busca no nome da familia so
# considera estes, para nao inventar valores de leitura ambigua.
ANGULOS_CANONICOS = [90.0, 60.0, 45.0, 30.0, 22.5, 11.25]


# ---------------------------------------------------------------------------
# Deteccao
# ---------------------------------------------------------------------------

def _free_end_info(pipe):
    """[(conector, ponta_livre, ponta_fixa, direcao_saida, comprimento)]."""
    loc = pipe.Location
    if not isinstance(loc, LocationCurve):
        return []
    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)
    saida = []
    try:
        conns = list(pipe.ConnectorManager.Connectors)
    except Exception:
        return []
    for conn in conns:
        if conn.IsConnected:
            continue
        if conn.Origin.DistanceTo(p0) < 0.01:
            livre, fixa = p0, p1
        elif conn.Origin.DistanceTo(p1) < 0.01:
            livre, fixa = p1, p0
        else:
            continue
        vec = livre - fixa
        if vec.GetLength() < 1e-9:
            continue
        saida.append((conn, livre, fixa, vec.Normalize(), vec.GetLength()))
    return saida


def find_offset_pairs(pipes):
    """Pares de tubos paralelos desalinhados que pedem um desvio.

    Cada item: dict com pipe_a/pipe_b (a = o mais CURTO, que sera preservado),
    os pontos das pontas livres, o eixo, o vetor de offset e o modulo dele.
    """
    dados = []
    for pipe in pipes:
        if not pipe.IsValidObject:
            continue
        for info in _free_end_info(pipe):
            dados.append((pipe,) + info)

    # Candidatos primeiro, escolha depois: pegar o primeiro par que aparece
    # fazia a ferramenta ligar tubos distantes atravessando a montagem, em vez
    # de fechar o que estava perto. Agora o mais proximo vence.
    candidatos = []
    for i in range(len(dados)):
        pipe_a, conn_a, livre_a, fixa_a, dir_a, len_a = dados[i]
        for j in range(i + 1, len(dados)):
            pipe_b, conn_b, livre_b, fixa_b, dir_b, len_b = dados[j]
            if pipe_b.Id == pipe_a.Id:
                continue
            # eixos paralelos e pontas apontando uma para a outra
            if abs(dir_a.DotProduct(dir_b)) < PARALLEL_DOT:
                continue
            if dir_a.DotProduct(dir_b) > FACING_DOT:
                continue
            # offset = componente perpendicular ao eixo
            entre = livre_b - livre_a
            ao_longo = entre.DotProduct(dir_a)
            perp = entre - dir_a.Multiply(ao_longo)
            offset = perp.GetLength()
            if offset < MIN_OFFSET or offset > MAX_OFFSET:
                continue
            if entre.GetLength() > MAX_GAP:
                continue   # pontas longe demais para isso ser um desvio
            try:
                if abs(pipe_a.Diameter - pipe_b.Diameter) > 1e-6:
                    continue  # diametros diferentes: precisa reducao, nao jog
            except Exception:
                continue

            # 'a' e sempre o tubo mais curto — e ele que sera preservado
            if len_a <= len_b:
                par = dict(pipe_a=pipe_a, conn_a=conn_a, livre_a=livre_a,
                           fixa_a=fixa_a, eixo=dir_a, len_a=len_a,
                           pipe_b=pipe_b, conn_b=conn_b, livre_b=livre_b,
                           fixa_b=fixa_b, len_b=len_b)
            else:
                par = dict(pipe_a=pipe_b, conn_a=conn_b, livre_a=livre_b,
                           fixa_a=fixa_b, eixo=dir_b, len_a=len_b,
                           pipe_b=pipe_a, conn_b=conn_a, livre_b=livre_a,
                           fixa_b=fixa_a, len_b=len_a)
            par['offset'] = offset
            # do ponto de vista do tubo 'a'
            entre2 = par['livre_b'] - par['livre_a']
            par['vao'] = entre2.DotProduct(par['eixo'])
            perp2 = entre2 - par['eixo'].Multiply(par['vao'])
            if perp2.GetLength() < 1e-9:
                continue
            par['offset_dir'] = perp2.Normalize()
            par['dist_pontas'] = entre.GetLength()
            candidatos.append((entre.GetLength(), i, j, par))

    # Guloso do mais proximo para o mais distante; cada ponta serve uma vez.
    candidatos.sort(key=lambda c: c[0])
    pares, usados = [], set()
    for _dist, i, j, par in candidatos:
        if i in usados or j in usados:
            continue
        usados.add(i)
        usados.add(j)
        pares.append(par)
    return pares


# ---------------------------------------------------------------------------
# Angulos disponiveis
# ---------------------------------------------------------------------------

def available_angles(pipe):
    """Angulos de joelho que a familia das routing preferences oferece.

    Le do NOME da familia (ex: Elbow-90_60_45_22_5-HxH-PVC_DWV). O Bend Angle
    e read-only na instancia, entao nao ha de onde ler a lista — o nome e a
    fonte pratica. Sem conseguir, devolve os padroes.
    """
    nomes = []
    try:
        rpm = pipe.PipeType.RoutingPreferenceManager
        n = rpm.GetNumberOfRules(RoutingPreferenceRuleGroupType.Elbows)
        for i in range(n):
            sym = revit.doc.GetElement(
                rpm.GetRule(RoutingPreferenceRuleGroupType.Elbows, i).MEPPartId)
            if sym is not None:
                nomes.append(sym.Family.Name)
    except Exception:
        pass

    angulos = set()
    for nome in nomes:
        angulos.update(_angulos_no_nome(nome))
    if not angulos:
        return list(ANGULOS_PADRAO)
    return sorted(angulos, reverse=True)


def _angulos_no_nome(nome):
    """Angulos reconhecidos no nome da familia.

    Nao da para varrer numeros soltos: em "Elbow-90_60_45_22_5" o "_" e ao
    mesmo tempo separador e virgula decimal, e uma leitura ingenua entende
    "45_22" como 45.22 sobrando um "5". Por isso procuramos apenas angulos
    canonicos de conexao, cada um nas grafias que aparecem na pratica.
    """
    achados = []
    for ang in ANGULOS_CANONICOS:
        for texto in _grafias(ang):
            # so digito bloqueia: "-" e "_" sao os separadores do proprio nome,
            # e o lookahead impede casar "45" dentro de "4507"
            if re.search(r'(?<!\d)' + re.escape(texto) + r'(?!\d)', nome):
                achados.append(ang)
                break
    return achados


def _grafias(ang):
    """Como o angulo costuma aparecer no nome: 22.5 vira 22_5, 22.5 ou 22-5."""
    if float(ang).is_integer():
        return ["{:g}".format(ang)]
    txt = "{:g}".format(ang)
    return [txt.replace(".", "_"), txt, txt.replace(".", "-")]


def feasibility(par, angle_deg):
    """(cabe, faltando, motivo) do desvio nesse angulo.

    O tubo 'a' (mais curto) fica intacto: o vertice nasce na ponta livre dele.
    Quem cede e o tubo 'b', que estica ou encurta ate o segundo vertice.
    """
    avanco = advance_for(par['offset'], angle_deg)
    # ponta de 'b' precisa ir para vao_alvo medido a partir da ponta de 'a'
    alvo = avanco
    desloc = alvo - par['vao']          # >0 encurta b, <0 estica b
    sobra_b = par['len_b'] - desloc
    if sobra_b < MIN_STUB:
        return False, MIN_STUB - sobra_b, (
            "o tubo de {:.2f} ft ficaria com {:.2f} ft".format(
                par['len_b'], max(0.0, sobra_b)))
    return True, 0.0, ""


# ---------------------------------------------------------------------------
# Execucao
# ---------------------------------------------------------------------------

def _system_type_id(pipe):
    """Tipo de sistema para os trechos novos. Ver _mep_common.system_type_id."""
    from Autodesk.Revit.DB import ElementId
    tipo = _tipo_de_sistema(pipe, revit.doc)
    return tipo if tipo is not None else ElementId.InvalidElementId


def _set_free_end(pipe, ponta_livre, novo_ponto):
    """Leva a ponta livre ate novo_ponto preservando a conexao da oposta."""
    loc = pipe.Location
    if not isinstance(loc, LocationCurve):
        return False
    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)
    if ponta_livre.DistanceTo(p0) < 0.02:
        fixa, livre_e_p0 = p1, True
    elif ponta_livre.DistanceTo(p1) < 0.02:
        fixa, livre_e_p0 = p0, False
    else:
        return False
    if fixa.DistanceTo(novo_ponto) < 0.02:
        return False
    # o novo ponto tem de ficar A FRENTE da ponta fixa: atras dela o tubo
    # inverte e o Revit invalida as conexoes ("direcao oposta")
    eixo = novo_ponto - fixa
    orig = ponta_livre - fixa
    if eixo.GetLength() < 1e-9 or orig.GetLength() < 1e-9:
        return False
    if eixo.Normalize().DotProduct(orig.Normalize()) < 0.9:
        return False
    try:
        if livre_e_p0:
            loc.Curve = Line.CreateBound(novo_ponto, fixa)
        else:
            loc.Curve = Line.CreateBound(fixa, novo_ponto)
    except Exception:
        return False
    return True


def create_jog(par, angle_deg):
    """Cria o desvio de dois joelhos. Retorna (tubo_intermediario, motivo).

    O motivo do fracasso volta junto: engolir a excecao e devolver so None
    fazia todo desvio falhado virar "falhou ao montar o desvio", sem dizer
    qual passo caiu — e sem isso nao da para depurar o caso.

    Vertice 1 fica na ponta livre do tubo curto (preservado); vertice 2 sai
    dali, avancando ``offset/tan(angulo)`` no eixo e ``offset`` na lateral.
    O tubo longo e levado ate o vertice 2. Tudo dentro de uma SubTransaction:
    se qualquer passo falhar, nada sobra.
    """
    doc = revit.doc
    ok, _falta, motivo = feasibility(par, angle_deg)
    if not ok:
        return None, motivo or "nao cabe"

    eixo = par['eixo']
    lado = par['offset_dir']
    if lado is None:
        return None, "nao consegui achar a direcao do desvio"
    avanco = advance_for(par['offset'], angle_deg)

    v1 = par['livre_a']
    v2 = v1 + eixo.Multiply(avanco) + lado.Multiply(par['offset'])

    pipe_a, pipe_b = par['pipe_a'], par['pipe_b']

    sub = SubTransaction(doc)
    sub.Start()
    try:
        # o tubo longo vai ate o vertice 2
        if not _set_free_end(pipe_b, par['livre_b'], v2):
            raise Exception("nao consegui levar o tubo maior ate o desvio")
        doc.Regenerate()

        # trecho intermediario, herdando tipo/sistema/nivel/diametro
        novo = Pipe.Create(doc, _system_type_id(pipe_a),
                           pipe_a.PipeType.Id, pipe_a.ReferenceLevel.Id, v1, v2)
        try:
            novo.get_Parameter(BuiltInParameter.RBS_PIPE_DIAMETER_PARAM).Set(
                pipe_a.Diameter)
        except Exception:
            pass
        doc.Regenerate()

        # dois joelhos: o Revit deduz o angulo da geometria
        c_a = _conn_at(pipe_a, v1)
        c_n1 = _conn_at(novo, v1)
        c_n2 = _conn_at(novo, v2)
        c_b = _conn_at(pipe_b, v2)
        if not (c_a and c_n1 and c_n2 and c_b):
            raise Exception("conectores do desvio nao encontrados")

        doc.Create.NewElbowFitting(c_a, c_n1)
        doc.Regenerate()
        c_n2 = _conn_at(novo, v2)
        c_b = _conn_at(pipe_b, v2)
        if not (c_n2 and c_b):
            raise Exception("segundo joelho sem conectores")
        doc.Create.NewElbowFitting(c_n2, c_b)
        doc.Regenerate()

        sub.Commit()
        return novo, ""
    except Exception as erro:
        sub.RollBack()
        return None, (str(erro) or erro.__class__.__name__)



# ---------------------------------------------------------------------------
# Canto: duas pontas livres PERPENDICULARES e nao coplanares
# ---------------------------------------------------------------------------
#
# Caso real (banca de test, 02/09/2026): ramal horizontal com ponta livre em
# [288.414, 198.391, 42.506] rumo +X, e prumada com topo livre em
# [290.452, 197.578, 42.313] rumo +Z. As pontas estao a 90 graus e as retas
# nao se cruzam — nenhuma fase existente cobre isso: a Fase 2 exige ~180
# graus e o jog exige eixos paralelos.
#
# Com dA e dB ortogonais, (dA, dB, n = dA x dB) e base ortonormal e o
# deslocamento entre as pontas vira tres numeros:
#
#     t = delta . dA      quanto A avanca no proprio eixo
#     s = -(delta . dB)   quanto B avanca no proprio eixo
#     k = delta . n       o trecho entre os dois joelhos
#
# Nada e MOVIDO: as duas pontas livres sao esticadas com _set_free_end, que
# preserva a conexao da ponta oposta. Decisao em _mep_batch_connect
# (_tem_ligacao): o que ja esta ligado nao sai do lugar.

def find_corner_pairs(pipes, in_scope=None):
    """Pares de pontas livres perpendiculares que fecham com um canto.

    Devolve (pares, recusas). O par traz t, s e k medidos; a recusa traz o
    motivo — sem ele o caso vira "nada a conectar", que nao diz o que
    corrigir.
    """
    infos = []
    for pipe in pipes:
        if in_scope is not None and not in_scope(pipe):
            continue
        for conn, livre, fixa, direcao, comp in _free_end_info(pipe):
            infos.append((pipe, conn, livre, direcao, comp))

    pares, recusas, candidatos = [], [], {}
    for i, (pa, ca, la, da, compa) in enumerate(infos):
        for j, (pb, cb, lb, db, compb) in enumerate(infos):
            if j <= i or pa.Id == pb.Id:
                continue
            chave = frozenset((get_id_val(pa.Id), get_id_val(pb.Id)))
            if abs(da.DotProduct(db)) > PERP_DOT:
                continue                   # nao e canto: paralelo ou obliquo
            try:
                if abs(ca.Radius - cb.Radius) > 0.01:
                    continue
            except Exception:
                continue

            n = da.CrossProduct(db)
            if n.GetLength() < 1e-9:
                continue
            n = n.Normalize()

            delta = lb - la
            t = delta.DotProduct(da)
            s = -delta.DotProduct(db)
            k = delta.DotProduct(n)

            # sobrou componente fora da base: as pontas nao fecham canto reto
            resto = delta - da.Multiply(t) + db.Multiply(s) - n.Multiply(k)
            if resto.GetLength() > CONNECT_TOL:
                continue

            motivo = ""
            if abs(k) < CORNER_MIN_TRECHO:
                motivo = ("trecho de {:.0f} mm entre os joelhos — minimo "
                          "{:.0f} mm".format(abs(k) * 304.8,
                                             CORNER_MIN_TRECHO * 304.8))
            elif t > CORNER_MAX_ESTICAR or s > CORNER_MAX_ESTICAR:
                motivo = ("esticaria {:.2f} ft / {:.2f} ft — limite {:.0f} ft"
                          .format(t, s, CORNER_MAX_ESTICAR))
            elif t < 0 and compa + t < MIN_STUB:
                motivo = ("o tubo {} ficaria com {:.2f} ft".format(
                    get_id_val(pa.Id), max(0.0, compa + t)))
            elif s < 0 and compb + s < MIN_STUB:
                motivo = ("o tubo {} ficaria com {:.2f} ft".format(
                    get_id_val(pb.Id), max(0.0, compb + s)))

            # Um tubo solto tem DUAS pontas livres, e so uma delas aponta para
            # o canto. Fixar a primeira combinacao que passa no alinhamento
            # descarta o par inteiro pela ponta errada — o mesmo erro que
            # find_takeoff_pairs documenta e evita. Guardar todas e escolher
            # depois.
            candidatos.setdefault(chave, []).append(
                (motivo, t, s,
                 {'pipe_a': pa, 'livre_a': la, 'dir_a': da, 'len_a': compa,
                  'pipe_b': pb, 'livre_b': lb, 'dir_b': db, 'len_b': compb,
                  'n': n, 't': t, 's': s, 'k': k}))

    for chave, achados in candidatos.items():
        bons = [c for c in achados if not c[0]]
        if bons:
            # o canto mais curto: menos tubo esticado, menos rede mexida
            bons.sort(key=lambda c: abs(c[1]) + abs(c[2]))
            pares.append(bons[0][3])
            continue
        # nenhuma combinacao serviu: relatar a que chegou mais perto, uma
        # unica vez por par — quatro recusas do mesmo par viram ruido
        achados.sort(key=lambda c: abs(c[1]) + abs(c[2]))
        motivo, _t, _s, par = achados[0]
        recusas.append((get_id_val(par['pipe_a'].Id),
                        "canto com {}: {}".format(
                            get_id_val(par['pipe_b'].Id), motivo)))
    return pares, recusas


def create_corner(par):
    """Fecha o canto: estica as duas pontas livres e monta os dois joelhos.

    Retorna (tubo_do_trecho, motivo). Tudo numa SubTransaction: se um passo
    falhar, nada sobra pela metade.
    """
    doc = revit.doc
    pa, pb = par['pipe_a'], par['pipe_b']
    v1 = par['livre_a'] + par['dir_a'].Multiply(par['t'])
    v2 = v1 + par['n'].Multiply(par['k'])

    sub = SubTransaction(doc)
    sub.Start()
    try:
        if not _set_free_end(pa, par['livre_a'], v1):
            raise Exception("nao consegui levar {} ate o canto".format(
                get_id_val(pa.Id)))
        if not _set_free_end(pb, par['livre_b'], v2):
            raise Exception("nao consegui levar {} ate o canto".format(
                get_id_val(pb.Id)))
        doc.Regenerate()

        novo = Pipe.Create(doc, _system_type_id(pa), pa.PipeType.Id,
                           pa.ReferenceLevel.Id, v1, v2)
        try:
            novo.get_Parameter(BuiltInParameter.RBS_PIPE_DIAMETER_PARAM).Set(
                pa.Diameter)
        except Exception:
            pass
        doc.Regenerate()

        c_a = _conn_at(pa, v1)
        c_n1 = _conn_at(novo, v1)
        if not (c_a and c_n1):
            raise Exception("primeiro joelho sem conectores")
        doc.Create.NewElbowFitting(c_a, c_n1)
        doc.Regenerate()

        c_n2 = _conn_at(novo, v2)
        c_b = _conn_at(pb, v2)
        if not (c_n2 and c_b):
            raise Exception("segundo joelho sem conectores")
        doc.Create.NewElbowFitting(c_n2, c_b)
        doc.Regenerate()

        sub.Commit()
        return novo, ""
    except Exception as erro:
        sub.RollBack()
        return None, (str(erro) or erro.__class__.__name__)


def corner_pass(elements, in_scope=None):
    """Fecha todos os cantos possiveis. (elementos, n_cantos, recusas)."""
    pipes = [e for e in elements if isinstance(e, Pipe) and e.IsValidObject]
    pares, recusas = find_corner_pairs(pipes, in_scope)
    resultado = list(elements)
    feitos = 0
    for par in pares:
        if not (par['pipe_a'].IsValidObject and par['pipe_b'].IsValidObject):
            continue
        novo, motivo = create_corner(par)
        if novo is None:
            recusas.append((get_id_val(par['pipe_a'].Id),
                            "canto com {}: {}".format(
                                get_id_val(par['pipe_b'].Id), motivo)))
            continue
        resultado.append(novo)
        feitos += 1
    return resultado, feitos, recusas


def jog_pass(elements, angle_deg, in_scope=None):
    """Cria o desvio em todos os pares desalinhados. (elementos, n_desvios).

    ``in_scope``: funcao opcional (elem_a, elem_b) -> bool. Quando dada, so
    monta desvio se o par estiver no escopo — sem isso a insercao de kit podia
    criar desvio entre dois vizinhos que so entraram como contexto.
    """
    if not angle_deg:
        return elements, 0, []

    pipes = [e for e in elements if e is not None and e.IsValidObject]
    resultado = list(elements)
    feitos = 0
    pulados = []

    for par in find_offset_pairs(pipes):
        if in_scope is not None and not in_scope(par['pipe_a'], par['pipe_b']):
            continue
        ok, falta, motivo = feasibility(par, angle_deg)
        if not ok:
            pulados.append((par['pipe_a'].Id, motivo))
            continue
        novo, motivo_falha = create_jog(par, angle_deg)
        if novo is None:
            pulados.append((par['pipe_a'].Id,
                            motivo_falha or "falhou ao montar o desvio"))
            continue
        feitos += 1
        resultado.append(novo)

    return resultado, feitos, pulados
