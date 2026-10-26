# -*- coding: utf-8 -*-
"""Tudo que a Tags Organizadas le e escreve no Revit.

O motor (`Snippets._tag_arranjo`) e a regra dos lineares (`Snippets._tag_trechos`)
sao puros; aqui so ha coleta, medicao (Transaction DESFEITA), obstaculos e a
criacao final. Coordenadas sempre na tela da vista: u = RightDirection,
v = UpDirection, em pes.

Licoes que moram aqui (memoria api-tags):
- IndependentTag.Create nao respeita o ponto -> gravar TagHeadPosition depois.
- Caixa real do texto = bbox com a chamada desligada (a API nao tem extents).
- O ombro liga no CENTRO do texto; o motor ja devolve a cabeca certa.
- Vista FECHADA deixa a criacao ~300x mais lenta: o botao so trabalha na ativa.
"""
from Autodesk.Revit.DB import (
    BuiltInParameter,
    Curve,
    Dimension,
    ElementId,
    ElementType,
    FamilyInstance,
    FamilySymbol,
    FilteredElementCollector,
    GeometryInstance,
    HorizontalTextAlignment,
    ImportInstance,
    IndependentTag,
    LeaderEndCondition,
    Line,
    LocationCurve,
    LocationPoint,
    MEPCurve,
    Options,
    PolyLine,
    Reference,
    RevitLinkInstance,
    TagOrientation,
    TextElement,
    TextNote,
    VerticalTextAlignment,
    Transaction,
    XYZ,
)
from Autodesk.Revit.DB import BuiltInCategory, CategoryType, ViewPlan

from Autodesk.Revit.DB import ConnectorProfileType

from System.Collections.Generic import List

from Snippets._tag_regras import parte_aceita as _parte_aceita
from Snippets._tag_regras import recriaveis_sem_sobra, tags_para_apagar
from Snippets._tag_regras import descidas_na_parede, faixa_dominante, na_faixa, trechos_de_planta
from Snippets._tag_trechos import trechos

#: Motivos de tudo que foi pulado por erro — o script mostra no relatorio.
#: Erro engolido em laco vira 'nao fez nada' sem explicacao (orcamento de
#: except mudo do lab, test_orcamento_except).
AVISOS = []

#: Installation Plans: elemento de CADA pedaco do trecho oferecido como
#: alternativa (a tag alinhada pode ir em qualquer pedaco da trama) —
#: chave -> (link, tubo). O script junta aos 'elementos' antes de aplicar.
PECAS_DO_TRECHO = {}


def avisar(onde, ex):
    AVISOS.append(u'{}: {}'.format(onde, ex))


# ============================================================================
# UTILIDADES
# ============================================================================

def eid(e):
    return e.Value if hasattr(e, 'Value') else e.IntegerValue


def chave(link, e):
    return '{}:{}'.format(eid(link.Id) if link is not None else 0, eid(e.Id))


def chave_ref(ref):
    lid = ref.LinkedElementId
    if lid is not None and lid != ElementId.InvalidElementId:
        return '{}:{}'.format(eid(ref.ElementId), eid(lid))
    return '0:{}'.format(eid(ref.ElementId))


def nome_do_tipo(sym):
    fam = sym.get_Parameter(BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM)
    tip = sym.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
    return u'{} : {}'.format(fam.AsString() if fam else '?', tip.AsString() if tip else '?')


def nome_tipo_elemento(e):
    """'Familia : Tipo' de qualquer elemento (conduite nao e FamilyInstance)."""
    try:
        if isinstance(e, FamilyInstance):
            return nome_do_tipo(e.Symbol)
        t = e.Document.GetElement(e.GetTypeId())
        if t is None:
            return u''
        p = t.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
        f = t.get_Parameter(BuiltInParameter.ALL_MODEL_FAMILY_NAME)
        return u'{} : {}'.format(f.AsString() if f else u'', p.AsString() if p else u'')
    except Exception:
        return u''


def tipos_de_tag(doc, tag_bic):
    return dict((nome_do_tipo(s), s) for s in FilteredElementCollector(doc)
                .OfCategory(tag_bic).OfClass(FamilySymbol))


def uv(p, R, U):
    return (p.DotProduct(R), p.DotProduct(U))


def textos_da_cota(dm, view, R, U):
    """Caixa ESTIMADA do numero de cada segmento da cota. A API nao da a caixa
    do texto e TextPosition volta nulo quando o texto nao e ajustavel (MOTION
    DEM 57, 12/10/2026). O texto fica logo acima da origem do segmento,
    centrado; altura = TEXT_SIZE do tipo, largura ~0,62 da altura por
    caractere — conferido no print: '15 1/8"' ~13,5 mm e '22"' ~5,5 mm."""
    try:
        tam = dm.DimensionType.get_Parameter(BuiltInParameter.TEXT_SIZE).AsDouble()
    except Exception:
        return []
    try:
        fator = dm.DimensionType.get_Parameter(BuiltInParameter.TEXT_WIDTH_SCALE).AsDouble() or 1.0
    except Exception:
        fator = 1.0
    escala = float(view.Scale)
    h = tam * escala
    def _pos(obj):
        # TextPosition lanca NullReference quando o texto nao e ajustavel
        try:
            return obj.TextPosition
        except Exception:
            return None
    pedacos = []
    if dm.NumberOfSegments > 0:
        for sg in dm.Segments:
            if (sg.Value or 0.0) > 1e-9:
                pedacos.append((sg.ValueString, sg.Origin, _pos(sg)))
    elif (dm.Value or 0.0) > 1e-9:
        pedacos.append((dm.ValueString, dm.Origin, _pos(dm)))
    caixas = []
    for texto, origem, pos in pedacos:
        p = pos or origem
        if p is None:
            continue
        u, v = uv(p, R, U)
        w = max(1, len(texto or u'')) * 0.62 * h * fator
        base = v if pos else v + 0.15 * h
        caixas.append((u - w / 2.0, base, u + w / 2.0, base + 1.2 * h))
    return caixas


