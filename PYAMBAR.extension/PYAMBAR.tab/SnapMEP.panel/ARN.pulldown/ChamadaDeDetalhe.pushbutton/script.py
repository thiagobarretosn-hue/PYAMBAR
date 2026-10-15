# -*- coding: utf-8 -*-
"""
Chamada de Detalhe
Cria chamadas de detalhe para model groups do projeto.
Ativa o attached detail group na vista criada, rotaciona o crop view
para alinhar o lado maior na horizontal, e redimensiona pelo detail group.

A orientacao sai do marcador retangular do model group (`Plywood Frame`) e,
quando ele nao existe, das detail lines do attached detail group — a via antiga.
Sem nenhum dos dois a vista NAO gira, e a ferramenta diz isso no relatorio.
Decisao em `lib/Snippets/_group_orient.py` (pura, testada).

DESDE A v6.0 — PELA CHAPA, ANTES DO GRUPO (10/09/2026)
------------------------------------------------------
O Thiago: cotas e tags se organizam melhor na vista de detalhe, e o grupo e
o ULTIMO estagio ("depois de criado o grupo temos muitas limitacoes da API").
Entao a chamada deixou de depender do grupo.

Com a aranha SOLTA selecionada (sem Model Group, com a chapa de plywood):
  - orienta pela chapa e enquadra os quatro cantos dela + 0,5 ft — o mesmo
    ~9 x 5 ft das 16 vistas feitas a mao (medido);
  - nomeia "ARN TYP #N - 04 - LEVEL 4": a aranha, depois o nivel da vista;
  - aplica o modelo da config (padrao `ARN TYP`). Sem ele no projeto, copia
    de `ARN_TYP_modelo.rvt` — os 4 filtros `Pre Fab` chegam com os ids
    remapeados para os system types copiados junto.

Com grupos (ou nada) selecionados, segue o caminho de antes, e tambem aplica
o modelo da config em vez de perguntar.

A VISTA MOSTRA SO A ARANHA (v6.1, 10/09/2026)
---------------------------------------------
"So deveria aparecer a aranha e nada mais — usar ocultar na vista, pois o
filtro da vista nao supre tudo." Depois do modelo, oculta elemento a elemento
o que nao e da aranha: a aranha vizinha, linhas de separacao, marcas de
outras vistas. Da aranha = pecas + DEPENDENTES (as linhas de centro dos tubos
sao elementos proprios) + subcomponentes + os dependentes da vista (recorte e
anotacoes). Sistemas, sem grafico, ficam. Regra em `_vista_so_aranha`.
Vista que ja existe: oferece limpar — serve para as aranhas ja feitas.

ARANHA JA AGRUPADA, REABERTA PELO PAINEL (v6.2, 10/09/2026)
-----------------------------------------------------------
O Fluxo ARN abre uma aranha agrupada pelo GRUPO. Selecionado sozinho, um grupo
de aranha vale pelos membros: a chamada segue o caminho da chapa — e numa
vista que ja existe, oferece limpar.

VERSAO: 6.2
AUTOR: Thiago Barreto Sobral Nunes
"""
__title__ = "Chamada de\nDetalhe"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "6.2"

# ============================================================================
# IMPORTS
# ============================================================================

import math
import os
import sys
import traceback
from collections import OrderedDict

from Autodesk.Revit.DB import (
    BoundingBoxXYZ,
    BuiltInCategory,
    BuiltInParameter,
    CopyPasteOptions,
    DuplicateTypeAction,
    Element,
    ElementId,
    ElementTransformUtils,
    FamilyInstance,
    FilteredElementCollector,
    Group,
    IDuplicateTypeNamesHandler,
    Level,
    Line,
    MEPSystem,
    Transform,
    View,
    ViewPlan,
    ViewSection,
    ViewFamilyType,
    ViewFamily,
    ViewType,
    XYZ,
)
from System.Collections.Generic import List

from pyrevit import revit, forms, script

LIB_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.append(LIB_PATH)

from Snippets._group_orient import (
    FONTE_MARCADOR,
    escolher_angulo,
    precisa_rotacionar,
)
from Snippets._aranha_naming import (
    aranha_do_nome,
    nome_aranha,
    nome_vista_detalhe,
)
from Snippets._aranha_doc_config import (
    ARQUIVO_SEMENTE,
    MODELO,
    MODELO_DA_SEMENTE,
    carregar,
)
from Snippets._nivel_alvo import nivel_do_piso
from Snippets._vista_so_aranha import MANTIDO_NAO_PODE, ids_a_ocultar

# ============================================================================
# GLOBALS
# ============================================================================

doc = revit.doc
uidoc = revit.uidoc
active_view = doc.ActiveView
output = script.get_output()

ATTACHED_DETAIL_CAT = -2000097
VIEWER_CAT = -2000278
GENERIC_MODEL_CAT = -2000151
MARGIN = 0.5

# Nome (parcial, minusculas) da familia que serve de marcador de orientacao.
# Os grupos novos usam a `Plywood Frame`; se nenhuma familia bater o token,
# qualquer modelo generico do grupo e tentado como marcador.
MARCADOR_TOKEN = 'plywood'

#: O .rvt com o modelo `ARN TYP` — de onde ele vem quando o projeto nao o tem.
SEMENTE = os.path.join(os.path.dirname(__file__), ARQUIVO_SEMENTE)

TITULO = 'Chamada de Detalhe'

# ============================================================================
# HELPERS
# ============================================================================

