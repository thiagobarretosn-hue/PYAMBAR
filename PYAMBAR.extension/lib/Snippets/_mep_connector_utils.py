# -*- coding: utf-8 -*-
"""
Nome do arquivo: _mep_connector_utils.py
Localização: PYAMBAR(lab).extension/lib/Snippets/

Descrição:
Utilitários para trabalhar com conectores de elementos MEP (tubos, dutos, bandejas).
Funções para obter ConnectorManager, buscar conectores por proximidade e conectar elementos.

Autor: Thiago Barreto Sobral Nunes
Data: 23.10.2025
Versão: 2.0

Funções:
- get_connector_manager(element): Obtém ConnectorManager de elemento MEP
- get_connector_closest_to(connectors, xyz_point): Retorna conector mais próximo do ponto
- get_all_connectors(element): Retorna todos os conectores (usados e não usados)
- get_unused_connectors(element): Retorna apenas conectores não conectados
- connect_elements(doc, moved_element, moved_connector, target_connector): Conecta elementos
- MEPElementFilter: Classe de filtro para seleção de elementos MEP
"""

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from math import pi, sqrt
from System import Int64
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI.Selection import ISelectionFilter
from Autodesk.Revit.Exceptions import ArgumentsInconsistentException

from Snippets._slope_geometry import (
    SLOPE_INDETERMINADO, SLOPE_OK, SLOPE_VERIFY_TOL, describe_network_change,
    describe_slope_report, is_vertical, oriented_slope, resolve_connect_slope,
    signed_slope, slope_verdict
)

# describe_slope_report vive em _slope_geometry (puro, testado em CPython) e e
# reexportado daqui porque os call-sites o importam junto do resto da conexao.


def get_connector_manager(element):
    """
    Obtém o ConnectorManager de um elemento MEP.
    
    Args:
        element (Element): Elemento do Revit (Pipe, Duct, FamilyInstance, etc.)
    
    Returns:
        ConnectorManager: Manager de conectores do elemento
        
    Raises:
        AttributeError: Se elemento não possui ConnectorManager
    """
    if hasattr(element, 'ConnectorManager'):
        return element.ConnectorManager
    
    if hasattr(element, 'MEPModel'):
        if element.MEPModel and hasattr(element.MEPModel, 'ConnectorManager'):
            return element.MEPModel.ConnectorManager
    
    raise AttributeError("Elemento '{}' (Id: {}) não possui ConnectorManager".format(
        element.Name if hasattr(element, 'Name') else type(element).__name__,
        element.Id
    ))


def get_connector_closest_to(connectors, xyz_point):
    """
    Retorna o conector mais próximo de um ponto 3D.
    
    Args:
        connectors (ConnectorSet ou iterable): Coleção de conectores
        xyz_point (XYZ): Ponto de referência no espaço 3D
    
    Returns:
        Connector: Conector mais próximo do ponto, ou None se coleção vazia
    """
    min_distance = float("inf")
    closest_connector = None
    
    for connector in connectors:
        distance = connector.Origin.DistanceTo(xyz_point)
        if distance < min_distance:
            min_distance = distance
            closest_connector = connector
    
    return closest_connector


def get_all_connectors(element):
    """
    Retorna TODOS os conectores de um elemento (usados e não usados).
    
    Args:
        element (Element): Elemento MEP
    
    Returns:
        list: Lista de conectores (Connector objects)
    """
    try:
        cm = get_connector_manager(element)
        return list(cm.Connectors)
    except AttributeError:
        return []


def get_unused_connectors(element):
    """
    Retorna apenas conectores NÃO conectados de um elemento.
    
    Args:
        element (Element): Elemento MEP
    
    Returns:
        list: Lista de conectores não utilizados
    """
    try:
        cm = get_connector_manager(element)
        return list(cm.UnusedConnectors)
    except AttributeError:
        return []


def disconnect_connector(connector):
    """
    Desconecta um conector de suas conexões atuais.
    
    IMPORTANTE: Esta função deve ser chamada dentro de uma Transaction ativa.
    
    Args:
        connector (Connector): Conector a ser desconectado
    
    Returns:
        bool: True se desconectado com sucesso ou já estava desconectado
        
    Example:
        >>> with Transaction(doc, "Desconectar") as t:
        ...     t.Start()
        ...     disconnect_connector(conn1)
        ...     t.Commit()
    """
    try:
        if connector.IsConnected:
            # Desconectar todas as referências conectadas
            refs = connector.AllRefs
            for ref in refs:
                if ref.Owner.Id != connector.Owner.Id:
                    connector.DisconnectFrom(ref)
        return True
    except Exception:
        return False