def caixa_uv(bb, R, U):
    us, vs = [], []
    for x in (bb.Min.X, bb.Max.X):
        for y in (bb.Min.Y, bb.Max.Y):
            for z in (bb.Min.Z, bb.Max.Z):
                p = XYZ(x, y, z)
                us.append(p.DotProduct(R))
                vs.append(p.DotProduct(U))
    return (min(us), min(vs), max(us), max(vs))


def limites_da_vista(view, R, U):
    if not view.CropBoxActive:
        return None
    cb = view.CropBox
    t = cb.Transform
    a, b = t.OfPoint(cb.Min), t.OfPoint(cb.Max)
    ua, va = uv(a, R, U)
    ub, vb = uv(b, R, U)
    return (min(ua, ub), min(va, vb), max(ua, ub), max(va, vb))


def referencia(link, e):
    ref = Reference(e)
    return ref if link is None else ref.CreateLinkReference(link)


# ============================================================================
# PONTA DE SETA (parametro de TIPO da tag — testado 08/10/2026)
# ============================================================================

def listar_setas(doc):
    """[(nome, ElementId)] das pontas de seta do projeto, sem as internas."""
    saida = []
    for t in FilteredElementCollector(doc).OfClass(ElementType):
        if t.get_Parameter(BuiltInParameter.ARROW_TYPE) is None:
            continue
        try:
            nome = t.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
        except Exception:
            nome = None
        if not nome or nome.lower().startswith('secret'):
            continue
        saida.append((nome, t.Id))
    saida.sort(key=lambda x: x[0].lower())
    return saida


def seta_do_tipo(doc, sym):
    p = sym.get_Parameter(BuiltInParameter.LEADER_ARROWHEAD)
    if p is None:
        return None
    sid = p.AsElementId()
    if sid is None or sid == ElementId.InvalidElementId:
        return u'Nenhuma'
    s = doc.GetElement(sid)
    try:
        return s.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
    except Exception:
        return u'?'


def gravar_seta(sym, seta_id):
    """Grava no PROPRIO tipo (decisao do Thiago): muda todas as tags do tipo,
    igual a edicao manual. Chamar dentro de Transaction."""
    p = sym.get_Parameter(BuiltInParameter.LEADER_ARROWHEAD)
    if p is None or p.IsReadOnly:
        return False
    return p.Set(seta_id if seta_id is not None else ElementId.InvalidElementId)


# ============================================================================
# COLETA
# ============================================================================

def fontes(doc, view):
    """[(link ou None, documento, transformacao ou None)] — projeto e vinculos."""
    saida = [(None, doc, None)]
    for li in FilteredElementCollector(doc, view.Id).OfClass(RevitLinkInstance):
        ld = li.GetLinkDocument()
        if ld is not None:
            saida.append((li, ld, li.GetTotalTransform()))
    return saida


def coletor(doc, view, link, bic):
    if link is None:
        return FilteredElementCollector(doc, view.Id).OfCategory(bic).WhereElementIsNotElementType()
    return FilteredElementCollector(doc, view.Id, link.Id).OfCategory(bic).WhereElementIsNotElementType()


def ja_etiquetados(doc, view):
    chaves = set()
    for t in FilteredElementCollector(doc, view.Id).OfClass(IndependentTag):
        try:
            for r in t.GetTaggedReferences():
                chaves.add(chave_ref(r))
        except Exception as ex:
            avisar(u'tag {} sem referencia legivel'.format(eid(t.Id)), ex)
    return chaves


def faixa_da_trama(doc, view, tol_mm=300.0):
    """Faixa de altura (pes) da TRAMA da vista: a cota com mais comprimento
    de tubo HORIZONTAL visivel (projeto e vinculos), +- tol_mm. None se nao
    ha tubo horizontal. Regra pura em _tag_regras.faixa_dominante."""
    alturas = []
    for link, _ld, tr in fontes(doc, view):
        for e in coletor(doc, view, link, BuiltInCategory.OST_PipeCurves):
            lc = e.Location
            if not isinstance(lc, LocationCurve):
                continue
            a, b = lc.Curve.GetEndPoint(0), lc.Curve.GetEndPoint(1)
            if tr is not None:
                a, b = tr.OfPoint(a), tr.OfPoint(b)
            comp = a.DistanceTo(b)
            if comp > 1e-6 and abs(b.Z - a.Z) < 0.02 * comp:
                alturas.append(((a.Z + b.Z) / 2.0, comp))
    return faixa_dominante(alturas, tol_mm / 304.8)


def chaves_recriaveis(doc, view, cats, R, U, faixa=None):
    """Chaves que o 'Refazer' pode apagar: as dos elementos que o botao
    etiquetaria nesta vista nas categorias dadas (a MESMA coleta da
    etiquetagem), tirando toda unidade em que alguma tag ia sobrar.

    Unidade = o que o levantar() trata como um so: o ponto; o trecho de tubo
    (todos os tubos dele); o trecho de conduite (retos + conexoes). Tag que
    sobrevive ao apagar (stub com Stubs desligado, curva Bend, pente que
    junta trechos, tag manual multipla) faz o levantar() seguinte pular a
    unidade — entao as tags dela ficam tambem; sem isso o trecho ficava sem
    tag nenhuma (revisao 13/10/2026). A regra e Snippets._tag_regras
    .recriaveis_sem_sobra (testada sem Revit)."""
    unidades = []
    nenhum = set()
    for cat in cats:
        if cat['modo'] == 'ponto':
            lista, _p = alvos_pontuais(doc, view, cat, nenhum, faixa=faixa)
            unidades.extend((set([item[5]]), set([item[5]])) for item in lista)
        elif cat['modo'] == 'tubo':
            grupos = []
            alvos_tubos(doc, view, cat, nenhum, R, U, todos=grupos, faixa=faixa)
            unidades.extend((g, g) for g in grupos)
        else:
            retos, lig, cx, _el = rede_linear(doc, view, cat, R, U)
            comps, _adj = trechos(retos, lig, cx)
            unidades.extend((set(k for k in c if k in retos), set(c)) for c in comps)
    return recriaveis_sem_sobra(_refs_por_tag(doc, view), unidades)


