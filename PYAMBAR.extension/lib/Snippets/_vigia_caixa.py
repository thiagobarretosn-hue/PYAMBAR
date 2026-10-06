# -*- coding: utf-8 -*-
"""Vigia da caixa de entrada do LOG, DENTRO do Revit (v3.2, 05/10/2026).

Liga ao abrir o Revit (`startup.py` da extensao) e quando o LOG abre.
Observa UMA pasta — a caixa da pessoa ([[_caixa_entrada]]) — e mostra o
balao do InfoCenter da Autodesk, que nao trava a tela e some sozinho.

O QUE FOI MEDIDO ANTES ([[api-notificacao-revit]])
-------------------------------------------------
- arquivo criado por OUTRA pessoa no Google Drive chega ao
  FileSystemWatcher em 2-3 s;
- o evento vem numa thread do Windows; `Dispatcher.BeginInvoke` leva para a
  thread da tela e o balao sai no mesmo milissegundo;
- o balao e interface, nao Revit API: nao precisa de Idling.
Editar o CONTEUDO de um arquivo remoto nao foi testado — por isso tambem
confere a caixa a cada minuto (listar uma pasta pequena: ~1 ms).

UM VIGIA POR REVIT
------------------
O objeto vivo fica em `AppDomain` (CHAVE): o Reload do pyRevit cria motor
novo, e o vigia do motor velho seria um segundo balao para cada aviso. Quem
liga desliga o anterior. Duas extensoes carregadas (lab e distribuicao)
tambem dividem o mesmo vigia.

Clicar no balao: grava o apontamento em `caixa_abrir.json` e dispara um
ExternalEvent que faz PostCommand do botao LOG — o LOG le o arquivo e abre
no apontamento.
"""
import codecs
import json
import os

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('WindowsBase')
clr.AddReference('AdWindows')
clr.AddReference('RevitAPIUI')
# .NET 8 (Revit 2025+): o FileSystemWatcher mora numa DLL propria que o
# IronPython nao carrega sozinho — sem isto, "Cannot import name
# FileSystemWatcher" (medido 05/10/2026). No .NET Framework fica em System.
try:
    clr.AddReference('System.IO.FileSystem.Watcher')
except Exception:
    clr.AddReference('System')

from System import (  # noqa: E402
    Action, AppDomain, Array, Guid, Object, TimeSpan)
from System.IO import FileSystemWatcher, NotifyFilters  # noqa: E402
from System.Windows import Application  # noqa: E402
from System.Windows.Threading import DispatcherTimer  # noqa: E402
from Autodesk.Revit.UI import (  # noqa: E402
    ExternalEvent,
    IExternalEventHandler,
    RevitCommandId,
)

from Snippets import _caixa_entrada as caixa  # noqa: E402

CHAVE = 'PYAMBAR_LOG_CAIXA'
INTERVALO = 60          # s — a conferencia de seguranca
_APPDATA = os.path.join(os.getenv('APPDATA', ''), 'pyRevit', 'PYAMBAR',
                        'Interferencias')
#: identifica ESTE carregamento do modulo: depois de um Reload, o novo
#: assume no lugar do velho
_TOKEN = str(Guid.NewGuid())


def _anotar(texto):
    """Registro em `avisos.log` no APPDATA — NUNCA print: no motor do
    startup, print abre a janela de saida do pyRevit na cara do usuario."""
    try:
        import io
        import time
        if not os.path.isdir(_APPDATA):
            os.makedirs(_APPDATA)
        caminho = os.path.join(_APPDATA, 'avisos.log')
        if os.path.exists(caminho) and os.path.getsize(caminho) > 200000:
            os.remove(caminho)      # nao cresce para sempre
        with io.open(caminho, 'a', encoding='utf-8') as arquivo:
            arquivo.write(u'{} {}\n'.format(time.strftime('%Y-%m-%d %H:%M:%S'),
                                            texto))
    except Exception:
        return


def _ler_json(caminho, padrao):
    if not os.path.exists(caminho):
        return padrao
    try:
        with codecs.open(caminho, 'r', encoding='utf-8') as arquivo:
            return json.load(arquivo)
    except Exception as erro:
        _anotar(u'{} ilegivel ({})'.format(caminho, erro))
        return padrao


def _gravar_json(caminho, dados):
    pasta = os.path.dirname(caminho)
    if not os.path.isdir(pasta):
        os.makedirs(pasta)
    with codecs.open(caminho, 'w', encoding='utf-8') as arquivo:
        json.dump(dados, arquivo, indent=1, ensure_ascii=False)


def raiz_anotada():
    """A caixa da empresa que o LOG anotou (vazio se o LOG nunca abriu)."""
    caminho = os.path.join(_APPDATA, caixa.ARQUIVO_RAIZ)
    if not os.path.exists(caminho):
        return ''
    try:
        with codecs.open(caminho, 'r', encoding='utf-8') as arquivo:
            return arquivo.read().strip()
    except Exception as erro:
        _anotar(u'raiz nao lida ({})'.format(erro))
        return ''


