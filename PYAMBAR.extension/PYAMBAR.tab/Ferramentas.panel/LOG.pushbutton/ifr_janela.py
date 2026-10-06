# -*- coding: utf-8 -*-
"""
Interferências
Navega pelo relatório de interferência do Revit: lista agrupada, zoom, 3D e
status compartilhado.

POR QUE LER O HTML (decisão do Thiago, 16/09/2026)
--------------------------------------------------
> "A DETECÇÃO DO REVIT AO MEU VER É MUITO ROBUSTA"

A API não expõe o resultado da Interference Check; a detecção continua sendo
a do Revit, e esta janela lê o HTML do "Exportar...". Pesquisado antes: o
ClashFlag (pyRevit) detecta por conta própria e o ClashNavigator lê relatório
do Navisworks — nenhum lê o do Revit. Do ClashFlag veio a seleção de elemento
de vínculo (`CreateLinkReference` + `SetReferences`), verificada por MCP.

DECISÕES
--------
- Dois botões: "Na vista" (vista ativa) e "3D" (vista própria com caixa).
- Status num JSON ao lado do HTML (`ifr_disco`): o time vê, o modelo não é
  tocado.
- Recarregar depois de reexportar mostra o que SAIU do relatório.

v1.1 — AGRUPAR COMO O REVIT E FECHAR GRUPO (16/09/2026)
-------------------------------------------------------
> "OS FILTROS PODERIAM SEGUIR O MESMO DESSE EXEMPLO... PARA FICAR MENOS
>  POLUÍDO PODE USAR ESSE SISTEMA DE FECHAR GRUPO"

- "Agrupar por": Categoria A › B (o do Revit), B › A, ou Categoria A ›
  Elemento A (o tubo com N conflitos). Substitui o combo de categoria.
- Grupos começam fechados; clique no cabeçalho (ou → ←) abre e fecha. Com
  texto na busca, tudo abre.
- "Ao escolher" navega só no CONFLITO: clicar num grupo de 100 conflitos não
  joga a 3D numa caixa do tamanho do prédio. No grupo, os botões continuam.
- Marcar status num grupo com mais de 10 conflitos pede confirmação.

v1.2 — O GRUPO NAVEGA E O ELEMENTO A VOLTA (16/09/2026)
------------------------------------------------------
> "COMO ESTAVA ANTES ESTAVA BOM PELO GRUPO... NAVEGA PARA O GRUPO INTEIRO E
>  SE ABRE NAVEGA PARA O ELEMENTO TAMBÉM"

- Escolher um grupo navega para todos os elementos dele (a restrição da v1.1
  saiu); escolher um conflito navega para os dois elementos.
- "Agrupar por" ganhou "Elemento A" (o da v1.0, agora recolhível) e
  "Categoria A › Categoria B › Elemento A".

v1.3 — SANFONA (16/09/2026)
---------------------------
> "QUANDO CLICO NO PRÓXIMO FECHA O ATUAL E ABRE O PRÓXIMO — O MESMO VALE
>  PARA AS SETAS E PRÓXIMO PENDENTE"

Só fica aberta a cadeia até o item atual (`Snippets._interferencia.cadeia`):
abrir um grupo fecha os outros, menos os pais; ‹ › e "Próxima pendente"
fecham o caminho do anterior e abrem o do novo. "Expandir tudo" continua
abrindo tudo até o próximo clique.

v1.4 — A SETA ANDA DE GRUPO (16/09/2026)
----------------------------------------
> "SETA DO PRÓXIMO DEVE IR PARA O PRÓXIMO GRUPO, NÃO ELEMENTO"

‹ › vão ao grupo vizinho no mesmo nível (atravessando os pais); com um
conflito selecionado, ao grupo vizinho do dele. O grupo abre (sanfona) e é
navegado inteiro. "Próxima pendente" continua indo ao conflito.

v1.5 — VERIFICAÇÃO DE PASSES DE LAJE (18/09/2026)
-------------------------------------------------
> "preciso analisar se todos os passes de laje estão no eixo do tubo... a
>  ferramenta de interferência funcionaria bem para a análise, mas falta a
>  parte do relatório"

Botão "Verificar passes…": lajes (laje por laje — decisão dele), vínculos com
tubos e três medidas num diálogo; `ifr_passes` coleta e roda
`Snippets._passes_laje` dentro do ExternalEvent (só leitura). O resultado é
um `<modelo> - passes.json` ao lado do .rvt, aberto NESTA janela como fonte
nova: mesmo status, sanfona e navegação; achado de um lado só (passe sem
tubo, tubo sem passe) e a medida em cada linha. "Agrupar por" tem lista
própria (Laje › Regra padrão). Validado contra o CIQ antes de ligar: 29
passes acima de 1/4", 3 tubos sem passe no L2 — os números da medição.

v1.6 — DEPOIS DE MARCAR, O PRÓXIMO DO MESMO GRUPO (18/09/2026)
--------------------------------------------------------------
> "quando colocamos como resolvido ele fecha o grupo e vai para outro grupo;
>  o certo é ir de elemento a elemento"

O "próximo pendente" (depois de marcar e no botão) contava na ordem do HTML,
e o conflito seguinte do relatório costuma estar em outro grupo. Agora conta
na ordem da árvore (`ordem_da_arvore`): segue no mesmo grupo e só passa ao
seguinte quando ele acaba. Marcar um grupo inteiro segue para depois dele.

Na mesma versão, no relatório de passes: espessura automática por laje
(passes da laje > pisos dos vínculos > padrão), escolher as regras no
diálogo, diâmetro = 1 a 2 tamanhos WPS acima do tubo, "fora do eixo" numa
regra só (gravidade na medida) e as setas por ELEMENTO (no HTML continuam
por grupo, como na v1.4).

v1.7 — CORRIGIR NO VÍNCULO (21/09/2026)
---------------------------------------
> "conseguiria abrir o link e investigar... navegando para o tubo apontado"

Cada lado sabe o .rvt onde mora (`arquivo_de`); o evento acha o elemento no
modelo ABERTO — local, vinculado, ou avisa qual abrir. Abrir o WATER SUPPLY
e clicar no tubo seleciona o tubo lá. A linha do projeto se refaz ao voltar
para a janela. E o relatório de passes mora na pasta DAT ("deve ficar em DAT"):
o que estava ao lado do .rvt é movido na primeira carga, com o status.

v1.8 — O LOG DA OBRA, E A FERRAMENTA VIRA "LOG" (24/09/2026)
------------------------------------------------------------
> "o LogOcorrencias ficou pesado por causa da exportação para a planilha...
>  usar um arquivo de memória compartilhada dentro da pasta DAT, como o
>  relatório de interferências... deixar um recado para uma pessoa
>  específica, marcar elementos, navegar"

O LogOcorrencias (2.348 linhas) abria com DUAS chamadas HTTP síncronas a um
web app do Apps Script; agora é `DAT/LOG`, um arquivo por apontamento. Ler
é listar uma pasta. Fonte nova ('log') na mesma janela: o recado vira item
da mesma árvore (`Snippets._log_ocorrencias.como_registro`), com o mesmo
status (aberta=pendente), a mesma sanfona e a mesma navegação entre
modelos. Marcar ou responder grava NO arquivo da ocorrência, mesclando —
duas pessoas respondendo não se sobrescrevem. O alvo guarda UniqueId (o
ElementId é atalho) e o PONTO nas coordenadas do modelo dele: elemento
apagado e refeito, a região continua navegável.

v1.9 — O APONTAMENTO NÃO PRENDE O REVIT (24/09/2026)
----------------------------------------------------
> "NOVO APONTAMENTO DEVE SER NÃO MODAL... PODER SELECIONAR OS ELEMENTOS NÃO
>  SÓ DO PROJETO MAS DOS LINKS, MUDAR A SELEÇÃO ENQUANTO ESTÁ ESCREVENDO"
> "não tem como voltar para o log de interferência dos passes"

- A janela do apontamento virou MODELESS, com evento próprio: ela relê a
  seleção toda vez que você volta para ela, e tem o recorte de tela (o do
  Windows) num timer, sem travar enquanto espera.
- O cabeçalho ganhou o seletor **Lista**: LOG do projeto, os relatórios já
  abertos e "Abrir outro". Os botões levavam ao LOG e não traziam de volta.

v2.0 — A INTERFACE QUE NÃO SE EXPLICA (24/09/2026)
--------------------------------------------------
> "a interface tem que ser muito fluida, moderna, de uma forma que o usuário
>  não tenha que pensar como usar"

O que o uso real mostrou: o seletor "Lista" num combo era invisível (ele não
achava o caminho de volta para o relatório), o filtro num combo escondia o
estado (lista vazia com 5 resolvidos e nenhuma explicação — print de 24/09),
e a lista não dizia quem escreveu nem quando.

- ABAS no topo: LOG do projeto | Interferências | Passes de laje. A lista que
  existe é a que está marcada; sem relatório, a aba explica como obter um.
- CHIPS no lugar do combo de filtro — o estado fica à vista, num clique:
  Para mim (só no LOG), Abertos, Resolvidos, Todos, Saíram (só nos
  relatórios). Padrão do Newforma Konekt/BIM trackers: filtro no topo da
  lista e "atribuídas a mim" de um clique.
- ESTADO VAZIO que ensina e oferece a saída, em vez de lista muda.
- A linha diz QUEM e QUANDO ("thiago · há 2 h") e mostra a MINIATURA do
  recorte; o painel abre a imagem no Windows com um clique.

A lógica (leitura, chave, registro, filtro, árvore, próxima pendente) está em
`Snippets._interferencia`, testada em CPython. Este arquivo só costura.

A janela mora num MÓDULO, não no script.py ([[api-pyrevit-motor]]).

VERSAO: 2.0
AUTOR: Thiago Barreto Sobral Nunes
"""
import os
import sys
import traceback
from datetime import datetime

import clr
clr.AddReference('System')          # Uri, Diagnostics: não vêm de graça
clr.AddReference('PresentationCore')
clr.AddReference('PresentationFramework')
clr.AddReference('WindowsBase')
# .NET 8: o FileSystemWatcher (vigia da obra, v3.2) mora numa DLL própria
try:
    clr.AddReference('System.IO.FileSystem.Watcher')
except Exception:
    clr.AddReference('System')

SCRIPT_DIR = os.path.dirname(__file__)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
LIB_PATH = os.path.normpath(
    os.path.join(SCRIPT_DIR, '..', '..', '..', 'lib'))
if LIB_PATH not in sys.path:
    sys.path.insert(0, LIB_PATH)

from System import Action
from System import DateTime
from System import Guid
from System import TimeSpan
from System import Uri
from System.IO import FileSystemWatcher, NotifyFilters
from System.Threading import Thread, ThreadStart
from System.Windows.Threading import DispatcherTimer
from System.Windows import FontWeights, Visibility
from System.Windows.Media.Imaging import (
    BitmapCacheOption,
    BitmapImage,
)
from System.Windows.Controls import ContextMenu, ItemsControl, MenuItem
from System.Windows.Media import BrushConverter

from pyrevit import forms, script, HOST_APP
from pyrevit.forms import WPFWindow

from Snippets._clash import orientar
from Snippets._interferencia import (
    CAT_A,
    CAT_B,
    ELEM_A,
    F_PENDENTES,
    F_SAIRAM,
    F_RESOLVIDOS,
    F_TODOS,
    IGNORAR,
    PENDENTE,
    RESOLVIDO,
    SEPARADOR,
    achatar,
    agrupamentos,
    arquivo_de,
    arquivos_do_registro,
    arvore,
    cadeia,
    caminho_de,
    caminhos_ate,
    chave_do_lado,
    chaves_filtradas,
    contagem,
    grupo_vizinho,
    grupos_no_nivel,
    indice_do_agrupamento,
    ler_relatorio,
    ler_relatorio_passes,
    marcar,
    mesmo_projeto,
    nome_do_arquivo,
    ordem_da_arvore,
    proxima_pendente,
    sincronizar,
    todos_os_caminhos,
)
from Snippets._espelho import (
    achar_relatorio,
    origem_do_conflito,
    sincronizar_registro,
)
from Snippets import _caixa_entrada as caixa
from Snippets._log_obra import caminhos_existentes, modelos_do_apontamento
from Snippets import _repositorio as repo
from Snippets._log_equipe import nome_de as nome_de_pessoa
from Snippets._log_equipe import nomes as nomes_da_equipe
from Snippets._log_ocorrencias import (
    ABERTA,
    acrescentar_para,
    DA_JANELA,
    quando_relativo,
    so_para,
    como_registro,
    mudar_status,
    nova_ocorrencia,
    novidades,
    novo_id,
    ordem_do_log,
    responder,
    responder_a,
    e_do_autor,
    separar_nomes,
)
from Snippets._passes_laje import polegadas_texto

from Snippets import _vigia_caixa

import ifr_disco
import log_disco
import log_tempos
from ifr_evento import NOME_3D, evento, handler
from ifr_modelo import arquivo_do_modelo, caminho_do_modelo

AO_ESCOLHER = [('nada', u'Nada'), ('vista', u'Na vista'), ('3d', u'3D')]
#: print no comentário (v2.5) — mesmos tempos do "Novo apontamento"
INTERVALO_RECORTE = 700     # ms entre olhadas no clipboard
TENTATIVAS_RECORTE = 45     # ~30 s de espera pelo recorte
ESPERA_TELA = 350           # ms para a janela sair da tela antes da foto
#: folga em PES em volta dos elementos no zoom (v2.3, pedido do Thiago:
#: "tem como regular a quantidade de zoom quando movemos na vista?"). 2' era
#: fixo — perto demais para achar o contexto, longe demais para detalhe.
ZOOMS = [(0.5, u'Colado'), (2.0, u'Perto'), (6.0, u'Médio'),
         (15.0, u'Longe'), (40.0, u'Ambiente')]
ZOOM_PADRAO = 2.0
#: a caixa de corte da 3D precisa de mais ar que o zoom da planta
FATOR_CAIXA = 1.5
CONFIRMAR_ACIMA_DE = 10
#: o botão LOG nas duas extensões — o clique no balão o reabre
BOTOES_LOG = ('CustomCtrl_%CustomCtrl_%PYAMBAR(lab)%Ferramentas%LOG',
              'CustomCtrl_%CustomCtrl_%PYAMBAR%Ferramentas%LOG')
#: Entrega 2 (05/10/2026) — a janela aberta se atualiza sozinha. Espera
#: este tempo depois da ÚLTIMA mudança na pasta para juntar várias numa só
#: recarga (o Drive grava .tmp, troca, muda a data...).
ESPERA_DISCO = 2000         # ms
#: o que a própria janela acabou de gravar volta como evento: ignora
SILENCIO_APOS_CARGA = 3.0   # s
MAX_LINHAS_B = 25

COR = {
    PENDENTE: '#D9901A',
    RESOLVIDO: '#2E9D5B',
    IGNORAR: '#8A94A3',
    'saiu': '#2969B0',
}
ROTULO = {PENDENTE: u'pendente', RESOLVIDO: u'resolvido', IGNORAR: u'ignorado',
          'saiu': u'saiu do relatório'}
SETA_ABERTA = u''
SETA_FECHADA = u''
_ICONE = {
    'info': (u'', '#8A94A3'),
    'ok': (u'', '#2E9D5B'),
    'aviso': (u'', '#D9901A'),
    'erro': (u'', '#C0392B'),
}
_PINCEL = BrushConverter()


def agora():
    return datetime.now().strftime('%Y-%m-%dT%H:%M:%S')


