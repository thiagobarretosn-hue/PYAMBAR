# -*- coding: utf-8 -*-
"""Novo apontamento do LOG: janela MODELESS que acompanha a seleção.

O CASO QUE ISTO RESOLVE (Thiago, 24/09/2026)
-------------------------------------------
> "estou modelando o WATER SUPPLY e vejo um tubo do SEWER (vínculo) numa
>  altura errada... preciso anotar para, quando chegar no outro modelo,
>  localizar a mesma região rápido"

E, depois de usar a primeira versão:

> "NOVO APONTAMENTO DEVE SER NÃO MODAL, ONDE FAZER O PRINT DA TELA, PODER
>  SELECIONAR OS ELEMENTOS NÃO SÓ DO PROJETO MAS DOS LINKS, MUDAR A SELEÇÃO
>  ENQUANTO ESTÁ ESCREVENDO O APONTAMENTO"

Por isso a janela é modeless: o Revit continua vivo atrás dela. Ela tem
EVENTO PRÓPRIO (CLAUDE.md, seção 2.9 — modeless nunca fala com a API
direto) e relê a seleção toda vez que você volta para ela, o que cobre
"mudar a seleção enquanto escreve" sem botão nenhum.

O QUE O ALVO GUARDA
-------------------
O ARQUIVO onde o elemento mora — inclusive quando vem de vínculo — e o ponto
**nas coordenadas desse arquivo**: quem abrir o SEWER usa direto; quem o vê
como vínculo aplica a transform ([[api-interferencia-vinculos]]).
UniqueId, não ElementId: o UniqueId sobrevive (lição do LogOcorrencias);
o ElementId vai junto só como atalho de leitura.
"""
import os
import sys
import traceback

import clr
clr.AddReference('PresentationCore')
clr.AddReference('PresentationFramework')
clr.AddReference('RevitAPIUI')

from System import TimeSpan
from System.Windows.Threading import DispatcherTimer

from Autodesk.Revit.DB import Element, ElementId, RevitLinkInstance
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI import ExternalEvent, IExternalEventHandler
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType

from pyrevit.forms import WPFWindow

from Snippets._captura_tela import (
    abrir_recorte,
    capturar_clipboard,
    gravar_em,
    limpar_clipboard,
    tem_imagem_no_clipboard,
)
from Snippets._log_equipe import (
    nome_de as nome_da_pessoa,
    nomes as nomes_da_equipe,
)
from Snippets._log_ocorrencias import nova_ocorrencia, novo_id, pessoas

import log_disco
from ifr_modelo import arquivo_do_modelo, caminho_do_modelo

SCRIPT_DIR = os.path.dirname(__file__)
INVALIDO = ElementId.InvalidElementId
#: o recorte não trava a janela: um timer olha o clipboard de tempos em tempos
INTERVALO_RECORTE = 700     # ms
TENTATIVAS_RECORTE = 45     # ~30 s


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


def _ponto(elemento):
    """A caixa do elemento NAS COORDENADAS DO DOCUMENTO DELE."""
    caixa = elemento.get_BoundingBox(None)
    if caixa is None:
        return None
    return {'min': [caixa.Min.X, caixa.Min.Y, caixa.Min.Z],
            'max': [caixa.Max.X, caixa.Max.Y, caixa.Max.Z]}


def _alvo(elemento, arquivo):
    categoria = elemento.Category.Name if elemento.Category else u'Elemento'
    return {'arquivo': arquivo,
            'uniqueId': elemento.UniqueId,
            'elementId': int(elemento.Id.Value
                             if hasattr(elemento.Id, 'Value')
                             else elemento.Id.IntegerValue),
            'categoria': categoria, 'descricao': _nome(elemento),
            'ponto': _ponto(elemento)}


