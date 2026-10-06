# -*- coding: utf-8 -*-
"""Interferência entre VÁRIOS modelos vinculados, numa passada só.

> "quero poder gerar o relatório para mais de um projeto linkado ao mesmo
>  tempo... interferências dos tubos para dutos de todos os links"
> (Thiago, 30/09/2026)

O QUE ESTE ARQUIVO FAZ E O QUE NÃO FAZ
--------------------------------------
Aqui mora só o que precisa do Revit: ler as caixas envolventes, perguntar ao
usuário, confirmar os candidatos com o sólido e gravar. A REGRA — cruzar as
caixas, descartar o que não é interferência, montar o relatório — está em
`Snippets._clash`, que é puro e tem teste em CPython.

POR QUE ASSIM (medido no CIQ, [[api-clash-geometrico]])
-------------------------------------------------------
Perguntar ao Revit par a par (`ElementIntersectsSolidFilter` por elemento)
custa 123 ms a consulta: 6 minutos no modelo. Ler a caixa de TODOS os
elementos de uma vez custa 0,03 ms cada — 6751 elementos de 25 documentos em
140 ms — e o cruzamento em memória leva 5 ms. O sólido só entra para
confirmar os candidatos (1,3 ms cada). Total: menos de 20 s.
"""
import os

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System.Windows import Thickness
from System.Windows.Controls import CheckBox

from Autodesk.Revit.DB import (
    BooleanOperationsType,
    BooleanOperationsUtils,
    BuiltInCategory,
    Element,
    ElementMulticategoryFilter,
    FilteredElementCollector,
    GeometryInstance,
    Options,
    RevitLinkInstance,
    Solid,
    SolidUtils,
    Transform,
    ViewDetailLevel,
    XYZ,
)
from System.Collections.Generic import List

from pyrevit.forms import WPFWindow

from Snippets._clash import (
    VOLUME_MINIMO,
    achado,
    caixa,
    cruzar,
    filtrar,
    montar_relatorio,
    resumo,
    volume_texto,
)

import ifr_disco
from ifr_modelo import arquivo_do_modelo, caminho_do_modelo

SCRIPT_DIR = os.path.dirname(__file__)
ESTE_PROJETO = u'(este projeto)'
#: pé³ -> pol³ (o volume da API vem em pés cúbicos)
POL3 = 1728.0

#: as categorias que oferecemos. MEP primeiro — é o uso do dia a dia; a
#: estrutura entra porque "tubo furando viga" é a pergunta seguinte.
CATEGORIAS = [
    (u'Tubulação', BuiltInCategory.OST_PipeCurves),
    (u'Conexões de tubo', BuiltInCategory.OST_PipeFitting),
    (u'Acessórios de tubo', BuiltInCategory.OST_PipeAccessory),
    (u'Isolamento de tubo', BuiltInCategory.OST_PipeInsulations),
    (u'Dutos', BuiltInCategory.OST_DuctCurves),
    (u'Conexões de duto', BuiltInCategory.OST_DuctFitting),
    (u'Acessórios de duto', BuiltInCategory.OST_DuctAccessory),
    (u'Terminais de ar', BuiltInCategory.OST_DuctTerminal),
    (u'Eletrocalhas', BuiltInCategory.OST_CableTray),
    (u'Conduítes', BuiltInCategory.OST_Conduit),
    (u'Equipamento mecânico', BuiltInCategory.OST_MechanicalEquipment),
    (u'Peças sanitárias', BuiltInCategory.OST_PlumbingFixtures),
    (u'Pilares estruturais', BuiltInCategory.OST_StructuralColumns),
    (u'Vigas e treliças', BuiltInCategory.OST_StructuralFraming),
    (u'Paredes', BuiltInCategory.OST_Walls),
    (u'Pisos', BuiltInCategory.OST_Floors),
    (u'Forros', BuiltInCategory.OST_Ceilings),
]
#: o pedido do dia a dia: tubo contra duto (Thiago, 30/09/2026)
PADRAO_DE = (u'Tubulação',)
PADRAO_CONTRA = (u'Dutos', u'Conexões de duto')