from pyrevit.compat import get_elementid_value_func
get_element_id_value = get_elementid_value_func()


def get_name(element):
    try:
        return Element.Name.GetValue(element)
    except Exception:
        return "SemNome"


def find_viewer_element(view):
    """Encontra o viewer element (cat -2000278) associado a vista."""
    dep_ids = view.GetDependentElements(None)
    for did in dep_ids:
        el = doc.GetElement(did)
        if el and el.Category and el.Category.Id.Value == VIEWER_CAT:
            return el
    return None


def find_detail_groups_in_view(model_group, view):
    """Todos os attached detail groups do model group visiveis na vista.

    Existe grupo com MAIS DE UM attached detail group (o `ARN TYP#V` tem dois
    chamados COTAS). Pegar so o primeiro perdia metade do conteudo no resize.
    """
    encontrados = []
    all_groups = (
        FilteredElementCollector(doc, view.Id)
        .OfClass(Group)
        .WhereElementIsNotElementType()
        .ToElements()
    )
    for g in all_groups:
        gt = doc.GetElement(g.GetTypeId())
        if not gt or not gt.Category:
            continue
        if gt.Category.Id.Value != ATTACHED_DETAIL_CAT:
            continue
        if g.AttachedParentId == model_group.Id:
            encontrados.append(g)
    return encontrados


def find_marker_instance(model_group):
    """Familia retangular do model group que define a orientacao.

    Prioriza a familia cujo nome contem MARCADOR_TOKEN; se nenhuma bater,
    devolve o primeiro modelo generico do grupo (o snippet descarta sozinho o
    que for quase quadrado). Devolve None quando o grupo nao tem nenhum.
    """
    try:
        member_ids = model_group.GetMemberIds()
    except Exception:
        return None

    reserva = None
    for mid in member_ids:
        m = doc.GetElement(mid)
        if not m or not m.Category:
            continue
        if m.Category.Id.Value != GENERIC_MODEL_CAT:
            continue
        if not hasattr(m, 'Symbol'):
            continue
        nome_familia = get_name(m.Symbol.Family).lower()
        if MARCADOR_TOKEN in nome_familia:
            return m
        if reserva is None:
            reserva = m
    return reserva


def marker_metrics(instance):
    """(rotacao, dx_local, dy_local) do marcador, ou (None, None, None).

    As medidas saem do bounding box do SYMBOL — espaco da familia, sem a
    rotacao junto. Medido: `Plywood Frame` = 8 x 4 ft, e a rotacao do
    LocationPoint bate com atan2(BasisX.Y, BasisX.X) em 6 de 6 instancias.
    """
    if instance is None:
        return None, None, None

    loc = instance.Location
    if not hasattr(loc, 'Rotation'):
        return None, None, None

    bb = instance.Symbol.get_BoundingBox(None)
    if bb is None:
        return None, None, None

    return loc.Rotation, bb.Max.X - bb.Min.X, bb.Max.Y - bb.Min.Y


def collect_marker_points(instance):
    """Os quatro cantos do marcador no mundo.

    Servem para enquadrar o crop quando o detail group nao tem mais linhas.
    O insertion point da familia e o CANTO (symMin = 0,0), nao o centro — por
    isso os cantos saem do bbox do symbol, nunca de um centro presumido.
    """
    if instance is None:
        return []

    bb = instance.Symbol.get_BoundingBox(None)
    if bb is None:
        return []

    transform = instance.GetTransform()
    cantos_locais = [
        XYZ(bb.Min.X, bb.Min.Y, 0),
        XYZ(bb.Max.X, bb.Min.Y, 0),
        XYZ(bb.Max.X, bb.Max.Y, 0),
        XYZ(bb.Min.X, bb.Max.Y, 0),
    ]
    return [transform.OfPoint(p) for p in cantos_locais]


def collect_line_points(group_instance):
    """Coleta pontos de todas as linhas/curvas recursivamente."""
    points = []
    try:
        member_ids = group_instance.GetMemberIds()
    except Exception:
        return points

    for mid in member_ids:
        m = doc.GetElement(mid)
        if not m:
            continue
        if isinstance(m, Group):
            points.extend(collect_line_points(m))
            continue
        loc = m.Location
        if loc and hasattr(loc, 'Curve'):
            try:
                curve = loc.Curve
                points.append(curve.GetEndPoint(0))
                points.append(curve.GetEndPoint(1))
            except Exception:
                pass
    return points


def collect_line_data(group_instance):
    """Coleta (angulo, comprimento) de todas as linhas recursivamente."""
    results = []
    try:
        member_ids = group_instance.GetMemberIds()
    except Exception:
        return results

    for mid in member_ids:
        m = doc.GetElement(mid)
        if not m:
            continue
        if isinstance(m, Group):
            results.extend(collect_line_data(m))
            continue
        loc = m.Location
        if loc and hasattr(loc, 'Curve'):
            try:
                curve = loc.Curve
                p0 = curve.GetEndPoint(0)
                p1 = curve.GetEndPoint(1)
                dx = p1.X - p0.X
                dy = p1.Y - p0.Y
                length = math.sqrt(dx * dx + dy * dy)
                if length > 0.01:
                    results.append((math.atan2(dy, dx), length))
            except Exception:
                pass
    return results