def _refs_por_tag(doc, view):
    """[(Id da tag, [chave de cada elemento marcado])] das tags da vista."""
    saida = []
    for t in FilteredElementCollector(doc, view.Id).OfClass(IndependentTag):
        try:
            saida.append((t.Id, [chave_ref(r) for r in t.GetTaggedReferences()]))
        except Exception as ex:
            avisar(u'tag {} sem referencia legivel'.format(eid(t.Id)), ex)
    return saida


def apagar_tags(doc, view, recriaveis):
    """'Refazer': apaga as tags da vista cujos elementos o botao vai etiquetar
    de novo (chaves_recriaveis). Antes apagava por CATEGORIA e recriava so
    parte — em planta a tag manual de Elbow/Cap, de curva Bend e de peca
    aninhada sumia e nao voltava (auditoria 12/10/2026). Chamar dentro de
    Transaction. Devolve quantas apagou."""
    apagar = tags_para_apagar(_refs_por_tag(doc, view), recriaveis)
    for i in apagar:
        doc.Delete(i)
    return len(apagar)


def parte_aceita(e, cat, em_planta):
    """Filtro de PartType e de familia (conexoes de tubo, installation plans).
    A regra mora em Snippets._tag_regras (testada sem Revit)."""
    if not (cat.get('partes') or cat.get('partes_planta') or cat.get('excluir_familia')):
        return True
    mep = getattr(e, 'MEPModel', None)
    pt = getattr(mep, 'PartType', None) if mep is not None else None
    return _parte_aceita(cat, str(pt) if pt is not None else None,
                         nome_tipo_elemento(e).lower(), em_planta)


def alvos_paredes(doc, view, cat, feitos):
    """Paredes que recebem tag no Installation Plans: as do tipo
    cat['prefixo_tipo'] (WALL_; a parede vem em 3 pecas — WALL_, _STUD_ e
    _REINF_ — e so a WALL_ tem tag) com DESCIDA de tubo dentro (PH3 UNIT B5,
    23/10/2026: as 5 paredes com tag tem descida; o numero e o 'Stage', que
    a familia da tag ja mostra). Mesmo formato de alvos_pontuais; a ancora e
    o ponto da linha da parede na projecao da media das descidas."""
    descidas = []
    for link, _ld, tr in fontes(doc, view):
        for e in coletor(doc, view, link, BuiltInCategory.OST_PipeCurves):
            lc = e.Location
            if not isinstance(lc, LocationCurve):
                continue
            a, b = lc.Curve.GetEndPoint(0), lc.Curve.GetEndPoint(1)
            if tr is not None:
                a, b = tr.OfPoint(a), tr.OfPoint(b)
            comp = a.DistanceTo(b)
            if comp > 1e-6 and abs(b.Z - a.Z) > 0.7 * comp:
                descidas.append(((a.X + b.X) / 2.0, (a.Y + b.Y) / 2.0))
    saida = []
    pulados = 0
    if not descidas:
        return saida, pulados
    prefixo = (cat.get('prefixo_tipo') or u'').lower()
    for link, _ld, tr in fontes(doc, view):
        for e in coletor(doc, view, link, cat['bic']):
            lc = e.Location
            if not isinstance(lc, LocationCurve) or not hasattr(e, 'Width'):
                continue
            nome = nome_tipo_elemento(e).lower().split(u' : ')[-1]
            if prefixo and not nome.startswith(prefixo):
                continue
            a, b = lc.Curve.GetEndPoint(0), lc.Curve.GetEndPoint(1)
            if tr is not None:
                a, b = tr.OfPoint(a), tr.OfPoint(b)
            dentro, anc = descidas_na_parede((a.X, a.Y), (b.X, b.Y), e.Width / 2.0, descidas, tol=0.05)
            if not dentro:
                continue
            k = chave(link, e)
            if k in feitos:
                pulados += 1
                continue
            p = XYZ(anc[0], anc[1], min(a.Z, b.Z))
            saida.append((cat['chave'], link, e, p, max(0.05, e.Width / 2.0), k))
    return saida, pulados


def alvos_pontuais(doc, view, cat, feitos, faixa=None):
    if cat.get('coletor') == 'paredes_com_descida':
        return alvos_paredes(doc, view, cat, feitos)
    """[(chave_cat, link, elemento, ponto, raio, chave)] e quantos ja tinham tag."""
    saida = []
    pulados = 0
    filtro = cat.get('filtro')
    em_planta = isinstance(view, ViewPlan)
    for link, _ld, tr in fontes(doc, view):
        for e in coletor(doc, view, link, cat['bic']):
            if not isinstance(e, FamilyInstance) or e.SuperComponent is not None:
                continue
            if filtro and filtro not in nome_tipo_elemento(e).lower():
                continue
            if not parte_aceita(e, cat, em_planta):
                continue
            lp = e.Location
            if not isinstance(lp, LocationPoint):
                continue
            p = lp.Point if tr is None else tr.OfPoint(lp.Point)
            # fora da trama (na parede): nao entra, nem como 'ja tinha'
            if not na_faixa(p.Z, faixa):
                continue
            k = chave(link, e)
            if k in feitos:
                pulados += 1
                continue
            bb = e.get_BoundingBox(None)
            r = 0.15
            if bb is not None:
                r = max(0.05, min(0.6, max(bb.Max.X - bb.Min.X, bb.Max.Y - bb.Min.Y) / 2.0))
            saida.append((cat['chave'], link, e, p, r, k))
    return saida, pulados


def corpo_na_vista(link, e, R, U):
    """Caixa (u0, v0, u1, v1) da peca na vista, pelos 8 cantos da bbox
    (transformada do vinculo). None se o Revit nao der caixa."""
    bb = e.get_BoundingBox(None)
    if bb is None:
        return None
    tr = link.GetTotalTransform() if link is not None else None
    us, vs = [], []
    for x in (bb.Min.X, bb.Max.X):
        for y in (bb.Min.Y, bb.Max.Y):
            for z in (bb.Min.Z, bb.Max.Z):
                p = XYZ(x, y, z)
                if tr is not None:
                    p = tr.OfPoint(p)
                u, v = uv(p, R, U)
                us.append(u)
                vs.append(v)
    return (min(us), min(vs), max(us), max(vs))


