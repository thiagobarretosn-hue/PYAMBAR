# -*- coding: utf-8 -*-
"""O ExternalEvent da janela: achar os elementos, selecionar e dar zoom.

A janela e modeless (CLAUDE.md, secao 2.9): deixa o pedido em
`handler.pedido` e chama `evento.Raise()`.

    ('vista', [lados])   seleciona e da zoom na vista ativa    sem Transaction
    ('3d', [lados])      vista "Interferências 3D" + caixa     1 Transaction
    ('passes', None)     verificação de passes (v1.5)          sem Transaction

VERIFICADO POR MCP (16/09/2026, MIIQLUX-SEW-RSR + MIIIQLUX-MEC.rvt)
-------------------------------------------------------------------
- `Selection.SetReferences` aceita, na MESMA lista, a referencia de um
  elemento do projeto e `Reference(elem).CreateLinkReference(instancia)` de
  um do vinculo: `GetReferences` devolveu as duas (a do vinculo com
  `LinkedElementId`). `SetElementIds` nao consegue selecionar elemento de
  vinculo.
- O vinculo MEC tem transform que NAO e identidade: a caixa do elemento
  vinculado passa pelos 8 cantos (`caixa_transformada`) antes do zoom.
- `ZoomAndCenterRectangle` com essa caixa, na planta ativa, funcionou.
- `ActiveView` + selecao + zoom no mesmo evento: o padrao do Fluxo ARN
  (`af_evento._ui`, verificado em 14/09).

O MODELO ABERTO NÃO PRECISA SER O DO RELATÓRIO (v1.7, 21/09/2026)
----------------------------------------------------------------
> "conseguiria abrir o link e investigar... navegando para o tubo apontado"

Cada lado chega com `arquivo` (o vínculo, ou o modelo do relatório). Se é o
modelo ABERTO (pelo nome do central), o elemento é local; se é um vínculo
dele, vai pelo vínculo; senão, avisa qual modelo abrir.

O VINCULO PELO NOME DO ARQUIVO
------------------------------
O HTML so traz `MIIIQLUX-MEC.rvt`. O nome da instancia comeca por ele
(`MIIIQLUX-MEC.rvt : 33 : localização ...`). O mesmo arquivo carregado duas
vezes e ambiguo: usa a primeira instancia e AVISA.
"""
import os
import traceback

import clr
clr.AddReference('RevitAPIUI')

from System import Environment, Int64
from System.Collections.Generic import List

from Autodesk.Revit.DB import (
    BasicFileInfo,
    BoundingBoxXYZ,
    Element,
    ModelPathUtils,
    WorksharingUtils,
    ElementId,
    FilteredElementCollector,
    Reference,
    RevitLinkInstance,
    Transaction,
    View3D,
    ViewFamily,
    ViewFamilyType,
    ViewType,
    XYZ,
)
from Autodesk.Revit.UI import ExternalEvent, IExternalEventHandler

from Snippets._interferencia import (
    caixa_transformada,
    nome_do_vinculo,
    onde_esta,
)

import ifr_clash
import ifr_passes
import log_novo
from ifr_modelo import arquivo_do_modelo

NOME_3D = u'Interferências 3D'
FOLGA_ZOOM = 2.0        # pes em volta dos elementos no zoom (o padrao)
#: a caixa de corte da 3D quer mais ar que o zoom da planta
FATOR_CAIXA = 1.5

_SEM_ZOOM = (ViewType.Schedule, ViewType.ProjectBrowser,
             ViewType.SystemBrowser, ViewType.Internal, ViewType.Undefined)


def _vista_grafica(uidoc):
    """A vista onde se trabalha. Com o foco no Navegador de projeto ou do
    sistema, `ActiveView` É o navegador (06/10/2026: "a vista ativa não
    permite zoom" numa planta); `ActiveGraphicalView` é a última vista de
    desenho ativa."""
    try:
        return uidoc.ActiveGraphicalView or uidoc.ActiveView
    except Exception:
        return uidoc.ActiveView


def _id_value(eid):
    return eid.Value if hasattr(eid, 'Value') else eid.IntegerValue


def _caixa_de(caixas, folga):
    if not caixas:
        return None
    menor = tuple(min(c[0][i] for c in caixas) - folga for i in range(3))
    maior = tuple(max(c[1][i] for c in caixas) + folga for i in range(3))
    return menor, maior