def alvos_da_selecao(uidoc):
    """Os elementos selecionados, do projeto E dos vínculos.

    -> ([alvo], [aviso]). O vínculo INTEIRO selecionado não é um
    apontamento: em vez de a janela dizer "nada selecionado", o aviso
    explica como escolher o elemento dentro dele (Tab).

    AS DUAS FONTES SÃO LIDAS SEMPRE (24/09/2026)
    --------------------------------------------
    `GetReferences()` é a única que enxerga elemento DENTRO de vínculo, mas
    não devolve referência para tudo que está selecionado — seleção por
    janela, por filtro ou vinda de outra ferramenta costuma aparecer só em
    `GetElementIds()`. A versão anterior lia as referências e, **se viesse
    qualquer uma**, largava os ids: o Thiago selecionava tubos e conexões e
    o apontamento gravava parte. Agora lê as duas e junta (`juntar` remove
    o repetido por arquivo + UniqueId); um elemento que falhe na leitura
    vira aviso, nunca derruba os outros.
    """
    documento = uidoc.Document
    deste = arquivo_do_modelo(documento)
    alvos, avisos, perdidos = [], [], []

    def guardar(elemento, arquivo):
        try:
            juntar(alvos, [_alvo(elemento, arquivo)])
        except Exception as erro:
            perdidos.append(erro)
            print(u'LOG: elemento não lido ({})'.format(erro))

    def avisar_vinculo(instancia):
        aviso = _aviso_do_vinculo(instancia)
        if aviso not in avisos:
            avisos.append(aviso)

    try:
        referencias = list(uidoc.Selection.GetReferences())
    except Exception:
        referencias = []
    for referencia in referencias:
        if referencia.LinkedElementId != INVALIDO:
            instancia = documento.GetElement(referencia.ElementId)
            if not isinstance(instancia, RevitLinkInstance):
                continue
            doc_vinculo = instancia.GetLinkDocument()
            if doc_vinculo is None:
                continue
            elemento = doc_vinculo.GetElement(referencia.LinkedElementId)
            arquivo = arquivo_do_modelo(doc_vinculo)
        else:
            elemento = documento.GetElement(referencia.ElementId)
            arquivo = deste
            if isinstance(elemento, RevitLinkInstance):
                avisar_vinculo(elemento)
                continue
        if elemento is not None:
            guardar(elemento, arquivo)

    try:
        ids = list(uidoc.Selection.GetElementIds())
    except Exception:
        ids = []
    for eid in ids:
        elemento = documento.GetElement(eid)
        if elemento is None:
            continue
        if isinstance(elemento, RevitLinkInstance):
            avisar_vinculo(elemento)
            continue
        guardar(elemento, deste)

    if perdidos:
        avisos.append(u'{} elemento(s) da seleção não puderam ser lidos.'
                      .format(len(perdidos)))
    return alvos, avisos


class SemVinculos(ISelectionFilter):
    """No "selecionar elementos do modelo", o vinculo nao e clicavel.

    Sem isto, clicar num tubo do vinculo devolve o RevitLinkInstance, que o
    codigo descarta — e o apontamento saia com ZERO alvos, calado (foi o que
    aconteceu em 24/09/2026: dois arquivos sem alvo na pasta da obra).
    """

    def AllowElement(self, elemento):
        return not isinstance(elemento, RevitLinkInstance)

    def AllowReference(self, referencia, ponto):
        return True


def escolher_no_vinculo(uidoc):
    """Clique direto no elemento DENTRO do vínculo (sem Tab).

    O Revit seleciona o vínculo inteiro no clique simples; `PickObjects` com
    `ObjectType.LinkedElement` é o modo em que o clique pega o elemento de
    dentro. Era o que o LogOcorrencias fazia em `elements.pick_em_link`.
    """
    documento = uidoc.Document
    try:
        referencias = uidoc.Selection.PickObjects(
            ObjectType.LinkedElement,
            u'Selecione os itens DO VÍNCULO — Enter para terminar')
    except OperationCanceledException:
        return [], []
    alvos, avisos = [], []
    for referencia in referencias:
        instancia = documento.GetElement(referencia.ElementId)
        if not isinstance(instancia, RevitLinkInstance):
            continue
        doc_vinculo = instancia.GetLinkDocument()
        if doc_vinculo is None:
            avisos.append(u'{} não está carregado.'.format(
                _nome(instancia).split(' : ')[0]))
            continue
        elemento = doc_vinculo.GetElement(referencia.LinkedElementId)
        if elemento is not None:
            try:
                juntar(alvos, [_alvo(elemento, arquivo_do_modelo(doc_vinculo))])
            except Exception as erro:
                print(u'LOG: elemento do vínculo não lido ({})'.format(erro))
    return alvos, avisos