def miolo(corpo, frac=0.25):
    """Faixa central da peca: centro +- frac da largura/altura. A seta dentro
    dela cai SOBRE a peca — o LocationPoint do tampao e o conector, na BORDA
    (DEM 57, 12/10/2026: a seta deslocada caiu no tubo)."""
    u0, v0, u1, v1 = corpo
    cu, cv = (u0 + u1) / 2.0, (v0 + v1) / 2.0
    return (cu - frac * (u1 - u0), cv - frac * (v1 - v0), cu + frac * (u1 - u0), cv + frac * (v1 - v0))


def para_dentro(ponto, caixa):
    return (min(max(ponto[0], caixa[0]), caixa[2]), min(max(ponto[1], caixa[1]), caixa[3]))


def _gerenciador(e):
    cm = getattr(e, 'ConnectorManager', None)
    if cm is None:
        mep = getattr(e, 'MEPModel', None)
        cm = mep.ConnectorManager if mep is not None else None
    return cm


def _vizinhos(e):
    """Elementos ligados a 'e' pelos conectores (mesmo documento)."""
    cm = _gerenciador(e)
    saida = []
    if cm is None:
        return saida
    for cn in cm.Connectors:
        try:
            refs = list(cn.AllRefs)
        except Exception as ex:
            avisar(u'conector de {} sem ligacoes legiveis'.format(eid(e.Id)), ex)
            continue
        for o in refs:
            dono = o.Owner
            if dono is not None and eid(dono.Id) != eid(e.Id):
                saida.append(dono)
    return saida


def alvos_tubos(doc, view, cat, feitos, R, U, todos=None, faixa=None):
    """Tubos a etiquetar: [(chave_cat, link, tubo, ponto_medio, chave, alternativas)].

    Corte/elevacao: TODO tubo reto visivel (comprimento na vista >= minimo).
    Planta: UM por trecho entre tes — cotovelo, luva e uniao nao separam; vai
    no tubo de maior comprimento visivel do trecho, e trecho curto fica sem
    (medido no MOTION, 08/10/2026). alternativas: pontos ao longo do tubo,
    em (u, v), para a ponta da chamada deslizar.
    todos: lista opcional que recebe, por trecho que ganha tag, o set das
    chaves de TODOS os tubos dele (o 'Refazer' apaga so o que recria)."""
    minimo = cat.get('comp_min_mm', 1.0) * view.Scale / 304.8
    em_planta = isinstance(view, ViewPlan)
    saida = []
    pulados = 0
    for link, _ld, tr in fontes(doc, view):
        tubos = {}
        for e in coletor(doc, view, link, cat['bic']):
            lc = e.Location
            if not isinstance(lc, LocationCurve):
                continue
            a, b = lc.Curve.GetEndPoint(0), lc.Curve.GetEndPoint(1)
            if tr is not None:
                a, b = tr.OfPoint(a), tr.OfPoint(b)
            ua, ub = uv(a, R, U), uv(b, R, U)
            vis = ((ua[0] - ub[0]) ** 2 + (ua[1] - ub[1]) ** 2) ** 0.5
            tubos[eid(e.Id)] = (e, a, b, ua, ub, vis)
        # so a trama recebe tag: o tubo que desce na parede ou corre noutra
        # cota fica para os cortes — mas CONTINUA no trecho (tubo + bend +
        # descida e um segmento so; sem ela o ramal de 556 mm da trama caia
        # abaixo do minimo de 24", IP001 7 PAV, 14/10/2026)
        na_trama = set(k for k, t in tubos.items() if na_faixa(t[1].Z, faixa) and na_faixa(t[2].Z, faixa))
        if em_planta:
            # trecho = tubos ligados por conexao de 2 bocas da MESMA bitola; te e
            # mudanca de bitola dividem. Regra pura: _tag_regras.trechos_de_planta
            lig2, tes = [], []
            for k, (e, _a, _b, _ua, _ub, _v) in tubos.items():
                for o in _vizinhos(e):
                    ok = eid(o.Id)
                    if ok in tubos:
                        lig2.append((k, ok))
                        continue
                    cm = _gerenciador(o)
                    if cm is None:
                        continue
                    outros = [eid(o2.Id) for o2 in _vizinhos(o) if eid(o2.Id) in tubos]
                    # so CONEXAO de tubo emenda trecho: o misturador tem 2 bocas
                    # (quente e fria) e juntava o Red e o Blue (PH3, 23/10/2026)
                    if o.Category is None or o.Category.Id.Value != int(BuiltInCategory.OST_PipeFitting):
                        continue
                    if cm.Connectors.Size == 2:
                        lig2.extend((k, x) for x in outros if x != k)
                    elif cm.Connectors.Size >= 3:
                        tes.append(outros)
            dados_t = {}
            for k, t in tubos.items():
                pd = t[0].get_Parameter(BuiltInParameter.RBS_PIPE_DIAMETER_PARAM)
                dados_t[k] = {'vis': t[5], 'diam': round(pd.AsDouble(), 6) if pd is not None else 0.0}
            # Installation Plans (com faixa): tag no tubo que encosta na descida,
            # sem minimo de 24" — so cai trecho curto entre tes de mesma bitola
            escolhas = trechos_de_planta(
                dados_t, lig2, tes, na_trama=na_trama, instalacao=faixa is not None,
                minimo=max(minimo, cat.get('comp_min_trecho_pol', 24.0) / 12.0),
                texto_min=cat.get('texto_min_mm', 10.0) * view.Scale / 304.8)
        else:
            escolhas = [(k, [k]) for k in tubos if tubos[k][5] >= minimo and k in na_trama]
        for k, g in escolhas:
            e, a, b, ua, ub, vis = tubos[k]
            if vis < 1e-6:
                continue
            if todos is not None:
                todos.append(set(chave(link, tubos[x][0]) for x in g))
            ch = chave(link, e)
            if any(chave(link, tubos[x][0]) in feitos for x in g):
                pulados += 1
                continue
            # ponta da chamada perto do MEIO do tubo: na borda ela parece apontar
            # para o plug/cotovelo da ponta (Thiago, 09/10/2026)
            alts = []
            # 0.2-0.8: no F10 15% das chamadas do projeto pegam o tubo entre 20 e
            # 35% da ponta — espalhar no ramal desafoga o no (10/10/2026)
            for t in (0.5, 0.42, 0.58, 0.35, 0.65, 0.25, 0.75, 0.2, 0.8):
                alts.append({'id': ch, 'ax': ua[0] + (ub[0] - ua[0]) * t, 'ay': ua[1] + (ub[1] - ua[1]) * t,
                             'desvio': abs(t - 0.5) * vis})
            if faixa is not None and em_planta:
                # Installation Plans: a tag ALINHADA pode ir em qualquer pedaco da
                # trama do trecho — onde houver espaco (PH3: num trecho o projeto
                # usou o pedaco do te, noutro o da descida, 23/10/2026)
                alts[0]['seg'] = [ua[0], ua[1], ub[0], ub[1]]
                for x in g:
                    if x == k or x not in na_trama or tubos[x][5] < 1e-6:
                        continue
                    ex, _xa, _xb, xua, xub, xvis = tubos[x]
                    chx = chave(link, ex)
                    PECAS_DO_TRECHO[chx] = (link, ex)
                    alts.append({'id': chx, 'ax': (xua[0] + xub[0]) / 2.0, 'ay': (xua[1] + xub[1]) / 2.0,
                                 'desvio': xvis * 0.5, 'seg': [xua[0], xua[1], xub[0], xub[1]]})
            saida.append((cat['chave'], link, e, (a + b) / 2.0, ch, alts))
    return saida, pulados


