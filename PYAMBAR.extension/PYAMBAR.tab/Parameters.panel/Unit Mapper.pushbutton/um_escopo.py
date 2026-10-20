# -*- coding: utf-8 -*-
"""Escopo do Unit Mapper: selecao, visiveis na vista ativa ou projeto inteiro.

Pedido do Thiago em 14/09/2026. Devolve so o TOPO: um membro de grupo entra
pelo grupo mais externo, e a descida (`coletar_selecao`) alcanca os membros —
o mesmo caminho da selecao, entao grupo e membro sao tratados igual nos tres.
"""
from Autodesk.Revit.DB import BuiltInCategory, CategoryType, FilteredElementCollector

from Snippets._mep_system_ops import id_value

SELECAO = 'selecao'
VISTA = 'vista'
PROJETO = 'projeto'

ESCOPOS = ((SELECAO, u'Seleção'), (VISTA, u'Visíveis na vista ativa'),
           (PROJETO, u'Projeto inteiro'))

#: Categorias de modelo que nao sao "coisa para parametrizar": espaco, linha
#: de centro (elemento dependente do tubo), vinculo, camera, linhas.
_NOMES_FORA = (
    'OST_Rooms', 'OST_Areas', 'OST_MEPSpaces', 'OST_RvtLinks', 'OST_Cameras',
    'OST_Lines', 'OST_SketchLines', 'OST_Levels', 'OST_Grids',
    'OST_PipeCurvesCenterLine', 'OST_PipeFittingCenterLine',
    'OST_DuctCurvesCenterLine', 'OST_DuctFittingCenterLine',
    'OST_FlexPipeCurvesCenterLine', 'OST_FlexDuctCurvesCenterLine',
    'OST_ConduitCenterLine', 'OST_ConduitFittingCenterLine',
    'OST_CableTrayCenterLine', 'OST_CableTrayFittingCenterLine',
    'OST_ProjectBasePoint', 'OST_SharedBasePoint', 'OST_IOS_GeoSite',
)
_FORA = set()
for _nome in _NOMES_FORA:
    _bic = getattr(BuiltInCategory, _nome, None)
    if _bic is not None:
        _FORA.add(int(_bic))


def categoria_de_grupos(doc):
    """Nome de "Grupos de modelo" na lingua do Revit ('' se nao achar)."""
    try:
        return doc.Settings.Categories.get_Item(
            BuiltInCategory.OST_IOSModelGroups).Name or ''
    except Exception:
        return ''


def eh_aninhado(elemento):
    """Peca DENTRO de outra familia (SuperComponent). Auditoria de 16/09/2026:
    340 "nao aplicados" em toda aplicacao eram plugs, cleanout covers e aneis
    aninhados — Floor/Unit ID read-only, quem manda e a familia hospedeira."""
    try:
        return getattr(elemento, 'SuperComponent', None) is not None
    except Exception:
        return False


def categoria_de(elemento):
    try:
        return elemento.Category.Name if elemento.Category is not None else ''
    except Exception:
        return ''


_GRUPO_DE_MODELO = int(BuiltInCategory.OST_IOSModelGroups)


def eh_de_modelo(elemento):
    try:
        categoria = elemento.Category
        if categoria is None:
            return False
        # 16/09/2026: "Grupos de modelo" e CategoryType.Internal (medido por
        # MCP) — sem esta linha a instancia do grupo sumia em "Visiveis na
        # vista"/"Projeto inteiro" e nao recebia os valores dos membros
        if id_value(categoria.Id) == _GRUPO_DE_MODELO:
            return True
        if categoria.CategoryType != CategoryType.Model:
            return False
        if elemento.ViewSpecific:
            return False
        return id_value(categoria.Id) not in _FORA
    except Exception:
        return False


def _topo(doc, elemento):
    atual = elemento
    for _ in range(20):
        try:
            gid = atual.GroupId
        except Exception:
            return atual
        if gid is None or id_value(gid) <= 0:
            return atual
        pai = doc.GetElement(gid)
        if pai is None:
            return atual
        atual = pai
    return atual


#: grupo mais externo (o proprio elemento, se solto) — publico para a janela
topo = _topo


def elementos(doc, uidoc, escopo):
    """Elementos do topo do escopo (grupos no lugar dos membros)."""
    if escopo == SELECAO:
        return [e for e in (doc.GetElement(i)
                            for i in uidoc.Selection.GetElementIds())
                if e is not None]
    if escopo == VISTA:
        coletor = FilteredElementCollector(doc, uidoc.ActiveView.Id)
    else:
        coletor = FilteredElementCollector(doc)
    vistos = set()
    saida = []
    for elemento in coletor.WhereElementIsNotElementType().ToElements():
        if not eh_de_modelo(elemento):
            continue
        topo = _topo(doc, elemento)
        chave = id_value(topo.Id)
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(topo)
    return saida