def escolher_no_modelo(uidoc):
    """Clique nos elementos DESTE modelo."""
    documento = uidoc.Document
    try:
        referencias = uidoc.Selection.PickObjects(
            ObjectType.Element, SemVinculos(),
            u'Selecione os elementos DESTE modelo — Enter para terminar')
    except OperationCanceledException:
        return [], []
    deste = arquivo_do_modelo(documento)
    alvos = []
    for referencia in referencias:
        elemento = documento.GetElement(referencia.ElementId)
        if elemento is not None and not isinstance(elemento,
                                                   RevitLinkInstance):
            try:
                juntar(alvos, [_alvo(elemento, deste)])
            except Exception as erro:
                print(u'LOG: elemento não lido ({})'.format(erro))
    return alvos, []


def juntar(alvos, novos):
    """Acrescenta sem repetir (mesmo arquivo + mesmo UniqueId)."""
    vistos = set((a['arquivo'].lower(), a['uniqueId']) for a in alvos)
    for alvo in novos:
        chave = (alvo['arquivo'].lower(), alvo['uniqueId'])
        if chave not in vistos:
            vistos.add(chave)
            alvos.append(alvo)
    return alvos


def _aviso_do_vinculo(instancia):
    nome = _nome(instancia).split(' : ')[0].strip()
    return u'O vínculo {} está selecionado INTEIRO. Para apontar um elemento ' \
           u'dele: passe o mouse por cima, tecle Tab até ele ficar realçado ' \
           u'e clique.'.format(nome)


def resumo_dos_alvos(alvos, modelo_aberto, avisos=()):
    if not alvos:
        base = u'Nenhum elemento selecionado: o apontamento será registrado no modelo {}, sem ' \
               u'elemento. Selecione no Revit e volte para esta janela.' \
               .format(modelo_aberto)
        return u'\n'.join([base] + list(avisos))
    por_arquivo = {}
    for alvo in alvos:
        por_arquivo.setdefault(alvo['arquivo'], []).append(alvo)
    linhas = []
    for arquivo in sorted(por_arquivo):
        deles = por_arquivo[arquivo]
        exemplos = u', '.join(u'{} {}'.format(a['categoria'], a['elementId'])
                              for a in deles[:3])
        linhas.append(u'{} — {} elemento(s): {}{}'.format(
            arquivo, len(deles), exemplos, u'…' if len(deles) > 3 else u''))
    # o total vem primeiro: é o número que o usuário confere contra a
    # seleção do Revit ("selecionei 14 e gravou 14")
    total = [u'{} elemento(s) no apontamento'.format(len(alvos))]
    return u'\n'.join(total + linhas + list(avisos))


# -------------------------------------------------------------- o evento

class NovoHandler(IExternalEventHandler):
    """Tudo o que precisa da API: ler a seleção e gravar o apontamento."""

    def __init__(self):
        self.janela = None
        self.pedido = None

    def GetName(self):
        return 'LOG.NovoApontamento'

    def Execute(self, uiapp):
        pedido, self.pedido = self.pedido, None
        if not pedido or self.janela is None:
            return
        try:
            if pedido in ('pick_vinculo', 'pick_modelo'):
                self._escolher(uiapp, pedido)
            elif pedido == 'gravar':
                self.janela.gravar_agora(uiapp)
        except Exception as erro:
            self.janela.avisar(u"{}".format(erro))
            print(traceback.format_exc())

    def _escolher(self, uiapp, pedido):
        """A janela SAI DA FRENTE enquanto voce clica no modelo e volta
        depois: ela e Topmost e brigava pelo foco no meio da escolha, o que
        parecia travamento (relato do Thiago, 24/09/2026)."""
        uidoc = uiapp.ActiveUIDocument
        no_vinculo = pedido == 'pick_vinculo'
        self.janela.Hide()
        try:
            alvos, avisos = (escolher_no_vinculo(uidoc) if no_vinculo
                             else escolher_no_modelo(uidoc))
        finally:
            self.janela.Show()
            self.janela.Activate()
        if alvos:
            self.janela.acrescentar_alvos(
                alvos, arquivo_do_modelo(uidoc.Document), avisos)
            self.janela.avisar('')
            return
        # nunca ficar calado: Esc, nada clicado ou botao trocado
        self.janela.avisar(u" ".join(avisos) if avisos else (
            u"Nada escolhido. Clique nos itens e tecle Enter para terminar "
            u"(Esc cancela)."))