def connect_elements(moved_element, moved_connector, target_connector, tolerance=0.001, auto_disconnect=True):
    """
    Conecta dois elementos MEP rotacionando e movendo o primeiro até o segundo.
    
    IMPORTANTE: Esta função deve ser chamada dentro de uma Transaction ativa.
    
    Args:
        moved_element (Element): Elemento a ser movido e rotacionado
        moved_connector (Connector): Conector do elemento a mover
        target_connector (Connector): Conector do elemento alvo
        tolerance (float): Tolerância para comparação de ângulos (radianos)
        auto_disconnect (bool): Se True, desconecta conectores automaticamente antes de conectar
    
    Returns:
        bool: True se conectado com sucesso, False se houve erro
        
    Example:
        >>> with Transaction(doc, "Conectar") as t:
        ...     t.Start()
        ...     success = connect_elements(pipe1, conn1, conn2)
        ...     t.Commit()
    """
    # Desconectar conectores se necessário
    if auto_disconnect:
        disconnect_connector(moved_connector)
        disconnect_connector(target_connector)

    # Obter direções dos conectores
    moved_dir = moved_connector.CoordinateSystem.BasisZ
    target_dir = target_connector.CoordinateSystem.BasisZ
    moved_point = moved_connector.Origin

    # Calcular ângulo entre direções
    angle = moved_dir.AngleTo(target_dir)

    # Rotacionar se necessário (direções devem ser opostas para conexão)
    if abs(angle - pi) > tolerance:
        if abs(angle) < tolerance:
            # Mesma direção - rotacionar 180 graus no eixo Y
            vector = moved_connector.CoordinateSystem.BasisY
            rotation_angle = pi
        else:
            # Calcular eixo perpendicular usando produto vetorial
            vector = moved_dir.CrossProduct(target_dir)
            if vector.GetLength() < 1e-12:
                vector = moved_connector.CoordinateSystem.BasisY
            # Normalizar: cross de direcoes quase antiparalelas e curto demais
            # para Line.CreateBound e a rotacao falharia silenciosamente
            vector = vector.Normalize()
            rotation_angle = angle - pi

        try:
            axis = Line.CreateBound(moved_point, moved_point + vector)
            moved_element.Location.Rotate(axis, rotation_angle)
        except ArgumentsInconsistentException:
            # Elemento não pode ser rotacionado (fixo, sem Location, etc)
            return False

    # Mover elemento para alinhar conectores
    translation = target_connector.Origin - moved_connector.Origin
    moved_element.Location.Move(translation)

    # Conectar logicamente os conectores
    moved_connector.ConnectTo(target_connector)

    return True


class MEPElementFilter(ISelectionFilter):
    """
    Filtro de seleção para elementos MEP com conectores.
    
    Permite selecionar apenas elementos que possuem ConnectorManager:
    - Pipes, Ducts, CableTray, Conduit
    - FamilyInstance com conectores MEP
    - Fittings (cotovelos, tês, uniões, etc.)
    
    Ignora automaticamente:
    - Isolamentos (InsulationLiningBase)
    - Elementos sem conectores
    """
    
    def AllowElement(self, elem):
        """Determina se elemento pode ser selecionado."""
        if isinstance(elem, InsulationLiningBase):
            return False
        
        try:
            get_connector_manager(elem)
            return True
        except AttributeError:
            return False
    
    def AllowReference(self, reference, position):
        """Permite referência ao elemento."""
        return True


def get_connector_info(connector):
    """
    Retorna informações detalhadas de um conector para debug.
    
    Args:
        connector (Connector): Conector a ser analisado
    
    Returns:
        dict: Dicionário com propriedades do conector
    """
    return {
        'Origin': connector.Origin,
        'Domain': str(connector.Domain),
        'Shape': str(connector.Shape),
        'IsConnected': connector.IsConnected,
        'ConnectorType': str(connector.ConnectorType),
        'Diameter': connector.Radius * 2 if hasattr(connector, 'Radius') else None,
        'Flow': connector.Flow if hasattr(connector, 'Flow') else None
    }


