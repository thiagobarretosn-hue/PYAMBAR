# -*- coding: utf-8 -*-
"""Os fatos de um elemento que as regras de parametros perguntam.

A decisao e pura (`Snippets._regras_param`); aqui so se LE o Revit.
Medido no MIIQLUX-SEW-RSR em 14/09/2026: tubo e conexao expoem o nome e a
classificacao do system pelos BuiltInParameter; nomes de categoria vem na
lingua do Revit ("Tubulação", "Conexões de tubo").
"""
from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    ElementId,
    FamilyInstance,
    Group,
    LocationCurve,
    MEPCurve,
    StorageType,
)

from Snippets import _trecho_horizontal as th
from Snippets._mep_system_ops import elem_name, id_value, physical_connectors
from Snippets._regras_param import (
    PAPEL_GRUPO,
    PAPEL_MEMBRO,
    PAPEL_SOLTO,
    classificar_orientacao,
    orientacao_herdada,
)

#: Conexao e acessorio nao tem eixo proprio: herdam a orientacao do tubo
#: ligado (decisao do Thiago, 15/09/2026). Peca de utilitario (bacia, ralo)
#: fica de fora — ligada a um tubo vertical ela nao e "Riser".
_NOMES_HERDAM = ('OST_PipeFitting', 'OST_PipeAccessory', 'OST_DuctFitting',
                 'OST_DuctAccessory', 'OST_ConduitFitting',
                 'OST_CableTrayFitting')
_HERDAM = set()
for _nome in _NOMES_HERDAM:
    _bic = getattr(BuiltInCategory, _nome, None)
    if _bic is not None:
        _HERDAM.add(int(_bic))

#: saltos pela rede ate achar tubo: conexao ligada direto a outra conexao
#: (wye encaixado no joelho) precisa de dois
_SALTOS = 2


def texto_do_parametro(param):
    if param is None or not param.HasValue:
        return ''
    try:
        if param.StorageType == StorageType.String:
            valor = param.AsString()
        else:
            valor = param.AsValueString()
    except Exception:
        valor = None
    return (valor or '').strip()


def _tipo_de_sistema(doc, elemento):
    """Nome do TIPO de system ("10.03.02-KIT ARN Sewer"), nao do system.

    Pedido do Thiago em 21/10/2026: no CIQ o nome e "SEWER 734" e quem diz que
    a peca e de KIT ARN e o tipo. Tubo e duto expoem por BuiltInParameter
    (RBS_PIPING_SYSTEM_TYPE_PARAM / RBS_DUCT_SYSTEM_TYPE_PARAM, conferidos no
    stub 2026); conexao e aparelho caem no MEPSystem, que leva ao mesmo tipo.
    """
    for bip in (BuiltInParameter.RBS_PIPING_SYSTEM_TYPE_PARAM,
                BuiltInParameter.RBS_DUCT_SYSTEM_TYPE_PARAM):
        texto = texto_do_parametro(elemento.get_Parameter(bip))
        if texto:
            return texto
    try:
        sistema = getattr(elemento, 'MEPSystem', None)
        if sistema is None:
            modelo = getattr(elemento, 'MEPModel', None)
            sistema = getattr(modelo, 'MEPSystem', None) if modelo else None
        if sistema is not None and _valido(sistema.GetTypeId()):
            return elem_name(doc.GetElement(sistema.GetTypeId())) or ''
    except Exception:
        pass
    return ''


def _valido(eid):
    try:
        return eid is not None and eid != ElementId.InvalidElementId \
            and id_value(eid) > 0
    except Exception:
        return False


def grupos_de(doc, elemento):
    """Nomes dos GroupTypes, do grupo mais interno ao mais externo.

    O proprio Model Group entra primeiro: "grupo que comeca com ARN TYP" tem
    de casar com a instancia do grupo, nao so com os membros.
    """
    nomes = []
    atual = elemento
    if isinstance(elemento, Group):
        nomes.append(elem_name(elemento.GroupType))
    vistos = set()
    while _valido(getattr(atual, 'GroupId', None)):
        pai = doc.GetElement(atual.GroupId)
        if pai is None or id_value(pai.Id) in vistos:
            break
        vistos.add(id_value(pai.Id))
        nomes.append(elem_name(pai.GroupType))
        atual = pai
    return nomes


def papel_de(elemento):
    if isinstance(elemento, Group):
        return PAPEL_GRUPO
    if _valido(getattr(elemento, 'GroupId', None)):
        return PAPEL_MEMBRO
    return PAPEL_SOLTO


def _orientacao_da_curva(elemento):
    local = elemento.Location
    if not isinstance(local, LocationCurve):
        return ''
    curva = local.Curve
    p0, p1 = curva.GetEndPoint(0), curva.GetEndPoint(1)
    return classificar_orientacao((p0.X, p0.Y, p0.Z), (p1.X, p1.Y, p1.Z))


def _vizinhos(elemento):
    """Elementos ligados fisicamente — sem o proprio e sem o system logico."""
    proprio = id_value(elemento.Id)
    saida = []
    for conector in physical_connectors(elemento):
        try:
            refs = list(conector.AllRefs)
        except Exception:
            continue
        for ref in refs:
            try:
                dono = ref.Owner
            except Exception:
                dono = None
            if dono is None or id_value(dono.Id) == proprio:
                continue
            if isinstance(dono, (MEPCurve, FamilyInstance)):
                saida.append(dono)
    return saida