def decidir_orientacao(model_group, detail_groups):
    """(angulo, fonte, marcador) para alinhar o lado maior na horizontal.

    Le as duas referencias possiveis e deixa a decisao com o snippet puro:
    o marcador do model group tem prioridade, as detail lines sao o fallback.
    `fonte` e None quando o grupo nao oferece nenhuma das duas — e ai a
    ferramenta relata em vez de girar por acaso.
    """
    marcador = find_marker_instance(model_group)
    rot, dx, dy = marker_metrics(marcador)

    linhas = []
    for dg in detail_groups:
        linhas.extend(collect_line_data(dg))

    angulo, fonte = escolher_angulo(rot, dx, dy, linhas)
    return angulo, fonte, marcador


def rotate_crop(view, angle, center):
    """Rotaciona o crop via viewer element."""
    viewer = find_viewer_element(view)
    if not viewer:
        return

    axis = Line.CreateBound(
        XYZ(center.X, center.Y, 0),
        XYZ(center.X, center.Y, 100),
    )
    ElementTransformUtils.RotateElement(doc, viewer.Id, axis, angle)


def resize_crop_to_points(view, points):
    """
    Redimensiona o crop para enquadrar os pontos dados.
    Transforma pontos world->local da vista rotacionada.
    """
    if not points:
        return

    crop = view.CropBox
    inv = crop.Transform.Inverse

    local_xs = []
    local_ys = []
    for p in points:
        lc = inv.OfPoint(p)
        local_xs.append(lc.X)
        local_ys.append(lc.Y)

    new_crop = BoundingBoxXYZ()
    new_crop.Transform = crop.Transform
    new_crop.Min = XYZ(
        min(local_xs) - MARGIN,
        min(local_ys) - MARGIN,
        crop.Min.Z,
    )
    new_crop.Max = XYZ(
        max(local_xs) + MARGIN,
        max(local_ys) + MARGIN,
        crop.Max.Z,
    )
    view.CropBox = new_crop


def get_view_family_type():
    vft = doc.GetElement(active_view.GetTypeId())
    if vft:
        return vft
    vfts = FilteredElementCollector(doc).OfClass(ViewFamilyType).ToElements()
    for v in vfts:
        if v.ViewFamily == ViewFamily.FloorPlan:
            return v
    return None


def rename_view_safe(view, base_name, group_name, group_id):
    # v6.0: grupo de aranha leva o nome padrao, "ARN TYP #N - 04 - LEVEL 4"
    target = (nome_padrao_da_vista(view, group_name)
              or "{} - {}".format(base_name, group_name))
    try:
        Element.Name.SetValue(view, target)
        return target
    except Exception:
        fallback = "{} - {} [{}]".format(base_name, group_name, group_id)
        try:
            Element.Name.SetValue(view, fallback)
            return fallback
        except Exception:
            return get_name(view)


def collect_view_templates():
    templates = []
    for v in FilteredElementCollector(doc).OfClass(View).ToElements():
        if v.IsTemplate:
            templates.append(v)
    return templates


def is_group_in_view(group, view):
    """Verifica se o grupo eh visivel na vista."""
    visible = (
        FilteredElementCollector(doc, view.Id)
        .OfCategory(BuiltInCategory.OST_IOSModelGroups)
        .WhereElementIsNotElementType()
        .ToElements()
    )
    for g in visible:
        if g.Id == group.Id:
            return True
    return False


def find_views_with_group(group):
    """Encontra ViewPlans onde o grupo eh visivel."""
    result = []
    all_views = FilteredElementCollector(doc).OfClass(ViewPlan).ToElements()
    for v in all_views:
        if v.IsTemplate:
            continue
        try:
            visible = (
                FilteredElementCollector(doc, v.Id)
                .OfCategory(BuiltInCategory.OST_IOSModelGroups)
                .WhereElementIsNotElementType()
                .ToElements()
            )
            for g in visible:
                if g.Id == group.Id:
                    result.append(v)
                    break
        except Exception:
            pass
    return result


# ============================================================================
# v6.0 - MODELO DE VISTA DA CONFIG, COM A SEMENTE DE RESERVA
# ============================================================================

class UsarTiposDoDestino(IDuplicateTypeNamesHandler):
    """Tipo com o mesmo nome no projeto: fica o do projeto.

    O `ARN TYP` leva junto os system types `10.03.02-ARN Sewer` e
    `10.03.02-KIT ARN Sewer`, que os filtros referenciam. Num projeto que ja
    os tem, duplicar criaria um `... 1` que nenhum tubo usa — e os filtros
    passariam a apontar para ele.
    """

    def OnDuplicateTypeNamesFound(self, args):
        return DuplicateTypeAction.UseDestinationTypes


def achar_modelo(nome, documento=None):
    """O modelo de PLANTA com esse nome — a chamada de detalhe e uma planta."""
    documento = documento or doc
    for v in FilteredElementCollector(documento).OfClass(View).ToElements():
        if (v.IsTemplate and v.ViewType == ViewType.FloorPlan
                and get_name(v) == nome):
            return v
    return None


def _mesmo_arquivo(a, b):
    return (os.path.normcase(os.path.abspath(a))
            == os.path.normcase(os.path.abspath(b)))