def _opcoes():
    # FINE, nao Coarse (medido no CIQ em 30/09/2026): em Coarse 1430 de 2091
    # conexoes/acessorios/dutos dos vinculos NAO tem solido — a familia so
    # desenha linhas no nivel grosso. Em Fine sobram 130, e o custo e o mesmo
    # (~1 s para todos). Coarse fazia o clash perder a maior parte das pecas.
    opcoes = Options()
    opcoes.DetailLevel = ViewDetailLevel.Fine
    opcoes.ComputeReferences = False
    return opcoes


def _solidos(elemento):
    """Os sólidos do elemento, inclusive os de dentro da família."""
    achados = []
    try:
        geometria = elemento.get_Geometry(_opcoes())
    except Exception:
        return achados
    if geometria is None:
        return achados
    for objeto in geometria:
        solido = objeto if isinstance(objeto, Solid) else None
        if solido is not None and solido.Volume > 1e-9:
            achados.append(solido)
            continue
        if isinstance(objeto, GeometryInstance):
            for dentro in objeto.GetInstanceGeometry():
                if isinstance(dentro, Solid) and dentro.Volume > 1e-9:
                    achados.append(dentro)
    return achados


def _transformar(solido, transform):
    """O sólido nas coordenadas do host. None quando o Revit recusa."""
    try:
        return SolidUtils.CreateTransformed(solido, transform)
    except Exception as erro:
        print(u'LOG/clash: CreateTransformed falhou ({})'.format(erro))
        return None


def _nome(elemento):
    """O nome do elemento — `Element.Name.GetValue`, nao `.Name`.

    `.Name` levanta AttributeError no IronPython para ElementType
    ([[ironpython-element-name-attributeerror]]): o except engolia e o
    clash saia sem descricao ("Dutos ·  · ID 9637535", 30/09/2026).
    """
    try:
        return Element.Name.GetValue(elemento) or ''
    except Exception:
        try:
            return elemento.Name
        except Exception:
            return ''


def _id(elemento):
    """O id como int de Python.

    `ElementId.Value` e Int64 no Revit 2026: sem o `int()` o relatorio morre
    ao gravar, com "10308160L is not JSON serializable"
    ([[elementid-value-json-serialize]], 30/09/2026).
    """
    eid = elemento.Id
    return int(eid.Value if hasattr(eid, 'Value') else eid.IntegerValue)


def modelos_abertos(documento):
    """[(nome, documento, transform)] — o projeto e os vínculos CARREGADOS.

    Vínculo descarregado não tem geometria: ele volta na lista de avisos, em
    vez de dar zero em silêncio.
    """
    modelos = [(arquivo_do_modelo(documento), documento, Transform.Identity)]
    descarregados = []
    for instancia in FilteredElementCollector(documento) \
            .OfClass(RevitLinkInstance):
        vinculado = instancia.GetLinkDocument()
        nome = _nome(instancia).split(' : ')[0].strip()
        if vinculado is None:
            if nome and nome not in descarregados:
                descarregados.append(nome)
            continue
        modelos.append((arquivo_do_modelo(vinculado), vinculado,
                        instancia.GetTotalTransform()))
    return modelos, descarregados


def _caixa_no_host(elemento, transform):
    """A caixa do elemento nas coordenadas do modelo anfitrião.

    Os 8 cantos, não Min/Max: vínculo girado tem transform que não é
    identidade e a caixa sairia torta ([[api-interferencia-vinculos]]).
    """
    bbox = elemento.get_BoundingBox(None)
    if bbox is None:
        return None
    menor, maior = bbox.Min, bbox.Max
    xs, ys, zs = [], [], []
    for i in range(8):
        canto = XYZ(menor.X if i & 1 == 0 else maior.X,
                    menor.Y if i & 2 == 0 else maior.Y,
                    menor.Z if i & 4 == 0 else maior.Z)
        no_host = transform.OfPoint(canto)
        xs.append(no_host.X)
        ys.append(no_host.Y)
        zs.append(no_host.Z)
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def contar(modelos, categorias):
    """{(nome do modelo, rótulo da categoria): quantos} — para o diálogo."""
    quantos = {}
    alvo = List[BuiltInCategory]()
    for _, bic in categorias:
        alvo.Add(bic)
    for nome, documento, _ in modelos:
        for rotulo, bic in categorias:
            n = FilteredElementCollector(documento).OfCategory(bic) \
                .WhereElementIsNotElementType().GetElementCount()
            if n:
                quantos[(nome, rotulo)] = n
    return quantos