def usuario():
    """Quem está mexendo — o usuário do Revit, sem login nenhum."""
    try:
        return HOST_APP.username or os.environ.get('USERNAME', '') or ''
    except Exception:
        return os.environ.get('USERNAME', '') or ''


def _sufixo():
    """4 caracteres para o id da ocorrência/mensagem (o snippet é puro e
    não inventa aleatório)."""
    return str(Guid.NewGuid()).replace('-', '')[:4]


def protegido(metodo):
    """WPF engole exceção de handler: sem isto o clique falha calado."""
    def envolvido(self, sender, args):
        try:
            return metodo(self, sender, args)
        except Exception as erro:
            try:
                self.mostrar_status(u'Erro em {}: {}'.format(
                    metodo.__name__, erro), 'erro')
            finally:
                script.get_output().print_md('```\n{}\n```'.format(
                    traceback.format_exc()))
    envolvido.__name__ = metodo.__name__
    return envolvido


def rotulo_do_lado(lado):
    """Três linhas: 'Categoria · ID n', a descrição e a origem."""
    origem = lado.get('vinculo') or u'este projeto'
    return u'{} · ID {}\n{}\n{}'.format(lado.get('categoria', ''), lado['id'],
                                        lado.get('descricao', ''), origem)


def _obra_curta(pasta):
    """'C10-SAGEWOOD CORP › IQ LUX' — o caminho de rede inteiro não cabe.

    Pula as pastas de serviço (DAT, LOG, 03-MODELING) e mostra as duas que
    identificam a obra para quem olha.
    """
    partes = [p for p in (pasta or '').replace('/', '\\').split('\\') if p]
    uteis = [p for p in partes
             if p.upper() not in ('DAT', 'LOG') and '-MODELING' not in
             p.upper()]
    return u' › '.join(uteis[-2:]) if uteis else (pasta or u'(sem pasta)')


def curto(lado):
    descricao = (lado.get('descricao') or u'').strip()
    if not descricao:
        return u'ID {}'.format(lado['id'])
    return u'{} · ID {}'.format(descricao, lado['id'])


def situacao(item):
    if not item.get('no_relatorio', True):
        return 'saiu'
    return item.get('status', PENDENTE)


class Fala(object):
    """Uma bolha da conversa — os nomes com maiúscula são os do binding.

    A PRIMEIRA fala é o apontamento (âmbar, letra maior); as respostas vêm
    abaixo, cinza e recuadas, na ordem em que foram escritas.
    """

    def __init__(self, quem, quando, texto, pedido=False, para='',
                 imagem=None):
        self.Quem = u'{} · {}{}'.format(
            quem or u'alguém', quando_relativo(quando, agora()),
            u' · para {}'.format(para) if pedido and para else u'')
        self.Texto = (texto or u'(sem texto)').strip()
        # v2.5: a resposta pode ter print. None (e não '') quando não tem:
        # string vazia no Source da Image vira erro de binding
        self.Imagem = imagem if imagem and os.path.exists(imagem) else None
        self.ImgVis = 'Visible' if self.Imagem else 'Collapsed'
        self.Tamanho = 15.0 if pedido else 13.0
        self.Fundo = '#FFF8E6' if pedido else '#F4F6F9'
        self.Borda = '#F0D9A0' if pedido else '#E3E7ED'
        # folga à direita: a barra de rolagem do painel passa por ali
        self.Recuo = '0,0,4,8' if pedido else '14,0,4,8'


class OpcaoAviso(object):
    """Um aviso em "Avisos recebidos" (v3.4) — os nomes com maiúscula são
    os do binding. Não lido em negrito."""

    def __init__(self, nome, aviso, lido):
        self.nome = nome
        self.aviso = aviso
        titulo, obra = caixa.resumo_do_aviso(aviso)
        self.Titulo = titulo
        self.Detalhe = u'{} · {}'.format(
            obra or u'—', quando_relativo(aviso.get('quando'), agora()))
        self.Texto = aviso.get('texto') or u''
        self.Dica = self.Texto
        self.Peso = 'Normal' if lido else 'SemiBold'


class OpcaoRelatorio(object):
    """Um relatório do repositório no dropdown (v3.1): o nome curto, quem
    gerou e quando, e o escopo inteiro no ToolTip."""

    def __init__(self, meta):
        self.meta = meta
        self.Nome = meta['nome']
        self.Detalhe = repo.detalhe(meta,
                                    lambda q: quando_relativo(q, agora()))
        self.Dica = u'{}\nGerado por {} · {}'.format(
            meta['descricao'], meta['autor'],
            (meta.get('gerado_em') or '').replace('T', ' ')[:16])


class Linha(object):
    """Uma linha da lista — os nomes com maiúscula são os do binding."""

    def __init__(self, dados, registro, niveis):
        self.tipo = dados['tipo']
        self.Recuo = '{},0,0,0'.format(18 * dados['profundidade'])
        if self.tipo == 'grupo':
            no = dados['no']
            self.QuemQuando = ''
            self.QuemVis = 'Collapsed'
            self.Miniatura = None
            self.MiniVis = 'Collapsed'
            self.no = no
            self.caminho = no['caminho']
            self.chaves = list(no['chaves'])
            self.aberto = dados['aberto']
            self.Seta = SETA_ABERTA if self.aberto else SETA_FECHADA
            self.Peso = 'SemiBold'
            situacoes = [situacao(registro['conflitos'][k])
                         for k in self.chaves]
            if no['nivel'] == ELEM_A:
                lado = no['item']['a']
                self.Titulo = u'{} · {}'.format(lado.get('categoria', ''),
                                                lado.get('descricao', ''))
                self.Subtitulo = u'ID {}{}'.format(
                    lado['id'], u' · ' + lado['vinculo']
                    if lado.get('vinculo') else '')
            else:
                self.Titulo = no['valor'] or u'(sem categoria)'
                self.Subtitulo = ''
            pendentes = situacoes.count(PENDENTE)
            self.Direita = u'{}{}'.format(
                len(self.chaves), u' · {} pend.'.format(pendentes)
                if pendentes and pendentes != len(self.chaves) else '')
            predominante = PENDENTE if PENDENTE in situacoes else situacoes[0]
            self.Cor = COR.get(predominante, COR[PENDENTE])
            self.SubVis = 'Visible' if self.Subtitulo else 'Collapsed'
            return

        k = dados['chave']
        item = registro['conflitos'][k]
        self.QuemQuando = ''
        self.QuemVis = 'Collapsed'
        self.Miniatura = None
        self.MiniVis = 'Collapsed'
        log = item.get('log')
        if log:
            # quem e quando, na lista: "thiago · há 2 h" (v2.0)
            self.QuemQuando = u'{} · {}'.format(
                dados.get('quem') or log.get('autor', ''),
                quando_relativo(log.get('criado_em'), agora()))
            self.QuemVis = 'Visible'
            caminho = dados.get('miniatura')
            if caminho:
                self.Miniatura = caminho
                self.MiniVis = 'Visible'
        self.no = None
        self.caminho = None
        self.chaves = [k]
        self.aberto = False
        self.Seta = ''
        self.Peso = 'Normal'
        self.SubVis = 'Visible'
        a, b = item['a'], item.get('b')
        if b and CAT_B in niveis and (CAT_A not in niveis or
                                      niveis.index(CAT_B) <
                                      niveis.index(CAT_A)):
            # "Categoria B › Categoria A" (01/10/2026): a folha fala na
            # mesma ordem do grupo — duto × tubo, não tubo × duto
            a, b = b, a
        if item.get('regra'):
            # achado de verificação própria (v1.5): a medida é o que importa
            self.Titulo = u'{} · {}'.format(a.get('categoria', ''), curto(a))
            origem_a = a.get('vinculo') or u'este projeto'
            self.Subtitulo = item.get('medida') or ''
            lados = item.get('lados') or []
            if len(lados) > 2:
                # apontamento com N elementos: contar vale mais que citar dois
                self.Subtitulo += u' · {} elementos'.format(len(lados))
            elif b:
                self.Subtitulo += u' · × {} · {}'.format(
                    curto(b), b.get('vinculo') or u'este projeto')
            elif a.get('vinculo'):
                self.Subtitulo += u' · {}'.format(origem_a)
        elif ELEM_A in niveis:
            origem_b = b.get('vinculo') or u'este projeto'
            # o elemento A já é o grupo: a folha é o B
            self.Titulo = u'{} · {}'.format(b.get('categoria', ''),
                                            b.get('descricao', ''))
            self.Subtitulo = u'ID {} · {}'.format(b['id'], origem_b)
        else:
            self.Titulo = curto(a)
            self.Subtitulo = u'× {} · {}'.format(
                curto(b), b.get('vinculo') or u'este projeto')
        comentario = item.get('comentario') or ''
        if comentario:
            self.Subtitulo += u' · “{}”'.format(comentario)
        self.Direita = ROTULO.get(situacao(item), situacao(item))
        self.Cor = COR.get(situacao(item), COR[PENDENTE])
        if dados.get('novo'):
            # v2.5 — notificacao: o que chegou para mim desde a ultima vez
            self.Titulo = u'NOVO · ' + self.Titulo
            self.Peso = 'SemiBold'
            self.Direita = u'novo · ' + self.Direita