def importar_da_semente(nome):
    """(modelo, erro) — copia o modelo do .rvt semente para este projeto.

    Medido em 10/09/2026, por MCP, num projeto vazio: a copia leva os 4
    filtros com os ids remapeados para os system types copiados junto; numa
    segunda copia, filtros de mesmo nome sao REUSADOS, nao duplicados. Chegam
    26 dos 46 parametros controlados — os 20 que faltam sao parametros do
    PROJETO (Unit ID, Floor, PHASE...) e as sobreposicoes de vinculo, que a
    semente nao tem como carregar.
    """
    if not os.path.exists(SEMENTE):
        return None, 'a semente não está em {}'.format(SEMENTE)

    aplicacao = doc.Application
    fonte = None
    abri = False
    for aberto in aplicacao.Documents:
        try:
            caminho = aberto.PathName
        except Exception:
            caminho = None
        if caminho and _mesmo_arquivo(caminho, SEMENTE):
            fonte = aberto
            break

    try:
        if fonte is None:
            fonte = aplicacao.OpenDocumentFile(SEMENTE)
            abri = True
        original = achar_modelo(nome, fonte)
        if original is None:
            return None, 'a semente não tem o modelo "{}"'.format(nome)
        ids = List[ElementId]()
        ids.Add(original.Id)
        opcoes = CopyPasteOptions()
        opcoes.SetDuplicateTypeNamesHandler(UsarTiposDoDestino())
        with revit.Transaction('Importar modelo {}'.format(nome), doc=doc):
            ElementTransformUtils.CopyElements(
                fonte, ids, doc, Transform.Identity, opcoes)
    except Exception as erro:
        return None, 'a cópia da semente falhou: {}'.format(erro)
    finally:
        if abri and fonte is not None:
            try:
                fonte.Close(False)
            except Exception as erro:
                output.print_md('- a semente ficou aberta: {}'.format(erro))

    modelo = achar_modelo(nome)
    if modelo is None:
        return None, ('a cópia terminou, mas o modelo "{}" não apareceu no '
                      'projeto'.format(nome))
    return modelo, None


def garantir_modelo(nome):
    """(modelo, origem, aviso). `origem` e 'projeto' ou 'semente'."""
    if not nome:
        return None, None, 'a configuração diz para não usar modelo de vista'
    modelo = achar_modelo(nome)
    if modelo is not None:
        return modelo, 'projeto', None
    if nome != MODELO_DA_SEMENTE:
        return None, None, (
            'o modelo "{}" não existe neste projeto, e só o "{}" vem da '
            'semente. Troque na aba Configuração do Fluxo ARN.'.format(
                nome, MODELO_DA_SEMENTE))
    modelo, erro = importar_da_semente(nome)
    if modelo is None:
        return None, None, erro
    return modelo, 'semente', None


def aplicar_modelo(vistas, modelo):
    """Lista de (vista, erro) das que recusaram o modelo."""
    recusadas = []
    with revit.Transaction('Aplicar modelo de vista'):
        for vista in vistas:
            try:
                vista.ViewTemplateId = modelo.Id
            except Exception as erro:
                recusadas.append((vista, str(erro)))
    return recusadas


def relatar_modelo(modelo, origem, aviso, recusadas):
    if modelo is not None:
        output.print_md('- modelo de vista: **{}**{}'.format(
            get_name(modelo),
            ' — importado de `{}`'.format(ARQUIVO_SEMENTE)
            if origem == 'semente' else ''))
        for vista, erro in recusadas:
            output.print_md('  - {} recusou o modelo: {}'.format(
                output.linkify(vista.Id), erro))
    elif aviso:
        output.print_md('- **sem modelo de vista:** {}'.format(aviso))


# ============================================================================
# v6.0 - A ARANHA SOLTA, GUIADA PELA CHAPA
# ============================================================================

def ocultar_o_que_nao_e_da_aranha(vista, ids_da_aranha):
    """Oculta na vista o que nao e da aranha. Devolve (quantos, resumo).

    Da aranha = as pecas, os DEPENDENTES delas (a linha de centro de cada tubo
    e um elemento proprio — ocultar so pelas pecas apagaria o desenho) e os
    subcomponentes; mais os dependentes da propria vista (o recorte e as
    anotacoes). A decisao mora em `_vista_so_aranha` (pura, testada).

    Abre a propria Transaction: chamar fora de outra.
    """
    da_aranha = set()
    for eid in ids_da_aranha:
        elemento = doc.GetElement(eid)
        if elemento is None:
            continue
        da_aranha.add(get_element_id_value(eid))
        for dep in elemento.GetDependentElements(None):
            da_aranha.add(get_element_id_value(dep))
        if isinstance(elemento, FamilyInstance):
            for sub in elemento.GetSubComponentIds():
                da_aranha.add(get_element_id_value(sub))
    for dep in vista.GetDependentElements(None):
        da_aranha.add(get_element_id_value(dep))

    visiveis = []
    por_valor = {}
    for elemento in (FilteredElementCollector(doc, vista.Id)
                     .WhereElementIsNotElementType().ToElements()):
        valor = get_element_id_value(elemento.Id)
        por_valor[valor] = elemento.Id
        dono = get_element_id_value(elemento.OwnerViewId)
        try:
            pode = elemento.CanBeHidden(vista)
        except Exception:
            pode = False        # contado como "nao pode ocultar" no resumo
        visiveis.append((valor, dono if dono > 0 else None, pode,
                         not isinstance(elemento, MEPSystem)))

    ocultar, resumo = ids_a_ocultar(visiveis, da_aranha,
                                    get_element_id_value(vista.Id))
    if ocultar:
        ids = List[ElementId]()
        for valor in ocultar:
            ids.Add(por_valor[valor])
        with revit.Transaction('Ocultar o que não é da aranha'):
            vista.HideElements(ids)
    return len(ocultar), resumo