def coletar_caixas(modelos, por_lado, escolhidos):
    """As caixas dos elementos escolhidos, ja no sistema do host.

    `por_lado` = {'a': [(rotulo, BuiltInCategory)], 'b': [...]} — o "verificar
    ESTES contra AQUELES" (v2, 30/09/2026). Uma passada por lado; quem cai
    nos dois (mesma categoria marcada nas duas colunas) vira UMA caixa com os
    dois lados, nao duas.

    -> ([caixa], {(arquivo, id): (documento, transform)}) — o segundo e o
    caminho de volta ao elemento, para a confirmacao com solido.
    """
    por_chave, origem = {}, {}
    for lado in ('a', 'b'):
        categorias = por_lado.get(lado) or []
        if not categorias:
            continue
        bics = List[BuiltInCategory]()
        for _, bic in categorias:
            bics.Add(bic)
        filtro = ElementMulticategoryFilter(bics)
        for nome, documento, transform in modelos:
            if nome not in escolhidos:
                continue
            coletor = FilteredElementCollector(documento) \
                .WherePasses(filtro).WhereElementIsNotElementType()
            for elemento in coletor:
                ident = _id(elemento)
                chave = (nome.lower(), ident)
                if chave in por_chave:
                    cx = por_chave[chave]
                    if lado not in cx['lados']:
                        cx['lados'] = tuple(cx['lados']) + (lado,)
                    continue
                extremos = _caixa_no_host(elemento, transform)
                if extremos is None:
                    continue
                # a categoria vem do proprio Revit (ja no idioma da
                # interface), nao do meu rotulo: e o que o usuario le
                por_chave[chave] = caixa(
                    nome, ident, _categoria(elemento), _descricao(elemento),
                    extremos[0], extremos[1], unique_id=elemento.UniqueId,
                    lados=(lado,))
                origem[chave] = (documento, transform)
    return list(por_chave.values()), origem


def _categoria(elemento):
    try:
        return elemento.Category.Name
    except Exception:
        return u'Elemento'


def _descricao(elemento):
    try:
        tipo = elemento.Document.GetElement(elemento.GetTypeId())
        if tipo is not None:
            return _nome(tipo)
    except Exception:
        pass
    return _nome(elemento)


def _conexoes(documento, ident):
    """Os ids ligados a este elemento — o tubo e o tê dele.

    Só é chamado para quem aparece num par do MESMO modelo: percorrer os
    conectores de tudo custaria caro à toa.
    """
    ligados = set()
    try:
        elemento = documento.GetElement(_element_id(documento, ident))
    except Exception:
        return ligados
    if elemento is None:
        return ligados
    gerente = getattr(elemento, 'ConnectorManager', None)
    if gerente is None:
        modelo_mep = getattr(elemento, 'MEPModel', None)
        gerente = getattr(modelo_mep, 'ConnectorManager', None) \
            if modelo_mep is not None else None
    if gerente is None:
        return ligados
    try:
        for conector in gerente.Connectors:
            for outro in conector.AllRefs:
                dono = outro.Owner
                if dono is not None:
                    ligados.add(_id(dono))
    except Exception:
        pass
    return ligados


def _element_id(documento, ident):
    from Autodesk.Revit.DB import ElementId
    try:
        return ElementId(ident)
    except Exception:                       # Revit 2026 quer Int64
        from System import Int64
        return ElementId(Int64(ident))


def marcar_conexoes(caixas, pares, origem):
    """Preenche `conectados` só de quem aparece em par do mesmo modelo."""
    interessa = set()
    for i, j in pares:
        a, b = caixas[i], caixas[j]
        if (a['arquivo'] or '').lower() == (b['arquivo'] or '').lower():
            interessa.add(i)
            interessa.add(j)
    cache = {}
    for indice in interessa:
        cx = caixas[indice]
        chave = (cx['arquivo'].lower(), cx['id'])
        if chave not in cache:
            dados = origem.get(chave)
            cache[chave] = _conexoes(dados[0], cx['id']) if dados else set()
        cx['conectados'] = tuple(cache[chave])
    return caixas