def connect_elements_no_rotate(moved_element, moved_connector, target_connector, auto_disconnect=True):
    """
    Conecta dois elementos MEP movendo o primeiro até o segundo SEM ROTACIONAR.
    Mantém a inclinação/orientação original do elemento movido.
    Similar ao comportamento do Move and Connect da Microdesk.

    IMPORTANTE: Esta função deve ser chamada dentro de uma Transaction ativa.

    Args:
        moved_element (Element): Elemento a ser movido (sem rotação)
        moved_connector (Connector): Conector do elemento a mover
        target_connector (Connector): Conector do elemento alvo
        auto_disconnect (bool): Se True, desconecta conectores automaticamente antes de conectar

    Returns:
        bool: True se conectado com sucesso, False se houve erro

    Example:
        >>> with Transaction(doc, "Conectar Sem Rotação") as t:
        ...     t.Start()
        ...     success = connect_elements_no_rotate(pipe1, conn1, conn2)
        ...     t.Commit()
    """
    try:
        # Desconectar conectores se necessário
        if auto_disconnect:
            disconnect_connector(moved_connector)
            disconnect_connector(target_connector)

        # Mover elemento para alinhar conectores (SEM ROTAÇÃO)
        # Apenas translação - mantém orientação original
        translation = target_connector.Origin - moved_connector.Origin
        moved_element.Location.Move(translation)

        # Conectar logicamente os conectores
        moved_connector.ConnectTo(target_connector)

        return True

    except Exception:
        return False


def _neighbor_slopes(target_connector):
    """Inclinacoes dos demais conectores CONECTADOS do fitting alvo.

    Usado quando o proprio conector alvo e horizontal (ex: joelho 90). Os
    conectores apontam para dentro do fitting; a inversao de sinal fica a
    cargo de resolve_connect_slope().
    """
    try:
        owner = target_connector.Owner
        if hasattr(owner, 'ConnectorManager'):
            cm = owner.ConnectorManager
        elif hasattr(owner, 'MEPModel') and owner.MEPModel:
            cm = owner.MEPModel.ConnectorManager
        else:
            return []
        slopes = []
        for conn in cm.Connectors:
            if not conn.IsConnected:
                continue
            bz = conn.CoordinateSystem.BasisZ
            dxy_n = sqrt(bz.X ** 2 + bz.Y ** 2)
            if dxy_n < 0.0001:      # conector vertical: sem slope de referencia
                continue
            slopes.append(bz.Z / dxy_n)
        return slopes
    except Exception:
        return []


def measure_pipe_slope(pipe, from_point):
    """Inclinacao assinada do tubo, medida de from_point para a outra ponta.

    Convencao identica a usada por apply_slope_from_connector: positivo sobe
    indo da extremidade que conecta para a extremidade livre. Deve ser chamada
    ANTES de mover/rotacionar o tubo.

    Args:
        pipe (Pipe): tubo a medir
        from_point (XYZ): extremidade de referencia (a que vai conectar)

    Returns:
        float: inclinacao (dz / comprimento horizontal); 0.0 se indeterminada
    """
    try:
        loc = pipe.Location
        if not isinstance(loc, LocationCurve):
            return 0.0
        p0 = loc.Curve.GetEndPoint(0)
        p1 = loc.Curve.GetEndPoint(1)
        near, far = (p0, p1) if p0.DistanceTo(from_point) <= p1.DistanceTo(from_point) else (p1, p0)
        return signed_slope((near.X, near.Y, near.Z), (far.X, far.Y, far.Z))
    except Exception:
        return 0.0


def id_value(element_id):
    """Valor inteiro do ElementId (Revit 2024+ usa .Value, antes .IntegerValue)."""
    return element_id.Value if hasattr(element_id, 'Value') else element_id.IntegerValue


_id_val = id_value      # alias curto para uso interno deste modulo


def _is_pipe(elem):
    """Mesmo criterio de Snippets._prumada_utils.is_pipe, sem criar dependencia.

    Por categoria, nao por isinstance: o modulo so importa Autodesk.Revit.DB
    com *, entao o namespace Plumbing nao esta no escopo aqui.
    """
    return (elem is not None and elem.Category is not None
            and _id_val(elem.Category.Id) == int(BuiltInCategory.OST_PipeCurves))


def _pipe_curve_slope(pipe):
    """(slope orientado, e_vertical) do tubo, ou (None, False) se indisponivel."""
    try:
        loc = pipe.Location
        if not isinstance(loc, LocationCurve):
            return None, False
        p0 = loc.Curve.GetEndPoint(0)
        p1 = loc.Curve.GetEndPoint(1)
        a = (p0.X, p0.Y, p0.Z)
        b = (p1.X, p1.Y, p1.Z)
        return oriented_slope(a, b), is_vertical(a, b)
    except Exception:
        return None, False