def relatar_ocultos(quantos, resumo):
    output.print_md(
        '- ocultados na vista: **{}** elemento(s) que não são da aranha{}'
        .format(quantos,
                ' ({} não aceitaram ocultar)'.format(resumo[MANTIDO_NAO_PODE])
                if resumo.get(MANTIDO_NAO_PODE) else ''))
    output.print_md(
        '  O que for modelado depois na região aparece: rode a Chamada de '
        'novo para limpar. Para ver o oculto: "Revelar elementos ocultos".')


def nome_padrao_da_vista(view, nome_do_grupo):
    """'ARN TYP #N - 04 - LEVEL 4' quando o grupo e de aranha, senao None."""
    aranha = aranha_do_nome(nome_do_grupo)
    nivel = getattr(view, 'GenLevel', None)
    if aranha is None or nivel is None:
        return None
    return nome_vista_detalhe(aranha, get_name(nivel))


def selecao_da_aranha():
    """(elementos, chapa) quando a selecao e uma aranha SOLTA com plywood.

    Com Model Group na selecao, ou sem chapa, devolve (None, None) e a
    ferramenta segue o caminho antigo, por grupo.
    """
    elementos = []
    chapa = None
    selecionados = [doc.GetElement(eid)
                    for eid in uidoc.Selection.GetElementIds()]
    selecionados = [e for e in selecionados if e is not None]
    # uma aranha JA agrupada, sozinha na selecao (o Fluxo ARN a reabre
    # assim): vale pelos membros
    if (len(selecionados) == 1 and isinstance(selecionados[0], Group)
            and aranha_do_nome(get_name(selecionados[0].GroupType))):
        selecionados = [doc.GetElement(m)
                        for m in selecionados[0].GetMemberIds()]
    for elemento in selecionados:
        if elemento is None:
            continue
        if isinstance(elemento, Group):
            return None, None
        elementos.append(elemento)
        if chapa is None and isinstance(elemento, FamilyInstance):
            familia = get_name(elemento.Symbol.Family) or ''
            if MARCADOR_TOKEN in familia.lower():
                chapa = elemento
    if chapa is None:
        return None, None
    return elementos, chapa


def aranha_da_selecao(elementos):
    """'ARN TYP #N' — do painel, ou pelo system DOMINANTE dos elementos.

    Pelo Fluxo ARN a letra chega pronta (`__arn_letra__`). Solta, a
    ferramenta a le do system que a Separar Aranha gravou — o dominante, nunca
    o primeiro encontrado ([[feedback-medir-pelo-dominante]]).
    """
    letra = globals().get('__arn_letra__')
    if letra:
        return nome_aranha(letra)
    contagem = {}
    for elemento in elementos:
        param = elemento.get_Parameter(BuiltInParameter.RBS_SYSTEM_NAME_PARAM)
        aranha = aranha_do_nome(param.AsString() if param is not None
                                else None)
        if aranha:
            contagem[aranha] = contagem.get(aranha, 0) + 1
    if not contagem:
        return None
    return max(sorted(contagem), key=lambda a: contagem[a])


def nivel_do_piso_da_chapa(chapa):
    """O Level da laje que a chapa serve — o de elevacao mais proxima.

    Mesma medida da Inserir Plywood (`Level.Elevation` contra o Z da chapa),
    que foi quem a pos ali.
    """
    elevacoes = {}
    niveis = {}
    for nivel in (FilteredElementCollector(doc).OfClass(Level)
                  .WhereElementIsNotElementType().ToElements()):
        chave = get_element_id_value(nivel.Id)
        elevacoes[chave] = nivel.Elevation
        niveis[chave] = nivel
    return niveis.get(nivel_do_piso(elevacoes,
                                    chapa.GetTransform().Origin.Z))


def vista_com_o_nome(nome):
    for v in FilteredElementCollector(doc).OfClass(View).ToElements():
        if not v.IsTemplate and get_name(v) == nome:
            return v
    return None


