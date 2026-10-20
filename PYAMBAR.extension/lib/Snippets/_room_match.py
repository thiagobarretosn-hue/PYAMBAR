# -*- coding: utf-8 -*-
"""Room que contem cada elemento — rooms do modelo e dos vinculos (Revit).

As decisoes (pre-filtro, sondagem, desempate pelo nivel mais alto, Unit ID do
room) sao puras e medidas: `Snippets._ambiente_match`. Aqui so a leitura.

A ideia do room de vinculo com transform invertido veio do SyncFromRoom
(`core/room_mep_sync.py`), que continua com a versao dele: la vale o PRIMEIRO
room e o elemento recebe todos os parametros; aqui vale o do nivel mais alto
(medido: 80% contra 59%).
"""
from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    FilteredElementCollector,
    Group,
    LocationCurve,
    LocationPoint,
    RevitLinkInstance,
    StorageType,
    XYZ,
)

from Snippets._mep_system_ops import elem_name
from Snippets._ambiente_match import (
    DIRECAO_BASE,
    dentro_da_caixa,
    distancia_xy_da_caixa,
    escolher_room,
    offset_do_room,
    pontos_de_sondagem,
)

FOLGA_CAIXA = 0.01  # pes


def _texto(param):
    if param is None or not param.HasValue:
        return u''
    try:
        if param.StorageType == StorageType.String:
            valor = param.AsString()
        else:
            valor = param.AsValueString()
    except Exception:
        valor = None
    return (valor or u'').strip()


def valores_do_room(room):
    """{nome: texto} de todo parametro preenchido do room."""
    valores = {}
    for param in room.Parameters:
        try:
            if param.Definition is None:
                continue
            texto = _texto(param)
            if texto:
                valores[param.Definition.Name] = texto
        except Exception:
            continue
    return valores


def _rooms_colocados(doc, vista=None):
    if vista is not None:
        coletor = FilteredElementCollector(doc, vista.Id)
    else:
        coletor = FilteredElementCollector(doc)
    saida = []
    for room in coletor.OfCategory(BuiltInCategory.OST_Rooms) \
            .WhereElementIsNotElementType().ToElements():
        try:
            if room.Area > 0:
                saida.append(room)
        except Exception:
            continue
    return saida


def _item(room, link=None, inversa=None, dz=0.0):
    caixa = room.get_BoundingBox(None)
    if caixa is None:
        return None
    nome = _texto(room.get_Parameter(BuiltInParameter.ROOM_NAME))
    numero = (room.Number or u'').strip()
    try:
        elevacao = room.Level.Elevation
        nivel = elem_name(room.Level)
    except Exception:
        elevacao = caixa.Min.Z
        nivel = u''
    # chave estavel entre leituras (offset por room, 16/09/2026): UniqueId,
    # prefixado pelo do vinculo — o mesmo room pode vir de duas instancias
    chave = room.UniqueId if link is None else u'{}/{}'.format(
        link.UniqueId, room.UniqueId)
    return {
        'room': room, 'link': link, 'inversa': inversa, 'chave': chave,
        'min': (caixa.Min.X, caixa.Min.Y, caixa.Min.Z),
        'max': (caixa.Max.X, caixa.Max.Y, caixa.Max.Z),
        # altura no sistema do MODELO (min/max ficam no do vinculo)
        'faixa_z': (caixa.Min.Z + dz, caixa.Max.Z + dz),
        'elevacao': elevacao + dz, 'nome': nome, 'numero': numero,
        'nivel': nivel,
        'rotulo': u'{} {}'.format(numero, nome).strip(),
        'valores': valores_do_room(room),
        'origem': u'vínculo' if link is not None else u'modelo',
    }


def indice_de_rooms(doc, vista, incluir_links=True, so_vista=False):
    """Rooms colocados, prontos para casar.

    `so_vista`: so os rooms do MODELO visiveis na vista (rooms de vinculo nao
    passam pelo coletor da vista — entram todos).
    """
    itens = []
    for room in _rooms_colocados(doc, vista if so_vista else None):
        item = _item(room)
        if item is not None:
            itens.append(item)
    if incluir_links:
        for instancia in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
            doc_link = instancia.GetLinkDocument()
            if doc_link is None:
                continue
            transform = instancia.GetTotalTransform()
            inversa = transform.Inverse
            for room in _rooms_colocados(doc_link):
                item = _item(room, instancia, inversa, transform.Origin.Z)
                if item is not None:
                    itens.append(item)
    return itens


def ponto_do_elemento(elemento):
    """Meio da curva, ponto de insercao, ou centro da caixa (grupo)."""
    try:
        local = elemento.Location
    except Exception:
        local = None
    if not isinstance(elemento, Group):
        if isinstance(local, LocationCurve):
            return local.Curve.Evaluate(0.5, True)
        if isinstance(local, LocationPoint):
            return local.Point
    try:
        caixa = elemento.get_BoundingBox(None)
    except Exception:
        caixa = None
    if caixa is None:
        return None
    return (caixa.Min + caixa.Max) * 0.5