def snapshot_network_slopes(seeds, max_elements=80):
    """Fotografa a inclinacao dos tubos ao redor. Chamar ANTES da operacao.

    Conectar arrasta a vizinhanca: em log real, uma unica operacao mexeu em 4
    tubos e os dois que perderam inclinacao NAO eram o tubo movido. Verificar
    so o elemento que a ferramenta moveu nao enxerga esse estrago.

    Args:
        seeds: elementos de partida (tipicamente o movido e o alvo).
        max_elements: teto do BFS, para nao varrer o sistema inteiro.

    Returns:
        dict {id: (slope_orientado, e_vertical)} - passar para
        diff_network_slopes() depois da operacao.
    """
    snap = {}
    vistos = set()
    fila = [e for e in (seeds or []) if e is not None]
    while fila and len(vistos) < max_elements:
        elem = fila.pop()
        try:
            eid = _id_val(elem.Id)
        except Exception:
            continue
        if eid in vistos:
            continue
        vistos.add(eid)

        if _is_pipe(elem):
            slope, vert = _pipe_curve_slope(elem)
            if slope is not None:
                snap[eid] = (slope, vert)
        try:
            cm = get_connector_manager(elem)
        except Exception:
            continue
        for conn in cm.Connectors:
            try:
                if conn.ConnectorType != ConnectorType.End or not conn.IsConnected:
                    continue
                for ref in conn.AllRefs:
                    if ref.Owner is None or _id_val(ref.Owner.Id) == eid:
                        continue
                    fila.append(ref.Owner)
            except Exception:
                continue
    return snap


def diff_network_slopes(doc, snapshot, tol=SLOPE_VERIFY_TOL, ignore_ids=None):
    """Remede o snapshot e devolve os tubos que mudaram de inclinacao.

    Deve ser chamada DEPOIS da operacao, dentro da Transaction ativa.

    Tubos verticais (antes ou depois) ficam de fora: prumada nao tem cota
    unica e a razao dz/dxy explode - so produziria ruido.

    Args:
        doc: documento
        snapshot: retorno de snapshot_network_slopes()
        tol: divergencia tolerada
        ignore_ids: ids ja cobertos por verificacao dedicada (evita aviso
            duplicado para o tubo que a ferramenta moveu de proposito).

    Returns:
        lista de dicts (id, before, after, verdict, diff), so dos alterados.
    """
    if not snapshot:
        return []
    try:
        doc.Regenerate()
    except Exception:
        pass
    ignorar = set(ignore_ids or [])
    mudou = []
    for eid, (antes, vert_antes) in snapshot.items():
        if eid in ignorar or vert_antes:
            continue
        try:
            # Revit 2026: ElementId(int) foi removido, precisa de Int64
            pipe = doc.GetElement(ElementId(Int64(eid)))
        except Exception:
            continue
        if pipe is None:
            continue        # apagado no processo (fusao de colineares, etc.)
        depois, vert_depois = _pipe_curve_slope(pipe)
        if depois is None or vert_depois:
            continue
        verdict, diff = slope_verdict(antes, depois, tol)
        if verdict != SLOPE_OK:
            mudou.append({'id': eid, 'before': antes, 'after': depois,
                          'verdict': verdict, 'diff': diff})
    return mudou


def intended_connect_slope(target_connector, original_slope=0.0):
    """Inclinacao que o tubo DEVE ter depois de conectar neste conector.

    Isolada de apply_slope_from_connector() para que a verificacao
    pos-condicao saiba o que era pretendido sem repetir a regra.

    Returns:
        float com a inclinacao assinada, ou None quando o alvo e vertical
        (sem slope de referencia) ou nao ha nada a gravar.
    """
    try:
        bz = target_connector.CoordinateSystem.BasisZ
    except Exception:
        return None
    dxy = sqrt(bz.X ** 2 + bz.Y ** 2)
    if dxy < 0.0001:            # alvo vertical - sem slope de referencia
        return None
    return resolve_connect_slope(bz.Z / dxy,
                                 _neighbor_slopes(target_connector),
                                 original_slope)


def target_allows_slope(target_connector):
    """True se o conector alvo aceita ajuste de inclinacao.

    Conectores cuja System Classification e "Fitting" NAO possuem o parametro
    Allow Slope Adjustments (so os "Global" possuem) - incidente Autodesk
    89172, sem resolucao. Ao receber um tubo inclinado, esses fittings
    absorvem o desvio no proprio angulo (89.4 no lugar de 90) em vez de
    deixar o tubo inclinar. E a explicacao mais comum para um veredito
    ACHATADO ou ALTERADO.

    Returns:
        bool, ou None se a propriedade nao pode ser lida.
    """
    try:
        return bool(target_connector.AllowsSlopeAdjustments)
    except Exception:
        return None