def confirmar(caixas, pares, origem, volume_minimo=VOLUME_MINIMO):
    """O sólido decide. -> ([achado], pulados, sem_geometria).

    O par de caixas só diz "podem estar no mesmo lugar". Aqui os sólidos dos
    dois vão para o sistema do host e o boolean mede a sobreposição.
    """
    solidos_cache = {}
    #: sólido que não aceita a transform do vínculo não pode sumir calado —
    #: ele vira número no rodapé (regra do orçamento de `except` do lab)
    contador = {'transform': 0}

    def solidos_no_host(cx):
        chave = (cx['arquivo'].lower(), cx['id'])
        if chave in solidos_cache:
            return solidos_cache[chave]
        dados = origem.get(chave)
        saida = []
        if dados is not None:
            documento, transform = dados
            elemento = documento.GetElement(_element_id(documento, cx['id']))
            if elemento is not None:
                for solido in _solidos(elemento):
                    movido = _transformar(solido, transform)
                    if movido is None:
                        contador['transform'] += 1
                        print(u'LOG/clash: sólido de {} #{} não aceitou a '
                              u'transform do vínculo'.format(cx['arquivo'],
                                                             cx['id']))
                        continue
                    saida.append(movido)
        solidos_cache[chave] = saida
        return saida

    achados, pulados, sem_geometria = [], 0, 0
    for i, j in pares:
        a, b = caixas[i], caixas[j]
        de_a, de_b = solidos_no_host(a), solidos_no_host(b)
        if not de_a or not de_b:
            # familia so com linhas: as caixas se cruzam e nao ha como
            # medir — entra como ATENCAO em vez de sumir
            sem_geometria += 1
            achados.append(achado(a, b, sem_solido=True))
            continue
        volume = 0.0
        erro = False
        for sa in de_a:
            for sb in de_b:
                try:
                    juntos = BooleanOperationsUtils.ExecuteBooleanOperation(
                        sa, sb, BooleanOperationsType.Intersect)
                except Exception:
                    erro = True
                    continue
                if juntos is not None:
                    volume += juntos.Volume
        if erro and volume <= 0:
            pulados += 1
            continue
        volume_pol3 = volume * POL3
        if volume_pol3 < volume_minimo:
            continue
        achados.append(achado(a, b, volume_pol3))
    return achados, pulados + contador['transform'], sem_geometria


# ----------------------------------------------------------------- diálogo

class DialogoClash(WPFWindow):
    """Modelos, categorias e o cruzamento dentro do mesmo modelo."""

    def __init__(self, modelos, quantos, salvo):
        WPFWindow.__init__(self, os.path.join(SCRIPT_DIR, 'clash.xaml'))
        self.resultado = None
        marcados = salvo.get('modelos')
        self._modelos = []
        for nome, _, _ in modelos:
            total = sum(n for (arq, _), n in quantos.items() if arq == nome)
            self._modelos.append((nome, self._caixa(
                self.ModelosPanel, u'{}  ({})'.format(nome, total),
                nome in marcados if marcados is not None else bool(total))))
        ligadas = salvo.get('categorias')
        contra = salvo.get('contra')
        self._categorias, self._contra = [], []
        for rotulo, bic in CATEGORIAS:
            total = sum(n for (_, cat), n in quantos.items() if cat == rotulo)
            texto = u'{}  ({})'.format(rotulo, total)
            de = rotulo in ligadas if ligadas is not None \
                else rotulo in PADRAO_DE
            ate = rotulo in contra if contra is not None \
                else rotulo in PADRAO_CONTRA
            self._categorias.append(((rotulo, bic), self._caixa(
                self.CategoriasPanel, texto, de and bool(total))))
            self._contra.append(((rotulo, bic), self._caixa(
                self.ContraPanel, texto, ate and bool(total))))
        self.MesmoModeloCheck.IsChecked = salvo.get('mesmo_modelo', True)

    def _caixa(self, painel, texto, marcada):
        caixa_ui = CheckBox()
        caixa_ui.Content = texto
        caixa_ui.IsChecked = marcada
        caixa_ui.Margin = Thickness(0, 2, 0, 2)
        painel.Children.Add(caixa_ui)
        return caixa_ui

    def ao_verificar(self, sender, args):
        config = {
            'modelos': [n for n, c in self._modelos if c.IsChecked],
            'categorias': [par for par, c in self._categorias if c.IsChecked],
            'contra': [par for par, c in self._contra if c.IsChecked],
            'mesmo_modelo': bool(self.MesmoModeloCheck.IsChecked),
        }
        if len(config['modelos']) < 1:
            self.ErroLabel.Text = u'Marque pelo menos um modelo.'
            return
        if not config['categorias']:
            self.ErroLabel.Text = u'Marque pelo menos uma categoria.'
            return
        if len(config['modelos']) == 1 and not config['mesmo_modelo']:
            self.ErroLabel.Text = u'Com um modelo só, marque "cruzar também ' \
                                  u'elementos do MESMO modelo".'
            return
        self.resultado = config
        self.Close()

    def ao_cancelar(self, sender, args):
        self.Close()