def lado_do_sistema(e):
    """-1 (esquerda) agua quente, +1 (direita) agua fria, None sem sistema.
    Conexao sem sistema herda do que esta ligado (busca curta). Regra do
    Thiago nos cortes do MOTION: 33 de 34 tags."""
    vistos = set()
    fila = [e]
    while fila and len(vistos) < 12:
        x = fila.pop(0)
        if eid(x.Id) in vistos:
            continue
        vistos.add(eid(x.Id))
        p = x.get_Parameter(BuiltInParameter.RBS_SYSTEM_CLASSIFICATION_PARAM)
        s = (p.AsString() or u'').lower() if p is not None else u''
        if u'quente' in s or u'hot' in s:
            return -1
        if u'fria' in s or u'cold' in s:
            return 1
        fila.extend(_vizinhos(x))
    return None


def linhas_vinculo(doc, view, R, U, limites):
    """Contorno (caixa) dos elementos de modelo dos VINCULOS visiveis na vista
    — montantes e travessas da parede no corte. Elemento que cobre a vista
    inteira (a parede toda) nao entra."""
    linhas = []
    if limites is None:
        return linhas
    L = limites
    for li in FilteredElementCollector(doc, view.Id).OfClass(RevitLinkInstance):
        if li.GetLinkDocument() is None:
            continue
        tr = li.GetTotalTransform()
        for e in FilteredElementCollector(doc, view.Id, li.Id).WhereElementIsNotElementType():
            if e.Category is None or e.Category.CategoryType != CategoryType.Model:
                continue
            bb = e.get_BoundingBox(None)
            if bb is None:
                continue
            us, vs = [], []
            for x in (bb.Min.X, bb.Max.X):
                for y in (bb.Min.Y, bb.Max.Y):
                    for z in (bb.Min.Z, bb.Max.Z):
                        q = tr.OfPoint(XYZ(x, y, z))
                        us.append(q.DotProduct(R))
                        vs.append(q.DotProduct(U))
            x0, y0 = max(min(us), L[0]), max(min(vs), L[1])
            x1, y1 = min(max(us), L[2]), min(max(vs), L[3])
            if x1 <= x0 or y1 <= y0:
                continue
            if (x1 - x0) > 0.9 * (L[2] - L[0]) and (y1 - y0) > 0.9 * (L[3] - L[1]):
                continue
            linhas += [(x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)]
            # miolo NAO e obstaculo: o Thiago passa ombro por dentro do plywood
            # (ZZ_MARGEM4_DEM 105) e o miolo dos montantes encheu o 04 de
            # diagonais — 09/10/2026
    return linhas


def direcao_livre(link, e, p, R, U):
    """Vetor unitario (u, v) do conduite/tubo que chega ao elemento PARA o
    elemento — o lado 'livre', alem da ponta. None se nao ha exatamente um
    MEPCurve ligado ou se ele e vertical na vista (vira ponto em planta)."""
    mep = getattr(e, 'MEPModel', None)
    cm = mep.ConnectorManager if mep is not None else None
    if cm is None:
        return None
    tr = link.GetTotalTransform() if link is not None else None
    curvas = {}
    for cn in cm.Connectors:
        try:
            refs = list(cn.AllRefs)
        except Exception as ex:
            avisar(u'conector de {} sem ligacoes legiveis'.format(eid(e.Id)), ex)
            continue
        for o in refs:
            dono = o.Owner
            if isinstance(dono, MEPCurve) and eid(dono.Id) != eid(e.Id):
                curvas[eid(dono.Id)] = dono
    if len(curvas) != 1:
        return None
    lc = list(curvas.values())[0].Location
    if not isinstance(lc, LocationCurve):
        return None
    a, b = lc.Curve.GetEndPoint(0), lc.Curve.GetEndPoint(1)
    if tr is not None:
        a, b = tr.OfPoint(a), tr.OfPoint(b)
    pu, pv = uv(p, R, U)
    longe = max((uv(a, R, U), uv(b, R, U)), key=lambda q: (q[0] - pu) ** 2 + (q[1] - pv) ** 2)
    dx, dy = pu - longe[0], pv - longe[1]
    L = (dx * dx + dy * dy) ** 0.5
    if L < 0.3:
        return None
    return (dx / L, dy / L)