def _achar(documento, lado):
    """O elemento pelo UniqueId (LOG) ou pelo ElementId (relatórios).

    UniqueId primeiro: ele sobrevive ao que o ElementId não sobrevive
    (lição do LogOcorrencias). `GetElement(str)` devolve None quando não
    existe mais.
    """
    unico = lado.get('uniqueId') or ''
    if unico:
        try:
            elemento = documento.GetElement(unico)
        except Exception:
            elemento = None
        if elemento is not None:
            return elemento
    if not lado.get('id'):
        return None
    return documento.GetElement(ElementId(Int64(lado['id'])))


def _rotulo(lado):
    return u'{} {}'.format(lado.get('categoria') or u'ID',
                           lado.get('id') or lado.get('uniqueId') or '?')


def _nome(elemento):
    # Element.Name.GetValue: `.Name` levanta AttributeError no IronPython em
    # ElementType ([[ironpython-element-name-attributeerror]])
    try:
        return Element.Name.GetValue(elemento) or ''
    except Exception:
        try:
            return elemento.Name
        except Exception:
            return ''


class NavegarHandler(IExternalEventHandler):

    def __init__(self):
        self.janela = None
        self.pedido = None
        #: quanto a vista "abre" em volta dos elementos — a janela escolhe
        #: (combo Zoom, v2.3) e grava antes do Raise
        self.folga = FOLGA_ZOOM

    def GetName(self):
        return 'Interferencias.Navegar'

    def Execute(self, uiapp):
        # consumido: um Raise perdido nao repete o pedido
        pedido, self.pedido = self.pedido, None
        if not pedido:
            return
        acao, lados = pedido
        if acao == 'passes':
            self._verificar_passes(uiapp)
            return
        if acao == 'clash':
            self._verificar_clash(uiapp)
            return
        if acao == 'log_novo':
            self._novo_apontamento(uiapp, lados)
            return
        if acao == 'abrir_modelo':
            self._abrir_modelo(uiapp, lados)
            return
        uidoc = uiapp.ActiveUIDocument
        try:
            referencias, caixas, avisos = self._resolver(uidoc.Document, lados)
            if not referencias:
                self._status(u'Nenhum elemento encontrado: {}'.format(
                    '; '.join(avisos) or u'sem detalhe'), 'aviso')
                return
            if acao == '3d':
                aviso_3d = self._abrir_3d(uidoc, caixas)
                if aviso_3d:
                    avisos.append(aviso_3d)
            elif _vista_grafica(uidoc).ViewType in _SEM_ZOOM:
                avisos.append(u'a vista ativa não permite zoom; use a vista 3D')
            lista = List[Reference]()
            for referencia in referencias:
                lista.Add(referencia)
            uidoc.Selection.SetReferences(lista)
            self._zoom(uidoc, _caixa_de(caixas, self.folga))
            texto = u'{} elemento(s) selecionado(s){}.'.format(
                len(referencias), u' em 3D' if acao == '3d' else '')
            if avisos:
                self._status(texto + u' Atenção: ' + '; '.join(avisos),
                             'aviso')
            else:
                self._status(texto, 'ok')
        except Exception as erro:
            self._status(u'Não foi possível localizar os elementos: {}'.format(erro), 'erro')

    def _selecionar(self, uidoc, lados):
        """Só seleciona (sem zoom) — o apontamento lê a seleção depois."""
        referencias, _, avisos = self._resolver(uidoc.Document, lados)
        if not referencias:
            return u'Nenhum dos elementos do achado está neste modelo: ' \
                   u'{}'.format('; '.join(avisos) or u'sem detalhe')
        lista = List[Reference]()
        for referencia in referencias:
            lista.Add(referencia)
        uidoc.Selection.SetReferences(lista)
        if len(referencias) < len(lados):
            return u'{} de {} elemento(s) selecionado(s): {}'.format(
                len(referencias), len(lados), '; '.join(avisos[:2]))
        return ''

    def _verificar_clash(self, uiapp):
        """v2.4 — interferencia entre varios vinculos (so leitura)."""
        if self.janela is None:
            return
        try:
            self._status(ifr_clash.executar(uiapp, self.janela), 'ok')
        except Exception as erro:
            self._status(u'Não foi possível verificar as interferências: '
                         u'{}'.format(erro), 'erro')
            print(traceback.format_exc())

    def _verificar_passes(self, uiapp):
        """v1.5 — coleta, diálogo e verificação num evento só (só leitura)."""
        if self.janela is None:
            return
        try:
            self._status(ifr_passes.executar(uiapp, self.janela), 'ok')
        except Exception as erro:
            self._status(u'Não foi possível verificar os passes: {}'.format(erro),
                         'erro')
            print(traceback.format_exc())

    def _novo_apontamento(self, uiapp, dados):
        """v1.8 — o recado do LOG: seleção do Revit + diálogo + arquivo.

        v2.1: vindo de um achado (interferência/passe), os `lados` chegam
        junto e são selecionados ANTES — a janela lê a seleção, então o
        apontamento nasce com os elementos do achado.
        """
        if self.janela is None:
            return
        agora, sufixo, lados = dados
        try:
            if lados:
                aviso = self._selecionar(uiapp.ActiveUIDocument, lados)
                if aviso:
                    self._status(aviso, 'aviso')
            self._status(log_novo.abrir(uiapp, self.janela, agora, sufixo),
                         'ok')
        except Exception as erro:
            self._status(u'Não foi possível gravar o apontamento: {}'.format(erro),
                         'erro')
            print(traceback.format_exc())

    # ------------------------------------------------------------ elementos

    def _instancias(self, documento):
        por_nome = {}
        for instancia in FilteredElementCollector(documento) \
                .OfClass(RevitLinkInstance):
            por_nome.setdefault(nome_do_vinculo(_nome(instancia)),
                                []).append(instancia)
        return por_nome

    def _resolver(self, documento, lados):
        """-> ([Reference], [((min), (max))], [avisos])."""
        referencias, caixas, avisos = [], [], []
        instancias = self._instancias(documento)
        modelo = arquivo_do_modelo(documento)
        for lado in lados:
            # v1.7: 'arquivo' = onde o elemento mora (a janela resolve pelo
            # relatório); o modelo ABERTO pode ser o vínculo do relatório
            arquivo = lado.get('arquivo', lado.get('vinculo') or '')
            lugar = onde_esta(arquivo, modelo, instancias.keys())
            if lugar is None:
                avisos.append(u'{} está em {}: abra esse modelo ou vincule-o '
                              u'ao modelo ativo'.format(_rotulo(lado),
                                                          arquivo))
                continue
            vinculo = arquivo if lugar == 'vinculo' else ''
            if not vinculo:
                elemento = _achar(documento, lado)
                if elemento is None:
                    # v1.8: apontamento do LOG guarda o PONTO — o elemento
                    # pode ter sido apagado e refeito, a região continua lá
                    if self._caixa_do_ponto(lado, caixas):
                        avisos.append(u'{} não existe mais em {}; exibida a posição '
                                      u'registrada'.format(_rotulo(lado),
                                                              modelo))
                        continue
                    avisos.append(u'{} não existe mais em {}'.format(
                        _rotulo(lado), modelo or u'este modelo'))
                    continue
                referencias.append(Reference(elemento))
                bb = elemento.get_BoundingBox(None)
                if bb is not None:
                    caixas.append(((bb.Min.X, bb.Min.Y, bb.Min.Z),
                                   (bb.Max.X, bb.Max.Y, bb.Max.Z)))
                continue

            candidatas = instancias.get(vinculo.lower(), [])
            if not candidatas:
                avisos.append(u'o vínculo {} não está no projeto'.format(
                    vinculo))
                continue
            if len(candidatas) > 1:
                avisos.append(u'{} está carregado {} vezes; considerada a '
                              u'primeira instância'.format(vinculo, len(candidatas)))
            instancia = candidatas[0]
            doc_vinculo = instancia.GetLinkDocument()
            if doc_vinculo is None:
                avisos.append(u'o vínculo {} não está carregado'.format(
                    vinculo))
                continue
            elemento = _achar(doc_vinculo, lado)
            if elemento is None:
                if self._caixa_do_ponto(lado, caixas,
                                        instancia.GetTotalTransform()):
                    avisos.append(u'{} não existe mais em {}; exibida a posição '
                                  u'registrada'.format(_rotulo(lado), vinculo))
                    continue
                avisos.append(u'{} não existe mais em {}'.format(
                    _rotulo(lado), vinculo))
                continue
            referencias.append(
                Reference(elemento).CreateLinkReference(instancia))
            bb = elemento.get_BoundingBox(None)
            if bb is not None:
                transform = instancia.GetTotalTransform()

                def transformar(p, t=transform):
                    q = t.OfPoint(XYZ(p[0], p[1], p[2]))
                    return (q.X, q.Y, q.Z)
                caixas.append(caixa_transformada(
                    (bb.Min.X, bb.Min.Y, bb.Min.Z),
                    (bb.Max.X, bb.Max.Y, bb.Max.Z), transformar))
        return referencias, caixas, avisos

    def _caixa_do_ponto(self, lado, caixas, transform=None):
        """O ponto anotado no LOG vira caixa de zoom. -> True se havia um."""
        ponto = lado.get('ponto') or {}
        minimo, maximo = ponto.get('min'), ponto.get('max')
        if not minimo or not maximo:
            return False
        if transform is None:
            caixas.append((tuple(minimo), tuple(maximo)))
            return True

        def transformar(p, t=transform):
            q = t.OfPoint(XYZ(p[0], p[1], p[2]))
            return (q.X, q.Y, q.Z)
        caixas.append(caixa_transformada(tuple(minimo), tuple(maximo),
                                         transformar))
        return True

    # ---------------------------------------------------------------- vistas

    def _zoom(self, uidoc, envolve):
        if envolve is None:
            return
        ativa = _id_value(_vista_grafica(uidoc).Id)
        for uiview in uidoc.GetOpenUIViews():
            if _id_value(uiview.ViewId) == ativa:
                uiview.ZoomAndCenterRectangle(XYZ(*envolve[0]),
                                              XYZ(*envolve[1]))

    def _abrir_3d(self, uidoc, caixas):
        """Abre a "Interferências 3D" com a caixa de corte. -> aviso ou ''.

        Vista propria: a caixa de corte nao mexe na {3D} de ninguem (mesma
        decisao do Fluxo ARN).
        """
        documento = uidoc.Document
        envolve = _caixa_de(caixas, self.folga * FATOR_CAIXA)
        vista = None
        for candidata in FilteredElementCollector(documento).OfClass(View3D):
            if not candidata.IsTemplate and _nome(candidata) == NOME_3D:
                vista = candidata
                break
        aviso = ''
        transacao = Transaction(documento, u'Interferências — vista 3D')
        transacao.Start()
        try:
            if vista is None:
                tipo = None
                for vft in FilteredElementCollector(documento) \
                        .OfClass(ViewFamilyType):
                    if vft.ViewFamily == ViewFamily.ThreeDimensional:
                        tipo = vft
                        break
                vista = View3D.CreateIsometric(documento, tipo.Id)
                vista.Name = NOME_3D
            if envolve is not None:
                limites = BoundingBoxXYZ()
                limites.Min = XYZ(*envolve[0])
                limites.Max = XYZ(*envolve[1])
                vista.SetSectionBox(limites)
                vista.IsSectionBoxActive = True
                documento.Regenerate()
                if not vista.IsSectionBoxActive:
                    aviso = u'o modelo de vista da "{}" desativou a caixa de ' \
                            u'corte'.format(NOME_3D)
            transacao.Commit()
        except Exception:
            transacao.RollBack()
            raise
        uidoc.ActiveView = vista
        return aviso

    def _abrir_modelo(self, uiapp, caminho):
        """Abre o modelo do apontamento de outra obra (v3.3, 06/10/2026).

        Workshared: NUNCA o central — abre a cópia local em Documentos
        (cria se não houver), como o "Criar novo local" do Revit
        ([[_log_obra]]). Já aberto: o Revit só o ativa.
        """
        from Snippets._log_obra import nome_da_copia_local
        try:
            abrir = caminho
            info = BasicFileInfo.Extract(caminho)
            if info.IsWorkshared and info.IsCentral:
                local = os.path.join(
                    Environment.GetFolderPath(
                        Environment.SpecialFolder.MyDocuments),
                    nome_da_copia_local(caminho, uiapp.Application.Username))
                if not os.path.exists(local):
                    WorksharingUtils.CreateNewLocal(
                        ModelPathUtils.ConvertUserVisiblePathToModelPath(
                            caminho),
                        ModelPathUtils.ConvertUserVisiblePathToModelPath(
                            local))
                abrir = local
            uiapp.OpenAndActivateDocument(abrir)
        except Exception as erro:
            self._status(u'Não foi possível abrir {}: {}'.format(
                os.path.basename(caminho), erro), 'erro')
            return
        if self.janela is not None:
            try:
                self.janela.modelo_aberto(os.path.basename(caminho))
            except Exception as erro:
                self._status(u'Modelo aberto; a navegação não foi '
                             u'concluída: {}'.format(erro), 'aviso')

    def _status(self, texto, nivel):
        janela = self.janela
        if janela is None:
            return
        try:
            janela.mostrar_status(texto, nivel)
        except Exception as erro:
            print(u'Interferências: {} ({})'.format(texto, erro))


handler = NavegarHandler()
evento = ExternalEvent.Create(handler)