# ---------------------------------------------------------------- executar

def executar(uiapp, janela):
    """Pergunta, cruza, confirma, grava e abre na janela. -> texto do rodapé."""
    from datetime import datetime

    documento = uiapp.ActiveUIDocument.Document
    modelos, descarregados = modelos_abertos(documento)
    quantos = contar(modelos, CATEGORIAS)
    if not quantos:
        return u'Nenhum elemento dessas categorias no projeto nem nos ' \
               u'vínculos carregados.'

    salvo = janela.prefs.get('clash') or {}
    dialogo = DialogoClash(modelos, quantos, salvo)
    dialogo.ShowDialog()
    config = dialogo.resultado
    if config is None:
        return u'Verificação de interferências cancelada.'

    escolhidos = set(config['modelos'])
    # sem a coluna da direita, o lado B e o proprio A: tudo contra tudo
    contra = config.get('contra') or config['categorias']
    por_lado = {'a': config['categorias'], 'b': contra}
    caixas, origem = coletar_caixas(modelos, por_lado, escolhidos)
    if not caixas:
        return u'Os modelos marcados não têm elementos dessas categorias.'
    pares = cruzar(caixas, mesmo_modelo=config['mesmo_modelo'])
    marcar_conexoes(caixas, pares, origem)
    pares, conectados_fora = filtrar(caixas, pares)
    achados, pulados, sem_geometria = confirmar(caixas, pares, origem)

    parametros = {
        'modelos': config['modelos'],
        'categorias': [rotulo for rotulo, _ in config['categorias']],
        'contra': [rotulo for rotulo, _ in contra],
        'mesmo_modelo': config['mesmo_modelo'],
        'elementos': len(caixas), 'candidatos': len(pares),
        'conectados_descartados': conectados_fora,
        'sem_geometria': sem_geometria, 'pulados': pulados,
        'descarregados': descarregados,
        'volume_minimo': VOLUME_MINIMO,
    }
    modelo = janela.caminho_do_modelo()
    relatorio = montar_relatorio(
        achados, modelo, datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        config['modelos'], parametros)
    # v3.1 — REPOSITORIO: a mesma pergunta (modelos + o que x o que)
    # atualiza o mesmo relatorio; pergunta diferente vira outro, lado a lado
    caminho, ja_existia = janela.gravar_rodada(relatorio)

    janela.prefs['clash'] = {
        'modelos': config['modelos'],
        'categorias': [rotulo for rotulo, _ in config['categorias']],
        'contra': [rotulo for rotulo, _ in (config.get('contra') or [])],
        'mesmo_modelo': config['mesmo_modelo'],
    }
    ifr_disco.gravar_preferencias(janela.prefs)
    janela.carregar(caminho)

    quando = datetime.now().strftime('%H:%M')
    partes = [u'{} em {}'.format(n, par) for par, n in resumo(achados)[:3]]
    avisos = []
    if descarregados:
        avisos.append(u'{} vínculo(s) descarregado(s) não incluído(s): '
                      u'{}'.format(len(descarregados),
                                   ', '.join(descarregados[:3])))
    if sem_geometria:
        avisos.append(u'{} par(es) com elemento sem sólido, incluído(s) '
                      u'como "conferir"'.format(sem_geometria))
    if pulados:
        avisos.append(u'{} par(es) sem medição possível no Revit'.format(
            pulados))
    return u'Interferências {} às {}: {} achado(s) em {} elemento(s) de {} ' \
           u'modelo(s){}{}.'.format(
               u'ATUALIZADAS' if ja_existia else u'verificadas', quando,
               len(achados), len(caixas), len(config['modelos']),
               u' — ' + u', '.join(partes) if partes else u'',
               u'. Atenção: ' + u'; '.join(avisos) if avisos else u'')