def rede_linear(doc, view, cat, R, U):
    """Retos, conexoes e ligacoes de uma categoria linear (conduite).

    Devolve (retos {k: ((u0,v0),(u1,v1))}, ligacoes [(ka,kb)], conexoes set,
    elementos {k: (link, elemento, ponto_medio XYZ)}).
    """
    retos = {}
    elementos = {}
    conexoes = set()
    ligacoes = []
    filtro = cat.get('filtro')
    for link, _ld, tr in fontes(doc, view):
        locais = {}
        for e in coletor(doc, view, link, cat['bic']):
            lc = e.Location
            if not isinstance(lc, LocationCurve):
                continue
            if filtro and filtro not in nome_tipo_elemento(e).lower():
                continue
            c = lc.Curve
            a, b = c.GetEndPoint(0), c.GetEndPoint(1)
            if tr is not None:
                a, b = tr.OfPoint(a), tr.OfPoint(b)
            k = chave(link, e)
            retos[k] = (uv(a, R, U), uv(b, R, U))
            elementos[k] = (link, e, (a + b) / 2.0)
            locais[eid(e.Id)] = (k, e)
        if cat.get('bic_conexao') is not None:
            for e in coletor(doc, view, link, cat['bic_conexao']):
                k = chave(link, e)
                conexoes.add(k)
                locais[eid(e.Id)] = (k, e)
        # guarda o proprio elemento: ElementId(int) nao existe no Revit 2026
        for idv, (k, e) in locais.items():
            # conduite (MEPCurve) tem ConnectorManager; conexao, pelo MEPModel
            cm = getattr(e, 'ConnectorManager', None)
            if cm is None:
                mep = getattr(e, 'MEPModel', None)
                cm = mep.ConnectorManager if mep is not None else None
            if cm is None:
                continue
            for cn in cm.Connectors:
                try:
                    refs = cn.AllRefs
                except Exception as ex:
                    avisar(u'conector de {} sem ligacoes legiveis'.format(k), ex)
                    continue
                for o in refs:
                    dono = o.Owner
                    if dono is None:
                        continue
                    outro = locais.get(eid(dono.Id))
                    if outro is not None and eid(dono.Id) > idv:
                        ligacoes.append((k, outro[0]))
    return retos, ligacoes, conexoes, elementos


# ============================================================================
# OBSTACULOS
# ============================================================================

def linhas_mep(doc, view, R, U):
    linhas = []
    for link, _ld, tr in fontes(doc, view):
        for bic in (BuiltInCategory.OST_Conduit, BuiltInCategory.OST_PipeCurves,
                    BuiltInCategory.OST_DuctCurves, BuiltInCategory.OST_CableTray):
            for e in coletor(doc, view, link, bic):
                lc = e.Location
                if not isinstance(lc, LocationCurve):
                    continue
                m = 0.03
                for bip in (BuiltInParameter.RBS_CONDUIT_OUTER_DIAM_PARAM,
                            BuiltInParameter.RBS_PIPE_OUTER_DIAMETER,
                            BuiltInParameter.RBS_CURVE_WIDTH_PARAM):
                    p = e.get_Parameter(bip)
                    if p is not None and p.HasValue and p.AsDouble() > 0:
                        m = p.AsDouble() / 2.0
                        break
                c = lc.Curve
                a, b = c.GetEndPoint(0), c.GetEndPoint(1)
                if tr is not None:
                    a, b = tr.OfPoint(a), tr.OfPoint(b)
                linhas.append(uv(a, R, U) + uv(b, R, U) + (m,))
        for bic in (BuiltInCategory.OST_ConduitFitting, BuiltInCategory.OST_PipeFitting):
            for e in coletor(doc, view, link, bic):
                mep = getattr(e, 'MEPModel', None)
                cm = mep.ConnectorManager if mep is not None else None
                if cm is None:
                    continue
                pts = []
                m = 0.03
                for cn in cm.Connectors:
                    o = cn.Origin if tr is None else tr.OfPoint(cn.Origin)
                    pts.append(uv(o, R, U))
                    if cn.Shape == ConnectorProfileType.Round:
                        m = max(m, cn.Radius)
                for i in range(len(pts) - 1):
                    linhas.append(pts[i] + pts[i + 1] + (m,))
    return linhas


def linhas_paredes(doc, view, R, U):
    """Paredes da planta como linha COM largura (eixo + meia espessura): o
    motor cobra o texto sobre elas como sobre tubo. No projeto do Thiago
    nenhuma tag fica em cima de parede (PH3 UNIT B5, 23/10/2026).

    Parede de steel frame do PH3 e parede CORTINA (uma por camada: WALL_,
    _STUD_, _REINF_) e o Width dela vale sempre 25,4 mm: a faixa real sai das
    caixas dos paineis e montantes (3 5/8" = 92 mm, 6" = 152 mm), medidas na
    normal da linha — exata na parede ortogonal."""
    linhas = []
    for link, ld, tr in fontes(doc, view):
        for e in coletor(doc, view, link, BuiltInCategory.OST_Walls):
            lc = e.Location
            if not isinstance(lc, LocationCurve):
                continue
            c = lc.Curve
            desvio = 0.0
            largura = getattr(e, 'Width', None)
            if largura is None:
                continue
            m = largura / 2.0
            gr = getattr(e, 'CurtainGrid', None)
            if gr is not None and isinstance(c, Line):
                d = c.Direction
                o = c.GetEndPoint(0)
                ps = []
                for i in list(gr.GetPanelIds()) + list(gr.GetMullionIds()):
                    p = ld.GetElement(i)
                    bb = p.get_BoundingBox(None) if p is not None else None
                    if bb is None:
                        continue
                    for x in (bb.Min.X, bb.Max.X):
                        for y in (bb.Min.Y, bb.Max.Y):
                            ps.append((x - o.X) * -d.Y + (y - o.Y) * d.X)
                if ps:
                    m = (max(ps) - min(ps)) / 2.0
                    desvio = (max(ps) + min(ps)) / 2.0
            if isinstance(c, Line):
                nrm = XYZ(-c.Direction.Y, c.Direction.X, 0.0) * desvio
                pts = [c.GetEndPoint(0) + nrm, c.GetEndPoint(1) + nrm]
            else:
                pts = list(c.Tessellate())
            if tr is not None:
                pts = [tr.OfPoint(p) for p in pts]
            for a, b in zip(pts, pts[1:]):
                linhas.append(uv(a, R, U) + uv(b, R, U) + (m, 'parede'))
    return linhas