def pedido_de_abrir(apagar=True):
    """O apontamento que o clique no balao pediu para abrir (ou None)."""
    caminho = os.path.join(_APPDATA, caixa.ARQUIVO_ABRIR)
    dados = _ler_json(caminho, None)
    if dados is not None and apagar:
        try:
            os.remove(caminho)
        except Exception as erro:
            _anotar(u'pedido nao apagado ({})'.format(erro))
    return dados


class _AbrirLog(IExternalEventHandler):
    """Contexto de API para o PostCommand do botao LOG."""

    def __init__(self, botoes):
        self.botoes = list(botoes)

    def Execute(self, uiapp):
        for botao in self.botoes:
            try:
                comando = RevitCommandId.LookupCommandId(botao)
                if comando is not None and uiapp.CanPostCommand(comando):
                    uiapp.PostCommand(comando)
                    return
            except Exception as erro:
                _anotar(u'{} ({})'.format(botao, erro))

    def GetName(self):
        return 'PYAMBAR LOG - abrir pelo aviso'


class Vigia(object):

    def __init__(self, raiz, ident, botoes):
        self.token = _TOKEN
        self.pasta = os.path.join(raiz, caixa.nome_de_pasta(ident))
        if not os.path.isdir(self.pasta):
            os.makedirs(self.pasta)
        self.evento = ExternalEvent.Create(_AbrirLog(botoes))
        self.tela = Application.Current.Dispatcher
        self.vigia = FileSystemWatcher(self.pasta, '*.json')
        self.vigia.NotifyFilter = NotifyFilters.FileName | \
            NotifyFilters.LastWrite
        self.vigia.Created += self._no_disco
        self.vigia.Renamed += self._no_disco
        self.vigia.EnableRaisingEvents = True
        self.relogio = DispatcherTimer()
        self.relogio.Interval = TimeSpan.FromSeconds(INTERVALO)
        self.relogio.Tick += self._no_relogio
        self.relogio.Start()
        self._ultimo = None

    def parar(self):
        try:
            self.vigia.EnableRaisingEvents = False
            self.vigia.Dispose()
            self.relogio.Stop()
        except Exception as erro:
            _anotar(u'vigia nao parou ({})'.format(erro))

    def _no_disco(self, sender, args):
        # thread do Windows: so agenda na thread da tela
        self.tela.BeginInvoke(Action(self.conferir))

    def _no_relogio(self, sender, args):
        self.conferir()

    def conferir(self):
        """Mostra o que chegou e ainda nao virou balao. Thread da tela."""
        try:
            nomes = os.listdir(self.pasta)
            arquivo_vistos = os.path.join(_APPDATA, caixa.ARQUIVO_VISTOS)
            vistos = _ler_json(arquivo_vistos, [])
            novos = caixa.pendentes(nomes, vistos)
            avisos = []
            for nome in novos:
                aviso = _ler_json(os.path.join(self.pasta, nome), None)
                if isinstance(aviso, dict):
                    avisos.append(aviso)
            if avisos:
                self.mostrar(avisos)
            existentes = set(n.lower() for n in nomes)
            if novos or len(vistos) > len(existentes):
                _gravar_json(arquivo_vistos,
                             [v for v in vistos if v.lower() in existentes] +
                             list(novos))
            self._limpar(nomes)
            # o contador do botao LOG (v3.4): o que ainda nao foi aberto
            atualizar_botao(len(caixa.nao_lidos(nomes, ler_lidos())))
        except Exception:
            import traceback
            _anotar(u'conferir falhou:\n' + traceback.format_exc())

    def _limpar(self, nomes):
        from datetime import datetime
        agora = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        for nome in caixa.vencidos(nomes, agora):
            try:
                os.remove(os.path.join(self.pasta, nome))
            except Exception as erro:
                _anotar(u'{} nao apagado ({})'.format(nome, erro))

    def mostrar(self, avisos):
        categoria, titulo = caixa.balao(avisos)
        self._ultimo = avisos[-1]
        mostrar_balao(categoria, titulo, self._ao_clicar)

    def _ao_clicar(self, sender, args):
        try:
            _gravar_json(os.path.join(_APPDATA, caixa.ARQUIVO_ABRIR),
                         self._ultimo or {})
            self.evento.Raise()
        except Exception as erro:
            _anotar(u'clique falhou ({})'.format(erro))


def mostrar_balao(categoria, titulo, ao_clicar=None):
    """O balao do InfoCenter (canto superior direito do Revit)."""
    from Autodesk.Internal.InfoCenter import ResultItem
    from Autodesk.Windows import ComponentManager
    item = ResultItem()
    item.Category = categoria
    item.Title = titulo
    item.IsNew = True
    if ao_clicar is not None:
        item.ResultClicked += ao_clicar
    gerente = ComponentManager.InfoCenterPaletteManager
    # ha dois ShowBalloon com a mesma assinatura (reflexao: "Ambiguous
    # match"); o primeiro da lista e o que funcionou no teste
    metodo = [m for m in gerente.GetType().GetMethods()
              if m.Name == 'ShowBalloon'][0]
    metodo.Invoke(gerente, Array[Object]([item]))