handler = NovoHandler()
evento = ExternalEvent.Create(handler)


# -------------------------------------------------------------- a janela

class JanelaNovo(WPFWindow):
    """Modeless: escreve, troca a seleção no Revit, recorta a tela, grava."""

    def __init__(self, janela_principal, equipe, agora, sufixo):
        WPFWindow.__init__(self, os.path.join(SCRIPT_DIR, 'log_novo.xaml'))
        self.principal = janela_principal
        self.alvos = []
        self.imagem = None
        self.agora = agora
        self.sufixo = sufixo
        self._tentativas = 0
        self.ParaCombo.ItemsSource = equipe
        self.Closed += self.ao_fechar
        self._timer = DispatcherTimer()
        self._timer.Interval = TimeSpan.FromMilliseconds(INTERVALO_RECORTE)
        self._timer.Tick += self.ao_conferir_recorte
        handler.janela = self

    # ------------------------------------------------------------ seleção

    def ao_escolher_no_vinculo(self, sender, args):
        """O Revit só seleciona o vínculo inteiro no clique simples; aqui o
        clique pega o elemento de dentro (sem Tab)."""
        self.ErroLabel.Text = ''
        self.pedir('pick_vinculo')

    def ao_escolher_no_modelo(self, sender, args):
        self.ErroLabel.Text = ''
        self.pedir('pick_modelo')

    def acrescentar_alvos(self, alvos, modelo_aberto, avisos=()):
        """O escolhido SOMA ao que já havia, sem repetir."""
        self.alvos = juntar(list(self.alvos), alvos)
        self.AlvosLabel.Text = resumo_dos_alvos(self.alvos, modelo_aberto,
                                                avisos)

    def definir_alvos(self, alvos, modelo_aberto, avisos=()):
        self.alvos = alvos
        self.AlvosLabel.Text = resumo_dos_alvos(alvos, modelo_aberto, avisos)

    def pedir(self, o_que):
        handler.janela = self
        handler.pedido = o_que
        evento.Raise()

    # ------------------------------------------------------------- imagem

    def ao_recortar(self, sender, args):
        """Abre o recorte do Windows (o mesmo Win+Shift+S) e fica de olho no
        clipboard SEM travar a janela."""
        self.ErroLabel.Text = ''
        try:
            limpar_clipboard()
            abrir_recorte()
        except Exception as erro:
            self.ErroLabel.Text = u'Não foi possível iniciar o recorte: {}'.format(
                erro)
            return
        self._tentativas = 0
        self.ImagemLabel.Text = u'Recorte de tela iniciado: selecione a área desejada.'
        self._timer.Start()

    def ao_conferir_recorte(self, sender, args):
        self._tentativas += 1
        try:
            tem = tem_imagem_no_clipboard()
        except Exception:
            tem = False
        if tem:
            self._timer.Stop()
            self.imagem = capturar_clipboard()
            self.ImagemLabel.Text = u'Imagem anexada ({}).'.format(
                (self.imagem or {}).get('filename', ''))
            return
        if self._tentativas >= TENTATIVAS_RECORTE:
            self._timer.Stop()
            self.ImagemLabel.Text = u'Recorte não recebido (tempo esgotado). Clique ' \
                                    u'novamente para tentar outra vez.'

    def ao_tirar_imagem(self, sender, args):
        self.imagem = None
        self.ImagemLabel.Text = u'Sem imagem.'

    # ------------------------------------------------------------- gravar

    def ao_gravar(self, sender, args):
        if not (self.TextoBox.Text or '').strip():
            self.ErroLabel.Text = u'Escreva o que precisa ser feito.'
            return
        self.GravarBtn.IsEnabled = False
        self.pedir('gravar')

    def gravar_agora(self, uiapp):
        """Roda no evento (contexto de API): monta o item e grava."""
        documento = uiapp.ActiveUIDocument.Document
        pasta = log_disco.pasta_do_log(caminho_do_modelo(documento))
        autor = self.principal.usuario_atual()          # 'Thiago Nunes'
        autor_id = self.principal.usuario_id()          # 'thiagonunesXNUJD'
        para = (self.ParaCombo.Text or '').strip()
        item = nova_ocorrencia(
            (self.TextoBox.Text or '').strip(), autor, self.agora,
            autor_id=autor_id,
            id_=novo_id(self.agora, autor, self.sufixo),
            para=[para] if para else [], alvos=self.alvos,
            modelo=(self.alvos[0]['arquivo'] if self.alvos
                    else arquivo_do_modelo(documento)),
            vista=_nome(documento.ActiveView),
            nivel=_nivel_da_vista(documento))
        if self.imagem:
            try:
                item['imagem'] = gravar_em(
                    self.imagem,
                    log_disco.garantir_imagens(pasta), item['id'])
            except Exception as erro:
                self.avisar(u'Apontamento sem a imagem: {}'.format(erro))
        item, erro = log_disco.gravar(pasta, item)
        log_disco.registrar_pessoa(pasta, autor_id, autor, self.agora)
        if erro:
            self.avisar(u'Não foi possível gravar em {}: {}'.format(pasta, erro))
            return
        # v3.2 — o balão de quem está no "Para"
        self.principal.avisar_caixa('novo', item, self.agora, pasta=pasta)
        self.principal.carregar_log(manter=('conflito', item['id']))
        self.principal.mostrar_status(
            u'Apontamento registrado ({} elemento(s), para {}).'.format(
                len(self.alvos), para or u'toda a equipe'), 'ok')
        self.Close()

    def avisar(self, texto):
        self.ErroLabel.Text = texto
        self.GravarBtn.IsEnabled = True

    def ao_cancelar(self, sender, args):
        self.Close()

    def ao_fechar(self, sender, args):
        self._timer.Stop()
        handler.janela = None
        sys.modules[__name__].__dict__['_JANELA_ABERTA'] = None