#: publico: a janela percorre a rede para o Unit ID fora de room (16/09/2026)
vizinhos = _vizinhos


def _herda_orientacao(elemento):
    try:
        categoria = elemento.Category
        return categoria is not None and id_value(categoria.Id) in _HERDAM
    except Exception:
        return False


def orientacao_de(elemento):
    """Tubo: pela curva. Conexao / acessorio: herdada dos tubos ligados."""
    if isinstance(elemento, MEPCurve):
        return _orientacao_da_curva(elemento)
    if not _herda_orientacao(elemento):
        return ''
    vistos = set([id_value(elemento.Id)])
    fronteira = [elemento]
    for _ in range(_SALTOS):
        orientacoes, proxima = [], []
        for atual in fronteira:
            for vizinho in _vizinhos(atual):
                chave = id_value(vizinho.Id)
                if chave in vistos:
                    continue
                vistos.add(chave)
                if isinstance(vizinho, MEPCurve):
                    orientacoes.append(_orientacao_da_curva(vizinho))
                else:
                    proxima.append(vizinho)
        herdada = orientacao_herdada(orientacoes)
        if herdada or not proxima:
            return herdada
        fronteira = proxima
    return ''


def _nivel(doc, elemento):
    nivel = None
    try:
        if _valido(elemento.LevelId):
            nivel = doc.GetElement(elemento.LevelId)
    except Exception:
        nivel = None
    if nivel is None:
        nivel = getattr(elemento, 'ReferenceLevel', None)
    return elem_name(nivel) if nivel is not None else ''


def _diametro(elemento):
    """Polegadas, ou None."""
    for bip in (BuiltInParameter.RBS_PIPE_DIAMETER_PARAM,
                BuiltInParameter.RBS_CURVE_DIAMETER_PARAM):
        param = elemento.get_Parameter(bip)
        if param is not None and param.HasValue:
            try:
                return round(param.AsDouble() * 12.0, 4)
            except Exception:
                return None
    return None


def _comprimento(elemento):
    """Pes, so de tubo/duto (MEPCurve); None nas conexoes (16/09/2026)."""
    if not isinstance(elemento, MEPCurve):
        return None
    try:
        param = elemento.get_Parameter(BuiltInParameter.CURVE_ELEM_LENGTH)
        if param is not None and param.HasValue:
            return round(param.AsDouble(), 6)
    except Exception:
        pass
    return None


def trecho_horizontal(elemento):
    """{'pecas', 'comprimento', 'pontas'} do trecho horizontal, ou None.

    Percorre a rede pelos conectores (Snippets._trecho_horizontal decide o
    que entra). Os elementos aparecem pelos vizinhos: nao precisa de
    `GetElement` por id (16/09/2026)."""
    elementos = {id_value(elemento.Id): elemento}

    def peca_de(chave):
        el = elementos.get(chave)
        if el is None:
            return None
        if isinstance(el, MEPCurve):
            tipo, orientacao = th.TUBO, _orientacao_da_curva(el)
        elif _herda_orientacao(el):
            tipo, orientacao = th.CONEXAO, ''
        else:
            tipo, orientacao = th.OUTRO, ''
        try:
            grupo = id_value(el.GroupId)
        except Exception:
            grupo = -1
        return {'tipo': tipo, 'orientacao': orientacao, 'grupo': grupo,
                'comprimento': _comprimento(el) if tipo == th.TUBO else None}

    def vizinhos_de(chave):
        el = elementos.get(chave)
        if el is None:
            return []
        saida = []
        for vizinho in _vizinhos(el):
            outra = id_value(vizinho.Id)
            elementos.setdefault(outra, vizinho)
            saida.append(outra)
        return saida

    return th.trecho_de(id_value(elemento.Id), peca_de, vizinhos_de)


def fatos_estaticos(doc, elemento):
    """Tudo que nao depende das regras — calculado uma vez por elemento."""
    tipo = None
    try:
        if _valido(elemento.GetTypeId()):
            tipo = doc.GetElement(elemento.GetTypeId())
    except Exception:
        tipo = None
    categoria = elemento.Category.Name if elemento.Category is not None else ''
    try:
        orientacao = orientacao_de(elemento)
    except Exception:
        orientacao = ''
    return {
        'papel': papel_de(elemento),
        'orientacao': orientacao,
        'grupos': grupos_de(doc, elemento),
        'system': texto_do_parametro(elemento.get_Parameter(
            BuiltInParameter.RBS_SYSTEM_NAME_PARAM)),
        'system_tipo': _tipo_de_sistema(doc, elemento),
        'classificacao': texto_do_parametro(elemento.get_Parameter(
            BuiltInParameter.RBS_SYSTEM_CLASSIFICATION_PARAM)),
        'categoria': categoria,
        'familia': (getattr(tipo, 'FamilyName', '') or '') if tipo else '',
        'tipo': elem_name(tipo) if tipo is not None else '',
        'nivel': _nivel(doc, elemento),
        'diametro': _diametro(elemento),
        'comprimento': _comprimento(elemento),
        'room': '',
        'room_numero': '',
    }


def ler_parametros(elemento, nomes, cache):
    """Preenche `cache` {nome: texto} com os nomes que ainda faltam."""
    for nome in nomes:
        if not nome or nome in cache:
            continue
        try:
            cache[nome] = texto_do_parametro(elemento.LookupParameter(nome))
        except Exception:
            cache[nome] = ''
    return cache