def verify_slope_applied(moved_pipe, target_connector, intended,
                         tol=SLOPE_VERIFY_TOL):
    """Remede a inclinacao do tubo DEPOIS que o Revit consolidou a conexao.

    Gravar LocationCurve nao e garantia: o Revit pode desfazer ao resolver a
    conexao com um fitting que nao aceita slope. Regenera o documento, remede
    e emite um veredito.

    Deve ser chamada dentro da Transaction ativa, apos a conexao.

    Args:
        moved_pipe (Pipe): tubo conectado
        target_connector (Connector): conector do alvo (extremidade fixa)
        intended (float|None): inclinacao assinada pretendida
        tol (float): divergencia tolerada

    Returns:
        dict: verdict, intended, measured, diff, allows_slope
    """
    report = {'verdict': SLOPE_OK, 'intended': intended, 'measured': 0.0,
              'diff': 0.0, 'allows_slope': target_allows_slope(target_connector),
              'applied': True}
    if intended is None:
        return report
    try:
        moved_pipe.Document.Regenerate()
        origem = target_connector.Origin
        measured = measure_pipe_slope(moved_pipe, origem)
    except Exception:
        # Regenerate pode falhar e o Connector pode ser invalidado por ele.
        # Nao medir NAO e o mesmo que estar certo.
        report['verdict'] = SLOPE_INDETERMINADO
        return report
    report['measured'] = measured
    report['verdict'], report['diff'] = slope_verdict(intended, measured, tol)
    return report


def _pipe_is_vertical(pipe):
    """True se o tubo nao tem cota unica (prumada ou quase).

    Tubo quase vertical tem comprimento horizontal minusculo: a razao dz/dxy
    explode (medimos 102 e 33902 em modelo real) e comparar inclinacao ali
    so produz ruido. Usa o mesmo criterio do resto do projeto.
    """
    try:
        loc = pipe.Location
        if not isinstance(loc, LocationCurve):
            return False
        p0 = loc.Curve.GetEndPoint(0)
        p1 = loc.Curve.GetEndPoint(1)
        return is_vertical((p0.X, p0.Y, p0.Z), (p1.X, p1.Y, p1.Z))
    except Exception:
        return False


def apply_and_verify_slope(moved_pipe, target_connector, original_slope=0.0):
    """Aplica a inclinacao e confere se o Revit respeitou.

    Substitui apply_slope_from_connector() nos pontos onde interessa saber se
    a inclinacao sobreviveu. Nao altera o que e gravado - so acrescenta a
    medicao depois.

    Quando nao ha slope a aplicar mas o tubo JA vinha inclinado, verifica
    mesmo assim: o fallback de mover rotaciona o tubo ate o eixo do alvo e
    pode ter achatado a inclinacao original sem que ninguem grave nada.

    Returns:
        dict: o relatorio de verify_slope_applied(), mais 'applied' (bool).
    """
    intended = intended_connect_slope(target_connector, original_slope)
    applied = apply_slope_from_connector(moved_pipe, target_connector,
                                         original_slope)

    # Prumada nao tem inclinacao para conferir - o alinhamento dela e problema
    # de _prumada_utils, nao desta verificacao.
    if _pipe_is_vertical(moved_pipe):
        return {'verdict': SLOPE_OK, 'intended': intended, 'measured': 0.0,
                'diff': 0.0, 'allows_slope': None, 'applied': applied,
                'skipped': 'vertical'}

    referencia = intended
    if referencia is None and abs(original_slope) > SLOPE_VERIFY_TOL:
        referencia = original_slope     # nada gravado, mas havia o que perder

    report = verify_slope_applied(moved_pipe, target_connector, referencia)
    report['applied'] = applied
    return report