def linhas_dwg(doc, view, R, U, limites):
    linhas = []
    opt = Options()
    opt.View = view
    for imp in FilteredElementCollector(doc, view.Id).OfClass(ImportInstance):
        geo = imp.get_Geometry(opt)
        if geo is None:
            continue
        for go in geo:
            if not isinstance(go, GeometryInstance):
                continue
            for o in go.GetInstanceGeometry():
                gs = doc.GetElement(o.GraphicsStyleId)
                if gs is not None and gs.GraphicsStyleCategory is not None:
                    if view.GetCategoryHidden(gs.GraphicsStyleCategory.Id):
                        continue
                if isinstance(o, Line):
                    pts = [o.GetEndPoint(0), o.GetEndPoint(1)]
                elif isinstance(o, PolyLine):
                    pts = list(o.GetCoordinates())
                elif isinstance(o, Curve):
                    pts = list(o.Tessellate())
                else:
                    continue
                for i in range(len(pts) - 1):
                    a, b = uv(pts[i], R, U), uv(pts[i + 1], R, U)
                    if limites is not None and (max(a[0], b[0]) < limites[0] or min(a[0], b[0]) > limites[2]
                                                or max(a[1], b[1]) < limites[1] or min(a[1], b[1]) > limites[3]):
                        continue
                    linhas.append(a + b)
    return linhas


# ============================================================================
# MEDICAO (Transaction desfeita)
# ============================================================================

_ALINHA = {HorizontalTextAlignment.Left: 'esquerda', HorizontalTextAlignment.Center: 'centro',
           HorizontalTextAlignment.Right: 'direita'}


def alinhamento_do_texto(doc, simbolo):
    """Alinhamento horizontal dos labels da familia da tag ('esquerda',
    'centro', 'direita'), pelo voto dos labels — a de tubo e Left, a de
    conexao Center (MOTION, 09/10/2026). Abre a familia so para ler: tem de
    rodar SEM Transaction nem TransactionGroup abertos. None se nao der."""
    fd = None
    try:
        fd = doc.EditFamily(simbolo.Family)
        votos = {}
        for te in FilteredElementCollector(fd).OfClass(TextElement):
            a = _ALINHA.get(te.HorizontalAlignment)
            if a:
                votos[a] = votos.get(a, 0) + 1
        return max(votos, key=votos.get) if votos else None
    except Exception as ex:
        avisar(u'alinhamento do texto de {}'.format(eid(simbolo.Id)), ex)
        return None
    finally:
        if fd is not None:
            fd.Close(False)


_VERT = {VerticalTextAlignment.Bottom: 'base', VerticalTextAlignment.Middle: 'meio',
         VerticalTextAlignment.Top: 'topo'}


def rotulo_da_tag(doc, simbolo):
    """Rotulo VISIVEL no tipo de tag: {'h', 'x', 'y' (mm de papel), 'va',
    'ha'}. Cada tipo da familia de tubo liga um parametro de visibilidade
    proprio (Ambar_US_Tag_Pipe_Segment 2026-, 26/10/2026). Abre a familia so
    para ler: SEM Transaction nem TransactionGroup abertos. None se nao der."""
    fd = None
    try:
        nome_tipo = nome_do_tipo(simbolo).split(u' : ', 1)[-1]
        fd = doc.EditFamily(simbolo.Family)
        fm = fd.FamilyManager
        tipo = None
        for ft in fm.Types:
            if ft.Name == nome_tipo:
                tipo = ft
        visiveis = []
        for te in FilteredElementCollector(fd).OfClass(TextElement):
            p = te.get_Parameter(BuiltInParameter.IS_VISIBLE_PARAM)
            if p is None:
                continue
            fp = fm.GetAssociatedFamilyParameter(p)
            if fp is not None and tipo is not None:
                ligado = tipo.AsInteger(fp) == 1
            else:
                ligado = p.AsInteger() == 1
            if ligado:
                visiveis.append(te)
        if len(visiveis) != 1:
            avisar(u'rotulo da tag {}'.format(nome_tipo), u'{} rotulos visiveis'.format(len(visiveis)))
            return None
        te = visiveis[0]
        t = fd.GetElement(te.GetTypeId())
        return {'h': t.get_Parameter(BuiltInParameter.TEXT_SIZE).AsDouble() * 304.8,
                'x': te.Coord.X * 304.8, 'y': te.Coord.Y * 304.8,
                'va': _VERT.get(te.VerticalAlignment), 'ha': _ALINHA.get(te.HorizontalAlignment)}
    except Exception as ex:
        avisar(u'rotulo da tag {}'.format(eid(simbolo.Id)), ex)
        return None
    finally:
        if fd is not None:
            fd.Close(False)