def criar_pela_chapa(elementos, chapa):
    """A chamada da aranha solta: guiada pela chapa, nomeada e com modelo."""
    config, erro_config = carregar()

    aranha = aranha_da_selecao(elementos)
    if not aranha:
        forms.alert(
            'Não achei o nome da aranha: nenhum elemento tem system '
            '"ARN TYP #..." e o painel não passou a letra.\n\n'
            'Rode a Separar Aranha, ou use o Fluxo ARN.',
            title=TITULO, warn_icon=True)
        return

    nivel_vista = active_view.GenLevel
    if nivel_vista is None:
        forms.alert('A vista ativa não tem nível associado.',
                    title=TITULO, warn_icon=True)
        return

    nivel_chapa = nivel_do_piso_da_chapa(chapa)
    if nivel_chapa is not None and nivel_chapa.Id != nivel_vista.Id:
        if not forms.alert(
                'A vista ativa e do nível "{}", mas a chapa está no piso do '
                '"{}".\n\nA chamada nasce na vista ativa e leva o nível dela '
                'no nome. Criar assim mesmo?'.format(
                    get_name(nivel_vista), get_name(nivel_chapa)),
                title=TITULO, yes=True, no=True):
            return

    nome = nome_vista_detalhe(aranha, get_name(nivel_vista))
    existente = vista_com_o_nome(nome)
    if existente is not None:
        output.print_md('## Chamada de Detalhe')
        output.print_md('A vista **{}** já existe: {}.'.format(
            nome, output.linkify(existente.Id)))
        if forms.alert(
                'A vista "{}" já existe.\n\nOcultar nela o que não é da '
                'aranha?'.format(nome),
                title=TITULO, yes=True, no=True):
            quantos, resumo = ocultar_o_que_nao_e_da_aranha(
                existente, [e.Id for e in elementos])
            relatar_ocultos(quantos, resumo)
            try:
                uidoc.RequestViewChange(existente)
            except Exception as erro:
                output.print_md('- não consegui abrir a vista: {}'.format(erro))
        return

    if aranha_do_nome(get_name(active_view)):
        forms.alert(
            'A vista ativa já é a vista de detalhe de uma aranha ("{}").\n\n'
            'Abra a planta do piso e rode de novo — a chamada nasce na vista '
            'ativa.'.format(get_name(active_view)),
            title=TITULO, warn_icon=True)
        return

    vft = get_view_family_type()
    if not vft:
        forms.alert('Nenhum tipo de vista de planta encontrado.',
                    title=TITULO, warn_icon=True)
        return

    cantos = collect_marker_points(chapa)
    caixa = chapa.get_BoundingBox(None)
    if not cantos or caixa is None:
        forms.alert('A chapa não devolveu o contorno (bounding box vazio).',
                    title=TITULO, warn_icon=True)
        return

    # o modelo ANTES do grupo de transacoes: importar da semente abre outro
    # documento, e isso nao tem por que ficar preso ao Ctrl+Z da vista
    modelo, origem, aviso = garantir_modelo(config[MODELO])

    rot, dx, dy = marker_metrics(chapa)
    angulo, fonte = escolher_angulo(rot, dx, dy, [])
    xs = [p.X for p in cantos]
    ys = [p.Y for p in cantos]
    centro = XYZ(sum(xs) / len(xs), sum(ys) / len(ys), cantos[0].Z)

    recusadas = []
    with revit.TransactionGroup('Chamada de detalhe - {}'.format(aranha)):
        with revit.Transaction('Callout - {}'.format(aranha)):
            vista = ViewSection.CreateCallout(
                doc, active_view.Id, vft.Id,
                XYZ(min(xs) - MARGIN, min(ys) - MARGIN, caixa.Min.Z),
                XYZ(max(xs) + MARGIN, max(ys) + MARGIN, caixa.Max.Z))
            vista.CropBoxActive = True
            vista.CropBoxVisible = True

        if precisa_rotacionar(angulo):
            with revit.Transaction('Rotacionar - {}'.format(aranha)):
                rotate_crop(vista, angulo, centro)

        with revit.Transaction('Enquadrar - {}'.format(aranha)):
            resize_crop_to_points(vista, cantos)

        with revit.Transaction('Nomear - {}'.format(aranha)):
            Element.Name.SetValue(vista, nome)
        nome_final = get_name(vista)

        if modelo is not None:
            recusadas = aplicar_modelo([vista], modelo)

        # depois do modelo: o filtro dele ja tirou os tubos que nao sao
        # Pre Fab; o resto sai elemento a elemento
        quantos, resumo_oculto = ocultar_o_que_nao_e_da_aranha(
            vista, [e.Id for e in elementos])

    # ------------------------------------------------------------ relatorio
    output.print_md('## Chamada de Detalhe')
    output.print_md('- vista: {} **{}**'.format(
        output.linkify(vista.Id), nome_final))
    if nome_final != nome:
        output.print_md('  pedi "{}" e o Revit gravou outro. Confira.'.format(
            nome))
    relatar_modelo(modelo, origem, aviso, recusadas)
    relatar_ocultos(quantos, resumo_oculto)
    if fonte == FONTE_MARCADOR and precisa_rotacionar(angulo):
        output.print_md('- orientada pela chapa ({:.1f} graus)'.format(
            math.degrees(angulo)))
    elif fonte == FONTE_MARCADOR:
        output.print_md('- a chapa já está na horizontal: não precisou girar')
    else:
        output.print_md(
            '- **não girou:** a chapa e quase quadrada e não diz qual lado e '
            'o maior')
    if erro_config:
        output.print_md('- {}'.format(erro_config))
    output.print_md('Um Ctrl+Z desfaz a vista.{}'.format(
        ' O modelo importado da semente e desfeito a parte.'
        if origem == 'semente' else ''))

    try:
        uidoc.RequestViewChange(vista)
    except Exception as erro:
        output.print_md('- não consegui abrir a vista: {}'.format(erro))


# ============================================================================
# MAIN
# ============================================================================