def apply_slope_from_connector(moved_pipe, target_connector, original_slope=0.0):
    """
    Aplica slope ao tubo movido baseado no BasisZ do conector alvo.
    Ajusta o Z do endpoint livre via LocationCurve.

    IMPORTANTE: deve ser chamado dentro de Transaction ativa, apos connect_elements()
                ou connect_elements_no_rotate().
    So aplicavel quando o elemento movido e um Pipe nao-vertical.

    Se o alvo nao fornece inclinacao (fitting horizontal, sem vizinho inclinado),
    a inclinacao ORIGINAL do tubo e preservada — connect_elements() rotaciona o
    tubo ate o eixo do conector alvo e, sem isso, um tubo inclinado seria
    achatado silenciosamente.

    Args:
        moved_pipe (Pipe): Tubo que foi movido e conectado
        target_connector (Connector): Conector do elemento alvo
        original_slope (float): Inclinacao do tubo ANTES da operacao, medida
            por measure_pipe_slope() a partir da extremidade que conecta.

    Returns:
        bool: True se slope foi aplicado, False se operacao foi ignorada (SKIP)
    """
    loc = moved_pipe.Location
    if not isinstance(loc, LocationCurve):
        return False

    slope = intended_connect_slope(target_connector, original_slope)
    if slope is None:   # alvo vertical, ou nada derivavel e tubo ja horizontal
        return False

    p0 = loc.Curve.GetEndPoint(0)
    p1 = loc.Curve.GetEndPoint(1)

    # Identificar endpoint fixo (conectado) e endpoint livre
    # tol = 0.002 ft (~0.6 mm): preciso o suficiente apos Location.Move()
    tol = 0.002
    p0_dist = p0.DistanceTo(target_connector.Origin)
    p1_dist = p1.DistanceTo(target_connector.Origin)
    p0_is_fixed = p0_dist < tol and p0_dist <= p1_dist
    fixed_pt = p0 if p0_is_fixed else p1
    free_pt  = p1 if p0_is_fixed else p0

    # Calcular nova posicao Z do endpoint livre
    h_dist = sqrt((free_pt.X - fixed_pt.X) ** 2 + (free_pt.Y - fixed_pt.Y) ** 2)
    if h_dist < 0.001:  # pipe muito curto ou conector centrado
        return False

    new_z    = fixed_pt.Z + slope * h_dist
    new_free = XYZ(free_pt.X, free_pt.Y, new_z)
    new_p0   = fixed_pt if p0_is_fixed else new_free
    new_p1   = new_free  if p0_is_fixed else fixed_pt

    if new_p0.DistanceTo(new_p1) < 0.001:
        return False

    try:
        loc.Curve = Line.CreateBound(new_p0, new_p1)
        return True
    except Exception:
        return False


def validate_connectors_compatible(conn1, conn2, allow_connected=False):
    """
    Valida se dois conectores são compatíveis para conexão.

    Args:
        conn1 (Connector): Primeiro conector
        conn2 (Connector): Segundo conector
        allow_connected (bool): Se True, permite conectores já conectados (serão desconectados)

    Returns:
        tuple: (bool, str) - (é_compatível, mensagem_erro)

    Example:
        >>> valid, msg = validate_connectors_compatible(conn1, conn2)
        >>> if not valid:
        ...     print(msg)
    """
    # Verificar domínio
    if conn1.Domain != conn2.Domain:
        return False, "Dominios incompativeis: {} vs {}".format(
            conn1.Domain, conn2.Domain
        )

    # Verificar forma do conector (round/rectangular)
    try:
        if conn1.Shape != conn2.Shape:
            return False, "Formas incompativeis: {} vs {}".format(
                conn1.Shape, conn2.Shape
            )
    except Exception:
        pass

    # Verificar tamanho
    try:
        if str(conn1.Shape) == "Round":
            r1, r2 = conn1.Radius, conn2.Radius
            if abs(r1 - r2) > 0.00164:  # ~0.5 mm em feet
                d1 = int(round(r1 * 2 * 304.8))
                d2 = int(round(r2 * 2 * 304.8))
                return False, "Diametros incompativeis: {}mm vs {}mm".format(d1, d2)
        else:
            if (abs(conn1.Width - conn2.Width) > 0.001 or
                    abs(conn1.Height - conn2.Height) > 0.001):
                return False, "Dimensoes incompativeis: {}x{} vs {}x{}".format(
                    int(round(conn1.Width * 304.8)),
                    int(round(conn1.Height * 304.8)),
                    int(round(conn2.Width * 304.8)),
                    int(round(conn2.Height * 304.8))
                )
    except Exception:
        pass  # conectores sem propriedade de tamanho (ex: eletrica)

    # Verificar se já conectados (se não permitido)
    if not allow_connected:
        if conn1.IsConnected:
            return False, "Primeiro conector ja esta conectado"

        if conn2.IsConnected:
            return False, "Segundo conector ja esta conectado"

    return True, ""