def _nivel_da_vista(documento):
    try:
        nivel = documento.ActiveView.GenLevel
        return _nome(nivel) if nivel is not None else ''
    except Exception:
        return ''


def abrir(uiapp, janela_principal, agora, sufixo):
    """Sobe a janela modeless (chamado de dentro do evento da principal)."""
    aberta = globals().get('_JANELA_ABERTA')
    if aberta is not None:
        try:
            aberta.Activate()
            return u'A janela do apontamento já está aberta.'
        except Exception:
            pass
    uidoc = uiapp.ActiveUIDocument
    janela = JanelaNovo(janela_principal, _equipe(uidoc.Document), agora,
                        sufixo)
    alvos, avisos = alvos_da_selecao(uidoc)
    janela.definir_alvos(alvos, arquivo_do_modelo(uidoc.Document), avisos)
    globals()['_JANELA_ABERTA'] = janela
    janela.Show()
    return u'Escreva o apontamento. A seleção do Revit pode mudar enquanto ' \
           u'você escreve.'


def _equipe(documento):
    """Quem pode receber o apontamento: a empresa inteira mais quem já
    escreveu nesta obra (o auto-completar do campo 'Para')."""
    pasta = log_disco.pasta_do_log(caminho_do_modelo(documento))
    itens, _ = log_disco.ler(pasta)
    equipe = log_disco.ler_equipe(pasta)
    saida = []
    for quem in pessoas(itens, nomes_da_equipe(equipe)):
        # apontamento antigo gravou o ID no autor: quem já se cadastrou
        # entra na lista pelo NOME, e uma vez só
        nome = nome_da_pessoa(equipe, quem)
        if nome.lower() not in [n.lower() for n in saida]:
            saida.append(nome)
    return sorted(saida, key=lambda n: n.lower())