def room_do_elemento(indice, elemento, offset_ft=0.0, direcao=DIRECAO_BASE,
                     offsets=None):
    """O item do indice que vale para o elemento, ou None."""
    return escolher_room(rooms_do_elemento(indice, elemento, offset_ft,
                                           direcao, offsets))


def rooms_do_elemento(indice, elemento, offset_ft=0.0, direcao=DIRECAO_BASE,
                      offsets=None):
    """Todos os rooms que contem o ponto do elemento.

    Mais de um e sinal de erro de MODELO — alturas de room sobrepostas (o
    Thiago confirmou no MIIQLUX: LEVEL 3 e 4 se cruzando "era um erro"). A
    janela escolhe o do nivel mais alto e AVISA, em vez de esconder.

    `offset_ft`/`direcao` sao o padrao; `offsets` ({chave do room: ...},
    `_ambiente_match.normalizar_offsets`) troca o de cada room (16/09/2026).
    """
    ponto = ponto_do_elemento(elemento)
    if ponto is None:
        return []
    base = (ponto.X, ponto.Y, ponto.Z)
    candidatos = []
    for item in indice:
        offset, sentido, _proprio = offset_do_room(
            offsets, item.get('chave'), offset_ft, direcao)
        for sonda in pontos_de_sondagem(base, offset, sentido):
            alvo = sonda
            if item['inversa'] is not None:
                convertido = item['inversa'].OfPoint(XYZ(*sonda))
                alvo = (convertido.X, convertido.Y, convertido.Z)
            if not dentro_da_caixa(alvo, item['min'], item['max'], FOLGA_CAIXA):
                continue
            try:
                if item['room'].IsPointInRoom(XYZ(*alvo)):
                    candidatos.append(item)
                    break
            except Exception:
                continue
    return candidatos


def room_do_topo(indice, elemento, folga=0.05):
    """Room que contem o TOPO da peca, ou None.

    A aranha (ARN TYP) fica no forro do pavimento de baixo e atende a unidade
    de CIMA: o Floor sai do nivel onde ela esta, e o Unit ID / Type vem do room
    que o topo dela alcanca (decisao do Thiago, 16/09/2026).

    IMPORTANTE: quem atravessa a laje e o GRUPO, nao cada peca — a janela
    passa o grupo mais externo (`_room_do_topo`). Medido no MIIQLUX contra o
    que ja estava gravado a mao: topo da PECA acerta 280 de 820; topo do
    GRUPO, 970 de 1.016 (as 46 divergencias sao aranhas de duas unidades).
    """
    try:
        caixa = elemento.get_BoundingBox(None)
    except Exception:
        caixa = None
    if caixa is None:
        return None
    ponto = XYZ((caixa.Min.X + caixa.Max.X) / 2.0,
                (caixa.Min.Y + caixa.Max.Y) / 2.0,
                caixa.Max.Z - folga)
    candidatos = []
    for item in indice:
        alvo = (ponto.X, ponto.Y, ponto.Z)
        if item['inversa'] is not None:
            convertido = item['inversa'].OfPoint(ponto)
            alvo = (convertido.X, convertido.Y, convertido.Z)
        if not dentro_da_caixa(alvo, item['min'], item['max'], FOLGA_CAIXA):
            continue
        try:
            if item['room'].IsPointInRoom(XYZ(*alvo)):
                candidatos.append(item)
        except Exception:
            continue
    return escolher_room(candidatos)


def _xy_no_room(item, ponto):
    if item['inversa'] is not None:
        convertido = item['inversa'].OfPoint(ponto)
        return convertido.X, convertido.Y
    return ponto.X, ponto.Y


def rooms_na_vertical(indice, elemento):
    """(z do elemento, rooms cuja PLANTA contem o ponto, em qualquer altura).
    Testa o ponto levado a meia altura de cada room. Para quem esta fora de
    room: tubo no forro ou sob a laje acha o room de cima/baixo (16/09/2026)."""
    ponto = ponto_do_elemento(elemento)
    if ponto is None:
        return None, []
    saida = []
    for item in indice:
        x, y = _xy_no_room(item, ponto)
        alvo = (x, y, (item['min'][2] + item['max'][2]) / 2.0)
        if not dentro_da_caixa(alvo, item['min'], item['max'], FOLGA_CAIXA):
            continue
        try:
            if item['room'].IsPointInRoom(XYZ(*alvo)):
                saida.append(item)
        except Exception:
            continue
    return ponto.Z, saida


def rooms_perto(indice, elemento, limite):
    """[(distancia em planta, item)] dos rooms ate `limite` do elemento, so os
    da mesma altura (faixa do room folgada pelo mesmo limite) — o room do
    andar de cima, logo acima, nao e "o mais proximo"."""
    ponto = ponto_do_elemento(elemento)
    if ponto is None:
        return []
    pares = []
    for item in indice:
        baixo, alto = item['faixa_z']
        if ponto.Z < baixo - limite or ponto.Z > alto + limite:
            continue
        x, y = _xy_no_room(item, ponto)
        distancia = distancia_xy_da_caixa((x, y), item['min'], item['max'])
        if distancia <= limite:
            pares.append((distancia, item))
    return pares