class InterferenciasWindow(WPFWindow):

    def __init__(self, uiapp):
        WPFWindow.__init__(self, os.path.join(SCRIPT_DIR, 'ui.xaml'))
        self.uiapp = uiapp
        self.caminho = None
        self.registro = {'conflitos': {}}
        self.ordem = []
        self.nos = []
        self.linhas = []
        self.abertos = set()
        self.atual = None
        self._montando = False
        self.fonte = 'html'
        self._relatorio = None
        self.itens_log = {}
        self._fontes = [None]
        self.pasta_log = ''
        self._delta = {}
        #: cada carga ganha um número; resposta de leitura antiga é jogada
        #: fora (o usuário trocou de aba enquanto o disco respondia)
        self._geracao = 0
        self._lendo = False
        #: aberto pelo balão num apontamento de OUTRA obra: a janela fica
        #: nela até a pessoa trocar de aba (v3.2)
        self._obra_fixa = False
        #: v3.4 — a caixa de entrada: {arquivo: aviso} e os já abertos
        self._avisos = {}
        self._lidos = []
        self._meu_nome = ''
        self._equipe = None
        self._perguntei_nome = False
        self._erro_log = None
        # v3.1 — o repositório de relatórios do projeto
        self.metas = []
        self._migrados = set()
        self.prefs = ifr_disco.preferencias()

        handler.janela = self
        self.Closed += self.ao_fechar
        self.Activated += self.ao_ativar
        self.ConflitosList.PreviewMouseLeftButtonUp += self.ao_clique_na_lista
        self.ConflitosList.KeyDown += self.ao_tecla_na_lista
        self.ConversaLista.PreviewMouseLeftButtonUp += self.ao_clicar_conversa
        # v2.5: print no comentário — recorte (espera o clipboard sem travar)
        # e tela inteira (a janela sai da frente na hora da foto)
        self._anexo = None
        self._novos = set()
        self._tentativas_recorte = 0
        self._timer_recorte = DispatcherTimer()
        self._timer_recorte.Interval = TimeSpan.FromMilliseconds(
            INTERVALO_RECORTE)
        self._timer_recorte.Tick += self.ao_conferir_recorte
        self._timer_tela = DispatcherTimer()
        self._timer_tela.Interval = TimeSpan.FromMilliseconds(ESPERA_TELA)
        self._timer_tela.Tick += self.ao_tirar_foto
        # Entrega 2: vigia das pastas da obra + espera para juntar eventos
        self._vigias = []
        self._pastas_vigiadas = ()
        self._ultima_carga = DateTime.Now
        self._timer_disco = DispatcherTimer()
        self._timer_disco.Interval = TimeSpan.FromMilliseconds(ESPERA_DISCO)
        self._timer_disco.Tick += self.ao_mudar_no_disco

        self._montando = True
        self.montar_agrupamentos()
        self.AoEscolherCombo.ItemsSource = [r for _, r in AO_ESCOLHER]
        # padrao 'vista' (v3.0): so seleciona e da zoom. O '3d' cria/altera
        # a vista 'Interferencias 3D' — uma Transaction no modelo a cada
        # clique, sem a pessoa pedir. Quem ja escolheu 3D continua com 3D.
        modo = self.prefs.get('ao_escolher', 'vista')
        self.AoEscolherCombo.SelectedIndex = next(
            (i for i, (m, _) in enumerate(AO_ESCOLHER) if m == modo), 2)
        self.ZoomCombo.ItemsSource = [r for _, r in ZOOMS]
        folga = self.prefs.get('zoom', ZOOM_PADRAO)
        self.ZoomCombo.SelectedIndex = next(
            (i for i, (f, _) in enumerate(ZOOMS) if f == folga),
            next(i for i, (f, _) in enumerate(ZOOMS) if f == ZOOM_PADRAO))
        self._montando = False

        self.mostrar_detalhe()
        # SEMPRE abre no LOG do projeto (pedido do Thiago, 24/09/2026): o
        # relatório continua guardado em `recentes` e volta por um clique na
        # aba — abrir no último relatório fazia a ferramenta começar no lugar
        # errado todo dia.
        ifr_disco.realocar(self.prefs.get('ultimo') or '')
        self.carregar_log()

    def ao_fechar(self, sender, args):
        sys.modules[__name__].__dict__['_JANELA_ABERTA'] = None
        handler.janela = None
        self.parar_vigias()

    ABAS = [('AbaLog', 'log'), ('AbaInterferencias', 'html'),
            ('AbaPasses', 'passes')]
    #: o clash mora na aba de interferências (decisão do Thiago, 30/09)
    ABA_DA_FONTE = {'clash': 'html'}

    @protegido
    def ao_aba_log(self, sender, args):
        self.ir_para_aba('log')

    @protegido
    def ao_aba_interferencias(self, sender, args):
        self.ir_para_aba('html')

    @protegido
    def ao_aba_passes(self, sender, args):
        self.ir_para_aba('passes')

    def ir_para_aba(self, fonte):
        """Aba em vez de combo escondido: a lista que existe é a que está
        marcada (v2.0)."""
        if self._montando:
            return
        self._obra_fixa = False
        self.OutraObraPanel.Visibility = Visibility.Collapsed
        if fonte == 'log':
            self.carregar_log()
            return
        # v3.1 (Thiago, 30/09/2026): "quando o usuário abre ... o relatório
        # carregado seja o último que ELE gerou" — o meu último nesta aba;
        # sem ele, o mais recente do projeto
        self.atualizar_repositorio()
        escolhido = repo.escolher(
            self.metas, fonte,
            meu_ultimo=(self.prefs.get('ultimo_por_aba') or {}).get(fonte))
        # SÓ o repositório do projeto aberto (02/10/2026): o fallback para
        # os "recentes" da máquina abria relatório de OUTRA obra e, achando
        # que todo .json era de passes, travava a aba Passes no clash
        if escolhido:
            self.carregar(escolhido['caminho'])
        else:
            self.fonte = fonte
            self.RelatorioCombo.ItemsSource = []
            self.marcar_aba()
            self.mostrar_vazio_sem_relatorio(fonte)

    #: a ação principal do topo é a DA ABA (v2.1, pedido do Thiago): apontar
    #: no LOG, abrir o relatório de interferências, verificar os passes
    #: v2.4: a aba de interferências tem DUAS ações — verificar (nosso) e
    #: abrir o HTML exportado do Revit
    ACAO_DA_ABA = {'log': ('NovoBtn',), 'html': ('ClashBtn', 'AbrirBtn'),
                   'clash': ('ClashBtn', 'AbrirBtn'), 'passes': ('PassesBtn',)}
    BOTOES_DE_ACAO = ('NovoBtn', 'ClashBtn', 'AbrirBtn', 'PassesBtn')

    def marcar_aba(self):
        eram = self._montando
        self._montando = True
        try:
            atual = self.ABA_DA_FONTE.get(self.fonte, self.fonte)
            for nome, fonte in self.ABAS:
                getattr(self, nome).IsChecked = (fonte == atual)
            visiveis = self.ACAO_DA_ABA.get(self.fonte, ('NovoBtn',))
            for nome in self.BOTOES_DE_ACAO:
                getattr(self, nome).Visibility = (
                    Visibility.Visible if nome in visiveis
                    else Visibility.Collapsed)
            # relatório: o dropdown do repositório no lugar do título
            combo = self.fonte != 'log' and bool(
                self.RelatorioCombo.ItemsSource and
                list(self.RelatorioCombo.ItemsSource))
            self.RelatorioCombo.Visibility = (
                Visibility.Visible if combo else Visibility.Collapsed)
            self.ArquivoLabel.Visibility = (
                Visibility.Collapsed if combo else Visibility.Visible)
        finally:
            self._montando = eram

    def recentes(self):
        """Os relatórios já abertos, o mais novo primeiro (v1.8)."""
        return [c for c in (self.prefs.get('recentes') or [])
                if c and os.path.exists(c)]

    def lembrar_relatorio(self, caminho):
        recentes = [caminho] + [c for c in self.recentes()
                                if c.lower() != caminho.lower()]
        self.prefs['recentes'] = recentes[:6]

    def mostrar_vazio(self, n_na_lista, total):
        """Lista vazia nunca fica muda (v2.0): diz por que e oferece a saída."""
        if n_na_lista:
            self.VazioPanel.Visibility = Visibility.Collapsed
            self.ConflitosList.Visibility = Visibility.Visible
            return
        self.ConflitosList.Visibility = Visibility.Collapsed
        self.VazioPanel.Visibility = Visibility.Visible
        chip = self.chip_ativo()[0]
        if total and chip != 'ChipTodos':
            self.VazioTitulo.Text = u'Nada aqui com este filtro.'
            self.VazioTexto.Text = u'O projeto tem {} item(ns). Veja todos ou ' \
                                   u'limpe a busca.'.format(total)
            self._acao_vazio = 'todos'
            self.VazioBtn.Content = u'Ver todos'
        elif self.fonte == 'log':
            self.VazioTitulo.Text = u'Nenhum apontamento neste projeto.'
            self.VazioTexto.Text = u'Selecione elementos no Revit e registre o ' \
                                   u'primeiro apontamento. Ele fica na pasta ' \
                                   u'da obra, disponível para toda a equipe.'
            self._acao_vazio = 'novo'
            self.VazioBtn.Content = u'Novo apontamento'
        else:
            self.VazioTitulo.Text = u'Relatório sem itens.'
            self.VazioTexto.Text = u'Abra outro relatório ou rode a ' \
                                   u'verificação de passes.'
            self._acao_vazio = 'abrir'
            self.VazioBtn.Content = u'Abrir relatório…'

    def mostrar_vazio_sem_relatorio(self, fonte):
        self.ArquivoLabel.Text = u'Nenhum relatório neste projeto'
        self.ArquivoLabel.ToolTip = self.pasta_relatorios()
        self.ProjetoLabel.Text = u''
        self.NovidadesLabel.Text = u''
        self.ConflitosList.ItemsSource = []
        self.linhas = []
        self.ConflitosList.Visibility = Visibility.Collapsed
        self.VazioPanel.Visibility = Visibility.Visible
        if fonte in ('html', 'clash'):
            self.VazioTitulo.Text = u'Nenhum relatório de interferência aberto.'
            self.VazioTexto.Text = (
                u'Verifique agora, cruzando os modelos vinculados '
                u'que você escolher — ou abra um HTML exportado '
                u'pelo Revit.')
            self._acao_vazio = 'clash'
            self.VazioBtn.Content = u'Verificar interferências…'
        elif fonte == 'passes':
            self.VazioTitulo.Text = u'Nenhuma verificação de passes ainda.'
            self.VazioTexto.Text = u'Rode a verificação: passes de laje × ' \
                                   u'tubos verticais, laje por laje.'
            self._acao_vazio = 'passes'
            self.VazioBtn.Content = u'Verificar passes…'
        else:
            self.VazioTitulo.Text = u'Nenhum relatório de interferência aberto.'
            self.VazioTexto.Text = u'No Revit: Colaborar › Verificação de ' \
                                   u'interferência › Exportar… (HTML). ' \
                                   u'Depois abra o arquivo aqui.'
            self._acao_vazio = 'abrir'
            self.VazioBtn.Content = u'Abrir relatório…'

    @protegido
    def ao_vazio(self, sender, args):
        acao = getattr(self, '_acao_vazio', 'todos')
        if acao == 'todos':
            self.BuscaBox.Text = ''
            self.ao_chip(self.ChipTodos, args)
        elif acao == 'novo':
            self.ao_novo_apontamento(sender, args)
        elif acao == 'passes':
            self.ao_verificar_passes(sender, args)
        elif acao == 'clash':
            self.ao_verificar_clash(sender, args)
        else:
            self.ao_abrir(sender, args)

    @protegido
    def ao_abrir_imagem(self, sender, args):
        """A imagem do apontamento, no visualizador do Windows.

        `System.Diagnostics` exige `clr.AddReference('System')` no
        IronPython — e um import que falha no topo derruba a janela INTEIRA
        (foi o que aconteceu em 24/09). Por isso o import mora aqui, com
        alternativa: abrir uma imagem nunca pode impedir o LOG de abrir.
        """
        self._abrir_arquivo(getattr(self, '_imagem_atual', ''))

    def _abrir_arquivo(self, caminho):
        """Abre no programa padrão do Windows (o visualizador de fotos)."""
        if not (caminho and os.path.exists(caminho)):
            return
        try:
            clr.AddReference('System')
            from System.Diagnostics import Process
            Process.Start(caminho)
        except Exception as erro:
            try:
                os.startfile(caminho)
            except Exception:
                self.mostrar_status(u'Não foi possível abrir a imagem ({}). Local: '
                                    u'{}'.format(erro, caminho),
                                    'aviso')

    def chave_do_agrupar(self):
        """Uma escolha por fonte: HTML e passes têm listas diferentes."""
        return 'agrupar' if self.fonte == 'html' else 'agrupar_' + self.fonte

    def montar_agrupamentos(self):
        opcoes = agrupamentos(self.fonte)
        eram = self._montando
        self._montando = True
        try:
            self.AgruparCombo.ItemsSource = [r for _, r in opcoes]
            self.AgruparCombo.SelectedIndex = indice_do_agrupamento(
                opcoes, self.prefs.get(self.chave_do_agrupar()))
        finally:
            self._montando = eram

    # ------------------------------------------------------------ o Revit

    def doc(self):
        return self.uiapp.ActiveUIDocument.Document

    def usuario_atual(self):
        """Como EU assino o apontamento: o nome, não o ID do Revit."""
        return self.meu_nome()

    def usuario_id(self):
        """O ID do Revit — a chave estável da pessoa."""
        return usuario()

    def meu_nome(self):
        """'Thiago Nunes' — o ID enquanto ninguém se cadastrou."""
        if not self._meu_nome:
            self._meu_nome = log_disco.nome_do_usuario(self.pasta_log,
                                                       usuario())
        return self._meu_nome or usuario()

    def eu(self):
        """Meus dois nomes (ID e nome) — apontamento antigo gravou o ID."""
        return [a for a in (usuario(), self.meu_nome()) if a]

    def apresentar_se(self):
        """Na PRIMEIRA vez, pergunta o nome e cruza com o ID do Revit.

        Pedido do Thiago (24/09/2026): "meu ID é thiagonunesXNUJD mas eu
        escreveria Thiago Nunes". O cadastro vale para TODAS as obras — vai
        para o `equipe.json` da empresa ([[_log_equipe]]).
        """
        if self._perguntei_nome:
            return
        self._perguntei_nome = True
        ident = usuario()
        try:
            if not log_disco.precisa_se_apresentar(self.pasta_log, ident):
                return
            nome = forms.ask_for_string(
                default=u'', title=u'LOG — identificação',
                prompt=u'Usuário do Revit: "{}".\nInforme o nome que '
                       u'aparecerá nos apontamentos (ex.: Thiago Nunes).\n'
                       u'Esta identificação é solicitada uma única vez e '
                       u'vale para todas as obras.'.format(ident))
            if nome and nome.strip():
                log_disco.registrar_pessoa(self.pasta_log, ident,
                                           nome.strip(), agora())
                self._meu_nome = nome.strip()
                self._equipe = None     # o cadastro novo entra na próxima leitura
        except Exception as erro:
            print(u'LOG: não consegui cadastrar o nome ({})'.format(erro))

    def caminho_do_modelo(self):
        """O do CENTRAL quando houver: o arquivo local tem sufixo do usuário."""
        return caminho_do_modelo(self.doc())

    def mostrar_projeto(self):
        """A linha do projeto — refeita ao voltar para a janela (v1.7): o
        Thiago troca de modelo no Revit para corrigir no vínculo."""
        relatorio = self._relatorio
        if relatorio is None:
            return
        ativo = arquivo_do_modelo(self.doc())
        if relatorio['fonte'] == 'log':
            # o LOG é da OBRA: vale para qualquer modelo daquela pasta.
            # O caminho de rede inteiro não cabe — vai no ToolTip (v2.1).
            self.ProjetoLabel.Text = u'Modelo aberto: {}'.format(ativo)
            self.ProjetoLabel.ToolTip = self.pasta_log
            self.ProjetoLabel.Foreground = _PINCEL.ConvertFromString('#5B6675')
            return
        do_relatorio = nome_do_arquivo(relatorio['projeto'])
        if mesmo_projeto(relatorio['projeto'], self.caminho_do_modelo()) \
                is not False:
            texto = u'Projeto: {}'.format(do_relatorio or u'(sem cabeçalho)')
            cor = '#5B6675'
        elif self.caminho and ifr_disco.no_repositorio(self.caminho) and \
                os.path.normcase(os.path.dirname(self.caminho)) == \
                os.path.normcase(self.pasta_relatorios()):
            # relatório do repositório é da OBRA (05/10/2026): rodado a partir
            # de outro modelo da mesma pasta não é "outro projeto"
            texto = u'Relatório da obra · gerado a partir de {} · modelo ' \
                    u'aberto: {}'.format(do_relatorio or u'?', ativo)
            cor = '#5B6675'
        elif ativo.lower() in arquivos_do_registro(self.registro,
                                                   do_relatorio):
            texto = (u'Modelo aberto: {} (vínculo do relatório de {}). '
                     u'Elementos de outros modelos são localizados se '
                     u'estiverem vinculados a este.'.format(ativo, do_relatorio))
            cor = '#2969B0'
        else:
            texto = (u'Atenção: relatório de {}. O modelo aberto ({}) não '
                     u'faz parte deste relatório.'.format(do_relatorio,
                                                               ativo))
            cor = '#C0392B'
        if relatorio['fonte'] == 'passes':
            p = relatorio.get('parametros') or {}
            texto += u' · passes em {} · tolerância {} · gerado {}'.format(
                u', '.join(relatorio.get('lajes') or []) or u'—',
                polegadas_texto(p.get('tolerancia')),
                (relatorio.get('gerado_em') or '').replace('T', ' ')[:16])
        self.ProjetoLabel.Text = texto
        self.ProjetoLabel.Foreground = _PINCEL.ConvertFromString(cor)

    def ao_ativar(self, sender, args):
        try:
            # OUTRA OBRA (05/10/2026): a janela fica aberta entre projetos e
            # clicar no LOG só a traz para a frente — a lista continuava a da
            # obra anterior. Mudou a pasta do projeto: recarrega a aba atual
            if not self._montando and not self._obra_fixa and \
                    self.pasta_log and \
                    os.path.normcase(self.pasta_log) != os.path.normcase(
                        log_disco.pasta_do_log(self.caminho_do_modelo())):
                self.trocar_de_obra()
                return
            self.mostrar_projeto()
        except Exception as erro:
            self.mostrar_status(u'Não foi possível ler o modelo aberto: {}'.format(
                erro), 'aviso')

    def abrir_do_aviso(self):
        """O clique no balão pediu um apontamento: abre nele (v3.2).

        Apontamento de outra obra abre o LOG DELA — dá para ler e
        responder; navegar no modelo só com um modelo daquela obra aberto.
        """
        return self.abrir_aviso(_vigia_caixa.pedido_de_abrir())

    def abrir_aviso(self, pedido):
        """Abre o LOG no apontamento do aviso (balão ou "Avisos recebidos")."""
        if not pedido or not pedido.get('pasta_log'):
            return False
        pasta = pedido['pasta_log']
        if not os.path.isdir(pasta):
            self.mostrar_status(u'A pasta do apontamento não está acessível: '
                                u'{}'.format(pasta), 'aviso')
            return False
        da_obra_aberta = os.path.normcase(pasta) == os.path.normcase(
            log_disco.pasta_do_log(self.caminho_do_modelo()))
        self._obra_fixa = not da_obra_aberta
        self.carregar_log(pasta=pasta)
        # o item pode estar num grupo recolhido ou fora do filtro:
        # `ir_para_chave` abre o caminho até ele
        if pedido.get('id') in self.registro.get('conflitos', {}):
            self.ir_para_chave(pedido['id'], navegar=da_obra_aberta)
        self.mostrar_outra_obra()
        return True

    # ---------------------------------------- avisos recebidos (v3.4)

    def nao_lidos(self):
        return caixa.nao_lidos(list(self._avisos), self._lidos)

    def mostrar_contador_de_avisos(self):
        """'Avisos · 2' no topo da janela e 'LOG · 2' na faixa do Revit."""
        quantos = len(self.nao_lidos())
        self.AvisosLabel.Text = caixa.rotulo_do_botao(u'Avisos', quantos)
        self.AvisosLabel.FontWeight = FontWeights.SemiBold if quantos \
            else FontWeights.Normal
        _vigia_caixa.atualizar_botao(quantos)

    @protegido
    def ao_abrir_avisos(self, sender, args):
        self._avisos = _vigia_caixa.ler_caixa(usuario())
        self._lidos = _vigia_caixa.ler_lidos()
        pendentes = set(self.nao_lidos())
        opcoes = [OpcaoAviso(nome, self._avisos[nome], nome not in pendentes)
                  for nome in sorted(self._avisos, reverse=True)]
        eram = self._montando
        self._montando = True
        try:
            self.AvisosLista.ItemsSource = opcoes
            self.AvisosLista.SelectedIndex = -1
        finally:
            self._montando = eram
        self.AvisosVazio.Visibility = Visibility.Collapsed if opcoes \
            else Visibility.Visible
        self.mostrar_contador_de_avisos()
        self.AvisosPopup.IsOpen = True

    @protegido
    def ao_escolher_aviso(self, sender, args):
        if self._montando:
            return
        opcao = self.AvisosLista.SelectedItem
        if opcao is None:
            return
        self.AvisosPopup.IsOpen = False
        if not self.abrir_aviso(opcao.aviso):
            self.mostrar_status(u'O apontamento deste aviso não foi '
                                u'encontrado.', 'aviso')

    def marcar_aviso_lido(self, item):
        """Abrir o apontamento dá como lidos os avisos dele."""
        log = self.log_do_item(item) or {}
        nomes = [n for n in caixa.avisos_do_apontamento(self._avisos,
                                                        log.get('id'))
                 if n in set(self.nao_lidos())]
        if not nomes:
            return
        try:
            _vigia_caixa.marcar_lidos(nomes, list(self._avisos))
            self._lidos = self._lidos + nomes
            self.mostrar_contador_de_avisos()
        except Exception as erro:
            print(u'LOG: aviso não marcado como lido ({})'.format(erro))

    # ------------------------------------- LOG de outra obra (v3.3)

    def mostrar_outra_obra(self):
        """A faixa que aparece quando o LOG mostra outra obra (06/10/2026):
        abrir o modelo do apontamento ou voltar à obra do modelo ativo."""
        if not self._obra_fixa or self.fonte != 'log':
            self.OutraObraPanel.Visibility = Visibility.Collapsed
            return
        ativa = log_disco.pasta_do_log(self.caminho_do_modelo())
        self.OutraObraLabel.Text = (
            u'LOG da obra {}. O modelo ativo ({}) pertence a outra obra: '
            u'para localizar os elementos, abra o modelo do apontamento.'
            .format(_obra_curta(self.pasta_log),
                    arquivo_do_modelo(self.doc())))
        self.VoltarObraLabel.Text = u'Voltar para {}'.format(
            _obra_curta(ativa))
        self.VoltarObraBtn.ToolTip = ativa
        modelos = self.modelos_do_atual()
        self.AbrirModeloBtn.IsEnabled = bool(modelos)
        if len(modelos) == 1:
            self.AbrirModeloLabel.Text = u'Abrir {}'.format(modelos[0][0])
        elif modelos:
            self.AbrirModeloLabel.Text = u'Abrir modelo ({})'.format(
                len(modelos))
        else:
            self.AbrirModeloLabel.Text = u'Abrir modelo'
        self.AbrirModeloBtn.ToolTip = (
            u'\n'.join(c for _, c in modelos) if modelos else
            u'Selecione um apontamento com elementos de um modelo desta obra.')
        self.OutraObraPanel.Visibility = Visibility.Visible

    def modelos_do_atual(self):
        """[(nome, caminho)] dos modelos do apontamento escolhido que
        existem na pasta da obra."""
        if self.atual is None or self.atual.tipo == 'grupo':
            return []
        item = self.registro['conflitos'].get(self.atual.chaves[0]) or {}
        log = self.log_do_item(item) or {}
        return caminhos_existentes(self.pasta_log,
                                   modelos_do_apontamento(log))

    @protegido
    def ao_abrir_modelo(self, sender, args):
        modelos = self.modelos_do_atual()
        if not modelos:
            self.mostrar_status(u'Nenhum modelo deste apontamento foi '
                                u'encontrado na pasta da obra.', 'aviso')
            return
        if len(modelos) == 1:
            self.pedir_modelo(modelos[0][1])
            return
        # mais de um modelo: o usuário escolhe
        menu = ContextMenu()
        for nome, caminho in modelos:
            opcao = MenuItem()
            opcao.Header = nome
            opcao.ToolTip = caminho
            opcao.Tag = caminho
            opcao.Click += self.ao_escolher_modelo
            menu.Items.Add(opcao)
        menu.PlacementTarget = self.AbrirModeloBtn
        menu.IsOpen = True

    @protegido
    def ao_escolher_modelo(self, sender, args):
        self.pedir_modelo(sender.Tag)

    def pedir_modelo(self, caminho):
        self.mostrar_status(u'Abrindo {}...'.format(os.path.basename(caminho)))
        handler.pedido = ('abrir_modelo', caminho)
        evento.Raise()

    def modelo_aberto(self, nome):
        """Chamado pelo evento depois que o modelo abriu: a obra agora é
        a do modelo ativo, e o apontamento escolhido é localizado."""
        ativa = log_disco.pasta_do_log(self.caminho_do_modelo())
        if os.path.normcase(ativa) == os.path.normcase(self.pasta_log):
            self._obra_fixa = False
        self.mostrar_outra_obra()
        self.mostrar_projeto()
        self.mostrar_status(u'{} aberto.'.format(nome), 'ok')
        if self.atual is not None and not self._obra_fixa:
            self.navegar(self.modo_ao_escolher()
                         if self.modo_ao_escolher() != 'nada' else 'vista')

    @protegido
    def ao_voltar_obra(self, sender, args):
        self.ir_para_aba('log')

    def ligar_avisos(self):
        """Liga o vigia da caixa se o startup não ligou (primeira vez que
        o LOG abre numa obra do servidor). Não troca um vigia que já existe."""
        try:
            _vigia_caixa.ligar(self.uiapp, BOTOES_LOG)
        except Exception as erro:
            print(u'LOG: avisos não ligaram ({})'.format(erro))

    def trocar_de_obra(self):
        """Recarrega a aba aberta com o LOG/relatórios da obra do modelo ativo."""
        aba = 'log' if self.fonte == 'log' else self.aba_da_fonte(self.fonte)
        self.caminho = None
        self.metas = []
        self.abertos = set()
        # já na obra nova: aba sem relatório não passa por `carregar`, e a
        # pasta velha faria cada Activated recarregar de novo
        self.pasta_log = log_disco.pasta_do_log(self.caminho_do_modelo())
        self.ir_para_aba(aba)
        if not self.NovidadesLabel.Text:
            self.NovidadesLabel.Text = u'O modelo ativo mudou de obra; a lista ' \
                                       u'foi atualizada para a obra correspondente.'

    # ------------------------------------------------------------- rodapé

    def mostrar_status(self, texto, nivel='info'):
        glifo, cor = _ICONE.get(nivel, _ICONE['info'])
        self.StatusLabel.Text = texto
        self.StatusIcone.Text = glifo
        self.StatusIcone.Foreground = _PINCEL.ConvertFromString(cor)

    # ----------------------------------------------------- LOG do projeto (v1.8)

    @protegido
    def ao_abrir_log(self, sender, args):
        self.carregar_log()

    @protegido
    def ao_novo_apontamento(self, sender, args):
        """Seleciona no Revit, clica aqui: o diálogo abre dentro do evento
        (só leitura) e o apontamento já volta aberto na lista."""
        self.pedir_apontamento()

    def pedir_apontamento(self, lados=None):
        self.mostrar_status(u'Lendo a seleção do Revit...')
        handler.pedido = ('log_novo', (agora(), _sufixo(), lados or []))
        evento.Raise()

    def avisar_novidades(self, novos):
        """O que chegou para mim desde a última vez que abri o LOG (v2.5).

        A aba mostra o número mesmo com outra aba aberta: quem está no
        relatório de interferências fica sabendo que alguém o chamou.
        Decisão do Thiago (24/09): aviso só dentro da janela, sem pop-up.
        """
        self._novos = set(item['id'] for item in novos)
        self.AbaLog.Content = u'LOG do projeto' + (
            u'  ● {}'.format(len(novos)) if novos else u'')

    def ler_apontamentos(self):
        """{id: apontamento} da DAT/LOG do projeto — a outra metade do
        espelho quando a lista aberta é um relatório."""
        try:
            itens, _ = log_disco.ler(self.pasta_log)
        except Exception as erro:
            print(u'LOG: apontamentos não lidos ({})'.format(erro))
            return {}
        return dict((item['id'], item) for item in itens)

    @staticmethod
    def _ler_log(pasta):
        """SÓ disco (05/10/2026): roda fora da thread da tela.

        Nada de Revit nem de WPF aqui — o Google Drive pode demorar a
        entregar um arquivo, e a janela não pode congelar esperando.
        """
        itens, avisos = log_disco.ler(pasta)
        # v3.2: anota onde fica a caixa de entrada — quem só RECEBE avisos
        # nunca gravaria nada que a anotasse, e o vigia precisa saber
        log_disco.raiz_da_caixa(pasta)
        return {'pasta': pasta, 'itens': itens, 'avisos': avisos,
                'visto': log_disco.visto_em(pasta),
                'equipe': log_disco.ler_equipe(pasta),
                # v3.4: a caixa entra na mesma leitura de fundo
                'caixa': _vigia_caixa.ler_caixa(usuario()),
                'lidos': _vigia_caixa.ler_lidos()}

    def carregar_log(self, manter=None, pasta=None, dados=None):
        """Lê a pasta `DAT\\LOG` do projeto aberto e mostra.

        `dados` (de `_ler_log`) vem pronto da recarga em segundo plano; sem
        ele, lê aqui mesmo — quem acabou de gravar precisa da lista na hora.
        """
        self._geracao += 1
        pasta = pasta or log_disco.pasta_do_log(self.caminho_do_modelo())
        if dados is None:
            dados = self._ler_log(pasta)
        self.pasta_log = pasta
        self._equipe = dados['equipe']
        self._avisos = dados.get('caixa') or {}
        self._lidos = dados.get('lidos') or []
        self.mostrar_contador_de_avisos()
        self.apresentar_se()
        itens, avisos = dados['itens'], dados['avisos']
        novos = novidades(itens, self.eu(), dados['visto'])
        self.avisar_novidades(novos)
        self.itens_log = dict((item['id'], item) for item in itens)
        self.caminho = None
        self.registro = como_registro(itens, self.meu_nome())
        self.ordem = ordem_do_log(itens)
        self.atual = None
        self._erro_log = None
        self._relatorio = {'projeto': self.caminho_do_modelo(),
                           'fonte': 'log'}
        self.RecarregarBtn.IsEnabled = True
        if self.fonte != 'log':
            self.fonte = 'log'
            self.abertos = set()
            self.montar_agrupamentos()
        # a aba já diz "LOG do projeto": aqui vai a OBRA, que é a informação
        # que muda (v2.2 — o título estava duplicado e comia espaço)
        self.ArquivoLabel.Text = _obra_curta(pasta)
        self.ArquivoLabel.ToolTip = pasta
        self.marcar_aba()
        self.NovidadesLabel.Text = (
            u'{} novo(s) para você desde a última vez.'.format(len(novos))
            if novos else u'')
        self.mostrar_projeto()
        self.montar_lista(manter=manter)
        if manter is None:
            self.escolher_primeiro()
        self.preencher_para()
        log_disco.marcar_visto(pasta, agora())
        self.vigiar_obra()
        if avisos:
            self.mostrar_status(u'{} apontamento(s); {} arquivo(s) não '
                                u'lidos: {}'.format(len(itens), len(avisos),
                                                    '; '.join(avisos[:3])),
                                'aviso')
        else:
            self.mostrar_status(u'{} apontamento(s) no LOG do projeto.{}'.format(
                len(itens), u' {} novo(s) para você.'.format(len(novos))
                if novos else u''), 'ok')

    # ------------------------------------------ composer: para + print (v2.5)

    def preencher_para(self):
        """A equipe no combo 'Para': a empresa inteira + quem já escreveu."""
        try:
            if self._equipe is None:
                self._equipe = log_disco.ler_equipe(self.pasta_log)
            equipe = nomes_da_equipe(self._equipe)
        except Exception as erro:
            print(u'LOG: equipe não lida ({})'.format(erro))
            equipe = []
        vistos = set(n.lower() for n in equipe)
        for item in self.itens_log.values():
            for nome in [item.get('autor')] + list(item.get('para') or []):
                nome = self.nome_de_pessoa(nome) if nome else ''
                if nome and nome.lower() not in vistos:
                    vistos.add(nome.lower())
                    equipe.append(nome)
        texto = self.ParaCombo.Text
        self.ParaCombo.ItemsSource = sorted(equipe, key=lambda n: n.lower())
        self.ParaCombo.Text = texto

    def para_escolhido(self):
        return separar_nomes(self.ParaCombo.Text or '')

    @protegido
    def ao_recortar(self, sender, args):
        """O recorte do Windows (Win+Shift+S); a janela segue viva enquanto o
        timer espera a imagem chegar no clipboard."""
        from Snippets._captura_tela import abrir_recorte, limpar_clipboard
        limpar_clipboard()
        abrir_recorte()
        self._tentativas_recorte = 0
        self.mostrar_status(u'Recorte de tela iniciado: selecione a área desejada.')
        self._timer_recorte.Start()

    @protegido
    def ao_conferir_recorte(self, sender, args):
        from Snippets._captura_tela import (capturar_clipboard,
                                            tem_imagem_no_clipboard)
        self._tentativas_recorte += 1
        try:
            tem = tem_imagem_no_clipboard()
        except Exception:
            # clipboard preso por outro programa: tenta de novo no próximo
            # tique — um print aqui abriria a janela de saída a cada 0,7 s
            tem = False
        if tem:
            self._timer_recorte.Stop()
            self.anexar(capturar_clipboard(), u'recorte')
        elif self._tentativas_recorte >= TENTATIVAS_RECORTE:
            self._timer_recorte.Stop()
            self.mostrar_status(u'Recorte não recebido (tempo esgotado).', 'aviso')

    @protegido
    def ao_capturar_tela(self, sender, args):
        """Print da tela inteira — o 'print completo' (Thiago, 30/09).

        A janela sai da frente, espera a tela redesenhar e volta: senão a
        foto seria da própria janela do LOG por cima do modelo.
        """
        self.Hide()
        self._timer_tela.Start()

    @protegido
    def ao_tirar_foto(self, sender, args):
        self._timer_tela.Stop()
        try:
            from Snippets._captura_tela import capturar_tela
            self.anexar(capturar_tela(), u'tela inteira')
        except Exception as erro:
            self.mostrar_status(u'Não foi possível capturar a tela: {}'.format(erro),
                                'erro')
        finally:
            self.Show()
            self.Activate()

    def anexar(self, resultado, de_onde):
        if not resultado:
            self.mostrar_status(u'Imagem não recebida ({}).'.format(de_onde),
                                'aviso')
            return
        self._anexo = resultado
        self.AnexoLabel.Text = u'{} anexado'.format(de_onde)
        self.AnexoChip.Visibility = Visibility.Visible
        self.mostrar_status(u'Imagem anexada ({}). Será enviada com o próximo '
                            u'comentário.'.format(de_onde), 'ok')

    @protegido
    def ao_tirar_anexo(self, sender, args):
        self.limpar_anexo()

    def limpar_anexo(self):
        self._anexo = None
        self.AnexoChip.Visibility = Visibility.Collapsed

    def gravar_anexo(self, nome_base):
        """O anexo vai para DAT/LOG/img. -> o nome do arquivo, ou ''."""
        if not self._anexo:
            return ''
        from Snippets._captura_tela import gravar_em
        return gravar_em(self._anexo, log_disco.garantir_imagens(
            self.pasta_log), nome_base)

    def aplicar_no_log(self, chaves, status, comentario, quando, para=(),
                       imagem=''):
        """Marcar/responder grava NO ARQUIVO da ocorrência (mesclando).

        v2.5: `para` SOMA destinatários (encaminhar); `imagem` vai na
        resposta. Se o apontamento nasceu de um conflito de relatório, a
        mesma marca vai para lá — espelho ([[_espelho]]).
        """
        self._erro_log = None
        for k in chaves:
            item = self.itens_log.get(k)
            if item is None:
                continue
            if comentario:
                responder(item, comentario, self.meu_nome(), quando,
                          novo_id(quando, self.meu_nome(), _sufixo()),
                          imagem=imagem)
            novos_para = self.quem_entra(item, para)
            if novos_para:
                acrescentar_para(item, novos_para)
            if status is not None:
                mudar_status(item, DA_JANELA.get(status, ABERTA),
                             self.meu_nome(), quando)
            item, erro = log_disco.gravar(self.pasta_log, item)
            self.itens_log[k] = item
            self._erro_log = self._erro_log or erro
            if not erro:
                # v3.2 — o balão de quem foi chamado (status não avisa)
                if comentario:
                    self.avisar_caixa(caixa.RESPOSTA, item, quando,
                                      texto=comentario, novos_para=novos_para)
                elif novos_para:
                    self.avisar_caixa(caixa.ENCAMINHADO, item, quando,
                                      novos_para=novos_para)
            self.espelhar_no_relatorio(item, status, comentario, quando)

    @staticmethod
    def quem_entra(item, para):
        """Dos nomes do "Para", os que ainda não estavam no apontamento.

        Quem criou o apontamento não entra (06/10/2026): ele já recebe as
        respostas, e o "Para" vem preenchido com ele — sem isto cada
        resposta o acrescentaria aos destinatários."""
        ja = set((n or u'').strip().lower() for n in item.get('para') or [])
        return [n for n in para or [] if n and n.strip().lower() not in ja
                and not e_do_autor(item, n)]

    def avisar_caixa(self, tipo, item, quando, texto=None, novos_para=(),
                     pasta=None):
        """Deixa o aviso na caixa de cada pessoa chamada (v3.2).

        Nunca impede o apontamento: sem caixa (obra fora do servidor) ou com
        erro, o recado já está gravado na obra e só o balão não sai.
        """
        pasta = pasta or self.pasta_log
        try:
            raiz = log_disco.raiz_da_caixa(pasta)
            if not raiz:
                return
            equipe = self._equipe if self._equipe is not None else \
                log_disco.ler_equipe(pasta)
            ids, sem_cadastro = caixa.destinatarios(
                tipo, item, self.usuario_id(), equipe, novos_para)
            recado = caixa.aviso(tipo, item, self.meu_nome(),
                                 self.usuario_id(), _obra_curta(pasta), pasta,
                                 quando, texto)
            erros = [e for e in (log_disco.deixar_aviso(raiz, i, recado,
                                                        _sufixo())
                                 for i in ids) if e]
            if erros:
                self.mostrar_status(u'Registrado. O aviso não foi entregue a {} '
                                    u'pessoa(s): {}'.format(len(erros),
                                                            erros[0]), 'aviso')
            elif sem_cadastro:
                self.mostrar_status(u'Registrado. {} ainda não está cadastrado(a) no '
                                    u'LOG e não receberá o aviso.'.format(
                                        u', '.join(sem_cadastro)), 'aviso')
        except Exception as erro:
            print(u'LOG: aviso na caixa falhou ({})'.format(erro))

    def espelhar_no_relatorio(self, item, status, comentario, quando):
        """LOG -> relatório: a marca feita aqui aparece no conflito de onde o
        apontamento veio. Relatório sumido não impede nada no LOG."""
        origem = item.get('origem') or {}
        caminho = achar_relatorio(origem, self.pasta_log)
        if not caminho:
            return
        try:
            # apontamento da v3.0 aponta o relatório antigo: o vivo é o do
            # repositório (v3.1)
            caminho = self.para_o_repositorio(caminho)
            registro, _ = ifr_disco.ler_registro(caminho)
            conflito = registro.get('conflitos', {}).get(origem['chave'])
            if conflito is None:
                return
            marcar(registro, origem['chave'], status,
                   comentario if comentario else None, self.meu_nome(),
                   quando)
            conflito['log_id'] = item['id']
            ifr_disco.gravar_registro(caminho, registro)
        except Exception as erro:
            print(u'LOG: espelho no relatório falhou ({})'.format(erro))
            self.mostrar_status(u'Registrado no LOG, mas o relatório de origem '
                                u'não foi atualizado: {}'.format(erro),
                                'aviso')

    # ------------------------------------------------- repositório (v3.1)

    def pasta_relatorios(self):
        """`<pasta do central>/DAT/RELATORIOS` do modelo aberto."""
        return ifr_disco.pasta_repositorio(self.caminho_do_modelo())

    def atualizar_repositorio(self):
        """Relê a lista de relatórios (só os que mudaram são relidos). Na
        primeira vez em cada projeto, traz os relatórios da v2."""
        pasta = self.pasta_relatorios()
        avisos = []
        if pasta not in self._migrados:
            self._migrados.add(pasta)
            _, avisos = ifr_disco.migrar_antigos(pasta)
        self.metas, ruins = ifr_disco.listar(pasta)
        avisos.extend(ruins)
        if avisos:
            self.mostrar_status(u'Relatórios não lidos: {}'.format(
                u'; '.join(avisos[:3])), 'aviso')

    @staticmethod
    def aba_da_fonte(fonte):
        return 'passes' if fonte == 'passes' else 'html'

    def lembrar_da_aba(self, fonte, id_do_relatorio):
        """O MEU último relatório desta aba — é o que abre da próxima vez."""
        ultimos = self.prefs.setdefault('ultimo_por_aba', {})
        ultimos[self.aba_da_fonte(fonte)] = id_do_relatorio
        ifr_disco.gravar_preferencias(self.prefs)

    def gravar_rodada(self, relatorio):
        """A verificação que acabou de rodar entra no repositório.

        -> (caminho, a mesma pergunta já existia). Chamado por `ifr_clash`
        e `ifr_passes`.
        """
        relatorio['escopo'] = repo.escopo_de_relatorio(relatorio)
        caminho, ja_existia = ifr_disco.gravar_no_repositorio(
            self.pasta_relatorios(), relatorio, self.meu_nome(),
            self.usuario_id(), agora())
        self.lembrar_da_aba(relatorio['fonte'],
                            os.path.splitext(os.path.basename(caminho))[0])
        return caminho, ja_existia

    def para_o_repositorio(self, caminho):
        """O caminho NO repositório de qualquer relatório que se abra.

        HTML do Revit: entra (decisão do Thiago, 30/09). Relatório da v2
        (`<modelo> - passes.json`): vai pela migração. Outro JSON: abre
        onde está. ValueError se o HTML não tem o que ler.
        """
        if ifr_disco.no_repositorio(caminho):
            return caminho
        pasta = self.pasta_relatorios()
        if not caminho.lower().endswith('.json'):
            lido = ler_relatorio(ifr_disco.ler_html(caminho))
            if not lido['conflitos']:
                raise ValueError(u'não contém conflitos legíveis. Confirme se é '
                                 u'o HTML exportado pela Verificação de '
                                 u'interferência.')
            projeto = nome_do_arquivo(lido.get('projeto')) or \
                arquivo_do_modelo(self.doc())
            destino, _ = ifr_disco.importar_html(
                pasta, caminho, lido, projeto, self.meu_nome(),
                self.usuario_id(), agora())
            return destino
        if repo.relatorio_antigo(os.path.basename(caminho)) is not None:
            ifr_disco.migrar_antigos(pasta)
            destino = ifr_disco.caminho_do_antigo(pasta, caminho)
            if destino and os.path.exists(destino):
                return destino
        return caminho

    def mostrar_relatorios(self):
        """O dropdown com os relatórios da aba, o aberto selecionado."""
        da = repo.da_aba(self.metas, self.aba_da_fonte(self.fonte))
        aberto = os.path.normcase(self.caminho or '')
        indice = next((i for i, m in enumerate(da)
                       if os.path.normcase(m['caminho']) == aberto), -1)
        eram = self._montando
        self._montando = True
        try:
            self.RelatorioCombo.ItemsSource = [OpcaoRelatorio(m) for m in da]
            self.RelatorioCombo.SelectedIndex = indice
        finally:
            self._montando = eram

    def meta_do_caminho(self, caminho):
        nome = os.path.basename(caminho or '').lower()
        return next((m for m in self.metas
                     if os.path.basename(m['caminho']).lower() == nome), None)

    @protegido
    def ao_escolher_relatorio(self, sender, args):
        if self._montando:
            return
        opcao = self.RelatorioCombo.SelectedItem
        if opcao is None or os.path.normcase(opcao.meta['caminho']) == \
                os.path.normcase(self.caminho or ''):
            return
        # escolher no dropdown é dizer "estou trabalhando neste"
        self.lembrar_da_aba(opcao.meta['fonte'], opcao.meta['id'])
        self.carregar(opcao.meta['caminho'])

    def origem_do_atual(self):
        """A origem do apontamento escolhido no LOG ({} se não veio de
        relatório)."""
        if self.fonte != 'log' or self.atual is None or \
                self.atual.tipo == 'grupo':
            return {}
        item = self.registro['conflitos'][self.atual.chaves[0]]
        return (self.log_do_item(item) or {}).get('origem') or {}

    def nome_da_origem(self, origem):
        """'Tubo × Duto' em vez de 'clash-3fa9c1d0e2b4.json'."""
        if not self.metas:
            self.atualizar_repositorio()
        caminho = achar_relatorio(origem, self.pasta_log)
        meta = self.meta_do_caminho(caminho) if caminho else None
        if meta is None and caminho and \
                repo.relatorio_antigo(os.path.basename(caminho)):
            meta = self.meta_do_caminho(ifr_disco.caminho_do_antigo(
                self.pasta_relatorios(), caminho))
        if meta is not None:
            return u'{} ({})'.format(meta['nome'], meta['autor'])
        return origem.get('arquivo') or u''

    @protegido
    def ao_ir_ao_relatorio(self, sender, args):
        """Do apontamento ao conflito, no relatório de quem o criou.

        Não muda o "meu último": a pessoa volta ao relatório dela pela aba
        (Thiago: "nada impede de ele voltar a trabalhar no relatório dele").
        """
        origem = self.origem_do_atual()
        caminho = achar_relatorio(origem, self.pasta_log)
        if not caminho:
            self.mostrar_status(u'O relatório de onde este apontamento veio '
                                u'não existe mais.', 'aviso')
            return
        self.atualizar_repositorio()
        self.carregar(self.para_o_repositorio(caminho))
        chave = origem.get('chave')
        if self.fonte != 'log' and chave in self.registro['conflitos']:
            self.ir_para_chave(chave)

    # ------------------------------------------------------------ carregar

    @protegido
    def ao_abrir(self, sender, args):
        # começa no projeto ABERTO — o último de outra obra confundia (02/10)
        pasta = os.path.dirname(self.caminho) if self.caminho else \
            os.path.dirname(self.pasta_relatorios())
        escolhido = forms.pick_file(
            files_filter=u'Relatórios (*.html;*.json)|*.html;*.json',
            init_dir=pasta, title=u'Relatório de interferência (HTML) ou de '
                                  u'passes (JSON)')
        if escolhido:
            self.carregar(escolhido)

    @protegido
    def ao_recarregar(self, sender, args):
        self.recarregar_em_segundo_plano(u'Atualizando…')

    def recarregar_em_segundo_plano(self, texto=None, sozinho=False):
        """Relê a aba aberta SEM congelar a janela (05/10/2026).

        O disco é lido numa thread de fundo; a tela só é tocada de volta na
        thread dela (`Dispatcher`). Revit e WPF ficam fora da thread: o que
        depende do modelo (a pasta da obra) é resolvido antes de sair.
        """
        if self._lendo:
            return
        manter = self.identidade(self.atual) if self.atual is not None             else None
        if self.fonte == 'log':
            pasta = self.pasta_log or log_disco.pasta_do_log(
                self.caminho_do_modelo())

            def ler():
                return self._ler_log(pasta)

            def aplicar(dados):
                self.carregar_log(manter=manter, pasta=pasta, dados=dados)
        elif self.caminho:
            caminho = self.caminho
            pasta_log = log_disco.pasta_do_log(self.caminho_do_modelo())

            def ler():
                return self._ler_relatorio(caminho, pasta_log)

            def aplicar(dados):
                self.carregar(caminho, dados=dados, manter=manter)
        else:
            return
        if sozinho:
            aplicar = self._preservando_composer(aplicar)
        if texto:
            self.mostrar_status(texto)
        self.em_segundo_plano(ler, aplicar)

    def _preservando_composer(self, aplicar):
        """A recarga que ninguém pediu não pode apagar o que a pessoa está
        escrevendo: resposta, Para e print anexado voltam ao lugar."""
        def aplicar_sem_perder(dados):
            texto = self.ComentarioBox.Text
            para = self.ParaCombo.Text
            anexo = self._anexo
            aplicar(dados)
            if texto and not self.ComentarioBox.Text and \
                    self.ComentarioBox.IsEnabled:
                self.ComentarioBox.Text = texto
            if para:
                # o detalhe repreenche o "Para" com a sugestão: vale o que a
                # pessoa deixou no campo
                self.ParaCombo.Text = para
            if anexo and not self._anexo:
                self.anexar(anexo, u'mantido')
            self.mostrar_status(u'Lista atualizada às {} (alterações registradas '
                                u'na pasta da obra).'.format(
                                    datetime.now().strftime('%H:%M')), 'ok')
        return aplicar_sem_perder

    # ------------------------------------- vigia das pastas da obra (v3.2)

    def vigiar_obra(self):
        """Liga o vigia do Windows nas pastas `DAT/LOG` e `DAT/RELATORIOS`.

        Testado em 05/10/2026: mudança feita por OUTRA pessoa no Google
        Drive chega ao FileSystemWatcher em 2-3 s ([[api-notificacao-revit]]).
        Só refaz o vigia se a obra mudou.
        """
        self._ultima_carga = DateTime.Now
        pastas = tuple(p for p in (self.pasta_log, self.pasta_relatorios())
                       if p and os.path.isdir(p))
        if pastas == self._pastas_vigiadas:
            return
        self.parar_vigias()
        self._pastas_vigiadas = pastas
        for pasta in pastas:
            try:
                vigia = FileSystemWatcher(pasta)
                vigia.IncludeSubdirectories = False
                vigia.NotifyFilter = (NotifyFilters.FileName |
                                      NotifyFilters.LastWrite |
                                      NotifyFilters.Size)
                vigia.Created += self._evento_no_disco
                vigia.Changed += self._evento_no_disco
                vigia.Deleted += self._evento_no_disco
                vigia.Renamed += self._evento_no_disco
                vigia.EnableRaisingEvents = True
                self._vigias.append(vigia)
            except Exception as erro:
                print(u'LOG: sem vigia em {} ({})'.format(pasta, erro))

    def parar_vigias(self):
        for vigia in self._vigias:
            try:
                vigia.EnableRaisingEvents = False
                vigia.Dispose()
            except Exception as erro:
                print(u'LOG: vigia não fechou ({})'.format(erro))
        self._vigias = []
        self._pastas_vigiadas = ()

    def _evento_no_disco(self, sender, args):
        """Thread do Windows, não da tela: só agenda."""
        nome = (args.Name or u'').lower()
        if not nome.endswith('.json') or nome.endswith('.tmp'):
            return
        self.Dispatcher.BeginInvoke(Action(self._reagendar))

    def _reagendar(self):
        if (DateTime.Now - self._ultima_carga).TotalSeconds < \
                SILENCIO_APOS_CARGA:
            return      # a própria janela acabou de gravar e recarregar
        self._timer_disco.Stop()
        self._timer_disco.Start()

    def ao_mudar_no_disco(self, sender, args):
        self._timer_disco.Stop()
        try:
            self.recarregar_em_segundo_plano(sozinho=True)
        except Exception as erro:
            self.mostrar_status(u'Atualização automática não concluída: {}'.format(
                erro), 'aviso')

    def em_segundo_plano(self, ler, aplicar):
        """`ler()` numa thread de fundo; `aplicar(resultado)` na da tela."""
        geracao = self._geracao
        self._lendo = True
        janela = self

        def na_tela(resultado, erro, detalhe):
            janela._lendo = False
            if geracao != janela._geracao:
                return      # outra carga começou depois: esta já é velha
            try:
                if erro is not None:
                    janela.mostrar_status(u'Não foi possível atualizar: {}'.format(
                        erro), 'erro')
                    print(detalhe)
                    return
                aplicar(resultado)
            except Exception as falha:
                janela.mostrar_status(u'Erro ao atualizar: {}'.format(falha),
                                      'erro')
                script.get_output().print_md('```\n{}\n```'.format(
                    traceback.format_exc()))

        def trabalho():
            resultado, erro, detalhe = None, None, ''
            try:
                resultado = ler()
            except Exception as falha:
                erro, detalhe = falha, traceback.format_exc()
            janela.Dispatcher.BeginInvoke(Action(
                lambda: na_tela(resultado, erro, detalhe)))

        linha = Thread(ThreadStart(trabalho))
        linha.IsBackground = True
        linha.Start()

    @protegido
    def ao_verificar_clash(self, sender, args):
        """v2.4 — cruza os modelos escolhidos; o diálogo abre no evento."""
        self.mostrar_status(u'Lendo as caixas dos elementos de todos os '
                            u'modelos...')
        handler.pedido = ('clash', None)
        evento.Raise()

    @protegido
    def ao_verificar_passes(self, sender, args):
        """v1.5 — o diálogo abre dentro do evento (só leitura, sem
        Transaction) e o resultado volta aberto nesta janela."""
        self.mostrar_status(u'Lendo passes, níveis e tubos dos vínculos...')
        handler.pedido = ('passes', None)
        evento.Raise()

    def ler(self, caminho):
        dados = ifr_disco.ler_html(caminho)
        if caminho.lower().endswith('.json'):
            return ler_relatorio_passes(dados)
        relatorio = ler_relatorio(dados)
        relatorio['fonte'] = 'html'
        return relatorio

    def _ler_relatorio(self, caminho, pasta_log):
        """SÓ disco (05/10/2026): relatório, status, status do projeto e os
        apontamentos — pode rodar fora da thread da tela. ValueError sobe."""
        relatorio = self.ler(caminho)
        if relatorio['fonte'] == 'clash':
            # antes de 01/10 o par vinha em qualquer ordem: A = categoria da
            # coluna "Verificar estes"
            escopo = (relatorio.get('repositorio') or {}).get('escopo') or \
                relatorio.get('parametros') or {}
            for conflito in relatorio['conflitos']:
                orientar(conflito, escopo.get('categorias'))
        registro, aviso_disco = ifr_disco.ler_registro(caminho)
        do_projeto = ifr_disco.ler_status_do_projeto(os.path.dirname(caminho)) \
            if ifr_disco.no_repositorio(caminho) else None
        try:
            itens, _ = log_disco.ler(pasta_log)
        except Exception as erro:
            print(u'LOG: apontamentos não lidos ({})'.format(erro))
            itens = []
        return {'caminho': caminho, 'relatorio': relatorio,
                'registro': registro, 'aviso_disco': aviso_disco,
                'do_projeto': do_projeto,
                'itens_log': dict((item['id'], item) for item in itens),
                'visto': log_disco.visto_em(pasta_log)}

    def carregar(self, caminho, dados=None, manter=None):
        """Abre um relatório. `dados` (de `_ler_relatorio`) vem pronto da
        recarga em segundo plano; sem ele, lê aqui mesmo. `manter`: o item
        que continua escolhido (recarga), em vez de pular para o primeiro."""
        self._geracao += 1
        movido = ''
        if dados is None:
            caminho, movido = ifr_disco.realocar(caminho)
            if caminho.lower().endswith('.status.json'):
                self.mostrar_status(u'Este é o arquivo de status. Abra o '
                                    u'relatório (.html ou "- passes.json").',
                                    'aviso')
                return
            try:
                caminho = self.para_o_repositorio(caminho)
                dados = self._ler_relatorio(caminho, log_disco.pasta_do_log(
                    self.caminho_do_modelo()))
            except ValueError as erro:
                self.mostrar_status(u'{}: {}'.format(os.path.basename(caminho),
                                                     erro), 'erro')
                return
        caminho = dados['caminho']
        relatorio = dados['relatorio']
        conflitos = relatorio['conflitos']
        if not conflitos and relatorio['fonte'] == 'html':
            self.mostrar_status(u'{} não contém conflitos legíveis. Confirme se é '
                                u'o HTML exportado pela Verificação de '
                                u'interferência.'.format(
                                    os.path.basename(caminho)), 'erro')
            return
        registro, aviso_disco = dados['registro'], dados['aviso_disco']
        tinha = len(registro.get('conflitos') or {})
        registro, novos, sairam, voltaram = sincronizar(registro, conflitos,
                                                        agora())
        # v3.1 — o status é do PAR, para o projeto: o que alguém marcou em
        # outro relatório com o mesmo tubo x duto vale aqui também
        de_outros = []
        if dados['do_projeto'] is not None:
            de_outros = repo.puxar_status(registro, dados['do_projeto'])
        # v2.5 — ESPELHO: o que mudou no LOG desde a última vez (outra pessoa
        # resolveu, respondeu) entra no conflito antes de a lista aparecer
        self.pasta_log = log_disco.pasta_do_log(self.caminho_do_modelo())
        self.itens_log = dados['itens_log']
        espelhados = sincronizar_registro(registro, self.itens_log)
        self.avisar_novidades(novidades(
            list(self.itens_log.values()), self.eu(), dados['visto']))
        # grava SÓ quando algo mudou (05/10/2026): antes, abrir ou atualizar
        # gravava o status e o status do projeto no drive toda vez — lento, e
        # cada carga virava sincronização para a equipe inteira
        mudou = bool(novos or sairam or voltaram or de_outros or espelhados
                     or len(registro.get('conflitos') or {}) != tinha)
        erro_gravar = None
        if mudou and not aviso_disco:
            registro, erro_gravar = ifr_disco.gravar_registro(caminho, registro)

        if caminho != self.caminho:
            self.abertos = set()
        if relatorio['fonte'] != self.fonte:
            self.fonte = relatorio['fonte']
            self.montar_agrupamentos()
        self.caminho = caminho
        self.atualizar_repositorio()
        self.mostrar_relatorios()
        self.registro = registro
        self.ordem = [c['chave'] for c in conflitos]
        self.atual = None
        self.RecarregarBtn.IsEnabled = True
        self.prefs['ultimo'] = caminho
        self.lembrar_relatorio(caminho)
        ifr_disco.gravar_preferencias(self.prefs)
        self.marcar_aba()

        self.ArquivoLabel.Text = os.path.basename(caminho)
        self.ArquivoLabel.ToolTip = caminho
        self._relatorio = relatorio
        self.mostrar_projeto()

        partes = []
        if sairam:
            partes.append(u'{} saíram do relatório'.format(len(sairam)))
        if novos:
            partes.append(u'{} novos'.format(len(novos)))
        if voltaram:
            partes.append(u'{} voltaram'.format(len(voltaram)))
        if de_outros:
            partes.append(u'{} marcado(s) em outro relatório do projeto'.format(
                len(de_outros)))
        if espelhados:
            # v2.5: alguém mexeu no LOG enquanto o relatório estava fechado —
            # aviso no cabeçalho, nunca na janela de saída do pyRevit
            partes.append(u'{} atualizado(s) pelo LOG do projeto'.format(
                len(espelhados)))
        if relatorio['ignoradas']:
            partes.append(u'{} linha(s) não lidas: {}'.format(
                len(relatorio['ignoradas']),
                ', '.join(relatorio['ignoradas'][:8])))
        self.NovidadesLabel.Text = (u'Desde a última leitura: ' +
                                    u' · '.join(partes)) if partes else ''
        # quem acabou de refazer a verificação precisa do MESMO numero em
        # palavras de mudança (v2.3): guarda o delta para `ifr_passes` dizer
        # "relatório atualizado: 3 novos, 5 sumiram"
        self._delta = {'novos': len(novos), 'sairam': len(sairam),
                       'voltaram': len(voltaram),
                       'total': len(self.ordem)}

        self.montar_lista(manter=manter)
        if manter is None or self.atual is None:
            self.escolher_primeiro()
        self.preencher_para()
        self.vigiar_obra()

        if aviso_disco:
            self.mostrar_status(aviso_disco, 'aviso')
        elif erro_gravar:
            self.mostrar_status(u'Relatório lido, mas não foi possível gravar o status em '
                                u'{}: {}'.format(ifr_disco.caminho_do_registro(
                                    caminho), erro_gravar), 'erro')
        else:
            self.mostrar_status(u'{} conflito(s) lido(s).{}'.format(
                len(conflitos), u' ' + movido[0].upper() + movido[1:] + u'.'
                if movido else u''), 'ok')

    # --------------------------------------------------------------- lista

    #: chip -> (filtro, só o que me interessa) — o estado fica à vista, em
    #: vez de escondido num combo (v2.0)
    CHIPS = [('ChipParaMim', F_PENDENTES, True),
             ('ChipAbertos', F_PENDENTES, False),
             ('ChipResolvidos', F_RESOLVIDOS, False),
             ('ChipTodos', F_TODOS, False),
             ('ChipSairam', F_SAIRAM, False)]

    def chip_ativo(self):
        for nome, filtro, para_mim in self.CHIPS:
            if getattr(self, nome).IsChecked:
                return nome, filtro, para_mim
        return self.CHIPS[1]

    def filtro(self):
        return self.chip_ativo()[1]

    def so_para_mim(self):
        return self.chip_ativo()[2]

    @protegido
    def ao_chip(self, sender, args):
        """Chip é escolha única: marcar um desmarca os outros."""
        if self._montando:
            return
        self._montando = True
        try:
            for nome, _, _ in self.CHIPS:
                chip = getattr(self, nome)
                chip.IsChecked = chip is sender
            if not any(getattr(self, n).IsChecked for n, _, _ in self.CHIPS):
                self.ChipAbertos.IsChecked = True
        finally:
            self._montando = False
        self.montar_lista()

    def niveis(self):
        opcoes = agrupamentos(self.fonte)
        indice = self.AgruparCombo.SelectedIndex
        return opcoes[indice if 0 <= indice < len(opcoes) else 0][0]

    def busca(self):
        return self.BuscaBox.Text or ''

    def escolher_primeiro(self):
        """Abrir a aba já mostra o PRIMEIRO apontamento (v2.2).

        > "ele já abre o primeiro só que sem me mostrar as mensagens, como
        >  se fosse um preview; o usuário vai ter que clicar duas vezes"
        > (Thiago, 24/09/2026)

        Só seleciona e abre o grupo — não navega no Revit: quem manda mexer
        no modelo é o clique do usuário.
        """
        na_tela = [k for k in self.ordem_na_tela()
                   if k in set(self.chaves_visiveis())]
        if not na_tela:
            return
        primeira = na_tela[0]
        item = self.registro['conflitos'][primeira]
        self.abertos = set(caminhos_ate(item, self.niveis()))
        self.montar_lista(manter=('conflito', primeira))

    def chaves_visiveis(self):
        """As chaves que passam pelo filtro e pela busca de agora."""
        chaves = chaves_filtradas(self.registro, self.ordem, self.filtro(),
                                  self.busca())
        if self.so_para_mim():
            chaves = so_para(self.registro, chaves, self.eu())
        return chaves

    def montar_lista(self, manter=None):
        """Refaz a árvore e a lista. `manter`: identidade a reselecionar."""
        if manter is None and self.atual is not None:
            manter = self.identidade(self.atual)
        niveis = self.niveis()
        chaves = self.chaves_visiveis()
        self.nos = arvore(self.registro, chaves, niveis)
        tudo_aberto = bool(self.busca().strip())
        linhas = [Linha(self.com_miniatura(dados), self.registro, niveis)
                  for dados in achatar(self.nos, self.abertos, tudo_aberto)]
        self._montando = True
        try:
            self.linhas = linhas
            self.ConflitosList.ItemsSource = linhas
            self.atual = None
            for linha in linhas:
                if manter and self.identidade(linha) == manter:
                    self.ConflitosList.SelectedItem = linha
                    self.ConflitosList.ScrollIntoView(linha)
                    self.atual = linha
                    break
        finally:
            self._montando = False
        self.montar_resumo(len(chaves))
        self.mostrar_rotulos()
        self.mostrar_vazio(len(chaves), contagem(self.registro)['total'])
        self.mostrar_detalhe()

    def com_miniatura(self, dados):
        """A imagem do apontamento vira miniatura na lista (v2.0)."""
        if dados.get('tipo') != 'conflito':
            return dados
        log = (self.registro['conflitos'].get(dados['chave']) or {}).get('log')
        if log and log.get('imagem'):
            dados['miniatura'] = log_disco.caminho_da_imagem(self.pasta_log,
                                                             log['imagem'])
        if log:
            # o apontamento antigo gravou o ID do Revit; a lista mostra gente
            dados['quem'] = self.nome_de_pessoa(log.get('autor_id') or
                                                log.get('autor'))
            dados['novo'] = log.get('id') in self._novos
        return dados

    def nome_de_pessoa(self, ident):
        """'thiagonunesXNUJD' -> 'Thiago Nunes' (o que o equipe.json souber)."""
        if not ident:
            return ''
        if self._equipe is None:
            try:
                self._equipe = log_disco.ler_equipe(self.pasta_log)
            except Exception:
                self._equipe = {}
        return nome_de_pessoa(self._equipe, ident)

    def identidade(self, linha):
        if linha.tipo == 'grupo':
            return ('grupo', linha.caminho)
        return ('conflito', linha.chaves[0])

    def mostrar_rotulos(self):
        """O cabeçalho e o painel falam a língua da fonte (v1.8)."""
        log = self.fonte == 'log'
        # cada lista mostra só os chips que fazem sentido nela (v2.0)
        self.ChipParaMim.Visibility = (Visibility.Visible if log
                                       else Visibility.Collapsed)
        self.ChipSairam.Visibility = (Visibility.Collapsed if log
                                      else Visibility.Visible)
        if log and self.ChipSairam.IsChecked:
            self.ChipSairam.IsChecked = False
            self.ChipAbertos.IsChecked = True
        if not log and self.ChipParaMim.IsChecked:
            self.ChipParaMim.IsChecked = False
            self.ChipAbertos.IsChecked = True
        # quem diz qual lista está aberta é a ABA (v2.0), não mais um rótulo
        # v2.5: a linha do rotulo e a dos botoes Pendente/Resolvido/Ignorar;
        # e no relatorio o comentario tambem e resposta (vira apontamento)
        self.ComentarioRotulo.Text = u'MARCAR'
        self.GravarComentarioBtn.Content = u'Responder'

    def montar_resumo(self, n_na_lista):
        c = contagem(self.registro)
        total = c['total']
        if self.fonte == 'log':
            self.ResumoLabel.Text = (
                u'{} apontamentos · {} abertos · {} resolvidos · {} '
                u'ignorados — no filtro: {}'.format(
                    total, c[PENDENTE], c[RESOLVIDO], c[IGNORAR], n_na_lista))
            self.ProgressoBar.Maximum = float(max(total, 1))
            self.ProgressoBar.Value = float(total - c[PENDENTE])
            return
        self.ResumoLabel.Text = (
            u'{} conflitos · {} pendentes · {} resolvidos · {} ignorados'
            u'{} — no filtro: {}'.format(
                total, c[PENDENTE], c[RESOLVIDO], c[IGNORAR],
                u' · {} saíram'.format(c['sairam']) if c['sairam'] else '',
                n_na_lista))
        self.ProgressoBar.Maximum = float(max(total, 1))
        self.ProgressoBar.Value = float(total - c[PENDENTE])


    @protegido
    def ao_buscar(self, sender, args):
        if not self._montando:
            self.montar_lista()

    @protegido
    def ao_agrupar(self, sender, args):
        if self._montando:
            return
        self.abertos = set()
        self.atual = None
        # pelo NOME (01/10/2026): opção nova na lista não muda a escolha
        self.prefs[self.chave_do_agrupar()] = self.AgruparCombo.SelectedItem
        ifr_disco.gravar_preferencias(self.prefs)
        self.montar_lista()

    @protegido
    def ao_expandir_tudo(self, sender, args):
        self.abertos = set(todos_os_caminhos(self.nos))
        self.montar_lista()

    @protegido
    def ao_recolher_tudo(self, sender, args):
        self.abertos = set()
        if self.atual is not None and self.atual.tipo == 'conflito':
            self.atual = None
        self.montar_lista()

    @protegido
    def ao_mudar_ao_escolher(self, sender, args):
        if self._montando:
            return
        self.prefs['ao_escolher'] = self.modo_ao_escolher()
        ifr_disco.gravar_preferencias(self.prefs)

    def modo_ao_escolher(self):
        return AO_ESCOLHER[max(self.AoEscolherCombo.SelectedIndex, 0)][0]

    @protegido
    def ao_mudar_zoom(self, sender, args):
        if self._montando:
            return
        self.prefs['zoom'] = self.folga_do_zoom()
        ifr_disco.gravar_preferencias(self.prefs)
        self.mostrar_status(u'Zoom: {} (margem de {} ao redor).'.format(
            ZOOMS[max(self.ZoomCombo.SelectedIndex, 0)][1],
            polegadas_texto(self.folga_do_zoom() * 12)))

    def folga_do_zoom(self):
        """Pés em volta dos elementos — o quanto a vista 'abre' (v2.3)."""
        if self.ZoomCombo.SelectedIndex < 0:
            return ZOOM_PADRAO
        return ZOOMS[self.ZoomCombo.SelectedIndex][0]

    @protegido
    def ao_escolher(self, sender, args):
        if self._montando:
            return
        self.atual = self.ConflitosList.SelectedItem
        self.mostrar_detalhe()
        modo = self.modo_ao_escolher()
        # grupo navega para o grupo inteiro; conflito, para os dois elementos
        # (v1.2 — pedido do Thiago, desfaz a restrição da v1.1)
        if self.atual is not None and modo != 'nada':
            self.navegar(modo)

    @protegido
    def ao_clique_na_lista(self, sender, args):
        """Clique no cabeçalho abre/fecha — só se o clique foi num item.

        PreviewMouseLeftButtonUp: o ListBoxItem já consumiu o MouseDown para
        selecionar. `ContainerFromElement` devolve None no clique na barra de
        rolagem, que não pode abrir grupo nenhum.
        """
        container = ItemsControl.ContainerFromElement(self.ConflitosList,
                                                      args.OriginalSource)
        if container is None:
            return
        linha = container.Content
        if linha is not None and linha.tipo == 'grupo':
            self.alternar(linha, not linha.aberto)

    @protegido
    def ao_tecla_na_lista(self, sender, args):
        linha = self.atual
        if linha is None or linha.tipo != 'grupo':
            return
        tecla = str(args.Key)
        if tecla in ('Right', 'Left', 'Enter', 'Space'):
            abrir = {'Right': True, 'Left': False}.get(tecla, not linha.aberto)
            self.alternar(linha, abrir)
            args.Handled = True

    def alternar(self, linha, abrir):
        """Sanfona (v1.3): abrir deixa só este grupo e os pais abertos;
        fechar fecha também os filhos dele."""
        if abrir:
            self.abertos = set(cadeia(linha.caminho))
        else:
            prefixo = linha.caminho + SEPARADOR
            self.abertos = set(c for c in self.abertos
                               if c != linha.caminho
                               and not c.startswith(prefixo))
        self.montar_lista(manter=('grupo', linha.caminho))

    # ------------------------------------------------------------- detalhe

    def chaves_do_alvo(self):
        return list(self.atual.chaves) if self.atual is not None else []

    def mostrar_lados(self, item):
        """Os elementos do item escolhido.

        Interferência é um PAR (A × B). Apontamento do LOG tem N elementos —
        e a janela mostrava só dois (24/09/2026: 12 gravados, 2 na tela e 1
        selecionado). Com 'lados', o painel lista todos.
        """
        lados = item.get('lados')
        if self.fonte == 'log':
            # no LOG o que importa é o RECADO: a lista de IDs só ocupava a
            # tela (v2.1). Uma linha diz onde e quantos; os botões levam lá.
            lados = lados or [item['a']]
            self.LadoALabel.Text = u'{} · {} elemento(s)'.format(
                lados[0].get('arquivo') or u'(sem modelo)', len(lados))
            self._mostrar_lado_b(False)
            return
        self._mostrar_lado_b(True)
        self.LadoALabel.Text = u'{} · {}'.format(
            item['a'].get('categoria', ''), curto(item['a']))
        self.LadoBRotulo.Text = u'EM CONFLITO COM'
        self.LadoBLabel.Text = rotulo_do_lado(item['b']) \
            if item.get('b') else u'—'

    def mostrar_situacao(self, item):
        """O chip colorido: pendente/resolvido/ignorado se lê de longe."""
        if item is None:
            self.SituacaoChip.Visibility = Visibility.Collapsed
            return
        como_esta = situacao(item)
        self.SituacaoLabel.Text = ROTULO.get(como_esta, u'').upper()
        self.SituacaoChip.Background = _PINCEL.ConvertFromString(
            COR.get(como_esta, COR[PENDENTE]))
        self.SituacaoChip.Visibility = Visibility.Visible

    def _mostrar_lado_b(self, visivel):
        como = Visibility.Visible if visivel else Visibility.Collapsed
        self.LadoBRotulo.Visibility = como
        self.LadoBLabel.Visibility = como

    def log_do_item(self, item):
        """O apontamento por trás do item escolhido.

        No LOG é o próprio item. Num relatório (v2.5), é o apontamento que o
        comentário criou — o conflito guarda o `log_id` e a conversa que
        aparece aqui é A MESMA do LOG: um é espelho do outro.
        """
        if not item:
            return None
        if item.get('log'):
            return item['log']
        if item.get('log_id'):
            return self.itens_log.get(item['log_id'])
        return None

    @protegido
    def ao_clicar_conversa(self, sender, args):
        """Clique na imagem de uma resposta abre em tamanho real.

        O evento fica na lista (não no template): evento declarado dentro
        de DataTemplate não chega ao code-behind do pyRevit.
        """
        fonte = getattr(args, 'OriginalSource', None)
        fala = getattr(fonte, 'DataContext', None)
        caminho = getattr(fala, 'Imagem', None)
        if caminho and type(fonte).__name__ == 'Image':
            self._abrir_arquivo(caminho)

    def mostrar_recado(self, item):
        """A conversa do apontamento — o coração do LOG (v2.1/v2.2).

        > "nessa aba lateral nem aparece qual é a mensagem que foi deixada...
        >  acho que é mais importante do que tudo"
        > "a primeira mensagem tem que ser a mensagem do apontamento, não a
        >  primeira resposta — para a gente saber o que foi solicitado"
        > (Thiago, 24/09/2026)
        """
        log = self.log_do_item(item)
        if not log:
            self.ConversaRotulo.Visibility = Visibility.Collapsed
            self.ConversaLista.Visibility = Visibility.Collapsed
            self.ConversaLista.ItemsSource = None
            return
        # o destinatário também vira gente: quem escolheu antes de se
        # cadastrar gravou o ID ("para thiagonunesXNUJD")
        destino = u', '.join(self.nome_de_pessoa(p)
                             for p in (log.get('para') or [])) \
            or u'toda a equipe'
        falas = [Fala(
            self.nome_de_pessoa(log.get('autor_id') or log.get('autor')),
            log.get('criado_em'), log.get('texto'), pedido=True,
            para=destino)]
        for mensagem in log.get('mensagens') or []:
            imagem = log_disco.caminho_da_imagem(
                self.pasta_log, mensagem['imagem'])                 if mensagem.get('imagem') else None
            falas.append(Fala(self.nome_de_pessoa(mensagem.get('autor')),
                              mensagem.get('quando'), mensagem.get('texto'),
                              imagem=imagem))
        self.ConversaRotulo.Text = (u'APONTAMENTO' if len(falas) == 1
                                    else u'APONTAMENTO E {} RESPOSTA(S)'.format(
                                        len(falas) - 1))
        self.ConversaLista.ItemsSource = falas
        self.ConversaRotulo.Visibility = Visibility.Visible
        self.ConversaLista.Visibility = Visibility.Visible
        # conversa com resposta: rola até a última, que é a que interessa
        # para responder (pin-to-bottom dos painéis de issue). Só o
        # apontamento: fica no topo, com a foto à vista.
        # sem o UpdateLayout o ScrollViewer ainda não sabe a altura do
        # conteúdo e o ScrollToEnd não sai do lugar
        self.LeituraScroll.UpdateLayout()
        if len(falas) > 1:
            self.LeituraScroll.ScrollToEnd()
        else:
            self.LeituraScroll.ScrollToTop()

    def mostrar_detalhe(self):
        tem = self.atual is not None
        if self._obra_fixa:
            self.mostrar_outra_obra()
        self.IrRelatorioBtn.Visibility = (
            Visibility.Visible if self.origem_do_atual().get('chave')
            else Visibility.Collapsed)
        for botao in (self.NaVistaBtn, self.Vista3DBtn, self.PendenteBtn,
                      self.ResolvidoBtn, self.IgnorarBtn,
                      self.GravarComentarioBtn):
            botao.IsEnabled = tem
        self.ComentarioBox.IsEnabled = tem
        self.AnteriorBtn.IsEnabled = bool(self.nos)
        self.ProximaBtn.IsEnabled = bool(self.nos)
        self.ProximaPendenteBtn.IsEnabled = bool(self.ordem)
        if not tem:
            self.mostrar_imagem(None)
            self.mostrar_recado(None)
            self.mostrar_situacao(None)
            self._mostrar_lado_b(True)
            self.LadoALabel.Text = u'Escolha um item na lista.'
            self.LadoBRotulo.Text = u'ELEMENTO B'
            self.LadoBLabel.Text = u'—'
            self.StatusAlvoLabel.Text = ''
            self.ComentarioBox.Text = ''
            self.MarcaLabel.Text = ''
            return
        itens = [self.registro['conflitos'][k] for k in self.atual.chaves]
        primeiro = itens[0]
        self.mostrar_imagem(self.log_do_item(primeiro))
        if self.atual.tipo != 'grupo':
            self.marcar_aviso_lido(primeiro)
        self.mostrar_recado(primeiro if self.atual.tipo != 'grupo' else None)
        self.mostrar_situacao(primeiro if self.atual.tipo != 'grupo' else None)
        if self.atual.tipo == 'grupo':
            self._mostrar_lado_b(True)
            if self.atual.no['nivel'] == ELEM_A:
                self.LadoALabel.Text = u'{} · {}'.format(
                    primeiro['a'].get('categoria', ''), curto(primeiro['a']))
            else:
                elementos_a = set(chave_do_lado(i['a']) for i in itens)
                self.LadoALabel.Text = u'{} · {} elemento(s) A'.format(
                    self.atual.Titulo, len(elementos_a))
            self.LadoBRotulo.Text = u'{} DO GRUPO — {}'.format(
                u'APONTAMENTOS' if self.fonte == 'log' else u'CONFLITOS',
                len(itens))
            linhas_b = [u'• {}{} ({})'.format(
                curto(i['a']),
                u' × ' + curto(i['b']) if i.get('b') else
                u' — ' + (i.get('medida') or ''),
                ROTULO.get(situacao(i)))
                for i in itens[:MAX_LINHAS_B]]
            if len(itens) > MAX_LINHAS_B:
                linhas_b.append(u'… e mais {}'.format(
                    len(itens) - MAX_LINHAS_B))
            self.LadoBLabel.Text = u'\n'.join(linhas_b)
            self.StatusAlvoLabel.Text = u'A marcação se aplica aos {} conflitos do grupo.'.format(
                len(itens))
            self.ComentarioBox.Text = ''
            self.MarcaLabel.Text = u'O comentário será registrado em todos os ' \
                u'conflitos do grupo.'
        else:
            self.mostrar_lados(primeiro)
            if self.fonte == 'log':
                # o texto já está no cartão do recado: aqui basta a situação
                origem = (self.log_do_item(primeiro) or {}).get('origem') or {}
                veio = u' Origem: relatório {}. As marcações são ' \
                       u'sincronizadas com ele.'.format(self.nome_da_origem(origem)) \
                    if origem.get('arquivo') else u''
                self.StatusAlvoLabel.Text = u'Agora: {}.{}'.format(
                    ROTULO.get(situacao(primeiro)), veio)
                # a resposta anterior está na CONVERSA; a caixa é para a nova
                self.ComentarioBox.Text = ''
                self.preencher_resposta(primeiro)
            else:
                achado = u'{}: {}. '.format(primeiro['regra'],
                                            primeiro.get('medida') or '') \
                    if primeiro.get('regra') else u''
                # voltou a aparecer depois de resolvido: dizer, senao o
                # "pendente" de novo parece engano da ferramenta (v2.3)
                virou = u''
                if primeiro.get('log_id'):
                    virou = u' Registrado como apontamento no LOG.'
                voltou = u''
                if primeiro.get('reaberto_em'):
                    antes = (primeiro.get('resolvido_antes_em') or
                             '').replace('T', ' ')[:16]
                    voltou = u' Reaberto: o conflito voltou a aparecer{}.'.format(
                        u' (estava resolvido em {})'.format(antes) if antes
                        else u'')
                self.StatusAlvoLabel.Text = u'{}Agora: {}.{}{}'.format(
                    achado, ROTULO.get(situacao(primeiro)), voltou, virou)
                # v2.5: conflito que ja virou apontamento mostra a CONVERSA —
                # a caixa e para a proxima fala, senao a mesma frase seria
                # mandada de novo como resposta
                self.ComentarioBox.Text = u'' if self.log_do_item(primeiro) \
                    else (primeiro.get('comentario') or '')
                self.preencher_resposta(primeiro)
            if primeiro.get('quando'):
                self.MarcaLabel.Text = u'Última marca: {} em {}.'.format(
                    primeiro.get('por') or u'alguém',
                    primeiro['quando'].replace('T', ' ')[:16])
            else:
                self.MarcaLabel.Text = ''

    def preencher_resposta(self, item):
        """O "Para" já vem com quem deve receber a resposta (06/10/2026):
        quem falou por último, ou quem criou o apontamento."""
        log = self.log_do_item(item)
        quem = responder_a(log, self.eu()) if log else u''
        self.ParaCombo.Text = self.nome_de_pessoa(quem) if quem else u''

    def mostrar_imagem(self, log):
        """A imagem do apontamento no painel; clicar abre no Windows."""
        caminho = ''
        if log and log.get('imagem'):
            caminho = log_disco.caminho_da_imagem(self.pasta_log,
                                                  log['imagem'])
        self._imagem_atual = caminho if caminho and os.path.exists(caminho) \
            else ''
        if not self._imagem_atual:
            self.MiniaturaImagem.Visibility = Visibility.Collapsed
            return
        try:
            imagem = BitmapImage()
            imagem.BeginInit()
            # OnLoad: o arquivo não fica preso, e a pasta é compartilhada
            imagem.CacheOption = BitmapCacheOption.OnLoad
            imagem.UriSource = Uri(self._imagem_atual)
            imagem.EndInit()
            self.MiniaturaImagem.Source = imagem
            self.MiniaturaImagem.Visibility = Visibility.Visible
        except Exception as erro:
            self.MiniaturaImagem.Visibility = Visibility.Collapsed
            print(u'LOG: imagem não abriu ({})'.format(erro))

    # ------------------------------------------------------------- navegar

    def lados_do_alvo(self):
        lados = []
        vistos = set()
        for k in self.chaves_do_alvo():
            item = self.registro['conflitos'][k]
            # 'lados' só existe no LOG, onde o apontamento tem N elementos;
            # no relatório de interferências o achado é o par a × b
            for lado in (item.get('lados') or [item['a'], item.get('b')]):
                if not lado:
                    continue        # achado de um lado só (v1.5)
                chave_lado = chave_do_lado(lado)
                if chave_lado not in vistos:
                    vistos.add(chave_lado)
                    lados.append(lado)
        return lados

    def navegar(self, modo):
        # v1.7: cada lado leva o .rvt onde mora — o modelo aberto pode ser o
        # vínculo do relatório, e o evento decide se acha local ou vinculado
        do_relatorio = nome_do_arquivo((self._relatorio or {}).get('projeto'))
        lados = [dict(lado, arquivo=arquivo_de(lado, do_relatorio))
                 for lado in self.lados_do_alvo()]
        if not lados:
            return
        self.mostrar_status(u'Procurando {} elemento(s){}...'.format(
            len(lados), u' na "{}"'.format(NOME_3D) if modo == '3d' else ''))
        handler.folga = self.folga_do_zoom()     # combo Zoom (v2.3)
        handler.pedido = (modo, lados)
        evento.Raise()

    @protegido
    def ao_na_vista(self, sender, args):
        self.navegar('vista')

    @protegido
    def ao_3d(self, sender, args):
        self.navegar('3d')

    def andar(self, passo):
        """‹ › andam de GRUPO em grupo (v1.4), no nível do item atual.

        Conflito selecionado: o nível é o do grupo mais fundo (o dele).
        Sem seleção: o primeiro/último grupo do nível mais fundo.
        """
        if not self.nos:
            return
        if self.fonte == 'passes':
            # v1.6: no relatório de passes os grupos são Laje › Regra —
            # enormes; a seta anda por elemento (pedido do Thiago)
            self.andar_por_elemento(passo)
            return
        fundo = len(self.niveis()) - 1
        if self.atual is None:
            grupos = grupos_no_nivel(self.nos, fundo)
            self.ir_para_grupo(grupos[0] if passo > 0 else grupos[-1])
            return
        if self.atual.tipo == 'grupo':
            caminho = self.atual.caminho
        else:
            caminho = caminho_de(self.registro['conflitos'][
                self.atual.chaves[0]], self.niveis())
        alvo = grupo_vizinho(self.nos, caminho, passo)
        if alvo is None:
            alvo = grupos_no_nivel(self.nos, fundo)[0]
        self.ir_para_grupo(alvo)

    def andar_por_elemento(self, passo):
        """‹ › de conflito em conflito, na ordem da árvore do filtro atual;
        do cabeçalho de um grupo, › entra no 1º conflito dele."""
        folhas = [l['chave'] for l in achatar(self.nos, set(), True)
                  if l['tipo'] == 'conflito']
        if not folhas:
            return
        if self.atual is None:
            self.ir_para_chave(folhas[0] if passo > 0 else folhas[-1])
            return
        if self.atual.tipo == 'grupo':
            do_grupo = [l['chave'] for l in
                        achatar([self.atual.no], set(), True)
                        if l['tipo'] == 'conflito']
            if not do_grupo or do_grupo[0] not in folhas:
                return
            if passo > 0:
                self.ir_para_chave(do_grupo[0])
                return
            k = do_grupo[0]
        else:
            k = self.atual.chaves[0]
            if k not in folhas:
                self.ir_para_chave(folhas[0])
                return
        self.ir_para_chave(folhas[(folhas.index(k) + passo) % len(folhas)])

    def ir_para_grupo(self, caminho):
        """Abre o grupo (sanfona), seleciona e navega para ele inteiro."""
        self.abertos = set(cadeia(caminho))
        self.montar_lista(manter=('grupo', caminho))
        modo = self.modo_ao_escolher()
        if self.atual is not None and modo != 'nada':
            self.navegar(modo)

    @protegido
    def ao_anterior(self, sender, args):
        self.andar(-1)

    @protegido
    def ao_proxima(self, sender, args):
        self.andar(1)

    @protegido
    def ao_proxima_pendente(self, sender, args):
        k = proxima_pendente(self.registro, self.ordem_na_tela(),
                             self.referencia())
        if k is None:
            self.mostrar_status(u'Nenhum conflito pendente.', 'ok')
            return
        self.ir_para_chave(k)

    def ordem_na_tela(self):
        """v1.6 — a ordem da árvore, não a do HTML: o próximo pendente é o
        do mesmo grupo, e o grupo seguinte só quando este acaba."""
        return ordem_da_arvore(self.registro, self.ordem, self.niveis())

    def referencia(self):
        """De onde contar o "próximo": o conflito atual, ou o ÚLTIMO do
        grupo atual na árvore (marcar um grupo segue para depois dele)."""
        if self.atual is None:
            return None
        if self.atual.tipo == 'grupo':
            folhas = [l['chave'] for l in achatar([self.atual.no], set(), True)
                      if l['tipo'] == 'conflito']
            return folhas[-1] if folhas else None
        return self.atual.chaves[0]

    def ir_para_chave(self, k, navegar=True):
        """Abre os grupos até o conflito, seleciona e navega ('Ao escolher').

        `navegar=False`: só mostra — apontamento de outra obra não tem os
        elementos no modelo aberto (v3.2, aberto pelo balão)."""
        if k not in chaves_filtradas(self.registro, self.ordem, self.filtro(),
                                     self.busca()):
            # escondido pelo filtro: volta para Pendentes, sem busca — ou
            # Todos, se o conflito já foi resolvido (v3.1: vindo do LOG)
            alvo = 'ChipAbertos' if situacao(
                self.registro['conflitos'][k]) == PENDENTE else 'ChipTodos'
            self._montando = True
            for nome, _, _ in self.CHIPS:
                getattr(self, nome).IsChecked = nome == alvo
            self.BuscaBox.Text = ''
            self._montando = False
        item = self.registro['conflitos'][k]
        # sanfona: fecha o caminho do anterior, abre só o do novo
        self.abertos = set(caminhos_ate(item, self.niveis()))
        self.montar_lista(manter=('conflito', k))
        modo = self.modo_ao_escolher()
        if navegar and self.atual is not None and modo != 'nada':
            self.navegar(modo)

    # -------------------------------------------------------------- marcar

    def apontar_comentario(self, chaves, comentario, quando, para=(),
                           imagem=''):
        """Comentar num conflito CRIA um apontamento no LOG (v2.5).

        > "quando crio um comentário em uma interferência ele deve virar um
        >  apontamento... o que for feito no log deve ser um espelho"
        > (Thiago, 30/09/2026)

        O conflito guarda o `log_id` e o apontamento guarda a `origem`: do
        segundo comentário em diante a fala entra como RESPOSTA no mesmo
        apontamento, e marcar de qualquer lado marca os dois ([[_espelho]]).
        -> quantos apontamentos foram criados ou respondidos.
        """
        pasta = log_disco.pasta_do_log(self.caminho_do_modelo())
        do_relatorio = nome_do_arquivo((self._relatorio or {}).get('projeto'))
        feitos = 0
        for k in chaves:
            item = self.registro['conflitos'].get(k)
            if item is None:
                continue
            try:
                if self._apontar_conflito(pasta, k, item, comentario, quando,
                                          do_relatorio, para, imagem):
                    feitos += 1
            except Exception as erro:
                self.mostrar_status(
                    u'Comentário registrado no relatório, mas o apontamento '
                    u'não foi criado: {}'.format(erro), 'aviso')
                print(traceback.format_exc())
        if feitos:
            # o registro ganhou `log_id`: grava já, senão o próximo
            # comentário criaria OUTRO apontamento
            self.registro, _ = ifr_disco.gravar_registro(self.caminho,
                                                         self.registro)
        return feitos

    def _apontar_conflito(self, pasta, chave, item, comentario, quando,
                          do_relatorio, para=(), imagem=''):
        """Cria o apontamento do conflito, ou responde o que já existe."""
        existente = None
        if item.get('log_id'):
            existente = self.itens_log.get(item['log_id']) or \
                log_disco.ler_um(pasta, item['log_id'])
        if existente is not None:
            responder(existente, comentario, self.meu_nome(), quando,
                      novo_id(quando, self.meu_nome(), _sufixo()),
                      imagem=imagem)
            novos_para = self.quem_entra(existente, para)
            if novos_para:
                acrescentar_para(existente, novos_para)
            gravado, erro = log_disco.gravar(pasta, existente)
            self.itens_log[gravado['id']] = gravado
            if not erro:
                self.avisar_caixa(caixa.RESPOSTA, gravado, quando,
                                  texto=comentario, novos_para=novos_para,
                                  pasta=pasta)
            return not erro
        alvos = []
        for lado in (item['a'], item.get('b')):
            if not lado or not lado.get('id'):
                continue
            alvos.append({
                'arquivo': arquivo_de(lado, do_relatorio),
                'uniqueId': lado.get('uniqueId') or '',
                'elementId': lado['id'],
                'categoria': lado.get('categoria') or u'Elemento',
                'descricao': lado.get('descricao') or '',
                'ponto': lado.get('ponto'),
            })
        contexto = u'{}: {}'.format(item.get('regra') or u'Interferência',
                                    item.get('medida') or '') \
            if item.get('regra') else u'Interferência'
        novo = nova_ocorrencia(
            comentario, self.meu_nome(), quando,
            id_=novo_id(quando, self.meu_nome(), _sufixo()),
            autor_id=self.usuario_id(), alvos=alvos, para=para,
            imagem=imagem,
            modelo=(alvos[0]['arquivo'] if alvos else do_relatorio),
            vista=contexto, nivel=item.get('nivel') or '',
            origem=origem_do_conflito(self.caminho, chave))
        gravado, erro = log_disco.gravar(pasta, novo)
        if erro:
            raise RuntimeError(erro)
        item['log_id'] = gravado['id']
        self.itens_log[gravado['id']] = gravado
        log_disco.registrar_pessoa(pasta, self.usuario_id(), self.meu_nome(),
                                   quando)
        self.avisar_caixa(caixa.NOVO, gravado, quando, pasta=pasta)
        return True

    def espelhar_no_log(self, chaves, status, quando):
        """Relatório -> LOG: marcar o conflito marca o apontamento dele."""
        pasta = log_disco.pasta_do_log(self.caminho_do_modelo())
        for k in chaves:
            item = self.registro['conflitos'].get(k) or {}
            log_id = item.get('log_id')
            if not log_id:
                continue
            apontamento = self.itens_log.get(log_id) or \
                log_disco.ler_um(pasta, log_id)
            if apontamento is None:
                continue
            mudar_status(apontamento, DA_JANELA.get(status, ABERTA),
                         self.meu_nome(), quando)
            gravado, erro = log_disco.gravar(pasta, apontamento)
            if erro:
                self.mostrar_status(u'Marcado no relatório, mas o apontamento '
                                    u'{} não foi atualizado: {}'.format(
                                        log_id, erro), 'aviso')
                continue
            self.itens_log[log_id] = gravado

    def aplicar(self, status=None, comentario=None):
        chaves = self.chaves_do_alvo()
        if not chaves or not (self.caminho or self.fonte == 'log'):
            return
        if len(chaves) > CONFIRMAR_ACIMA_DE and not forms.alert(
                u'Marcar {} conflitos de uma vez?'.format(len(chaves)),
                yes=True, no=True):
            return
        quando = agora()
        referencia = self.referencia()
        # v2.5: para quem + print valem nas quatro abas
        para = self.para_escolhido() if comentario else []
        imagem = self.gravar_anexo(novo_id(quando, self.meu_nome(),
                                           _sufixo())) if comentario else ''
        if self.fonte == 'log':
            self.aplicar_no_log(chaves, status, comentario, quando, para,
                                imagem)
        for k in chaves:
            marcar(self.registro, k, status, comentario, self.meu_nome(),
                   quando)
        apontados = 0
        if self.fonte != 'log':
            if comentario:
                apontados = self.apontar_comentario(chaves, comentario,
                                                    quando, para, imagem)
            if status is not None:
                self.espelhar_no_log(chaves, status, quando)
        if comentario:
            self.limpar_anexo()
            self.ParaCombo.Text = ''
        seguinte = None
        if status is not None and status != PENDENTE and \
                self.filtro() == F_PENDENTES:
            # a linha vai sumir da lista: segue para a próxima pendente NA
            # TELA — elemento a elemento dentro do grupo (v1.6)
            seguinte = proxima_pendente(self.registro, self.ordem_na_tela(),
                                        referencia)
        if self.fonte == 'log':
            erro = self._erro_log
        else:
            self.registro, erro = ifr_disco.gravar_registro(self.caminho,
                                                            self.registro)
        if seguinte is not None:
            self.ir_para_chave(seguinte)
        else:
            self.montar_lista()
        if erro:
            self.mostrar_status(u'Marcação feita na tela, mas não gravada em {}: '
                                u'{}'.format(ifr_disco.caminho_do_registro(
                                    self.caminho), erro), 'erro')
        elif seguinte is None or self.modo_ao_escolher() == 'nada':
            self.mostrar_status(u'{} conflito(s) marcado(s){}{}.'.format(
                len(chaves), u' como ' + ROTULO[status] if status else '',
                u' · {} apontamento(s) no LOG do projeto'.format(apontados)
                if apontados else ''), 'ok')

    @protegido
    def ao_pendente(self, sender, args):
        self.aplicar(PENDENTE)

    @protegido
    def ao_resolvido(self, sender, args):
        self.aplicar(RESOLVIDO)

    @protegido
    def ao_ignorar(self, sender, args):
        self.aplicar(IGNORAR)

    @protegido
    def ao_gravar_comentario(self, sender, args):
        texto = (self.ComentarioBox.Text or '').strip()
        if not texto and self._anexo:
            texto = u'(imagem)'      # só a imagem também é resposta
        if not texto:
            self.mostrar_status(u'Escreva o comentário ou anexe uma imagem.',
                                'aviso')
            return
        self.aplicar(comentario=texto)


#: cronômetro da auditoria de lentidão — sem o arquivo-chave, não faz nada
log_tempos.instrumentar(InterferenciasWindow, ifr_disco, log_disco)


def main(uiapp):
    """Sobe a janela — ou traz para a frente a que já está aberta.

    Import roda UMA vez por motor: `_JANELA_ABERTA` nos globais deste módulo
    sobrevive entre cliques ([[api-pyrevit-motor]]).
    """
    try:
        aberta = globals().get('_JANELA_ABERTA')
        if aberta is not None:
            try:
                aberta.Activate()
                aberta.abrir_do_aviso()
                return
            except Exception as erro:
                print(u'Janela anterior perdida ({}); abrindo outra.'.format(
                    erro))
        janela = InterferenciasWindow(uiapp)
        globals()['_JANELA_ABERTA'] = janela
        janela.Show()
        janela.abrir_do_aviso()
        janela.ligar_avisos()
    except Exception as erro:
        saida = script.get_output()
        saida.print_md(u'**Erro ao abrir Interferências:** {}'.format(erro))
        saida.print_md('```\n{}\n```'.format(traceback.format_exc()))