def medir(doc, view, a_medir, simbolos, R, U):
    """Cria as tags, mede a caixa real do texto e DESFAZ.

    a_medir: [(chave_cat, link, elemento, ponto XYZ, k)].
    Devolve (medidas {k: {'w','h','ox','oy','texto'}}, caixas fixas das tags e
    textos que ja estao na vista, chamadas dessas tags como linhas).
    """
    medidas = {}
    fixas = []
    linhas_existentes = []
    t = Transaction(doc, 'Tags Organizadas - medir')
    t.Start()
    try:
        existentes = list(FilteredElementCollector(doc, view.Id).OfClass(IndependentTag))
        for tg in existentes:
            try:
                if tg.HasLeader:
                    head = tg.TagHeadPosition
                    for r in tg.GetTaggedReferences():
                        fim = tg.GetLeaderEnd(r) if tg.LeaderEndCondition == LeaderEndCondition.Free else None
                        cot = tg.GetLeaderElbow(r) if tg.HasLeaderElbow(r) else None
                        pts = [p for p in (fim, cot, head) if p is not None]
                        for i in range(len(pts) - 1):
                            linhas_existentes.append(uv(pts[i], R, U) + uv(pts[i + 1], R, U))
                tg.HasLeader = False
            except Exception as ex:
                avisar(u'tag existente {} nao medida'.format(eid(tg.Id)), ex)
        criadas = []
        for item in a_medir:
            chave_cat, link, e, p, k = item
            # um elemento que o Revit recusa nao derruba a vista inteira
            try:
                criadas.append((k, IndependentTag.Create(doc, simbolos[chave_cat].Id, view.Id,
                                                         referencia(link, e), False,
                                                         TagOrientation.Horizontal, p)))
            except Exception as ex:
                avisar(u'{} nao aceitou tag'.format(k), ex)
        doc.Regenerate()
        for tg in existentes:
            bb = tg.get_BoundingBox(view)
            if bb is not None:
                fixas.append(caixa_uv(bb, R, U))
        for tn in FilteredElementCollector(doc, view.Id).OfClass(TextNote):
            bb = tn.get_BoundingBox(view)
            if bb is not None:
                fixas.append(caixa_uv(bb, R, U))
        # cotas da vista tambem sao obstaculo: no DEM 11 A5R (MOTION F10,
        # 09/10/2026) as tags da direita cairam sobre as cotas de altura do
        # stub-out ('22"' e '15 1/8"')
        for dm in FilteredElementCollector(doc, view.Id).OfClass(Dimension):
            try:
                bb = dm.get_BoundingBox(view)
                if bb is not None:
                    # marcada: a chamada pode atravessar as LINHAS da cota
                    fixas.append(tuple(caixa_uv(bb, R, U)) + ('cota',))
                    # ... mas nao o NUMERO (Thiago, DEM 57, 12/10/2026)
                    fixas.extend(textos_da_cota(dm, view, R, U))
            except Exception as ex:
                avisar(u'cota {} nao medida'.format(eid(dm.Id)), ex)
        for k, tag in criadas:
            bb = tag.get_BoundingBox(view)
            if bb is None:
                # sem caixa o item fica sem medida e e pulado — antes o erro
                # derrubava a vista inteira (auditoria 12/10/2026)
                avisar(u'{}: tag sem caixa na vista'.format(k), u'pulado')
                continue
            u0, v0, u1, v1 = caixa_uv(bb, R, U)
            hu, hv = uv(tag.TagHeadPosition, R, U)
            medidas[k] = {'w': u1 - u0, 'h': v1 - v0,
                          'ox': (u0 + u1) / 2.0 - hu, 'oy': (v0 + v1) / 2.0 - hv,
                          'texto': tag.TagText or u''}
    finally:
        t.RollBack()
    return medidas, fixas, linhas_existentes


# ============================================================================
# APLICAR
# ============================================================================

def aplicar(doc, view, rotulos, postos, elementos, simbolos, R, U, base, corpos=None):
    """Cria as tags de verdade. A geometria escolhida decide QUAL elemento a
    tag referencia e onde a chamada termina ('ids'/'ancoras' — no linear a
    ponta desliza e pode cair em outro conduite do trecho).
    base: ponto do plano da vista com u = v = 0 (a profundidade); em planta e
    (0, 0, z). Chamar dentro de Transaction.
    Devolve (criadas, falhas, {indice do rotulo: Id da tag criada}) — o
    relatorio usa os Ids para selecionar as tags que pedem revisao."""
    def xyz(par):
        return R.Multiply(par[0]).Add(U.Multiply(par[1])).Add(base)

    criadas = 0
    falhas = []
    ids_tags = {}
    for i, g in postos.items():
        rot = rotulos[i]
        ids = g.get('ids') or rot['ids']
        ancoras = g.get('ancoras') or rot['ancoras']
        try:
            membros = [elementos.get(k) or PECAS_DO_TRECHO[k] for k in ids]
            refs = [referencia(m[0], m[1]) for m in membros]
            head = xyz(g['head'])
            if g.get('alinhada'):
                # tubo alinhado (Installation Plans): sem chamada, no sentido do
                # tubo — vertical gira 90 graus (medido no PH3, 23/10/2026)
                ori = TagOrientation.Vertical if g['alinhada'] == 'V' else TagOrientation.Horizontal
                tag = IndependentTag.Create(doc, simbolos[rot['grupo']].Id, view.Id, refs[0], False, ori, head)
                tag.TagHeadPosition = head          # Create nao respeita o ponto
                criadas += 1
                continue
            tag = IndependentTag.Create(doc, simbolos[rot['grupo']].Id, view.Id, refs[0],
                                        True, TagOrientation.Horizontal, head)
            if len(refs) > 1:
                tag.AddReferences(List[Reference](refs[1:]))
                # leque e pente: cotovelo comum; ramos: um cotovelo por elemento
                tag.MergeElbows = bool(g.get('mesclada'))
            tag.TagHeadPosition = head          # Create nao respeita o ponto
            tag.LeaderEndCondition = LeaderEndCondition.Free
            marcadas = dict((chave_ref(r), r) for r in tag.GetTaggedReferences())
            for k, anc, elb in zip(ids, ancoras, g['elbows']):
                r = marcadas.get(k)
                if r is None:
                    falhas.append(u'{}: chamada de {} nao ajustada (referencia nao casou)'.format(
                        rot['texto'].replace('\n', ' / '), k))
                    continue
                # garantia: a seta de peca termina SOBRE a peca. A tag que
                # aponta para o tubo perde a referencia de quem ela marca
                # (Thiago, 12/10/2026 — "nao precisa estar centralizado,
                # mas em algum ponto do elemento")
                corpo = (corpos or {}).get(k)
                if corpo is not None:
                    dentro = para_dentro(anc, corpo)
                    if dentro != tuple(anc):
                        avisar(k, u'seta trazida para dentro da peca')
                        anc = dentro
                tag.SetLeaderEnd(r, xyz(anc))
                tag.SetLeaderElbow(r, xyz(elb))
            criadas += 1
            ids_tags[i] = tag.Id
        except Exception as ex:
            falhas.append(u'{}: {}'.format(rot['texto'].replace('\n', ' / '), ex))
    return criadas, falhas, ids_tags