def ligar(uiapp, botoes, assumir=False):
    """Liga (ou mantem) o vigia deste Revit. -> o vigia, ou None.

    `assumir`: quem acabou de carregar (startup depois de Reload) troca o
    vigia velho pelo seu. O LOG chama sem `assumir`: so liga se nao houver.
    """
    raiz = os.path.normpath(raiz_anotada()) if raiz_anotada() else ''
    if not raiz or not os.path.isdir(os.path.dirname(os.path.dirname(raiz))):
        return None     # o LOG ainda nao abriu numa obra do servidor
    ident = uiapp.Application.Username
    pasta = os.path.join(raiz, caixa.nome_de_pasta(ident))
    antigo = AppDomain.CurrentDomain.GetData(CHAVE)
    if antigo is not None:
        try:
            if antigo.pasta == pasta and \
                    (not assumir or antigo.token == _TOKEN):
                return antigo
            antigo.parar()
        except Exception as erro:
            _anotar(u'vigia antigo ({})'.format(erro))
    vigia = Vigia(raiz, ident, botoes)
    AppDomain.CurrentDomain.SetData(CHAVE, vigia)
    vigia.conferir()    # o que chegou com o Revit fechado
    return vigia


# --------------------------------------- avisos recebidos e contador (v3.4)
# Thiago, 06/10/2026: "se eu nao conseguir clicar na notificacao, eu perco".
# O botao LOG mostra quantos avisos ainda nao foram abertos, e o LOG lista
# todos ([[_caixa_entrada]]). Lido = a pessoa abriu o apontamento no LOG.

#: os botoes LOG das duas extensoes (lab e distribuicao)
BOTOES_LOG = ('CustomCtrl_%CustomCtrl_%PYAMBAR(lab)%Ferramentas%LOG',
              'CustomCtrl_%CustomCtrl_%PYAMBAR%Ferramentas%LOG')
_CHAVE_TEXTO = 'PYAMBAR_LOG_TEXTO_'


def pasta_da_caixa(ident):
    """A caixa desta pessoa ('' se o LOG ainda nao anotou a raiz)."""
    raiz = raiz_anotada()
    if not raiz or not ident:
        return ''
    return os.path.join(os.path.normpath(raiz), caixa.nome_de_pasta(ident))


def ler_caixa(ident):
    """{nome do arquivo: aviso} da caixa. Vazio se nao ha caixa."""
    pasta = pasta_da_caixa(ident)
    if not pasta or not os.path.isdir(pasta):
        return {}
    avisos = {}
    for nome in os.listdir(pasta):
        if nome.lower().endswith('.json'):
            aviso = _ler_json(os.path.join(pasta, nome), None)
            if isinstance(aviso, dict):
                avisos[nome] = aviso
    return avisos


def ler_lidos():
    return _ler_json(os.path.join(_APPDATA, caixa.ARQUIVO_LIDOS), [])


def marcar_lidos(nomes, existentes=None):
    """Da como lidos estes avisos. -> True se mudou alguma coisa."""
    lidos = ler_lidos()
    novos = [n for n in nomes if n.lower() not in
             set(x.lower() for x in lidos)]
    if not novos:
        return False
    lidos = lidos + novos
    if existentes is not None:
        lidos = caixa.manter_lidos(lidos, existentes)
    _gravar_json(os.path.join(_APPDATA, caixa.ARQUIVO_LIDOS), lidos)
    return True


def contar_nao_lidos(ident):
    return len(caixa.nao_lidos(list(ler_caixa(ident)), ler_lidos()))


def _itens_da_faixa(itens):
    """Todos os itens da faixa de opcoes, inclusive os de pilhas."""
    for item in itens:
        yield item
        filhos = getattr(item, 'Items', None)
        if filhos is not None:
            for filho in _itens_da_faixa(filhos):
                yield filho


def atualizar_botao(quantos):
    """'LOG' -> 'LOG · 2' nos botoes LOG da faixa de opcoes.

    Pelo AdWindows (a faixa do Revit). Se a Autodesk mudar a faixa, so o
    contador some: o erro vai para avisos.log, nunca para a tela.
    """
    try:
        from Autodesk.Windows import ComponentManager
        for aba in ComponentManager.Ribbon.Tabs:
            for painel in aba.Panels:
                for item in _itens_da_faixa(painel.Source.Items):
                    ident = getattr(item, 'Id', None) or ''
                    if ident not in BOTOES_LOG:
                        continue
                    chave = _CHAVE_TEXTO + ident
                    base = AppDomain.CurrentDomain.GetData(chave)
                    if base is None:
                        base = item.Text or 'LOG'
                        AppDomain.CurrentDomain.SetData(chave, base)
                    item.Text = caixa.rotulo_do_botao(base, quantos)
    except Exception:
        import traceback
        _anotar(u'contador do botao LOG falhou:\n' + traceback.format_exc())