def main():
    try:
        # ETAPA 1 - Verificar vista ativa
        # (alert + return, nao exitscript: pelo Fluxo ARN este script roda
        # dentro de um ExternalEvent, e o SystemExit escaparia do handler)
        if not isinstance(active_view, ViewPlan):
            forms.alert(
                "A vista ativa deve ser uma vista de planta.",
                title=TITULO,
            )
            return

        # v6.0 - a aranha solta, guiada pela chapa
        elementos, chapa = selecao_da_aranha()
        if chapa is not None:
            criar_pela_chapa(elementos, chapa)
            return

        # ETAPA 2 - Coletar model groups do projeto
        all_groups = list(
            FilteredElementCollector(doc)
            .OfCategory(BuiltInCategory.OST_IOSModelGroups)
            .WhereElementIsNotElementType()
            .ToElements()
        )

        if not all_groups:
            forms.alert("Nenhum model group encontrado.", exitscript=True)

        group_dict = OrderedDict()
        for g in all_groups:
            gt = doc.GetElement(g.GetTypeId())
            name = get_name(gt) if gt else 'SemNome'
            if name not in group_dict:
                group_dict[name] = []
            group_dict[name].append(g)

        # ETAPA 3 - Selecionar grupos
        display_items = []
        display_to_name = {}
        for name in sorted(group_dict.keys()):
            count = len(group_dict[name])
            sample = group_dict[name][0]
            has_detail = False
            try:
                avail = sample.GetAvailableAttachedDetailGroupTypeIds()
                has_detail = avail.Count > 0
            except Exception:
                pass

            suffix = " [+detail]" if has_detail else ""
            label = "{}{} ({})".format(name, suffix, count)
            display_items.append(label)
            display_to_name[label] = name

        selected_display = forms.SelectFromList.show(
            display_items,
            title='Grupos',
            multiselect=True,
            button_name='Selecionar',
        )

        if not selected_display:
            script.exit()

        # Montar lista de tipos selecionados com suas instancias
        selected_types = OrderedDict()
        for disp in selected_display:
            name = display_to_name[disp]
            selected_types[name] = group_dict[name]

        # Verificar se algum tipo tem mais de 1 instancia
        has_multiple = any(len(v) > 1 for v in selected_types.values())

        one_per_type = True  # default: 1 callout por tipo
        if has_multiple:
            mode = forms.CommandSwitchWindow.show(
                ['Uma por tipo', 'Uma por instância'],
                message='Alguns tipos tem múltiplas instâncias.\n'
                        'Criar uma chamada por tipo ou por instância?',
            )
            if not mode:
                script.exit()
            one_per_type = (mode == 'Uma por tipo')

        # Montar lista final de grupos
        selected_groups = []
        if one_per_type:
            for name, instances in selected_types.items():
                # Priorizar instancia com detail group shown
                best = instances[0]
                for inst in instances:
                    try:
                        shown = inst.GetShownAttachedDetailGroupTypeIds(
                            active_view
                        )
                        if shown.Count > 0:
                            best = inst
                            break
                    except Exception:
                        pass
                selected_groups.append(best)
        else:
            for name, instances in selected_types.items():
                selected_groups.extend(instances)

        vft = get_view_family_type()
        if not vft:
            forms.alert("Nenhum tipo de vista encontrado.", exitscript=True)

        created_views = []
        grupo_da_vista = {}
        errors = []
        sem_orientacao = []   # nem marcador nem detail lines: nao girou
        por_marcador = []     # girou pelo marcador (via nova)

        # Separar grupos visiveis na vista ativa dos que nao estao
        groups_in_active = []
        groups_elsewhere = []  # (group, group_name)
        for group in selected_groups:
            gt = doc.GetElement(group.GetTypeId())
            gn = get_name(gt) if gt else 'SemNome'
            if is_group_in_view(group, active_view):
                groups_in_active.append(group)
            else:
                groups_elsewhere.append((group, gn))

        # Perguntar sobre grupos fora da vista ativa
        extra_pairs = []  # (group, parent_view)
        if groups_elsewhere:
            names = [gn for _, gn in groups_elsewhere]
            msg = (
                "Os seguintes grupos NÃO estão na vista ativa:\n"
                "{}\n\nDeseja criar em outra vista onde aparecem?"
            ).format(", ".join(names))

            criar_outros = forms.alert(
                msg,
                yes=True,
                no=True,
                title="Grupos em outras vistas",
            )

            if criar_outros:
                for group, gn in groups_elsewhere:
                    alt_views = find_views_with_group(group)
                    if not alt_views:
                        errors.append(
                            "'{}': não encontrado em nenhuma vista".format(gn)
                        )
                        continue

                    if len(alt_views) == 1:
                        extra_pairs.append((group, alt_views[0]))
                    else:
                        view_names = [get_name(v) for v in alt_views]
                        chosen = forms.SelectFromList.show(
                            view_names,
                            title="Vista para '{}'".format(gn),
                            multiselect=False,
                            button_name='Selecionar',
                        )
                        if chosen:
                            for v in alt_views:
                                if get_name(v) == chosen:
                                    extra_pairs.append((group, v))
                                    break

        # Montar lista de trabalho: (group, parent_view)
        work_list = [(g, active_view) for g in groups_in_active]
        work_list.extend(extra_pairs)

        # ETAPAS 4-7
        with revit.TransactionGroup("Criar Chamadas de Detalhe"):
            for group, parent_view in work_list:
                group_name = "?"
                try:
                    gt = doc.GetElement(group.GetTypeId())
                    group_name = get_name(gt) if gt else 'SemNome'

                    # VFT da vista pai
                    pv_vft = doc.GetElement(parent_view.GetTypeId()) or vft

                    # Bbox do model group na vista pai
                    bbox = group.get_BoundingBox(parent_view)
                    if not bbox:
                        bbox = group.get_BoundingBox(None)
                    if not bbox:
                        errors.append("'{}' sem BoundingBox".format(group_name))
                        continue

                    p1 = XYZ(bbox.Min.X - MARGIN, bbox.Min.Y - MARGIN, bbox.Min.Z)
                    p2 = XYZ(bbox.Max.X + MARGIN, bbox.Max.Y + MARGIN, bbox.Max.Z)

                    # ETAPA 4 - Criar callout na vista pai
                    with revit.Transaction("Callout - {}".format(group_name)):
                        new_view = ViewSection.CreateCallout(
                            doc, parent_view.Id, pv_vft.Id, p1, p2,
                        )
                        new_view.CropBoxActive = True
                        new_view.CropBoxVisible = True

                    # ETAPA 5 - Ativar detail groups no callout
                    with revit.Transaction("Ativar detail - {}".format(group_name)):
                        groups_in_view = (
                            FilteredElementCollector(doc, new_view.Id)
                            .OfCategory(BuiltInCategory.OST_IOSModelGroups)
                            .WhereElementIsNotElementType()
                            .ToElements()
                        )
                        for gv in groups_in_view:
                            if gv.Id == group.Id:
                                gv.ShowAllAttachedDetailGroups(new_view)
                                break

                    # ETAPA 6 - Orientar e redimensionar o crop
                    details = find_detail_groups_in_view(group, new_view)
                    dominant, fonte, marcador = decidir_orientacao(
                        group, details)

                    if fonte is None:
                        sem_orientacao.append(group_name)
                    elif fonte == FONTE_MARCADOR:
                        por_marcador.append(group_name)

                    if precisa_rotacionar(dominant):
                        loc = group.Location
                        if hasattr(loc, 'Point'):
                            center = loc.Point
                        else:
                            center = XYZ(
                                (bbox.Min.X + bbox.Max.X) / 2,
                                (bbox.Min.Y + bbox.Max.Y) / 2,
                                0,
                            )

                        with revit.Transaction(
                            "Rotacionar - {}".format(group_name)
                        ):
                            rotate_crop(new_view, dominant, center)

                    # Redimensionar pelo que existir: detail lines e o
                    # contorno do marcador. Sem as duas fontes o crop
                    # ficava do tamanho do callout desenhado a mao.
                    points = []
                    for dg in details:
                        points.extend(collect_line_points(dg))
                    points.extend(collect_marker_points(marcador))

                    if points:
                        with revit.Transaction(
                            "Resize - {}".format(group_name)
                        ):
                            resize_crop_to_points(new_view, points)

                    # ETAPA 7 - Renomear
                    with revit.Transaction("Renomear - {}".format(group_name)):
                        original_name = get_name(new_view)
                        final_name = rename_view_safe(
                            new_view,
                            original_name,
                            group_name,
                            get_element_id_value(group.Id),
                        )
                        created_views.append((new_view, final_name))
                        grupo_da_vista[get_element_id_value(
                            new_view.Id)] = group

                except Exception as e:
                    errors.append("'{}': {}".format(group_name, str(e)))

        # ETAPA 8 - Modelo de vista: o da config, sem perguntar (v6.0)
        if created_views:
            config, erro_config = carregar()
            modelo, origem, aviso = garantir_modelo(config[MODELO])
            recusadas = []
            if modelo is not None:
                recusadas = aplicar_modelo(
                    [v for v, _ in created_views], modelo)
            output.print_md('## Chamada de Detalhe')
            relatar_modelo(modelo, origem, aviso, recusadas)
            if erro_config:
                output.print_md('- {}'.format(erro_config))

            # so o grupo na vista: membros, o proprio grupo e os detalhes
            # anexados que ela mostra (esses tem dono em OUTRA vista)
            for view_obj, _ in created_views:
                grupo = grupo_da_vista.get(get_element_id_value(view_obj.Id))
                if grupo is None:
                    continue
                ids = list(grupo.GetMemberIds()) + [grupo.Id]
                for dg in find_detail_groups_in_view(grupo, view_obj):
                    ids.append(dg.Id)
                    ids.extend(dg.GetMemberIds())
                try:
                    quantos, _resumo = ocultar_o_que_nao_e_da_aranha(
                        view_obj, ids)
                    output.print_md('- {}: {} elemento(s) de fora '
                                    'ocultados'.format(get_name(view_obj),
                                                       quantos))
                except Exception as erro:
                    output.print_md('- {}: não consegui ocultar — {}'.format(
                        get_name(view_obj), erro))

        # ETAPA 9 - Mensagem final
        if created_views:
            names = [n for _, n in created_views]
            forms.alert(
                "Vistas criadas: {}\n\n{}".format(
                    len(created_views),
                    "\n".join(names),
                ),
                title="Chamada de Detalhe",
            )

        # Quem nao girou tem de DIZER que nao girou — silencio aqui foi o que
        # escondeu por semanas que a familia tinha substituido as linhas.
        if por_marcador:
            output.print_md(
                "**Orientadas pelo marcador ({}):** {}".format(
                    len(por_marcador), ", ".join(por_marcador)))

        if sem_orientacao:
            output.print_md(
                "**Sem referência de orientação ({}):** {}".format(
                    len(sem_orientacao), ", ".join(sem_orientacao)))
            output.print_md(
                "Estes grupos não tem a família marcador (`{}`) nem detail "
                "lines no attached detail group — a vista foi criada, mas "
                "NÃO girou. Inserir o marcador no grupo resolve.".format(
                    MARCADOR_TOKEN))

        if errors:
            forms.alert(
                "Erros ({}):\n\n{}".format(len(errors), "\n".join(errors)),
                title="Erros",
                warn_icon=True,
            )

        if not created_views and not errors:
            forms.alert("Nenhuma chamada de detalhe criada.")

    except Exception as e:
        output.print_md("**Erro geral:** {}".format(str(e)))
        output.print_md("```\n{}\n```".format(traceback.format_exc()))


if __name__ == "__main__":
    main()
