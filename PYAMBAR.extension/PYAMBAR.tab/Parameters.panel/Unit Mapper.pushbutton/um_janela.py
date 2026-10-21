# -*- coding: utf-8 -*-
__title__ = "Unit\nMapper"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "3.5"

# v3.4 (16/09/2026) — pedido do Thiago: instancia de Model Group entra nos
# escopos vista/projeto (categoria Internal), offset normaliza para 1'-6".

# v3.1 (14/09/2026) — pedido do Thiago: regras de parametros "como no Fluxo
# ARN" (horizontal PHASE Colgante, vertical Riser, grupo ARN TYP Typical),
# dentro e fora de grupos, e escopo selecao / vista / projeto inteiro.
# Motor puro em Snippets._regras_param; fatos em um_fatos, escopo em
# um_escopo, editor em um_regra. Prioridade: Regra > Ambiente > Fixo.
#
# v3.2 (14/09/2026) — "tornar essa aba nao modal": este arquivo e o
# um_janela.py, executado como MODULO pelo script.py (Snippets._janela_modeless;
# motivo em [[api-pyrevit-motor]]). A janela abre com Show(); gravar e liberar
# variacao vao por ExternalEvent (UnitMapperHandler); a config e salva ao
# aplicar e ao fechar; o resultado aparece na propria janela.
#
# v3.3 (15/09/2026) — auditoria do 1o uso no MIIQLUX: a instancia do Model
# Group recebe o valor DOMINANTE dos membros nos parametros que existem nos
# dois (e o que der para gravar nela); regra de grupo vence as outras;
# conexao/acessorio herdam a orientacao do tubo; linha so com bloqueio some
# da lista ("Mostrar bloqueados"); duplo clique navega e da zoom.

import codecs
import os
import sys
import traceback

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import (
    BuiltInParameter, ElementId, FilteredElementCollector, Group, Level,
    LocationCurve, LocationPoint, StorageType, SubTransaction, XYZ,
)
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI import ExternalEvent, IExternalEventHandler
from pyrevit import HOST_APP, forms, revit, script
from pyrevit.forms import WPFWindow

from System import Action as System_Action
from System.Collections.Generic import List
from System.Windows import Setter, Style, Thickness, VerticalAlignment, Visibility
from System.Windows.Controls import (
    Button, CheckBox, ComboBox, DataGridCell, DataGridLength,
    DataGridTextColumn, Orientation, StackPanel, TextBlock,
)
from System.Windows.Controls.Primitives import DataGridColumnHeader
from System.Windows.Data import Binding
from System.Windows.Media import VisualTreeHelper

PATH_SCRIPT = os.path.dirname(__file__)
if PATH_SCRIPT not in sys.path:
    sys.path.insert(0, PATH_SCRIPT)

from Snippets import _ambiente_match as amb
from Snippets._aranha_vistas import caixa as caixa_que_envolve
from Snippets import _regras_param as rp
from Snippets import _resumo_aplicar as resumo_aplicar
from Snippets import _room_match as rmatch
from Snippets import _wbs_config as wcfg
from Snippets import _wbs_engine as weng
from Snippets import _wbs_obra as wobra
from Snippets._comprimento_texto import (
    normalizar_texto, pes_para_texto, texto_para_pes)
from Snippets.data._csv_utilities import escrever_csv_utf8, ler_csv_utf8

import um_escopo
import um_fatos
import um_log
import um_obra
import um_regra

VISIVEL = Visibility.Visible
OCULTO = Visibility.Collapsed

doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()
PATH_PULLDOWN = os.path.dirname(PATH_SCRIPT)


# Configs antigos das 4 ferramentas do pulldown, em ordem de prioridade —
# lidos so na primeira execucao, para montar a config unificada.
FONTES_LEGADO = wcfg.fontes_legado(
    PATH_PULLDOWN, seed_proprio=os.path.join(PATH_SCRIPT, 'config.json'))


# ── helpers Revit ─────────────────────────────────────────────────────────────

def get_element_id_value(eid):
    return eid.Value if hasattr(eid, 'Value') else eid.IntegerValue


def normalizar_campo(caixa):
    """Campo de comprimento no formato do Revit (1.5 -> 1'-6"); texto que nao
    se entende fica como esta, para o usuario ver o erro."""
    normalizado = normalizar_texto(caixa.Text)
    if normalizado is not None and normalizado != caixa.Text:
        caixa.Text = normalizado


def _coletar_membros(grupo, acumulador, vistos):
    """Membros de um Group, descendo em grupos aninhados (como a Paleta faz).

    A versao antiga descia UM nivel so: elemento dentro de grupo-dentro-de-grupo
    ficava de fora da selecao em silencio.
    """
    for mid in grupo.GetMemberIds():
        chave = get_element_id_value(mid)
        if chave in vistos:
            continue
        membro = doc.GetElement(mid)
        if not membro:
            continue
        vistos.add(chave)
        acumulador.append(membro)
        if isinstance(membro, Group):
            _coletar_membros(membro, acumulador, vistos)


def coletar_selecao(elementos):
    """(normais, membros_de_grupo) — a divisao que a Paleta de Parametros usa.

    O Group continua na lista principal (ele proprio recebe os parametros) e os
    membros vao para a segunda lista, onde so vale escrever parametro que varia
    entre instancias de grupo.
    """
    normais = []
    membros = []
    vistos = set()

    for el in elementos:
        chave = get_element_id_value(el.Id)
        if chave in vistos:
            continue
        vistos.add(chave)
        normais.append(el)
        if isinstance(el, Group):
            _coletar_membros(el, membros, vistos)

    return normais, membros


def get_element_span(element):
    """(z_min, z_max) em pes. Bounding box primeiro — cobre laje, parede e
    fundacao sketch-based, que nao tem Location. Sem nada: None."""
    try:
        bb = element.get_BoundingBox(None)
    except Exception:
        bb = None
    if bb is not None:
        return (bb.Min.Z, bb.Max.Z)

    try:
        loc = element.Location
    except Exception:
        return None
    if isinstance(loc, LocationCurve):
        z0 = loc.Curve.GetEndPoint(0).Z
        z1 = loc.Curve.GetEndPoint(1).Z
        return (min(z0, z1), max(z0, z1))
    if isinstance(loc, LocationPoint):
        z = loc.Point.Z
        return (z, z)
    return None


def esta_em_grupo(element):
    try:
        gid = element.GroupId
    except Exception:
        return False
    return gid is not None and get_element_id_value(gid) != -1


def diagnosticar_param(element, nome, dentro_de_grupo):
    """(param, problema, definicao_travada). problema=None quando da para gravar.

    Cobre o caso silencioso do §8 do CLAUDE.md: elemento dentro de Model Group
    com parametro que nao pode variar por instancia de grupo — o Revit rejeita
    a escrita, e antes isso virava so '+1 erro' sem motivo. Quando o bloqueio e
    esse, devolve a InternalDefinition para o botao "Liberar variacao por grupo".
    """
    try:
        p = element.LookupParameter(nome)
    except Exception as e:
        return None, "erro ao ler '{}': {}".format(nome, e), None

    if not p:
        return None, "parametro '{}' nao existe no elemento".format(nome), None
    if p.IsReadOnly:
        return None, "parametro '{}' e read-only".format(nome), None
    if p.StorageType not in (StorageType.String, StorageType.Integer):
        return None, "parametro '{}' nao e texto nem inteiro".format(nome), None

    if dentro_de_grupo:
        definicao = p.Definition
        varia = getattr(definicao, 'VariesAcrossGroups', None)
        if varia is False:
            return None, ("parametro '{}' nao varia entre instancias de grupo "
                          "(marque 'Values can vary by group instance')".format(nome)), definicao

    return p, None, None


def liberar_variacao_por_grupo(definicoes, documento=None):
    """Liga 'Values can vary by group instance' — SetAllowVaryBetweenGroups.

    Altera o binding do parametro no PROJETO INTEIRO, nao no grupo nem no
    elemento: chamar isso e uma decisao do usuario, nunca automatica.
    Devolve (liberados, falhas) com os nomes.
    """
    liberados = []
    falhas = []
    for nome, definicao in definicoes.items():
        try:
            definicao.SetAllowVaryBetweenGroups(documento or doc, True)
            liberados.append(nome)
        except Exception as e:
            falhas.append((nome, str(e)))
    return liberados, falhas


def executar_em_transacao(nome, funcao, documento=None):
    """Roda funcao() na transacao certa — SubTransaction se o doc ja estiver
    modificavel (padrao da Paleta de Parametros), Transaction normal se nao."""
    documento = documento or doc
    if documento.IsModifiable:
        sub = SubTransaction(documento)
        sub.Start()
        try:
            resultado = funcao()
            sub.Commit()
            return resultado
        except Exception:
            sub.RollBack()
            raise
        finally:
            sub.Dispose()

    with revit.Transaction(nome, doc=documento):
        return funcao()


def gravar_param(param, valor):
    try:
        if param.StorageType == StorageType.Integer:
            param.Set(int(valor))
        else:
            param.Set(str(valor))
        return True, None
    except Exception as e:
        return False, str(e)


def get_revit_levels():
    niveis = [(lv.Name, lv.Elevation)
              for lv in FilteredElementCollector(doc).OfClass(Level)]
    niveis.sort(key=lambda par: par[1])
    return niveis


def collect_param_names(elementos, limite=300):
    """Parametros de texto/inteiro editaveis presentes na selecao — alimenta os
    combos da aba Configuracoes. Varre no maximo `limite` elementos: a lista so
    precisa cobrir os tipos presentes, nao contar ocorrencias."""
    nomes = set()
    visitados = elementos[:limite]
    falhas = []
    for el in visitados:
        try:
            for p in el.Parameters:
                if p.IsReadOnly or p.Definition is None:
                    continue
                if p.StorageType in (StorageType.String, StorageType.Integer):
                    nome = p.Definition.Name
                    if nome:
                        nomes.add(nome)
        except Exception as e:
            falhas.append(str(e))

    # lista vazia porque TODOS falharam nao e o mesmo que "nao ha parametros":
    # sem isso os combos apareceriam vazios sem explicacao
    if visitados and len(falhas) == len(visitados):
        output.print_md("**Aviso:** nao foi possivel ler os parametros da selecao "
                        "({}). Os combos da aba Configuracoes ficam so com os "
                        "nomes salvos.".format(falhas[0]))
    return sorted(nomes)


def amostra_por_tipo(elementos, limite=400):
    """Um elemento por (categoria, tipo), ate `limite` — os parametros sao os
    do tipo. Antes a lista vinha dos 300 PRIMEIROS elementos: no projeto
    inteiro, 300 tubos iguais escondiam os parametros das outras categorias
    (achado da auditoria de 14/09/2026)."""
    vistos = set()
    amostra = []
    for el in elementos:
        try:
            categoria = el.Category.Name if el.Category is not None else ''
            chave = (categoria, get_element_id_value(el.GetTypeId()))
        except Exception:
            chave = ('', id(el))
        if chave in vistos:
            continue
        vistos.add(chave)
        amostra.append(el)
        if len(amostra) >= limite:
            break
    return amostra


# ── itens de UI (atributos simples: o binding TwoWay do WPF escreve neles) ─────

class LevelItem(object):
    def __init__(self, name, elev_ft, wbs_value, centena=None):
        self.Name = name
        self.ElevDisplay = weng.format_elevation(elev_ft)
        self.WbsValue = wbs_value
        # 24/09/2026: centena dita, para Floor sem numero ("UDG"). Em branco
        # (o normal), a centena continua saindo do texto do Floor.
        self.Centena = u'' if centena is None else str(centena)
        self.elev_ft = elev_ft


class TipItem(object):
    def __init__(self, chave, valor):
        self.Chave = chave
        self.Valor = valor


class RegraItem(object):
    """Linha da tabela de regras especiais (aba Configuracoes)."""

    def __init__(self, regra=None):
        regra = regra or {}
        self.Pavimento = regra.get('pavimento', '')
        self.WbsMin = regra.get('wbs_min', '')
        self.WbsMax = regra.get('wbs_max', '')
        self.Wbs = regra.get('wbs', '')
        self.Tipologia = regra.get('tipologia', '')

    def como_dict(self):
        return {
            'pavimento': (self.Pavimento or '').strip(),
            'wbs_min': str(self.WbsMin or '').strip(),
            'wbs_max': str(self.WbsMax or '').strip(),
            'wbs': (self.Wbs or '').strip(),
            'tipologia': (self.Tipologia or '').strip(),
        }


class RegraParamItem(object):
    """Linha da aba Regras. `Ativa` e ligada TwoWay ao CheckBox."""

    def __init__(self, regra):
        self.regra = regra
        self.Ativa = bool(regra.get('ativa', True))
        self.atualizar()

    def atualizar(self, contagem=None, encobertas=None):
        self.regra = dict(self.regra, ativa=bool(self.Ativa))
        self.Nome = self.regra['nome'] or u'(sem nome)'
        self.Descricao = rp.descrever_regra(self.regra)
        # v3.4: a regra se explica na lista — aviso, prioridade e quantas pegou
        avisos = rp.avisos_da_regra(self.regra)
        # v3.5: "nenhuma peça" enganava quando outra regra decidia antes
        encoberta = (encobertas or {}).get(self.regra['nome'])
        if encoberta and self.Ativa:
            avisos.insert(0, u'Encoberta por "{}" em {} peça(s): ela grava o '
                          u'mesmo parâmetro antes. Suba esta regra com ↑ se ela '
                          u'é que deve valer.'.format(encoberta['por'],
                                                      encoberta['qtd']))
        self.Aviso = u'⚠ ' + u'  '.join(avisos) if avisos else u''
        self.TemAviso = bool(avisos)
        self.Prioridade = (u'prioridade: grupo'
                           if rp.prioridade_da_regra(self.regra) == 0 else u'')
        quantos = (contagem or {}).get(self.regra['nome'])
        if not self.Ativa:
            # o que enganou o Thiago: regra desativada parecia "nao pega nada"
            self.Casos = u'DESATIVADA'
        elif quantos:
            self.Casos = u'{} peça(s) na preview'.format(quantos)
        else:
            self.Casos = u'' if contagem is None else u'nenhuma peça'


_ORIGEM_TEXTO = {rp.ORIGEM_REGRA: u'regra', rp.ORIGEM_AMBIENTE: u'ambiente',
                 rp.ORIGEM_FIXO: u'fixo', rp.ORIGEM_MEMBROS: u'membros do grupo'}

#: v3.4 — colunas calculadas que o cadeado segura:
#: (chave do hold, campo da linha do motor, atributo da celula, rotulo)
_CALC_SEGURAVEIS = (('#detail', 'detail', 'WbsDetail', u'Floor'),
                    ('#wbs', 'wbs', 'WbsNum', u'Unit ID'),
                    ('#tipologia', 'tipologia', 'Tipologia', u'Type'))
_CHAVES_DIRECAO = [d for d, _ in amb.DIRECOES]
#: itens sem nada a explicar que ainda vao para o log, de amostra (v3.4)
_AMOSTRA_DE_ITENS = 25
_CADEADO = u'\U0001F512'
_CADEADO_ABERTO = u'\U0001F513'


class RoomItem(object):
    """Linha da tabela de rooms (aba Ambientes)."""

    def __init__(self, info, unit, floor, tipo, qtd, offset=u''):
        self.chave = info.get('chave')
        self.Offset = offset
        self.Numero = info['numero']
        self.Nome = info['nome']
        self.Nivel = info.get('nivel') or ''
        self.Elevacao = weng.format_elevation(info['elevacao'])
        self.Unit = unit or u'—'
        self.Floor = floor or u'—'
        self.Tipo = tipo or u'—'
        self.Origem = info['origem']
        self.Qtd = qtd


VAZIO = '---'


def _texto_celula(valor):
    """Valor calculado -> o que a celula mostra ('---' quando nao ha)."""
    if valor is None or valor == '':
        return VAZIO
    return str(valor)


def _valor_celula(texto):
    """O que a celula mostra -> valor a gravar (None quando vazia)."""
    limpo = (texto or '').strip()
    if not limpo or limpo == VAZIO:
        return None
    return limpo


def _ancestral(origem, tipo):
    """Sobe a arvore visual ate um `tipo` (DataGridCell). O clique pode cair
    num Run, que nao e Visual: nesse caso sobe pelo Parent logico."""
    atual = origem
    for _ in range(40):
        if atual is None or isinstance(atual, tipo):
            return atual
        try:
            atual = VisualTreeHelper.GetParent(atual)
        except Exception:
            atual = getattr(atual, 'Parent', None)
    return None


class PreviewItem(object):
    """Linha da preview. As tres colunas de valor sao editaveis: guardamos o
    calculado ao lado para saber, na hora do recalculo, o que o usuario mexeu."""

    def __init__(self, linha, element, problemas, de_grupo=False, manual=None,
                 calcular=True, decisoes=None, bloqueios=None, atuais=None,
                 divergencias=None, previstas=None, congelados=None):
        # v3.4: coluna segurada (cadeado) — o valor da foto substitui o
        # calculado, e o motivo que ele resolve deixa de travar a gravacao
        segurados = []
        if congelados:
            linha = dict(linha)
            for _chave, campo, _atributo, rotulo in _CALC_SEGURAVEIS:
                if campo in congelados:
                    linha[campo] = _valor_celula(congelados[campo])
                    segurados.append(rotulo)
            if 'detail' in congelados and linha['detail'] is not None:
                linha['motivo'] = None
            elif (linha['motivo'] == weng.MOTIVO_FORA_SEM_SUFIXO
                  and linha['wbs'] is not None):
                linha['motivo'] = None
        self.element = element
        self.element_id = element.Id
        self.linha = linha
        self.problemas = problemas
        self.de_grupo = de_grupo
        self.calcular = calcular
        # regras / fixos: so o que MUDA, e o que o Revit nao deixa gravar
        self.decisoes = decisoes or {}
        self.bloqueios = bloqueios or {}
        self.atuais = atuais or {}
        # v3.4: tudo que regras/fixos/membros dao, mude ou nao
        self.previstas = previstas or {}
        self.fixos_fora = set()     # fixos que nao descem para este membro

        self.ElemId = str(linha['id'])
        self.Origem = 'membro de grupo' if de_grupo else ''
        if isinstance(element, Group):
            self.Origem = 'grupo'
        self.ElevDisplay = linha['elev_display']

        self.calc_detail = _texto_celula(linha['detail'])
        self.calc_wbs = _texto_celula(linha['wbs'])
        self.calc_tipologia = _texto_celula(linha['tipologia'])

        # edicao manual da rodada anterior sobrepoe o calculado
        manual = manual or {}
        self.WbsDetail = manual.get('detail', self.calc_detail)
        self.WbsNum = manual.get('wbs', self.calc_wbs)
        self.Tipologia = manual.get('tipologia', self.calc_tipologia)
        self.Manual = 'M' if manual else ''

        motivo = linha['motivo']
        if not calcular:
            self.Situacao = ''
            self.Severidade = 'ok'
        elif motivo and not manual:
            self.Situacao = weng.MOTIVO_TEXTO.get(motivo, motivo)
            self.Severidade = 'erro'
        elif problemas:
            self.Situacao = problemas[0]
            self.Severidade = 'erro'
        elif manual:
            self.Situacao = 'editado à mão'
            self.Severidade = 'aviso'
        elif linha.get('regra'):
            self.Situacao = linha['regra']
            self.Severidade = 'ok'
        elif not linha['tipologia']:
            self.Situacao = 'sem entrada na tabela de Type'
            self.Severidade = 'aviso'
        else:
            self.Situacao = 'ok'
            self.Severidade = 'ok'

        extra = ''
        if self.bloqueios:
            nome = sorted(self.bloqueios)[0]
            extra = u'{} parâmetro(s) bloqueado(s) — {}'.format(
                len(self.bloqueios), self.bloqueios[nome])
            self.Severidade = 'aviso' if self.gravavel else 'erro'
        elif self.decisoes:
            extra = u'{} parâmetro(s) por regra/fixo'.format(len(self.decisoes))
        if extra:
            self.Situacao = (extra if self.Situacao in ('', 'ok')
                             else u'{} · {}'.format(self.Situacao, extra))
        if divergencias:
            # grupo: o valor que sobe e o dominante — dizer quantos discordam
            texto = u'membros divergem: {}'.format(u'; '.join(divergencias))
            self.Situacao = (texto if self.Situacao in ('', 'ok')
                             else u'{} · {}'.format(self.Situacao, texto))
            if self.Severidade == 'ok':
                self.Severidade = 'aviso'
        if segurados:
            texto = u'{} segurado(s)'.format(u', '.join(segurados))
            self.Situacao = (texto if self.Situacao in ('', 'ok')
                             else u'{} · {}'.format(self.Situacao, texto))
        if not self.Situacao:
            self.Situacao = u'sem mudança'

    def preencher_colunas(self, nomes):
        """P0..Pn (texto 'atual → novo') e T0..Tn (dica) para as colunas de
        parametro montadas em codigo na preview.

        v3.4 (pedido do Thiago): sem mudanca a celula nao fica em branco —
        mostra o que vai ficar ('= valor'); fixo que nao desce para membro de
        grupo diz por que."""
        for posicao, nome in enumerate(nomes):
            decisao = self.decisoes.get(nome)
            prevista = self.previstas.get(nome)
            if decisao is None and prevista is not None:
                texto = u'= {}'.format(prevista['valor'])
                dica = u'{}: {} — o elemento já tem este valor'.format(
                    _ORIGEM_TEXTO.get(prevista['origem'], prevista['origem']),
                    prevista['regra'])
            elif decisao is None and nome in self.fixos_fora:
                texto = u'—'
                dica = (u'Fixos desligados para membros de Model Group '
                        u'(aba Parâmetros fixos).')
            elif decisao is None:
                texto = dica = ''
            else:
                texto = u'{} → {}'.format(self.atuais.get(nome) or u'∅',
                                          decisao['valor'])
                dica = u'{}: {}'.format(
                    _ORIGEM_TEXTO.get(decisao['origem'], decisao['origem']),
                    decisao['regra'])
                if nome in self.bloqueios:
                    texto = u'⛔ ' + texto
                    dica = self.bloqueios[nome]
            setattr(self, 'P{}'.format(posicao), texto)
            setattr(self, 'T{}'.format(posicao), dica)

    def casa_com(self, busca):
        """Busca da aba Elementos (16/09/2026) — o que está na tela."""
        for texto in (self.ElemId, self.WbsDetail, self.WbsNum, self.Tipologia,
                      self.Origem, self.Situacao):
            if texto and busca in u'{}'.format(texto).lower():
                return True
        return False

    def edicoes(self):
        """{campo: texto} do que difere do calculado. {} se nada foi editado."""
        mudou = {}
        for campo, atual, calculado in (
                ('detail', self.WbsDetail, self.calc_detail),
                ('wbs', self.WbsNum, self.calc_wbs),
                ('tipologia', self.Tipologia, self.calc_tipologia)):
            texto = (str(atual) if atual is not None else '').strip()
            if texto != calculado:
                mudou[campo] = texto
        return mudou

    def valores_finais(self):
        """(detail, wbs, tipologia) a gravar — ja com a edicao manual."""
        return (_valor_celula(self.WbsDetail),
                _valor_celula(self.WbsNum),
                _valor_celula(self.Tipologia))

    @property
    def calc_gravavel(self):
        """Floor / Unit ID / Type podem ser gravados."""
        if not self.calcular or self.problemas:
            return False
        # linha editada a mao vale mesmo quando o calculo nao resolveu o
        # pavimento: e exatamente para esses casos que a edicao existe
        if self.linha['motivo'] and not self.edicoes():
            return False
        return any(v is not None for v in self.valores_finais())

    @property
    def gravaveis_regra(self):
        """{parametro: valor} das regras/fixos que o Revit deixa gravar."""
        return dict((nome, d['valor']) for nome, d in self.decisoes.items()
                    if nome not in self.bloqueios)

    @property
    def gravavel(self):
        return self.calc_gravavel or bool(self.gravaveis_regra)

    @property
    def so_bloqueado(self):
        """Nada a gravar POR CAUSA de bloqueio (read-only, parametro ausente,
        nao varia por grupo). Pedido do Thiago em 15/09: essas linhas sujam a
        analise — somem com "Mostrar bloqueados" desligado. Linha sem mudanca
        ou fora das faixas nao e bloqueio e continua."""
        return not self.gravavel and bool(self.problemas or self.bloqueios)


# ── janela ────────────────────────────────────────────────────────────────────

class WBSCompletoWindow(WPFWindow):

    def __init__(self, cfg, projeto, aviso_migracao, escopo, conflitos=None,
                 handler=None, evento=None):
        # caminho absoluto: rodando como modulo, o relativo seria resolvido
        # pela pasta do comando em execucao
        WPFWindow.__init__(self, os.path.join(PATH_SCRIPT, 'ui.xaml'))
        self.result = None
        # v3.3: o log nasce primeiro — tudo depois dele pode registrar
        self._log = um_log.LogDeSessao()
        self._conflitos = conflitos or {}
        self._handler = handler
        self._evento = evento
        self._doc_titulo = doc.Title
        self._amb_ativo = False
        self._pre_falhas = {}
        self._ids_falhas = []
        self._itens_aplicados = []
        self._calculados_aplicados = []
        self.Closing += self.ao_fechar
        self.escopo = escopo
        self._categorias_excluidas = set(
            cfg['prefs'].get('categorias_excluidas') or [])
        self._categorias_presentes = []
        self._fatos = {}            # {id: fatos estaticos}
        self._params_lidos = {}     # {id: {parametro: valor atual}}
        self._diag_regras = {}      # {(tipo, em_grupo, parametro): (problema, def)}
        self._n_colunas_regra = 0
        self._rooms = None          # indice de rooms (aba Ambientes)
        self._room_de = {}          # {id: item do indice | None}
        self._rooms_sujo = True
        self._amb_checks = []
        self._em_varios_rooms = []
        # v3.4 fora de room: caches refeitos a cada leitura de rooms
        self._vertical_de = {}
        self._perto_de = {}
        self._room_extra = {}
        self._vizinhos_cache = {}
        self._units_grupo = {}
        self._nomes_grupo = {}      # {GroupType: parametros gravaveis no grupo}
        self._coletar_escopo()
        self.cfg = cfg
        self.projeto = projeto
        self.prefs = cfg['prefs']
        self.itens = []
        self._cache_diag = {}
        self._diag_regras = {}
        self._defs_travadas = {}
        self._fixos = []            # [(combo_nome, combo_valor, check)]
        self._manuais = {}          # {element_id: {campo: texto digitado}}
        self._holds = {}            # v3.4 {coluna segurada: {element_id: foto}}
        self._fixos_da_rodada = {}
        self._floors_ordem = []     # Floors da aba, de baixo para cima
        self._tabela_tip = {}       # tabela de Type da rodada (unidade de cima)
        self._trecho_de = {}        # {id: trecho horizontal} — refeito no Reler
        self._usa_trecho = False
        self._topo_de = {}          # {id: room do topo da peça} (aranha)
        self._usa_topo = False
        self._encobertas = {}       # {regra: {'por', 'qtd'}} — casou e perdeu
        self._aninhados_fora = 0
        self._pronto = False

        # pavimentos: nivel do modelo + valor salvo (ou ordinal automatico)
        salvos = wcfg.levels_como_mapa(cfg)
        centenas_salvas = wcfg.centenas_por_nivel(cfg)
        self.level_items = [
            LevelItem(nome, elev, salvos.get(nome, weng.auto_ordinal(nome)),
                      centenas_salvas.get(nome))
            for nome, elev in get_revit_levels()
        ]
        self.FloorGrid.ItemsSource = self.level_items
        self.FloorInfo.Text = "{} níveis no modelo".format(len(self.level_items))

        # tipologia DO MODELO ABERTO — projeto novo comeca vazio de proposito
        tabela = wcfg.tipologia_do_projeto(cfg, projeto)
        self.tip_items = [TipItem(k, tabela[k])
                          for k in sorted(tabela, key=self._ordem_chave)]
        self._refresh_tip_grid()

        # regras especiais do modelo
        self.regra_items = [RegraItem(r) for r in wcfg.regras_do_projeto(cfg, projeto)]
        self._refresh_regras_grid()

        # parametros de destino (aba Configuracoes)
        nomes_disponiveis = collect_param_names(amostra_por_tipo(self.elementos))
        self.nomes_disponiveis = nomes_disponiveis
        for combo, pref in ((self.ParamDetailBox, 'param_detail'),
                            (self.ParamWbsBox, 'param_wbs'),
                            (self.ParamTipologiaBox, 'param_tipologia')):
            atual = self.prefs[pref]
            opcoes = list(nomes_disponiveis)
            if atual and atual not in opcoes:
                opcoes.insert(0, atual)
            combo.ItemsSource = opcoes
            combo.Text = atual

        # preferencias
        self.SufixoBox.Text = str(self.prefs['sufixo'])
        self.OffsetBox.Text = pes_para_texto(self.prefs['offset_ft'])
        self.ChkIncrement.IsChecked = bool(self.prefs['incrementar'])
        self.ChkReiniciar.IsChecked = bool(self.prefs['reiniciar_por_pavimento'])
        self.ChkReiniciar.IsEnabled = bool(self.prefs['incrementar'])

        # parametros fixos: recarrega o ultimo CSV usado, com as escolhas
        self.ChkFixosGrupo.IsChecked = bool(self.prefs.get('fixos_em_grupo', True))
        self.csv_fixos = ''
        csv_salvo = self.prefs.get('fixos_csv') or ''
        if csv_salvo and os.path.exists(csv_salvo):
            self._carregar_csv_fixos(csv_salvo,
                                     self.prefs.get('fixos_valores') or {},
                                     self.prefs.get('fixos_ativos') or [])
        else:
            if csv_salvo:
                self.FixosCsvLabel.Text = "CSV anterior não encontrado: {}".format(csv_salvo)
            self._atualizar_info_fixos()

        self.CfgProjetoLabel.Text = "Modelo aberto: {}".format(projeto or '(sem nome)')
        self.CfgArquivoLabel.Text = u'{}\nLog da sessão: {}'.format(
            wcfg.caminho_config(), um_log.CAMINHO)

        self._aviso = aviso_migracao
        self._atualizar_rodape()
        self.ConfigLabel.ToolTip = wcfg.caminho_config()

        # v3.1: escopo, calcular, regras de parametros
        for _chave, rotulo in um_escopo.ESCOPOS:
            self.EscopoCombo.Items.Add(rotulo)
        self.EscopoCombo.SelectedIndex = [c for c, _ in um_escopo.ESCOPOS].index(
            self.escopo)
        self.ChkCalcular.IsChecked = bool(self.prefs.get('calcular', True))
        self.ChkSoMudancas.IsChecked = bool(self.prefs.get('so_mudancas'))
        self.ChkMostrarBloqueados.IsChecked = bool(self.prefs.get('mostrar_bloqueados'))
        self._reorganizar_abas()
        self._indice_situacao = self.PreviewGrid.Columns.Count - 1
        # Floor, Unit ID, Type (ordem do ui.xaml) — o cabecalho ganha o cadeado
        self._colunas_calc = [self.PreviewGrid.Columns[i] for i in (2, 3, 4)]
        self.rp_items = [RegraParamItem(r) for r in rp.normalizar_regras(
            wcfg.regras_param_do_projeto(cfg, projeto))]
        self._refresh_rp()

        # aba Ambientes
        self.ChkUsarAmbientes.IsChecked = bool(self.prefs.get('amb_usar'))
        self.FonteUnitCombo.Items.Add(u'Sufixo')
        self.FonteUnitCombo.Items.Add(u'Ambiente')
        self.FonteUnitCombo.SelectedIndex = (
            1 if self.prefs.get('unit_fonte') == 'ambiente' else 0)
        self._rotular_sufixo()
        self.ChkRoomsLinks.IsChecked = bool(self.prefs.get('amb_links', True))
        self.ChkRoomsVista.IsChecked = bool(self.prefs.get('amb_vista'))
        for _, rotulo in amb.DIRECOES:
            self.RoomDirecaoCombo.Items.Add(rotulo)
        self.RoomDirecaoCombo.SelectedIndex = 0
        self._amb_offsets = wcfg.offsets_de_ambiente_do_projeto(cfg, projeto)
        self._nao_migrar = set(self.prefs.get('grupo_nao_migrar') or [])
        self.ChkAutoUnit.IsChecked = bool(self.prefs.get('amb_auto', True))
        self.AutoLimiteBox.Text = pes_para_texto(
            self.prefs.get('amb_auto_limite_ft', amb.LIMITE_PROXIMO_PADRAO))
        for nome in (u'Unit ID', amb.PARAM_NUMERO, amb.PARAM_NOME):
            self.ParamUnitRoomBox.Items.Add(nome)
        self.ParamUnitRoomBox.Text = self.prefs.get('amb_param_unit') or u'Unit ID'
        self._amb_copiar_salvos = set(self.prefs.get('amb_copiar') or [])
        # 21/10/2026: regras, Type, Floors, nomes de parametro e offsets de
        # ambiente sao DA OBRA. Carregado depois de tudo porque SOBREPOE o que
        # veio do APPDATA.
        self._carregar_obra()
        self.AmbInfo.Text = (u'Marque "Usar ambientes" e clique em "Ler ambientes" '
                             u'para ver quantos elementos caem em algum room.')

        self._log.registrar(
            'abertura', versao=__version__, documento=doc.Title, projeto=projeto,
            escopo=self.escopo, normais=len(self.normais),
            membros=len(self.membros), aviso_migracao=aviso_migracao,
            config=wcfg.caminho_config(), log=um_log.CAMINHO)
        self._pronto = True
        self._recalcular()

    # ── leitura dos campos ────────────────────────────────────────────────────

    @staticmethod
    def _ordem_chave(chave):
        """Ordena 102 antes de 1015 quando ambos sao numericos."""
        try:
            return (0, int(chave), '')
        except (TypeError, ValueError):
            return (1, 0, str(chave))

    def _parse_sufixo(self):
        try:
            return int(self.SufixoBox.Text.strip())
        except (ValueError, AttributeError):
            return None

    def _parse_offset(self):
        """Pes. Aceita 0.1" 0.1' 1'-6" 1 1/2" 3 in; numero puro = pes
        (Snippets._comprimento_texto — antes so float, 15/09/2026)."""
        try:
            return texto_para_pes(self.OffsetBox.Text)
        except Exception:
            return None

    def tabela_tipologia(self):
        tabela = {}
        for item in self.tip_items:
            chave = weng.normalizar_chave_wbs(item.Chave)
            if chave:
                tabela[chave] = (item.Valor or '').strip()
        return tabela

    def _ranges(self):
        return weng.build_ranges([(i.elev_ft, (i.WbsValue or '').strip())
                                  for i in self.level_items
                                  if (i.WbsValue or '').strip()])

    def _centenas(self):
        """{texto do Floor: centena} da grade — o que foi digitado agora.

        Chaveado pelo Floor, nao pelo Level: dois niveis podem dividir o mesmo
        Floor, e quem numera o Unit ID e o Floor.
        """
        mapa = {}
        for item in self.level_items:
            floor = (item.WbsValue or '').strip()
            centena = wcfg.normalizar_centena(getattr(item, 'Centena', ''))
            if floor and centena is not None:
                mapa[floor] = centena
        return mapa

    def _nomes_params(self):
        """Nomes escolhidos na aba Configuracoes; combo vazio cai na pref."""
        def do_combo(combo, pref):
            texto = (combo.Text or '').strip()
            return texto or self.prefs[pref]

        return (do_combo(self.ParamDetailBox, 'param_detail'),
                do_combo(self.ParamWbsBox, 'param_wbs'),
                do_combo(self.ParamTipologiaBox, 'param_tipologia'))

    # ── diagnostico de parametros (antes da Transaction) ──────────────────────

    def _problemas_do_elemento(self, element):
        """Problemas de escrita nos 3 parametros. Cache por (tipo, em grupo) —
        elementos do mesmo tipo expoem os mesmos parametros."""
        em_grupo = esta_em_grupo(element)
        try:
            type_id = get_element_id_value(element.GetTypeId())
        except Exception:
            type_id = -1

        # elemento sem tipo (-1) nao pode compartilhar cache com outro sem tipo:
        # nada garante que exponham os mesmos parametros
        chave = (type_id, em_grupo) if type_id != -1 else None
        if chave is not None and chave in self._cache_diag:
            problemas, travadas = self._cache_diag[chave]
            # o cache tambem devolve as definicoes travadas: sem isso o botao
            # "Liberar variacao por grupo" sumiria a partir do 2o elemento
            self._defs_travadas.update(travadas)
            return problemas

        problemas = []
        travadas = {}
        for nome in self._nomes_params():
            _, problema, travada = diagnosticar_param(element, nome, em_grupo)
            if problema:
                problemas.append(problema)
            if travada is not None:
                travadas[nome] = travada

        self._defs_travadas.update(travadas)
        if chave is not None:
            self._cache_diag[chave] = (problemas, travadas)
        return problemas

    # ── recalculo ─────────────────────────────────────────────────────────────

    def _recalcular(self):
        if not self._pronto:
            return

        calcular = bool(self.ChkCalcular.IsChecked)
        self._defs_travadas = {}
        usar_amb = self._usar_ambientes()
        # guardado: _fatos_de roda por elemento e nao pode normalizar as
        # regras a cada chamada
        self._amb_ativo = usar_amb
        if usar_amb:
            ler_de_novo = self._rooms_sujo or self._rooms is None
            self._garantir_ambientes()
            if ler_de_novo:
                self._registrar_ambientes()
        unit_amb = calcular and self._unit_pelo_ambiente()
        param_unit = (self.ParamUnitRoomBox.Text or '').strip() or u'Unit ID'
        nome_type = self._nomes_params()[2]
        # sem "Calcular", fonte, sufixo e offset nao fazem nada: nao enganar
        # o offset fica ativo: tambem acha o room, com ou sem "Calcular"
        for controle in (self.FonteUnitCombo, self.SufixoBox, self.ChkIncrement):
            controle.IsEnabled = calcular
        self.ChkReiniciar.IsEnabled = calcular and bool(self.ChkIncrement.IsChecked)
        self._ajustar_checks_reservados(calcular)

        fontes_auto = {}
        if calcular:
            sufixo = self._parse_sufixo()
            offset = self._parse_offset()
            # Unit ID pelo ambiente: o sufixo so serve para quem ficou fora de
            # room — em branco, esses ficam sem Unit ID, a preview nao trava
            if offset is None or (sufixo is None and not unit_amb):
                campo = 'Offset' if offset is None else 'Sufixo'
                self._sem_preview("{} inválido — corrija para continuar.".format(campo))
                return
            ranges = self._ranges()
            if not ranges:
                self._sem_preview("Nenhum nível com Floor preenchido — veja a aba "
                                  "Floors, ou desligue \"Calcular Floor / Unit ID / "
                                  "Type\" para usar só as regras.")
                return

            auto_unit = unit_amb and bool(self.ChkAutoUnit.IsChecked)
            self._units_grupo = self._units_por_grupo(param_unit) if auto_unit else {}
            registros = []
            for el in self.elementos:
                span = get_element_span(el)
                registro = {
                    'id': get_element_id_value(el.Id),
                    'z_min': span[0] if span else None,
                    'z_max': span[1] if span else None,
                }
                if unit_amb:
                    info = self._room_de.get(registro['id'])
                    unidade = amb.unit_do_room(info, param_unit)
                    if unidade:
                        valores = info['valores']
                        registro['unit_ambiente'] = unidade
                        registro['type_ambiente'] = (valores.get(nome_type)
                                                     or valores.get('Type', ''))
                        registro['room_rotulo'] = info['rotulo']
                    else:
                        auto = (self._unit_fora_do_room(el, registro['id'],
                                                        param_unit, nome_type)
                                if auto_unit else None)
                        if auto:
                            fonte = auto.pop('fonte')
                            fontes_auto[fonte] = fontes_auto.get(fonte, 0) + 1
                            registro.update(auto)
                        else:
                            registro['fora_ambiente'] = True
                registros.append(registro)

            linhas = weng.atribuir(
                registros, ranges,
                sufixo=sufixo,
                incrementar=bool(self.ChkIncrement.IsChecked),
                reiniciar_por_pavimento=bool(self.ChkReiniciar.IsChecked),
                offset_ft=offset,
                tipologia=self.tabela_tipologia(),
                regras=self.regras_como_dicts(),
                centenas=self._centenas(),
            )
        else:
            linhas = [{'id': get_element_id_value(el.Id), 'elev_display': '',
                       'detail': None, 'wbs': None, 'tipologia': None,
                       'motivo': None, 'regra': None}
                      for el in self.elementos]

        self._absorver_edicoes()

        regras = self.regras_param_ativas()
        self._usa_trecho = rp.precisa_de_trecho(regras)
        self._usa_topo = rp.precisa_de_ambiente_topo(regras)
        self._encobertas = {}   # regra que casou e perdeu para outra antes
        self._tabela_tip = self.tabela_tipologia()   # Type da unidade de cima
        self._floors_ordem = []
        for _baixo, _alto, floor in self._ranges():
            if floor not in self._floors_ordem:
                self._floors_ordem.append(floor)
        fixos = self.valores_fixos()
        fixos_grupo = self.valores_fixos_para_grupo()
        reservados = set(self._nomes_params()) if calcular else set()
        copiar = self._amb_copiar() if usar_amb else []
        segurados = set(k for k in self._holds if not k.startswith('#'))
        nomes = rp.parametros_usados(regras) | set(fixos) | set(copiar) | segurados
        nomes_calc = self._nomes_params()
        self._fixos_da_rodada = fixos

        qtd_normais = len(self.normais)
        ids_no_escopo = set(get_element_id_value(el.Id) for el in self.elementos)
        # v3.3: {id do grupo: {parametro: [valor de cada membro]}}. Os membros
        # vem DEPOIS do seu grupo na lista (coletar_selecao desce em
        # profundidade): de tras para frente, todo grupo acha os seus prontos.
        dos_membros = {}
        itens = [None] * len(self.elementos)
        for i in reversed(range(len(self.elementos))):
            linha, el = linhas[i], self.elementos[i]
            de_grupo = i >= qtd_normais
            eh_grupo = isinstance(el, Group)
            consolidados, divergencias = {}, []
            if eh_grupo:
                consolidados, divergencias = self._consolidar_membros(
                    dos_membros.pop(linha['id'], {}), linha, calcular, nomes_calc)
            congelados = self._congelados_calc(linha['id']) if calcular else {}
            problemas = (self._problemas_do_elemento(el)
                         if calcular and (linha['motivo'] is None or congelados)
                         else [])
            decisoes, bloqueios, atuais, previstas = self._decisoes(
                el, linha, regras, fixos_grupo if de_grupo else fixos,
                nomes | set(consolidados), reservados, copiar, consolidados,
                self._congelados_param(linha['id']))
            item = PreviewItem(
                linha, el, problemas,
                de_grupo=de_grupo,
                manual=self._manuais.get(linha['id']) if calcular else None,
                calcular=calcular, decisoes=decisoes, bloqueios=bloqueios,
                atuais=atuais, divergencias=divergencias,
                previstas=previstas, congelados=congelados)
            if de_grupo:
                item.fixos_fora = set(fixos) - set(fixos_grupo)
            itens[i] = item
            if not eh_grupo:
                self._subir_para_grupos(el, item, dos_membros, ids_no_escopo,
                                        nomes_calc)
        self.itens = itens

        self._montar_colunas_de_regra()
        self._aplicar_filtro()
        # a aba Regras mostra quantas cada uma pegou, sem perder a selecao
        self._refresh_rp(self.RegrasParamList.SelectedItem, recalcular=False)

        gravaveis = sum(1 for i in self.itens if i.gravavel)
        partes = [u'{}: {} elemento(s)'.format(
            dict(um_escopo.ESCOPOS)[self.escopo], len(self.elementos))]
        if calcular:
            resumo = weng.resumir(linhas)
            # uma linha editada a mao pode ser gravavel sem ter pavimento
            # calculado — nao existe bloqueio negativo
            bloqueados = max(0, sum(1 for i in self.itens if i.problemas))
            partes.append("{} com Floor".format(resumo['com_pavimento']))
            if resumo[weng.MOTIVO_FORA_DAS_FAIXAS]:
                partes.append("{} fora das faixas".format(resumo[weng.MOTIVO_FORA_DAS_FAIXAS]))
            if resumo[weng.MOTIVO_SEM_GEOMETRIA]:
                partes.append("{} sem geometria".format(resumo[weng.MOTIVO_SEM_GEOMETRIA]))
            if resumo[weng.MOTIVO_DETAIL_SEM_NUMERO]:
                partes.append("{} sem número no Floor".format(resumo[weng.MOTIVO_DETAIL_SEM_NUMERO]))
            if bloqueados:
                partes.append("{} com parâmetro bloqueado".format(bloqueados))
            if resumo['sem_tipologia']:
                partes.append("{} sem Type".format(resumo['sem_tipologia']))
        if usar_amb:
            dentro = sum(1 for el in self.elementos
                         if self._room_de.get(get_element_id_value(el.Id)))
            partes.append(u'{} dentro de room'.format(dentro))
            if fontes_auto:
                partes.append(u'fora de room resolvidos: {}'.format(u', '.join(
                    u'{} {}'.format(fontes_auto[f], f)
                    for f in amb.FONTES_AUTO if f in fontes_auto)))
        com_regra = sum(1 for i in self.itens if i.decisoes)
        if regras or fixos:
            partes.append(u'{} com mudança por regra/fixo'.format(com_regra))
        travados_regra = sum(1 for i in self.itens if i.bloqueios)
        if travados_regra:
            partes.append(u'{} com parâmetro de regra bloqueado'.format(travados_regra))
        grupos_dos_membros = sum(
            1 for i in self.itens
            if any(d['origem'] == rp.ORIGEM_MEMBROS for d in i.decisoes.values()))
        if grupos_dos_membros:
            partes.append(u'{} grupo(s) recebendo dos membros'.format(grupos_dos_membros))
        ocultos = sum(1 for i in self.itens if i.so_bloqueado)
        if ocultos and not self.ChkMostrarBloqueados.IsChecked:
            partes.append(u'{} só com bloqueio (ocultos)'.format(ocultos))
        if self.membros and fixos and not fixos_grupo:
            # a config do 1o uso tinha isso desligado e parecia bug
            partes.append(u'fixos NÃO vão para membros de grupo (aba Parâmetros fixos)')

        if self._aninhados_fora:
            partes.append(u'{} peça(s) aninhada(s) fora (o Revit não deixa '
                          u'gravar nelas)'.format(self._aninhados_fora))
        if self.membros:
            partes.append("{} membros de grupo".format(len(self.membros)))
        if self._manuais:
            partes.append("{} editados à mão".format(len(self._manuais)))

        self.StatusLabel.Text = "  |  ".join(partes)
        self._registrar_preview(partes, gravaveis)
        self.ApplyBtn.IsEnabled = gravaveis > 0
        self.ApplyBtn.Content = "Aplicar ({})".format(gravaveis)

        self.LimparManuaisBtn.Visibility = VISIVEL if self._manuais else OCULTO

        travados = sorted(self._defs_travadas)
        self.LiberarBtn.Visibility = VISIVEL if travados else OCULTO
        if travados:
            self.LiberarBtn.ToolTip = (
                "Liga 'Values can vary by group instance' para: {}.\n"
                "Altera o parametro no PROJETO INTEIRO.".format(', '.join(travados)))

    # ── log da sessao (v3.3) ──────────────────────────────────────────────────

    def _config_para_log(self):
        """Tudo que o usuario escolheu e muda o resultado."""
        return {
            'escopo': self.escopo,
            'categorias_excluidas': sorted(self._categorias_excluidas),
            'calcular': bool(self.ChkCalcular.IsChecked),
            'unit_por': 'ambiente' if self._unit_pelo_ambiente() else 'sufixo',
            'sufixo': self.SufixoBox.Text,
            'offset_ft': self.OffsetBox.Text,
            'incrementar': bool(self.ChkIncrement.IsChecked),
            'reiniciar_por_floor': bool(self.ChkReiniciar.IsChecked),
            'so_mudancas': bool(self.ChkSoMudancas.IsChecked),
            'mostrar_bloqueados': bool(self.ChkMostrarBloqueados.IsChecked),
            'colunas_seguradas': sorted(self._holds),
            'parametros_calculados': list(self._nomes_params()),
            'floors': dict((i.Name, i.WbsValue or '') for i in self.level_items),
            'centenas': self._centenas(),
            'tabela_type': self.tabela_tipologia(),
            'regras_especiais': self.regras_como_dicts(),
            'regras': [{'ativa': bool(i.Ativa), 'nome': i.regra['nome'],
                        'descricao': rp.descrever_regra(i.regra),
                        'prioridade_de_grupo': rp.prioridade_da_regra(i.regra) == 0}
                       for i in self.rp_items],
            'usar_ambientes': self._usar_ambientes(),
            'amb_param_unit': self.ParamUnitRoomBox.Text,
            'amb_copiar': self._amb_copiar(),
            'amb_links': bool(self.ChkRoomsLinks.IsChecked),
            'amb_so_vista': bool(self.ChkRoomsVista.IsChecked),
            'amb_direcao': self._amb_direcao(),
            'amb_offsets_por_room': len(self._amb_offsets),
            'amb_auto': bool(self.ChkAutoUnit.IsChecked),
            'amb_auto_limite_ft': self.AutoLimiteBox.Text,
            'fixos': self.valores_fixos(),
            'fixos_em_grupo': bool(self.ChkFixosGrupo.IsChecked),
            'edicoes_manuais': len(self._manuais),
        }

    def _descrever_item(self, item, valores=None):
        """Uma linha da preview como o log precisa: fatos, decisao, bloqueio."""
        chave = get_element_id_value(item.element_id)
        fatos = self._fatos.get(chave) or {}
        descricao = {
            'id': chave,
            'papel': fatos.get('papel') or item.Origem or 'solto',
            'categoria': fatos.get('categoria') or um_escopo.categoria_de(item.element),
            'familia': fatos.get('familia', ''),
            'tipo_elemento': fatos.get('tipo', ''),
            'orientacao': fatos.get('orientacao', ''),
            'grupos': fatos.get('grupos', []),
            'system': fatos.get('system', ''),
            'room': (self._room_de.get(chave) or {}).get('rotulo', '')
            if self._amb_ativo else '',
            'floor': item.WbsDetail, 'unit_id': item.WbsNum, 'type': item.Tipologia,
            'manual': item.Manual,
            'situacao': item.Situacao,
            'gravavel': item.gravavel,
            'so_bloqueado': item.so_bloqueado,
            'decisoes': item.decisoes,
            'bloqueios': item.bloqueios,
            'problemas': item.problemas,
            'atuais': dict((n, item.atuais.get(n)) for n in item.decisoes),
        }
        if valores is not None:
            descricao['grava'] = valores
        return descricao

    def _registrar_preview(self, partes, gravaveis):
        try:
            self._log.configuracao(self._config_para_log())
            resumo = um_log.ulog.resumo_da_preview(
                [self._descrever_item(i) for i in self.itens])
            resumo.update({
                'total': len(self.itens), 'gravaveis': gravaveis,
                'so_bloqueados': sum(1 for i in self.itens if i.so_bloqueado),
                'com_divergencia_de_membros': sum(
                    1 for i in self.itens if u'membros divergem' in i.Situacao),
                'status': u'  |  '.join(partes)})
            self._log.preview(resumo)
        except Exception as ex:
            self._log.registrar('erro_no_log', onde='preview', erro=str(ex),
                                rastro=traceback.format_exc())

    def _registrar_ambientes(self):
        self._log.registrar(
            'ambientes_lidos', elementos=len(self.elementos),
            dentro_de_room=sum(1 for v in self._room_de.values() if v),
            em_varios_rooms=len(self._em_varios_rooms),
            links=bool(self.ChkRoomsLinks.IsChecked),
            so_vista=bool(self.ChkRoomsVista.IsChecked),
            offset_ft=self.OffsetBox.Text)

    def _sem_preview(self, texto):
        self._log.preview({'sem_preview': texto})
        self.StatusLabel.Text = texto
        self.PreviewGrid.ItemsSource = None
        self.ApplyBtn.IsEnabled = False
        self.ApplyBtn.Content = "Aplicar"

    def _aplicar_filtro(self):
        itens = self.itens
        if not self.ChkMostrarBloqueados.IsChecked:
            itens = [i for i in itens if not i.so_bloqueado]
        if self.ChkSoMudancas.IsChecked:
            itens = [i for i in itens if i.decisoes]
        busca = (self.BuscaPreviewBox.Text or u'').strip().lower()
        if busca:
            itens = [i for i in itens if i.casa_com(busca)]
        self.PreviewGrid.ItemsSource = itens
        self.FiltroInfo.Text = (
            u'' if len(itens) == len(self.itens) else
            u'mostrando {} de {} — o Aplicar vale para todas'.format(
                len(itens), len(self.itens)))

    def busca_preview_alterada(self, sender, e):
        """Aba Elementos. (A aba Type tem a dela, `busca_alterada`.)"""
        if self._pronto:
            self._aplicar_filtro()

    def btn_limpar_busca_click(self, sender, e):
        self.BuscaPreviewBox.Text = u''

    # ── escopo (v3.1) ─────────────────────────────────────────────────────────

    def _coletar_escopo(self):
        brutos = um_escopo.elementos(doc, uidoc, self.escopo)
        normais, membros = coletar_selecao(brutos)
        # a descida no grupo traz as "Linhas de centro" dos tubos (elemento
        # dependente, tudo read-only): 80 "Floor read-only" no 1o teste
        membros = [e for e in membros if um_escopo.eh_de_modelo(e)]
        if self.escopo != um_escopo.SELECAO:
            normais = [e for e in normais if um_escopo.eh_de_modelo(e)]
        # peca aninhada em outra familia: os 340 "nao aplicados" de todo dia 15
        antes = len(normais) + len(membros)
        normais = [e for e in normais if not um_escopo.eh_aninhado(e)]
        membros = [e for e in membros if not um_escopo.eh_aninhado(e)]
        self._aninhados_fora = antes - len(normais) - len(membros)
        self._trecho_de = {}
        self._topo_de = {}
        self._categorias_presentes = sorted(
            set(um_escopo.categoria_de(e) for e in normais + membros) - set(['']))
        excluidas = self._categorias_excluidas
        if excluidas:
            normais = [e for e in normais
                       if um_escopo.categoria_de(e) not in excluidas]
            membros = [e for e in membros
                       if um_escopo.categoria_de(e) not in excluidas]
            # 16/09/2026 (Thiago): desmarcar "Grupos de modelo" = nada de
            # grupo, nem a instancia nem o que esta dentro (aninhado inclusive)
            if um_escopo.categoria_de_grupos(doc) in excluidas:
                membros = []
                normais = [e for e in normais if not esta_em_grupo(e)]
        self.normais = normais
        self.membros = membros
        self.elementos = list(normais) + list(membros)
        self.itens = []
        self._rooms_sujo = True     # outros elementos: casar de novo
        if getattr(self, '_pronto', False):
            self._atualizar_nomes_disponiveis()

    def _atualizar_nomes_disponiveis(self):
        """Os parametros das listas (Configuracoes, fixos, editor, Ambientes)
        acompanham o escopo — antes ficavam os do escopo inicial."""
        novos = collect_param_names(amostra_por_tipo(self.elementos))
        self.nomes_disponiveis = sorted(set(novos) | set(
            getattr(self, 'nomes_disponiveis', [])))
        for combo in (self.ParamDetailBox, self.ParamWbsBox, self.ParamTipologiaBox):
            texto = combo.Text
            opcoes = list(self.nomes_disponiveis)
            if texto and texto not in opcoes:
                opcoes.insert(0, texto)
            combo.ItemsSource = opcoes
            combo.Text = texto

    def _atualizar_rodape(self):
        rodape = "{} elemento(s)  ·  {}".format(len(self.elementos),
                                                self.projeto or '(sem nome)')
        if self._aviso:
            rodape = "{}  ·  {}".format(self._aviso, rodape)
        self.ConfigLabel.Text = rodape

    def escopo_alterado(self, sender, e):
        if not self._pronto:
            return
        indice = self.EscopoCombo.SelectedIndex
        if indice < 0 or not self._mesmo_documento():
            return
        self.PreviewGrid.CommitEdit()
        self._absorver_edicoes()
        self.escopo = um_escopo.ESCOPOS[indice][0]
        self._coletar_escopo()
        self._atualizar_rodape()
        self._recalcular()

    def btn_migrar_click(self, sender, e):
        """16/09/2026, pedido do Thiago: escolher o que sobe dos membros para
        a instancia do grupo (aba Configuracoes)."""
        nomes = set(self._nao_migrar)
        for el in self.elementos:
            if isinstance(el, Group):
                nomes |= self._nomes_do_grupo(el)
        if not nomes:
            forms.alert(u'Nenhum Model Group no escopo atual — selecione ou mude '
                        u'o escopo para ver os parâmetros dos grupos.',
                        title=u'Parâmetros migrados')
            return
        opcoes = [forms.TemplateListItem(nome, checked=nome not in self._nao_migrar)
                  for nome in sorted(nomes)]
        escolhidos = forms.SelectFromList.show(
            opcoes, title=u'Parâmetros que sobem dos membros para o grupo',
            multiselect=True, button_name='Usar')
        if escolhidos is None:
            return
        self._nao_migrar = nomes - set(escolhidos)
        self._log.registrar('migrar_para_grupo', nao_migrar=sorted(self._nao_migrar))
        self._recalcular()

    def btn_categorias_click(self, sender, e):
        if not self._categorias_presentes:
            forms.alert(u'Nenhuma categoria no escopo.', title='Categorias')
            return
        opcoes = [forms.TemplateListItem(nome, checked=nome not in
                                         self._categorias_excluidas)
                  for nome in self._categorias_presentes]
        escolhidas = forms.SelectFromList.show(
            opcoes, title=u'Categorias que entram no escopo',
            multiselect=True, button_name='Usar')
        if escolhidas is None:
            return
        escolhidas = set(escolhidas)
        # as de fora do escopo atual continuam como estavam
        self._categorias_excluidas = set(
            c for c in self._categorias_excluidas
            if c not in self._categorias_presentes) | set(
            c for c in self._categorias_presentes if c not in escolhidas)
        self._coletar_escopo()
        self._atualizar_rodape()
        self._recalcular()

    # ── regras de parametros (v3.1) ───────────────────────────────────────────

    def _fatos_de(self, el, linha, nomes):
        chave = get_element_id_value(el.Id)
        fatos = self._fatos.get(chave)
        if fatos is None:
            fatos = um_fatos.fatos_estaticos(doc, el)
            self._fatos[chave] = fatos
        params = self._params_lidos.setdefault(chave, {})
        um_fatos.ler_parametros(el, nomes, params)
        calculados = {}
        for rotulo, nome, valor in zip(('Floor', 'Unit ID', 'Type'),
                                       self._nomes_params(),
                                       (linha['detail'], linha['wbs'],
                                        linha['tipologia'])):
            if valor not in (None, ''):
                calculados[rotulo] = str(valor)
                calculados[nome] = str(valor)
        completos = dict(fatos, params=params, calculados=calculados,
                         floors=self._floors_ordem)
        # 24/09/2026: o Floor da linha vira fato — "Floor é UDG" pega quem a
        # GEOMETRIA pos no underground, enquanto "Nível é 00 - FOUNDATION" pega
        # quem apenas referencia esse Level (246 contra 13, medido no modelo).
        completos[rp.FLOOR] = linha.get('detail') or ''
        if self._usa_trecho:
            trecho = self._trecho(el, chave)
            if trecho:
                completos[rp.TRECHO_COMPRIMENTO] = trecho['comprimento']
                completos[rp.TRECHO_PONTAS] = trecho['pontas']
        if self._usa_topo:
            do_topo = self._room_do_topo(el, chave)
            if do_topo:
                completos['ambiente_topo'] = do_topo['valores']
            else:
                # 18/09: projeto sem rooms — a unidade de cima pelo sufixo
                pelo_sufixo = self._unidade_de_cima_pelo_sufixo(linha)
                if pelo_sufixo:
                    completos['ambiente_topo'] = pelo_sufixo
        info = self._room_de.get(chave) if self._amb_ativo else None
        if info:
            completos['room'] = info['nome']
            completos['room_numero'] = info['numero']
            completos['ambiente'] = info['valores']
        return completos

    def _unidade_de_cima_pelo_sufixo(self, linha):
        """Sem room no topo: Unit ID do pavimento de cima com o mesmo final
        (303 no 3rd -> 403) e o Type da tabela por esse Unit ID. Pedido do
        Thiago em 18/09/2026 — o projeto de um colega não tem rooms."""
        detail = linha.get('detail')
        de_cima = rp.floor_mais(detail, self._floors_ordem, 1)
        unidade = weng.unit_do_pavimento(linha.get('wbs'), detail, de_cima)
        if unidade is None:
            return None
        texto = str(unidade)
        _nome_floor, nome_unit, nome_type = self._nomes_params()
        valores = {u'Unit ID': texto, nome_unit: texto}
        tipo = self._tabela_tip.get(weng.normalizar_chave_wbs(texto))
        if tipo:
            valores[u'Type'] = tipo
            valores[nome_type] = tipo
        return valores

    def _room_do_topo(self, el, chave):
        """Room que o topo alcança — do GRUPO, quando a peça está em um.

        Medido no MIIQLUX em 16/09/2026 contra o que o Thiago já tinha gravado
        à mão (820 peças de aranha): pelo topo da PEÇA bate 280; pelo topo do
        GRUPO, 970 de 1.016. As peças da aranha ficam abaixo da laje (a ARN
        TYP#J inteira entre 20,5 e 21,5 ft) e só o grupo atravessa. As 46
        divergências são aranhas que atendem DUAS unidades.
        """
        if chave not in self._topo_de:
            alvo = el
            try:
                do_grupo = um_escopo.topo(doc, el)
                if do_grupo is not None:
                    alvo = do_grupo
            except Exception:
                pass
            chave_alvo = get_element_id_value(alvo.Id)
            if chave_alvo not in self._topo_de:
                try:
                    self._topo_de[chave_alvo] = rmatch.room_do_topo(
                        self._rooms or [], alvo)
                except Exception:
                    self._topo_de[chave_alvo] = None
            # uma sondagem por grupo: as peças dele compartilham o resultado
            self._topo_de[chave] = self._topo_de[chave_alvo]
        return self._topo_de[chave]

    def _trecho(self, el, chave):
        """O trecho horizontal do elemento — guardado para todas as pecas
        dele de uma vez (um BFS por trecho, nao por peca)."""
        if chave in self._trecho_de:
            return self._trecho_de[chave]
        try:
            trecho = um_fatos.trecho_horizontal(el)
        except Exception:
            trecho = None
        if trecho:
            for peca in trecho['pecas']:
                self._trecho_de[peca] = trecho
        else:
            self._trecho_de[chave] = None
        return trecho

    def _diagnostico_regra(self, el, nome, em_grupo):
        try:
            type_id = get_element_id_value(el.GetTypeId())
        except Exception:
            type_id = -1
        chave = (type_id, em_grupo, nome) if type_id != -1 else None
        if chave is not None and chave in self._diag_regras:
            problema, travada = self._diag_regras[chave]
        else:
            _, problema, travada = diagnosticar_param(el, nome, em_grupo)
            if chave is not None:
                self._diag_regras[chave] = (problema, travada)
        if travada is not None:
            self._defs_travadas[nome] = travada
        return problema

    # ── grupo recebe dos membros (v3.3) ───────────────────────────────────────

    def _nomes_do_grupo(self, grupo):
        """Parametros de texto/inteiro editaveis na INSTANCIA do grupo — os
        que podem receber o valor dos membros. Cache pelo GroupType. A Marca
        fica de fora: e identificacao da instancia, nao atributo do conteudo."""
        try:
            chave = get_element_id_value(grupo.GetTypeId())
        except Exception:
            chave = None
        if chave is not None and chave in self._nomes_grupo:
            return self._nomes_grupo[chave]
        nomes = set()
        for param in grupo.Parameters:
            try:
                definicao = param.Definition
                if param.IsReadOnly or definicao is None:
                    continue
                if param.StorageType not in (StorageType.String, StorageType.Integer):
                    continue
                if getattr(definicao, 'BuiltInParameter', None) == \
                        BuiltInParameter.ALL_MODEL_MARK:
                    continue
                if definicao.Name:
                    nomes.add(definicao.Name)
            except Exception:
                continue
        if chave is not None:
            self._nomes_grupo[chave] = nomes
        return nomes

    def _subir_para_grupos(self, el, item, dos_membros, ids_no_escopo, nomes_calc):
        """Guarda, para cada grupo do escopo que contem `el`, o valor que o
        membro TERA (decidido — mesmo bloqueado, e a intencao) ou ja TEM, nos
        parametros que o grupo aceita. So parametro que existe nos dois."""
        chave = get_element_id_value(el.Id)
        ancestrais = []
        vistos = set()
        gid = getattr(el, 'GroupId', None)
        while gid is not None and get_element_id_value(gid) > 0:
            gchave = get_element_id_value(gid)
            if gchave in vistos:
                break
            vistos.add(gchave)
            grupo = doc.GetElement(gid)
            if grupo is None:
                break
            if gchave in ids_no_escopo:
                ancestrais.append((gchave,
                                   self._nomes_do_grupo(grupo) - self._nao_migrar))
            gid = grupo.GroupId
        if not ancestrais:
            return
        params = self._params_lidos.setdefault(chave, {})
        todos = set()
        for _, nomes_g in ancestrais:
            todos |= nomes_g
        um_fatos.ler_parametros(el, todos, params)
        valores = dict(params)
        for nome, decisao in item.decisoes.items():
            valores[nome] = decisao['valor']
        if item.calc_gravavel:
            for nome, valor in zip(nomes_calc, item.valores_finais()):
                if valor not in (None, ''):
                    valores[nome] = str(valor)
        for gchave, nomes_g in ancestrais:
            destino = dos_membros.setdefault(gchave, {})
            for nome in nomes_g:
                if valores.get(nome):
                    destino.setdefault(nome, []).append(valores[nome])

    def _consolidar_membros(self, valores_por_nome, linha, calcular, nomes_calc):
        """({parametro: dominante}, [divergencias]) de um grupo. Com "Calcular"
        ligado, Floor/Unit ID/Type do grupo passam a ser os dos membros — o
        bounding box do grupo inteiro atravessa pavimentos e erra."""
        consolidados, divergencias = {}, []
        for nome in sorted(valores_por_nome):
            resumo = rp.dominante(valores_por_nome[nome])
            if resumo is None:
                continue
            consolidados[nome] = resumo['valor']
            if resumo['qtd'] < resumo['total']:
                divergencias.append(u'{} {} ({}/{})'.format(
                    nome, resumo['valor'], resumo['qtd'], resumo['total']))
        if calcular:
            for campo, nome in zip(('detail', 'wbs', 'tipologia'), nomes_calc):
                if nome in consolidados:
                    linha[campo] = consolidados[nome]
            if nomes_calc[0] in consolidados:
                linha['motivo'] = None
        return consolidados, divergencias

    def _aplicar_floor_mais(self, todas, linha, reservados, membros):
        """Acao "Floor do nivel + N" (16/09/2026). A regra pode dizer 'Floor'
        (rotulo) ou o nome do parametro da aba Configuracoes. Com "Calcular"
        ligado o Floor e reservado: a acao troca o Floor CALCULADO da linha.
        A instancia do grupo nao desloca de novo — recebe o dos membros."""
        nome_floor = self._nomes_params()[0]
        if nome_floor != u'Floor' and (todas.get(u'Floor') or {}).get('floor_mais'):
            deslocado = todas.pop(u'Floor')
            todas.setdefault(nome_floor, deslocado)
        deslocado = todas.get(nome_floor)
        if not deslocado or not deslocado.get('floor_mais'):
            return
        if nome_floor in (membros or {}):
            todas[nome_floor] = {'valor': membros[nome_floor],
                                 'origem': rp.ORIGEM_MEMBROS, 'regra': u'dos membros'}
            deslocado = None
        if deslocado is not None and nome_floor in reservados:
            linha['detail'] = deslocado['valor']
            nota = u'Floor {} ({})'.format(deslocado['floor_mais'], deslocado['regra'])
            linha['regra'] = u' · '.join(p for p in (linha.get('regra'), nota) if p)

    def _aplicar_ambiente_do_topo(self, todas, linha, reservados, membros):
        """Ação "do ambiente do topo" (16/09/2026, aranha): com "Calcular"
        ligado, Unit ID e Type são reservados — a ação troca o valor CALCULADO
        da linha, como o "Floor do nível + N". A instância do grupo não
        desloca de novo: ela recebe o dos membros."""
        campos = dict(zip(self._nomes_params(), ('detail', 'wbs', 'tipologia')))
        for nome, decisao in list(todas.items()):
            if not decisao.get('do_topo') or nome not in reservados:
                continue
            if nome in (membros or {}):
                continue
            linha[campos[nome]] = decisao['valor']
            if campos[nome] == 'wbs' and linha.get('motivo') == \
                    weng.MOTIVO_FORA_SEM_SUFIXO:
                linha['motivo'] = None
            nota = u'{} da unidade de cima ({})'.format(nome, decisao['regra'])
            linha['regra'] = u' · '.join(
                p for p in (linha.get('regra'), nota) if p)

    def _reservados_da_linha(self, linha, reservados):
        """Reservado de verdade: so o parametro que o calculo PREENCHEU aqui.

        24/09/2026 (Thiago, Floor "UDG"): texto de Floor sem numero nao gera
        Unit ID nem Type (weng.MOTIVO_DETAIL_SEM_NUMERO). Como os tres ficavam
        reservados de qualquer jeito, a regra que preencheria era descartada
        em silencio — e a aba Regras ainda dizia "nenhuma peca", porque a
        contagem le o que sobrou depois do descarte. Sem valor calculado,
        quem manda e a regra (ou o fixo).
        """
        if not reservados:
            return reservados
        vivos = set()
        for nome, seguravel in zip(self._nomes_params(), _CALC_SEGURAVEIS):
            if nome not in reservados:
                continue
            valor = linha.get(seguravel[1])
            if valor is not None and str(valor).strip() != '':
                vivos.add(nome)
        return vivos

    def _decisoes(self, el, linha, regras, fixos, nomes, reservados, copiar=None,
                  membros=None, congelados=None):
        """(decisoes que mudam, bloqueios, valores atuais, previstas) de um
        elemento. `previstas` e tudo que regras/fixos/membros dao, mude ou nao
        (v3.4: a preview mostra '= valor' em vez de branco)."""
        if not (regras or fixos or copiar or membros or congelados):
            return {}, {}, {}, {}
        reservados = self._reservados_da_linha(linha, reservados)
        fatos = self._fatos_de(el, linha, nomes)
        perdidas = {}
        todas = rp.decidir(regras, fatos, copiar, fixos, membros, perdidas)
        for nome_regra, vencedora in perdidas.items():
            registro = self._encobertas.setdefault(
                nome_regra, {'por': vencedora, 'qtd': 0})
            registro['qtd'] += 1
        self._aplicar_floor_mais(todas, linha, reservados, membros)
        self._aplicar_ambiente_do_topo(todas, linha, reservados, membros)
        for nome in reservados:
            todas.pop(nome, None)
        # v3.4: coluna segurada — a foto vale no lugar do que se decidiu agora;
        # None na foto = o elemento nao tinha proposta e continua sem
        for nome, foto in (congelados or {}).items():
            if foto is None:
                todas.pop(nome, None)
            else:
                todas[nome] = dict(foto, regra=u'{} · segurado'.format(
                    foto.get('regra') or u''))
        decisoes = rp.so_o_que_muda(todas, fatos['params'])
        em_grupo = esta_em_grupo(el)
        bloqueios = {}
        for nome in decisoes:
            problema = self._diagnostico_regra(el, nome, em_grupo)
            if problema:
                bloqueios[nome] = problema
        return decisoes, bloqueios, fatos['params'], todas

    # ── ambientes (v3.1, fase 3) ──────────────────────────────────────────────

    def _unit_pelo_ambiente(self):
        return self.FonteUnitCombo.SelectedIndex == 1

    def _usar_ambientes(self):
        """Ligado pela caixa, pelo "Unit ID por: Ambiente" — ou por regra que
        pergunta pelo room (sem isso a condicao nunca casaria, em silencio)."""
        regras = self.regras_param_ativas()
        return (bool(self.ChkUsarAmbientes.IsChecked)
                or (bool(self.ChkCalcular.IsChecked) and self._unit_pelo_ambiente())
                or rp.precisa_de_ambiente(regras)
                or rp.precisa_de_ambiente_topo(regras))

    def _ajustar_checks_reservados(self, calcular):
        """Floor / Unit ID / Type na lista de copia: com "Calcular" ligado
        quem decide e a aba Elementos — a caixa fica desabilitada e diz por
        que, em vez de ser ignorada em silencio."""
        reservados = set(self._nomes_params()) if calcular else set()
        for caixa in self._amb_checks:
            reservado = str(caixa.Content) in reservados
            caixa.IsEnabled = not reservado
            caixa.ToolTip = (u'Calculado na aba Elementos ("Unit ID por: Ambiente" '
                             u'usa o room). Desligue "Calcular" para copiar direto.'
                             if reservado else None)

    def _rotular_sufixo(self):
        self.SufixoLabel.Text = (u'Sufixo p/ fora de room:' if self._unit_pelo_ambiente()
                                 else u'Sufixo inicial:')

    def fonte_unit_alterada(self, sender, e):
        self._rotular_sufixo()
        if self._pronto:
            self._recalcular()

    def _parse_amb_offset(self):
        """16/09/2026 (Thiago): um offset so, o da aba Elementos. Para o room
        vale o modulo; o sinal vira a direcao (`_amb_direcao`)."""
        valor = self._parse_offset()
        return abs(valor) if valor is not None else 0.0

    def _garantir_ambientes(self):
        """Indice de rooms + room de cada elemento — so quando algo mudou."""
        offset = self._parse_amb_offset()
        chave_offset = (offset, self._amb_direcao())
        mesmo_offset = chave_offset == getattr(self, '_chave_offset_rooms', None)
        if not self._rooms_sujo and self._rooms is not None and mesmo_offset:
            return
        # so o offset mudou (campo da aba Elementos): casa de novo sem reler
        if self._rooms_sujo or self._rooms is None:
            self._rooms = rmatch.indice_de_rooms(
                doc, uidoc.ActiveView, bool(self.ChkRoomsLinks.IsChecked),
                bool(self.ChkRoomsVista.IsChecked))
        self._chave_offset_rooms = chave_offset
        self._room_de = {}
        self._em_varios_rooms = []
        for el in self.elementos:
            candidatos = rmatch.rooms_do_elemento(
                self._rooms, el, offset, self._amb_direcao(), self._amb_offsets)
            if len(candidatos) > 1:
                self._em_varios_rooms.append(el)
            self._room_de[get_element_id_value(el.Id)] = amb.escolher_room(candidatos)
        self._rooms_sujo = False
        self._vertical_de, self._perto_de = {}, {}
        self._room_extra, self._vizinhos_cache = {}, {}
        self._montar_params_ambiente()
        self._info_ambientes()

    def _montar_params_ambiente(self):
        """Caixas so para parametro do room que os ELEMENTOS tambem tem — sem
        isso a lista trazia as cargas eletricas do room (pedido do Thiago)."""
        marcados = set(self._amb_copiar())
        do_room = set(n for item in self._rooms or [] for n in item['valores'])
        dos_elementos = set(getattr(self, 'nomes_disponiveis', []))
        nomes = sorted((do_room & dos_elementos) | (marcados & do_room))
        self.AmbParamsPanel.Children.Clear()
        self._amb_checks = []
        for nome in nomes:
            caixa = CheckBox()
            caixa.Content = nome
            caixa.IsChecked = nome in marcados
            caixa.Margin = Thickness(0, 2, 16, 2)
            self.AmbParamsPanel.Children.Add(caixa)
            self._amb_checks.append(caixa)
        self._ajustar_checks_reservados(bool(self.ChkCalcular.IsChecked))
        texto = self.ParamUnitRoomBox.Text
        self.ParamUnitRoomBox.Items.Clear()
        for nome in [u'Unit ID', amb.PARAM_NUMERO, amb.PARAM_NOME] + sorted(
                n for n in do_room if n != u'Unit ID'):
            self.ParamUnitRoomBox.Items.Add(nome)
        self.ParamUnitRoomBox.Text = texto
        self._montar_tabela_rooms()

    def _montar_tabela_rooms(self):
        """A lista de rooms (como no ZoneSync): quem sao, que Unit ID dao e
        quantos elementos do escopo caem em cada um."""
        param_unit = (self.ParamUnitRoomBox.Text or '').strip() or u'Unit ID'
        nome_floor, _nome_unit, nome_type = self._nomes_params()
        quantos = {}
        for info in self._room_de.values():
            if info:
                quantos[id(info)] = quantos.get(id(info), 0) + 1
        linhas = []
        for info in sorted(self._rooms or [],
                           key=lambda i: (i['elevacao'], i['numero'])):
            valores = info['valores']
            linhas.append(RoomItem(
                info, amb.unit_do_room(info, param_unit),
                valores.get(nome_floor) or valores.get('Floor'),
                valores.get(nome_type) or valores.get('Type'),
                quantos.get(id(info), 0), self._rotulo_offset_room(info)))
        self.RoomsGrid.ItemsSource = linhas

    # ── offset por room (16/09/2026) ──────────────────────────────────────────

    def _amb_direcao(self):
        """+ sobe o ponto (base do room desce); − desce o ponto (topo sobe) —
        o mesmo sentido do offset do nivel."""
        valor = self._parse_offset()
        return amb.DIRECAO_TOPO if valor is not None and valor < 0 else amb.DIRECAO_BASE

    def _rotulo_offset_room(self, info):
        offset, direcao, proprio = amb.offset_do_room(
            self._amb_offsets, info.get('chave'), self._parse_amb_offset(),
            self._amb_direcao())
        texto = u'{} {}'.format(pes_para_texto(offset), amb.seta_da_direcao(direcao))
        return texto if proprio else u'padrão ({})'.format(texto)

    def rooms_selecionados(self, sender, e):
        selecionados = list(self.RoomsGrid.SelectedItems)
        if not selecionados:
            self.RoomSelInfo.Text = u'selecione com Ctrl/Shift'
            return
        self.RoomSelInfo.Text = u'{} room(s) selecionado(s)'.format(len(selecionados))
        proprio = self._amb_offsets.get(selecionados[0].chave)
        if proprio:
            self.RoomOffsetBox.Text = pes_para_texto(proprio['offset_ft'])
            self.RoomDirecaoCombo.SelectedIndex = _CHAVES_DIRECAO.index(proprio['direcao'])

    def _mudar_offsets_de_rooms(self, novo):
        """`novo` None = voltar ao padrao. Casa de novo na hora."""
        selecionados = [i for i in self.RoomsGrid.SelectedItems if i.chave]
        if not selecionados:
            forms.alert(u'Selecione rooms na tabela (Ctrl/Shift para vários).',
                        title=u'Offset por room')
            return
        for item in selecionados:
            if novo is None:
                self._amb_offsets.pop(item.chave, None)
            else:
                self._amb_offsets[item.chave] = dict(novo)
        self._log.registrar('offset_room', rooms=[i.Numero for i in selecionados],
                            offset=novo)
        self._rooms_sujo = True
        self._garantir_ambientes()
        self._registrar_ambientes()
        self._montar_tabela_rooms()

    def btn_room_offset_aplicar_click(self, sender, e):
        pes = texto_para_pes(self.RoomOffsetBox.Text)
        if pes is None:
            forms.alert(u'Offset inválido: "{}". Ex.: 6", 0.5\' ou 1\'-6".'.format(
                self.RoomOffsetBox.Text), title=u'Offset por room')
            return
        self._mudar_offsets_de_rooms({
            'offset_ft': abs(pes),
            'direcao': _CHAVES_DIRECAO[max(self.RoomDirecaoCombo.SelectedIndex, 0)]})

    def btn_room_offset_padrao_click(self, sender, e):
        self._mudar_offsets_de_rooms(None)

    # ── Unit ID fora de room (16/09/2026) ─────────────────────────────────────
    # Cadeia do Thiago: room acima/abaixo → grupo → rede → room mais proximo.

    def _parse_auto_limite(self):
        valor = texto_para_pes(self.AutoLimiteBox.Text or '')
        return abs(valor) if valor is not None else amb.LIMITE_PROXIMO_PADRAO

    def _units_por_grupo(self, param_unit):
        """{id do grupo mais externo: [Unit ID dos membros que estao em room]}."""
        por_grupo = {}
        for el in self.elementos:
            unidade = amb.unit_do_room(
                self._room_de.get(get_element_id_value(el.Id)), param_unit)
            if not unidade:
                continue
            topo = um_escopo.topo(doc, el)
            if topo is None or topo is el or isinstance(el, Group):
                continue
            por_grupo.setdefault(get_element_id_value(topo.Id), []).append(unidade)
        return por_grupo

    def _auto_do_room(self, unidade, info, nome_type, fonte, como=None):
        valores = info['valores']
        return {'unit_ambiente': unidade,
                'type_ambiente': valores.get(nome_type) or valores.get('Type', ''),
                'room_rotulo': info['rotulo'], 'como_ambiente': como or fonte,
                'fonte': fonte}

    def _unit_fora_do_room(self, el, eid, param_unit, nome_type):
        """Campos do registro do motor, ou None (vai para o sufixo)."""
        rooms = self._rooms or []
        if eid not in self._vertical_de:
            z, candidatos = rmatch.rooms_na_vertical(rooms, el)
            self._vertical_de[eid] = (amb.escolher_na_vertical(candidatos, z)
                                      if candidatos else None)
        info = self._vertical_de[eid]
        unidade = amb.unit_do_room(info, param_unit)
        if unidade:
            return self._auto_do_room(unidade, info, nome_type, amb.FONTE_VERTICAL)

        topo = um_escopo.topo(doc, el)
        valores = self._units_grupo.get(get_element_id_value(topo.Id)) if topo else None
        resumo = rp.dominante(valores) if valores else None
        if resumo:
            return {'unit_ambiente': resumo['valor'], 'como_ambiente': amb.FONTE_GRUPO,
                    'room_rotulo': u'{} ({}/{} membros em room)'.format(
                        resumo['valor'], resumo['qtd'], resumo['total']),
                    'fonte': amb.FONTE_GRUPO}

        unidade = self._unit_pela_rede(el, param_unit)
        if unidade:
            return {'unit_ambiente': unidade, 'room_rotulo': unidade,
                    'como_ambiente': amb.FONTE_REDE, 'fonte': amb.FONTE_REDE}

        if eid not in self._perto_de:
            limite = self._parse_auto_limite()
            self._perto_de[eid] = amb.mais_proximo(
                rmatch.rooms_perto(rooms, el, limite), limite)
        distancia, info = self._perto_de[eid]
        unidade = amb.unit_do_room(info, param_unit)
        if unidade:
            return self._auto_do_room(
                unidade, info, nome_type, amb.FONTE_PROXIMO,
                u'{} ({})'.format(amb.FONTE_PROXIMO, pes_para_texto(distancia)))
        return None

    def _room_direto(self, elemento, chave):
        """Room que contem a peca — do escopo ou lido na hora (vizinho fora)."""
        if chave in self._room_de:
            return self._room_de[chave]
        if chave not in self._room_extra:
            self._room_extra[chave] = rmatch.room_do_elemento(
                self._rooms or [], elemento, self._parse_amb_offset(),
                self._amb_direcao(), self._amb_offsets)
        return self._room_extra[chave]

    def _unit_pela_rede(self, el, param_unit, saltos=6):
        """Anda pelos conectores ate a primeira camada de pecas com room; a
        camada decide se for unanime (`amb.unit_pela_rede`)."""
        vistos = set([get_element_id_value(el.Id)])
        fronteira = [el]
        camadas = []
        for _ in range(saltos):
            camada, proxima = [], []
            for atual in fronteira:
                chave_atual = get_element_id_value(atual.Id)
                if chave_atual not in self._vizinhos_cache:
                    self._vizinhos_cache[chave_atual] = um_fatos.vizinhos(atual)
                for vizinho in self._vizinhos_cache[chave_atual]:
                    chave = get_element_id_value(vizinho.Id)
                    if chave in vistos:
                        continue
                    vistos.add(chave)
                    unidade = amb.unit_do_room(self._room_direto(vizinho, chave),
                                               param_unit)
                    if unidade:
                        camada.append(unidade)
                    else:
                        proxima.append(vizinho)
            camadas.append(camada)
            if camada or not proxima:
                break
            fronteira = proxima
        return amb.unit_pela_rede(camadas)

    def _amb_copiar(self):
        if self._amb_checks:
            return [str(c.Content) for c in self._amb_checks if c.IsChecked]
        return sorted(self._amb_copiar_salvos)

    def _info_ambientes(self):
        rooms = self._rooms or []
        de_link = sum(1 for item in rooms if item['link'] is not None)
        dentro = sum(1 for v in self._room_de.values() if v)
        param_unit = (self.ParamUnitRoomBox.Text or '').strip() or u'Unit ID'
        com_unit = sum(1 for v in self._room_de.values()
                       if v and amb.unit_do_room(v, param_unit))
        texto = (
            u'{} room(s): {} do modelo, {} de vínculos · {} de {} elemento(s) '
            u'dentro de room · {} com "{}" no room · os outros caem no '
            u'sufixo.'.format(len(rooms), len(rooms) - de_link, de_link, dentro,
                              len(self.elementos), com_unit, param_unit))
        varios = len(getattr(self, '_em_varios_rooms', []))
        if varios:
            texto += (u'\nATENÇÃO: {} elemento(s) dentro de 2 ou mais rooms — '
                      u'alturas de room se sobrepondo no modelo (ex.: LEVEL 3 '
                      u'invadindo o 4). Usei o room do nível mais alto; corrija '
                      u'os rooms para não depender disso.'.format(varios))
        self.AmbInfo.Text = texto

    def amb_alterado(self, sender, e):
        if not self._pronto:
            return
        if sender is self.AutoLimiteBox:
            normalizar_campo(sender)
        self._rooms_sujo = True
        self.AmbInfo.Text = (u'Configuração alterada — "Ler ambientes" ou volte à '
                             u'aba Elementos para casar de novo.')

    def amb_opcao_alterada(self, sender, e):
        # o parametro do room nao muda o casamento: so a coluna Unit ID da
        # tabela e o recalculo (ao voltar para Elementos)
        if self._pronto and self._rooms is not None:
            self._montar_tabela_rooms()
            self._info_ambientes()

    def btn_ler_ambientes_click(self, sender, e):
        self.ChkUsarAmbientes.IsChecked = True
        self._rooms_sujo = True
        self.AmbInfo.Text = u'Lendo os rooms e casando os elementos...'
        self._garantir_ambientes()
        self._registrar_ambientes()

    def _montar_colunas_de_regra(self):
        """Uma coluna por parametro decidido, previsto ou fixo marcado, antes
        da Situacao (v3.4: tambem quando nada muda)."""
        colunas = self.PreviewGrid.Columns
        for _ in range(self._n_colunas_regra):
            colunas.RemoveAt(self._indice_situacao)
        nomes = set(self._fixos_da_rodada)
        for item in self.itens:
            nomes.update(item.decisoes)
            nomes.update(item.previstas)
        nomes = sorted(nomes)
        for coluna, (chave, _campo, _atributo, rotulo) in zip(
                self._colunas_calc, _CALC_SEGURAVEIS):
            coluna.Header = self._cabecalho(chave, rotulo)
        # botao direito no titulo -> qual coluna segurar
        self._chaves_das_colunas = [
            (coluna, chave) for coluna, (chave, _c, _a, _r)
            in zip(self._colunas_calc, _CALC_SEGURAVEIS)]
        base = self.FindResource('CelulaTexto')
        for posicao, nome in enumerate(nomes):
            coluna = DataGridTextColumn()
            coluna.Header = self._cabecalho(nome, nome)
            self._chaves_das_colunas.append((coluna, nome))
            coluna.IsReadOnly = True
            coluna.Width = DataGridLength(150)
            coluna.Binding = Binding('P{}'.format(posicao))
            estilo = Style(TextBlock)
            estilo.BasedOn = base
            estilo.Setters.Add(Setter(TextBlock.ToolTipProperty,
                                      Binding('T{}'.format(posicao))))
            coluna.ElementStyle = estilo
            colunas.Insert(self._indice_situacao + posicao, coluna)
        self._n_colunas_regra = len(nomes)
        for item in self.itens:
            item.preencher_colunas(nomes)

    # ── segurar coluna (v3.4) ─────────────────────────────────────────────────
    # Pedido do Thiago: "mexer no offset mas so mexer em uma ou mais colunas".
    # Decisao dele: a coluna segurada CONGELA a proposta de cada elemento no
    # momento do cadeado — o recalculo nao a muda e o Aplicar grava a foto.

    def _cabecalho(self, chave, rotulo):
        return u'{} {}'.format(_CADEADO, rotulo) if chave in self._holds else rotulo

    def preview_botao_direito(self, sender, e):
        """Botao direito no titulo da coluna liga/desliga o cadeado (pedido do
        Thiago: no lugar da faixa de botoes)."""
        cabecalho = _ancestral(e.OriginalSource, DataGridColumnHeader)
        if cabecalho is None or cabecalho.Column is None:
            return
        for coluna, chave in getattr(self, '_chaves_das_colunas', []):
            if coluna == cabecalho.Column:
                e.Handled = True
                self._alternar_hold(chave)
                return

    def _alternar_hold(self, chave):
        self.PreviewGrid.CommitEdit()
        self._absorver_edicoes()
        ligar = chave not in self._holds
        if ligar:
            self._holds[chave] = self._foto_da_coluna(chave)
        else:
            self._holds.pop(chave, None)
        self._log.registrar('segurar', coluna=chave, ligado=ligar,
                            elementos=len(self._holds.get(chave) or {}))
        # as colunas sao refeitas no recalculo: nao dentro do evento do titulo
        self.Dispatcher.BeginInvoke(System_Action(self._recalcular))

    def _foto_da_coluna(self, chave):
        """{id: proposta atual}. Floor/Unit ID/Type: o texto da celula (com a
        edicao manual); parametro: a decisao/prevista, ou None se nao havia."""
        atributos = dict((c, a) for c, _campo, a, _r in _CALC_SEGURAVEIS)
        foto = {}
        for item in self.itens:
            eid = item.linha['id']
            if chave in atributos:
                foto[eid] = getattr(item, atributos[chave])
            else:
                proposta = item.decisoes.get(chave) or item.previstas.get(chave)
                foto[eid] = dict(proposta) if proposta else None
        return foto

    def _congelados_calc(self, eid):
        saida = {}
        for chave, campo, _atributo, _rotulo in _CALC_SEGURAVEIS:
            foto = self._holds.get(chave)
            if foto is not None and eid in foto:
                saida[campo] = foto[eid]
        return saida

    def _congelados_param(self, eid):
        return dict((chave, foto[eid]) for chave, foto in self._holds.items()
                    if not chave.startswith('#') and eid in foto)

    def regras_param_ativas(self):
        return rp.normalizar_regras(
            [dict(item.regra, ativa=bool(item.Ativa)) for item in self.rp_items])

    def _contagem_por_regra(self):
        """{nome da regra: peças da preview}. Regra ativa que nao pega ninguem
        aparece como "nenhuma peça" — o Thiago descobria isso só no Aplicar."""
        if not self.itens:
            return None
        contagem = {}
        for item in self.itens:
            nomes = set()
            for decisao in (list(item.decisoes.values())
                            + list(item.previstas.values())):
                if decisao.get('origem') == rp.ORIGEM_REGRA:
                    nomes.add(decisao.get('regra'))
            for nome in nomes:
                contagem[nome] = contagem.get(nome, 0) + 1
        return contagem

    def _refresh_rp(self, selecionar=None, recalcular=True):
        """`recalcular`: mexer na lista (ordem, ativa, editar) refaz a preview.

        16/09/2026: o Thiago subiu o KIT e a lista continuou mostrando
        "nenhuma peça" e "encoberta por Aranha" — números da preview anterior.
        """
        if recalcular and getattr(self, '_pronto', False):
            self._recalcular()      # ele chama este metodo de volta, sem repetir
            return
        contagem = self._contagem_por_regra()
        for item in self.rp_items:
            item.atualizar(contagem, self._encobertas)
        self.RegrasParamList.ItemsSource = None
        self.RegrasParamList.ItemsSource = self.rp_items
        if selecionar is not None:
            self.RegrasParamList.SelectedItem = selecionar
        ativas = sum(1 for item in self.rp_items if item.Ativa)
        texto = u'{} regra(s), {} ativa(s) — modelo "{}".'.format(
            len(self.rp_items), ativas, self.projeto or '(sem nome)')
        reservados = set(self._nomes_params())
        colidem = sorted(set(a['parametro'] for item in self.rp_items
                             for a in item.regra['entao']) & reservados)
        if colidem:
            # 24/09/2026: o calculado so vence quando existe. Onde ele nao sai
            # (Floor sem numero, fora das faixas), a regra passa a valer — antes
            # era descartada em silencio e a lista dizia "nenhuma peça".
            texto += (u' Com "Calcular Floor / Unit ID / Type" ligado, {} fica(m) '
                      u'com o valor calculado onde ele existe; onde o cálculo '
                      u'não resolve, vale a regra.'.format(', '.join(colidem)))
        self.RegrasParamInfo.Text = texto

    def _opcoes_do_editor(self):
        """Valores que existem no escopo — categorias vem na lingua do Revit."""
        conjuntos = dict((k, set()) for k in (
            'grupos', 'systems', 'tipos_system', 'classificacoes', 'categorias',
            'familias', 'tipos', 'niveis'))
        for el in self.elementos[:3000]:
            chave = get_element_id_value(el.Id)
            fatos = self._fatos.get(chave)
            if fatos is None:
                fatos = um_fatos.fatos_estaticos(doc, el)
                self._fatos[chave] = fatos
            conjuntos['grupos'].update(fatos['grupos'])
            for campo, destino in (('system', 'systems'),
                                   ('system_tipo', 'tipos_system'),
                                   ('classificacao', 'classificacoes'),
                                   ('categoria', 'categorias'),
                                   ('familia', 'familias'), ('tipo', 'tipos'),
                                   ('nivel', 'niveis')):
                if fatos[campo]:
                    conjuntos[destino].add(fatos[campo])
        opcoes = dict((k, sorted(v)) for k, v in conjuntos.items())
        opcoes['parametros'] = list(getattr(self, 'nomes_disponiveis', []))
        # 24/09/2026: os Floors da aba Configurações, para a condição "Floor é
        # UDG" sair do combo em vez de ser digitada
        opcoes['floors'] = [(i.WbsValue or '').strip() for i in self.level_items
                            if (i.WbsValue or '').strip()]
        return opcoes

    def _editar_regra(self, regra):
        editor = um_regra.EditorDeRegra(regra, self._opcoes_do_editor())
        editor.ShowDialog()
        return editor.resultado

    def _regra_marcada(self):
        item = self.RegrasParamList.SelectedItem
        if item is None:
            forms.alert(u'Selecione uma regra na lista.', title='Regras')
        return item

    def btn_rp_nova_click(self, sender, e):
        regra = self._editar_regra(None)
        if regra:
            item = RegraParamItem(regra)
            self.rp_items.append(item)
            self._refresh_rp(item)

    def btn_rp_editar_click(self, sender, e):
        item = self._regra_marcada()
        if item is None:
            return
        item.atualizar()
        regra = self._editar_regra(item.regra)
        if regra:
            item.regra = regra
            item.Ativa = regra['ativa']
            self._refresh_rp(item)

    def rp_duplo_clique(self, sender, e):
        if self.RegrasParamList.SelectedItem is not None:
            self.btn_rp_editar_click(sender, e)

    def btn_rp_duplicar_click(self, sender, e):
        item = self._regra_marcada()
        if item is None:
            return
        item.atualizar()
        copia = RegraParamItem(dict(item.regra,
                                    nome=u'{} (cópia)'.format(item.regra['nome'])))
        self.rp_items.insert(self.rp_items.index(item) + 1, copia)
        self._refresh_rp(copia)

    def btn_rp_remover_click(self, sender, e):
        item = self._regra_marcada()
        if item is None:
            return
        if not forms.alert(u'Remover a regra "{}"?'.format(item.Nome),
                           title='Regras', yes=True, no=True):
            return
        self.rp_items.remove(item)
        self._refresh_rp()

    def _mover_regra(self, passo):
        item = self._regra_marcada()
        if item is None:
            return
        de = self.rp_items.index(item)
        para = de + passo
        if 0 <= para < len(self.rp_items):
            self.rp_items.insert(para, self.rp_items.pop(de))
        self._refresh_rp(item)

    def rp_ativa_click(self, sender, e):
        """A caixa "Ativa" da lista: o binding muda o item, mas nada refazia a
        preview (16/09/2026)."""
        self._refresh_rp(self.RegrasParamList.SelectedItem)

    def btn_rp_subir_click(self, sender, e):
        self._mover_regra(-1)

    def btn_rp_descer_click(self, sender, e):
        self._mover_regra(+1)

    def btn_rp_modelos_click(self, sender, e):
        """Banco de regras por pacote (16/09/2026): aranha, KIT, riser e
        desvio, colgante. O desvio entra antes do colgante."""
        banco = rp.banco_de_regras()
        escolhidos = forms.SelectFromList.show(
            [forms.TemplateListItem(nome, checked=True) for nome, _ in banco],
            title=u'Banco de regras — o que trazer para este modelo',
            multiselect=True, button_name='Adicionar')
        if not escolhidos:
            return
        escolhidos = set(escolhidos)
        novas = [r for nome, regras in banco if nome in escolhidos for r in regras]
        if not novas:
            return
        # 16/09/2026: antes a de mesmo nome era PULADA — quem tinha a regra da
        # aranha desativada ficava sem ela e o riser pegava a aranha
        atuais = [dict(item.regra, ativa=bool(item.Ativa))
                  for item in self.rp_items]
        fundidas, trocadas = rp.fundir_regras(atuais, novas)
        # 16/09: o KIT entrava no fim e ficava encoberto pela aranha
        fundidas = rp.ordenar_pelo_banco(fundidas)
        self.rp_items = [RegraParamItem(regra) for regra in fundidas]
        self._refresh_rp()
        texto = u'{} regra(s) do banco: {} nova(s) e {} que já existiam pelo ' \
                u'nome — estas foram substituídas e entram ATIVAS.'.format(
                    len(novas), len(novas) - trocadas, trocadas)
        forms.alert(texto + u'\n\nConfira os valores (Colgante, Riser, '
                    u'Typical...) e a ordem antes de aplicar.',
                    title='Banco de regras')

    def btn_rp_importar_click(self, sender, e):
        caminho = forms.pick_file(file_ext='json',
                                  title=u'Regras exportadas pelo Unit Mapper')
        if not caminho:
            return
        substituir = False
        if self.rp_items:
            escolha = forms.alert(
                u'O modelo já tem {} regra(s).'.format(len(self.rp_items)),
                title='Importar regras',
                options=[u'Somar (troca as de mesmo nome)', u'Substituir tudo'])
            if not escolha:
                return
            substituir = escolha.startswith('Substituir')
        try:
            with codecs.open(caminho, 'r', encoding='utf-8-sig') as arquivo:
                texto = arquivo.read()
            regras, mensagem = rp.importar(
                texto, [item.regra for item in self.rp_items], substituir)
        except Exception as ex:
            forms.alert(u'Não importei: {}'.format(ex), title='Importar regras')
            return
        self.rp_items = [RegraParamItem(r) for r in regras]
        self._refresh_rp()
        forms.alert(mensagem, title='Importar regras')

    def btn_rp_exportar_click(self, sender, e):
        if not self.rp_items:
            forms.alert(u'Não há regra para exportar.', title='Exportar regras')
            return
        caminho = forms.save_file(
            file_ext='json',
            default_name=u'regras_{}'.format(self.projeto or 'modelo'))
        if not caminho:
            return
        try:
            with codecs.open(caminho, 'w', encoding='utf-8') as arquivo:
                arquivo.write(rp.exportar([item.regra for item in self.rp_items],
                                          self.projeto))
        except Exception as ex:
            forms.alert(u'Não exportei: {}'.format(ex), title='Exportar regras')
            return
        forms.alert(u'{} regra(s) exportada(s) para:\n{}'.format(
            len(self.rp_items), caminho), title='Exportar regras')

    # ── eventos: aba Elementos ────────────────────────────────────────────────

    def campo_alterado(self, sender, e):
        if not self._pronto:
            return
        self.ChkReiniciar.IsEnabled = bool(self.ChkIncrement.IsChecked)
        self._recalcular()

    def offset_saiu(self, sender, e):
        """1.5 vira 1'-6" ao sair do campo: o usuario ve o que foi entendido."""
        normalizar_campo(sender)

    def btn_recalcular_click(self, sender, e):
        self.PreviewGrid.CommitEdit()
        self._recalcular()

    # ── edicao manual da preview ──────────────────────────────────────────────

    def _absorver_edicoes(self):
        """Guarda o que foi digitado nas celulas antes de recriar as linhas.

        Sem isso, qualquer recalculo (mudar sufixo, offset, regra, tipologia)
        jogaria fora o ajuste pontual que o usuario acabou de fazer.
        """
        for item in self.itens:
            mudou = item.edicoes()
            if mudou:
                registro = self._manuais.setdefault(item.linha['id'], {})
                registro.update(mudou)

    def celula_editada(self, sender, e):
        # o valor so chega no objeto depois que a edicao e confirmada
        self.PreviewGrid.Dispatcher.BeginInvoke(
            System_Action(self._depois_da_edicao))

    def _depois_da_edicao(self):
        self._absorver_edicoes()
        self._log.registrar('edicao_manual', manuais=self._manuais)
        self.LimparManuaisBtn.Visibility = VISIVEL if self._manuais else OCULTO
        for item in self.itens:
            if item.linha['id'] in self._manuais and not item.Manual:
                item.Manual = 'M'
        self.PreviewGrid.Items.Refresh()
        self._atualizar_contagem_aplicar()

    def _atualizar_contagem_aplicar(self):
        gravaveis = sum(1 for i in self.itens if i.gravavel)
        self.ApplyBtn.IsEnabled = gravaveis > 0
        self.ApplyBtn.Content = "Aplicar ({})".format(gravaveis)

    def btn_limpar_manuais_click(self, sender, e):
        self.PreviewGrid.CommitEdit()
        if not self._manuais:
            return
        if not forms.alert("Descartar {} edição(ões) manual(is) e voltar ao "
                           "valor calculado?".format(len(self._manuais)),
                           title="Edições manuais", yes=True, no=True):
            return
        self._manuais = {}
        self._recalcular()

    # ── regras especiais (aba Configuracoes) ──────────────────────────────────

    def regras_como_dicts(self):
        return [item.como_dict() for item in self.regra_items]

    def _refresh_regras_grid(self):
        self.RegrasGrid.ItemsSource = None
        self.RegrasGrid.ItemsSource = self.regra_items
        validas = len(weng.normalizar_regras(self.regras_como_dicts()))
        total = len(self.regra_items)
        if total and validas < total:
            self.RegrasInfo.Text = ("{} de {} regras válidas — as demais estão sem "
                                    "critério ou sem ação.".format(validas, total))
        else:
            self.RegrasInfo.Text = "{} regra(s)".format(total)

    def btn_regra_add_click(self, sender, e):
        self.RegrasGrid.CommitEdit()
        nova = RegraItem()
        self.regra_items.append(nova)
        self._refresh_regras_grid()
        self.RegrasGrid.SelectedItem = nova
        self.RegrasGrid.ScrollIntoView(nova)

    def btn_regra_remove_click(self, sender, e):
        self.RegrasGrid.CommitEdit()
        selecionadas = [i for i in self.RegrasGrid.SelectedItems]
        if not selecionadas:
            forms.alert("Selecione a regra a remover.", title="Regras especiais")
            return
        for item in selecionadas:
            if item in self.regra_items:
                self.regra_items.remove(item)
        self._refresh_regras_grid()
        self._recalcular()

    def param_alterado(self, sender, e):
        # mudou o parametro de destino: o diagnostico anterior nao vale mais
        if not self._pronto:
            return
        self._cache_diag = {}
        self._diag_regras = {}
        self._recalcular()

    def btn_liberar_click(self, sender, e):
        """SetAllowVaryBetweenGroups nos parametros travados — com confirmacao,
        porque mexe no binding do parametro em todo o projeto."""
        travados = dict(self._defs_travadas)
        if not travados:
            return

        if not forms.alert(
                "Ligar \"Values can vary by group instance\" em:\n\n  {}\n\n"
                "Isso altera o parâmetro no PROJETO INTEIRO — todo Model Group "
                "passa a poder ter valor próprio nesse parâmetro, para toda a "
                "equipe no arquivo central.\n\nContinuar?".format(
                    '\n  '.join(sorted(travados))),
                title="Liberar variação por grupo", yes=True, no=True):
            return

        if not self._mesmo_documento():
            return
        # janela modeless: a Transaction so pode rodar dentro do ExternalEvent
        self._log.registrar('liberar_pedido', parametros=sorted(travados))
        self._pedir(('liberar', travados), u'Liberando a variação por grupo...')

    def _reorganizar_abas(self):
        """v3.5: Floors e Type viram seções de Configurações — a barra de cima
        fica com o fluxo (Elementos, Regras, Ambientes, Fixos, Configurações).
        Feito aqui, e não no XAML, para não duplicar 115 linhas de marcação."""
        for rotulo in (u'Floors', u'Type'):
            for item in list(self.Abas.Items):
                if u'{}'.format(getattr(item, 'Header', u'')) == rotulo:
                    self.Abas.Items.Remove(item)
                    self.AbasConfig.Items.Add(item)
                    break

    def tab_changed(self, sender, e):
        # o SelectionChanged dos DataGrids e das abas de Configurações borbulha
        # ate aqui: só a barra de cima conta
        if not self._pronto or e.OriginalSource is not self.Abas:
            return
        if self.Abas.SelectedIndex == 0:
            self._recalcular()
        else:
            self._atualizar_info_fixos()
            aba = self.Abas.SelectedItem
            if getattr(aba, 'Header', None) == 'Ambientes' and self._rooms is None:
                # a lista de rooms aparece ao abrir a aba, sem precisar clicar
                self.AmbInfo.Text = u'Lendo os rooms...'
                self._garantir_ambientes()

    # ── eventos: aba Pavimentos ───────────────────────────────────────────────

    def btn_auto_ordinais_click(self, sender, e):
        self.FloorGrid.CommitEdit()
        for item in self.level_items:
            item.WbsValue = weng.auto_ordinal(item.Name)
        self.FloorGrid.ItemsSource = None
        self.FloorGrid.ItemsSource = self.level_items

    # ── eventos: aba Tipologia ────────────────────────────────────────────────

    def _refresh_tip_grid(self):
        filtro = (self.BuscaBox.Text or '').strip().lower()
        if filtro:
            visiveis = [i for i in self.tip_items
                        if filtro in str(i.Chave).lower()
                        or filtro in str(i.Valor or '').lower()]
        else:
            visiveis = list(self.tip_items)

        self.TipGrid.ItemsSource = visiveis
        if filtro:
            self.TipInfo.Text = "{} de {} entradas".format(len(visiveis), len(self.tip_items))
        else:
            self.TipInfo.Text = "{} entradas".format(len(self.tip_items))

        if self.tip_items:
            self.ProjetoLabel.Text = (
                "Tabela do modelo \"{}\". Vale só para ele — o mesmo Unit ID em outro "
                "projeto é outro apartamento.".format(self.projeto or '(sem nome)'))
        else:
            outros = wcfg.projetos_com_tipologia(self.cfg, excluir=self.projeto)
            extra = ""
            if outros:
                extra = " Use \"Copiar de outro projeto...\" para trazer de {}.".format(
                    ', '.join('{} ({})'.format(n, q) for n, q in outros[:3]))
            self.ProjetoLabel.Text = (
                "O modelo \"{}\" ainda não tem tabela de Type.{}".format(
                    self.projeto or '(sem nome)', extra))

    def _substituir_tabela(self, tabela):
        self.tip_items = [TipItem(k, tabela[k])
                          for k in sorted(tabela, key=self._ordem_chave)]
        self.BuscaBox.Text = ''
        self._refresh_tip_grid()

    def _perguntar_modo_carga(self, titulo):
        """Somar ou substituir. Tabela vazia nao precisa perguntar."""
        if not self.tip_items:
            return 'substituir'
        escolha = forms.alert(
            "A tabela do modelo já tem {} entradas.".format(len(self.tip_items)),
            title=titulo, options=["Somar (atualiza repetidos)", "Substituir tudo"])
        if not escolha:
            return None
        return 'substituir' if escolha.startswith('Substituir') else 'somar'

    def busca_alterada(self, sender, e):
        if not self._pronto:
            return
        self._refresh_tip_grid()

    def btn_tip_add_click(self, sender, e):
        self.TipGrid.CommitEdit()
        novo = TipItem('', '')
        self.tip_items.insert(0, novo)
        self.BuscaBox.Text = ''
        self._refresh_tip_grid()
        self.TipGrid.SelectedItem = novo
        self.TipGrid.ScrollIntoView(novo)

    def btn_tip_remove_click(self, sender, e):
        self.TipGrid.CommitEdit()
        selecionados = [i for i in self.TipGrid.SelectedItems]
        if not selecionados:
            forms.alert("Selecione as linhas a remover.", title="Type")
            return
        for item in selecionados:
            if item in self.tip_items:
                self.tip_items.remove(item)
        self._refresh_tip_grid()

    def btn_tip_limpar_click(self, sender, e):
        self.TipGrid.CommitEdit()
        if not self.tip_items:
            return
        if not forms.alert("Apagar as {} entradas da tabela do modelo \"{}\"?".format(
                len(self.tip_items), self.projeto or '(sem nome)'),
                title="Limpar tabela", yes=True, no=True):
            return
        self._substituir_tabela({})

    def btn_tip_copiar_click(self, sender, e):
        self.TipGrid.CommitEdit()
        outros = wcfg.projetos_com_tipologia(self.cfg, excluir=self.projeto)
        if not outros:
            forms.alert("Não há outra tabela salva para copiar.", title="Copiar tabela")
            return

        rotulos = ["{}  ({} entradas)".format(nome, total) for nome, total in outros]
        escolhido = forms.SelectFromList.show(
            rotulos, title="Copiar a tabela de Type de qual projeto?", multiselect=False)
        if not escolhido:
            return
        origem = outros[rotulos.index(escolhido)][0]

        modo = self._perguntar_modo_carga("Copiar de {}".format(origem))
        if modo is None:
            return

        tabela = wcfg.tipologia_do_projeto(self.cfg, origem)
        if modo == 'somar':
            atual = self.tabela_tipologia()
            atual.update(tabela)
            tabela = atual
        self._substituir_tabela(tabela)
        forms.alert("{} entradas na tabela de \"{}\".".format(
            len(self.tip_items), self.projeto or '(sem nome)'), title="Copiar tabela")

    def btn_tip_import_click(self, sender, e):
        self.TipGrid.CommitEdit()
        caminho = forms.pick_file(file_ext='csv',
                                  title='CSV com as colunas Unit ID e Type')
        if not caminho:
            return

        modo = self._perguntar_modo_carga("Importar CSV")
        if modo is None:
            return
        if modo == 'substituir':
            self._substituir_tabela({})

        try:
            headers, rows = ler_csv_utf8(caminho, retornar_tupla=True)
        except Exception as ex:
            forms.alert("Nao foi possivel ler o CSV:\n{}".format(ex), title="Importar CSV")
            return

        # cabecalho e opcional: se a 1a linha ja for um par de dados, aproveita
        linhas = list(rows)
        if headers and len(headers) >= 2:
            primeiro = str(headers[0]).strip().lower()
            if primeiro not in ('unit id', 'unit_id', 'unitid', 'wbs', 'chave', 'codigo', 'código', ''):
                linhas.insert(0, headers)

        tabela = dict((i.Chave, i) for i in self.tip_items)
        novos = atualizados = ignorados = 0
        for row in linhas:
            if len(row) < 2:
                ignorados += 1
                continue
            chave = weng.normalizar_chave_wbs(row[0])
            valor = str(row[1]).strip()
            if not chave or not valor:
                ignorados += 1
                continue
            if chave in tabela:
                if tabela[chave].Valor != valor:
                    tabela[chave].Valor = valor
                    atualizados += 1
            else:
                item = TipItem(chave, valor)
                tabela[chave] = item
                self.tip_items.append(item)
                novos += 1

        self.tip_items.sort(key=lambda i: self._ordem_chave(i.Chave))
        self.BuscaBox.Text = ''
        self._refresh_tip_grid()
        forms.alert("Novos: {}\nAtualizados: {}\nIgnorados: {}".format(
            novos, atualizados, ignorados), title="Importar CSV")

    def btn_tip_export_click(self, sender, e):
        self.TipGrid.CommitEdit()
        caminho = forms.save_file(file_ext='csv', default_name='unit_mapper_types')
        if not caminho:
            return
        rows = [[i.Chave, i.Valor] for i in self.tip_items]
        if escrever_csv_utf8(caminho, ['Unit ID', 'Type'], rows):
            forms.alert("{} entradas exportadas para:\n{}".format(len(rows), caminho),
                        title="Exportar CSV")
        else:
            forms.alert("Falha ao escrever o CSV.", title="Exportar CSV")

    # ── aba Parametros fixos (estrutura da Paleta de Parametros) ──────────────

    def _montar_fixos(self, parametros, valores, ativos):
        """Uma linha por parametro: [x] [nome editavel] [valor editavel] [x].

        Estrutura da Paleta (coluna do CSV = parametro, valores da coluna =
        opcoes), com o nome tambem editavel: o cabecalho do CSV nem sempre
        bate com o nome do parametro no modelo. So linha marcada e gravada.
        """
        self.FixosPanel.Children.Clear()
        self._fixos = []
        for nome, opcoes in parametros:
            self._add_linha_fixo(nome, opcoes, valores.get(nome, ''), nome in ativos)
        self._atualizar_info_fixos()

    def _add_linha_fixo(self, nome, opcoes, valor, marcado):
        linha = StackPanel()
        linha.Orientation = Orientation.Horizontal
        linha.Margin = Thickness(0, 3, 0, 3)

        check = CheckBox()
        check.IsChecked = bool(marcado)
        check.VerticalAlignment = VerticalAlignment.Center
        check.Margin = Thickness(0, 0, 6, 0)
        check.Click += self.fixos_alterado
        linha.Children.Add(check)

        combo_nome = ComboBox()
        combo_nome.IsEditable = True
        combo_nome.Width = 190
        combo_nome.Height = 24
        combo_nome.Margin = Thickness(0, 0, 8, 0)
        combo_nome.ItemsSource = list(getattr(self, 'nomes_disponiveis', []))
        combo_nome.Text = nome or ''
        combo_nome.LostFocus += self.fixos_alterado
        linha.Children.Add(combo_nome)

        combo_valor = ComboBox()
        combo_valor.IsEditable = True
        combo_valor.Width = 250
        combo_valor.Height = 24
        combo_valor.Margin = Thickness(0, 0, 8, 0)
        combo_valor.ItemsSource = list(opcoes or [])
        combo_valor.Text = valor or ''
        combo_valor.LostFocus += self.fixos_alterado
        linha.Children.Add(combo_valor)

        remover = Button()
        remover.Content = "✕"
        remover.Width = 26
        remover.Height = 24
        remover.ToolTip = "remover este parâmetro da lista"
        remover.Tag = linha
        remover.Click += self.btn_fixos_remove_click
        linha.Children.Add(remover)

        self.FixosPanel.Children.Add(linha)
        self._fixos.append((combo_nome, combo_valor, check))
        return linha

    def _linhas_fixos(self):
        """[(nome, valor, marcado)] lidos dos controles."""
        dados = []
        for combo_nome, combo_valor, check in self._fixos:
            dados.append(((combo_nome.Text or '').strip(),
                          (combo_valor.Text or '').strip(),
                          bool(check.IsChecked)))
        return dados

    def fixos_alterado(self, sender, e):
        if not self._pronto:
            return
        self._atualizar_info_fixos()

    def btn_fixos_add_click(self, sender, e):
        self._add_linha_fixo('', [], '', True)
        self._atualizar_info_fixos()

    def btn_fixos_remove_click(self, sender, e):
        linha = sender.Tag
        indice = None
        for i, filho in enumerate(self.FixosPanel.Children):
            if filho is linha:
                indice = i
                break
        if indice is None:
            return
        self.FixosPanel.Children.RemoveAt(indice)
        del self._fixos[indice]
        self._atualizar_info_fixos()

    def _atualizar_info_fixos(self):
        marcados = self.valores_fixos()
        if not self._fixos:
            texto = "Nenhum CSV carregado."
        elif marcados:
            texto = "{} de {} parâmetros serão gravados: {}".format(
                len(marcados), len(self._fixos),
                ', '.join("{}={}".format(k, v) for k, v in sorted(marcados.items())))
        else:
            texto = "{} parâmetros carregados, nenhum marcado.".format(len(self._fixos))

        ignorados = self._fixos_reservados_marcados()
        if ignorados:
            texto += ("\nIgnorados por serem calculados pela ferramenta: {}."
                      .format(', '.join(ignorados)))
        self.FixosInfo.Text = texto

    def valores_fixos(self):
        """{nome: valor} dos parametros marcados e com valor preenchido.

        Os tres parametros calculados ficam de fora: o data.csv da Paleta tem
        colunas 'WBS', 'WBS Detail' e 'Tipologia UH', e um valor fixo dali
        sobrescreveria em silencio o que a ferramenta acabou de calcular.
        """
        reservados = set(self._nomes_params())
        resultado = {}
        for nome, valor, marcado in self._linhas_fixos():
            if not marcado or not nome or nome in reservados:
                continue
            if valor:
                resultado[nome] = valor
        return resultado

    def _fixos_reservados_marcados(self):
        """Nomes marcados que colidem com os parametros calculados."""
        reservados = set(self._nomes_params())
        return sorted(nome for nome, _, marcado in self._linhas_fixos()
                      if marcado and nome in reservados)

    def _carregar_csv_fixos(self, caminho, valores=None, ativos=None):
        try:
            headers, rows = ler_csv_utf8(caminho, retornar_tupla=True)
        except Exception as ex:
            forms.alert("Nao foi possivel ler o CSV:\n{}".format(ex),
                        title="Parâmetros fixos")
            return False

        parametros = weng.colunas_para_parametros(headers, rows)
        if not parametros:
            forms.alert("O CSV nao tem colunas com nome.", title="Parâmetros fixos")
            return False

        self._montar_fixos(parametros, valores or {}, ativos or [])
        self.FixosCsvLabel.Text = caminho
        self.FixosCsvLabel.ToolTip = caminho
        self.csv_fixos = caminho
        return True

    def btn_fixos_csv_click(self, sender, e):
        caminho = forms.pick_file(file_ext='csv',
                                  title='CSV no formato da Paleta de Parâmetros')
        if not caminho:
            return
        # mantem o que ja estava escolhido para as colunas que se repetirem
        atuais = self._linhas_fixos()
        self._carregar_csv_fixos(
            caminho,
            dict((n, v) for n, v, _ in atuais if n),
            [n for n, _, marcado in atuais if marcado and n])

    def btn_fixos_limpar_click(self, sender, e):
        for _, _, check in self._fixos:
            check.IsChecked = False
        self._atualizar_info_fixos()

    def valores_fixos_para_grupo(self):
        """Fixos que valem tambem nos membros de Model Group."""
        if not self.ChkFixosGrupo.IsChecked:
            return {}
        return self.valores_fixos()

    # ── rodape ────────────────────────────────────────────────────────────────

    def _commit_grids(self):
        self.PreviewGrid.CommitEdit()
        self.FloorGrid.CommitEdit()
        self.TipGrid.CommitEdit()
        self.RegrasGrid.CommitEdit()

    def btn_apply_click(self, sender, e):
        self._commit_grids()
        self._recalcular()
        aplicaveis = [i for i in self.itens if i.gravavel]
        if not aplicaveis:
            forms.alert("Nada a aplicar com a configuracao atual.", title="Unit Mapper")
            return
        if not self._mesmo_documento():
            return
        self.salvar_config()

        nomes_calc = self._nomes_params()
        trabalho = []
        self._pre_falhas = {}
        for item in aplicaveis:
            valores = []
            if item.calc_gravavel:
                valores.extend(list(zip(nomes_calc, item.valores_finais())))
            elif item.calcular and item.problemas:
                # grava a regra, mas Floor/Unit ID/Type nao: antes isso sumia
                # do relatorio (o item era "gravavel")
                for problema in item.problemas:
                    self._pre_falhas.setdefault(problema, []).append(
                        (item.element_id, item.ElemId))
            for problema in item.bloqueios.values():
                self._pre_falhas.setdefault(problema, []).append(
                    (item.element_id, item.ElemId))
            valores.extend(sorted(item.gravaveis_regra.items()))
            trabalho.append({'id': item.element_id, 'rotulo': item.ElemId,
                             'valores': valores})
        if not self._confirmar_aplicar(trabalho):
            return
        self._itens_aplicados = list(self.itens)
        self._calculados_aplicados = (list(nomes_calc)
                                      if self.ChkCalcular.IsChecked else [])
        # log (v3.4): só o que EXPLICA alguma coisa — bloqueio, problema,
        # edição manual, divergência de membros ou nada gravável — mais uma
        # amostra dos normais. Gravar os 2.540 itens de cada Aplicar fez o
        # log passar de 15 MB num dia (auditoria de 16/09).
        por_id = dict((get_element_id_value(t['id']), t['valores']) for t in trabalho)
        self._log.configuracao(self._config_para_log())
        interessantes, normais = [], []
        for item in self.itens:
            alvo = (interessantes if (item.problemas or item.bloqueios
                                      or item.Manual or not item.gravavel)
                    else normais)
            alvo.append(item)
        amostra = interessantes + normais[:_AMOSTRA_DE_ITENS]
        self._log.registrar('aplicar_pedido', escritas=len(trabalho),
                            itens=len(self.itens),
                            itens_no_log=len(amostra),
                            itens_omitidos=len(self.itens) - len(amostra))
        self._log.registrar_lote('item', [
            self._descrever_item(i, por_id.get(get_element_id_value(i.element_id)))
            for i in amostra])
        self._pedir(('aplicar', trabalho),
                    u'Aplicando em {} elemento(s)...'.format(len(trabalho)))

    def _confirmar_aplicar(self, trabalho):
        """O que vai ser gravado, por parametro, ANTES da Transaction (pedido
        do Thiago, 16/09/2026: 2.500 elementos de uma vez sem conferencia)."""
        linhas = resumo_aplicar.resumo_do_aplicar(
            [{'valores': t['valores']} for t in trabalho]
            + [{'bloqueios': i.bloqueios} for i in self.itens if i.bloqueios])
        texto = resumo_aplicar.texto_do_resumo(linhas, len(trabalho))
        if self._manuais:
            texto += u'\n\n{} linha(s) editada(s) à mão entram com o valor ' \
                     u'digitado.'.format(len(self._manuais))
        if self._holds:
            texto += u'\n{} coluna(s) segurada(s): {}.'.format(
                len(self._holds), u', '.join(
                    dict((c, r) for c, _campo, _a, r in _CALC_SEGURAVEIS).get(
                        chave, chave) for chave in sorted(self._holds)))
        escolha = forms.alert(texto, title=u'Aplicar no modelo',
                              options=[u'Aplicar', u'Cancelar'])
        return escolha == u'Aplicar'

    def btn_cancel_click(self, sender, e):
        self.Close()

    # ── modeless (v3.2) ───────────────────────────────────────────────────────

    def _mesmo_documento(self):
        """A janela fica aberta enquanto o usuario troca de modelo: os
        elementos dela sao do modelo em que foi aberta."""
        try:
            ativo = HOST_APP.uiapp.ActiveUIDocument.Document.Title
        except Exception:
            ativo = None
        if ativo == self._doc_titulo:
            return True
        forms.alert(u'O Unit Mapper foi aberto em "{}" e o modelo ativo agora é '
                    u'"{}".\n\nVolte para "{}" ou feche e abra o Unit Mapper de '
                    u'novo.'.format(self._doc_titulo, ativo or '?', self._doc_titulo),
                    title='Unit Mapper')
        return False

    def _pedir(self, pedido, texto):
        if self._evento is None or self._handler is None:
            forms.alert(u'Evento do Revit indisponível — feche e abra o Unit '
                        u'Mapper.', title='Unit Mapper')
            return
        self._handler.pedido = pedido
        self.ApplyBtn.IsEnabled = False
        self.StatusLabel.Text = texto
        self._evento.Raise()

    def depois_do_evento(self, tipo, resultado, erro):
        """Chamado na fila do WPF quando o ExternalEvent terminou."""
        if tipo in ('selecionar', 'zoom'):
            if erro:
                self._log.registrar('erro_evento', pedido=tipo, erro=erro)
                forms.alert(u'Não selecionei: {}'.format(erro[:800]),
                            title='Unit Mapper')
            return
        # o modelo mudou: o que foi lido antes nao vale mais
        self._params_lidos = {}
        self._cache_diag = {}
        self._diag_regras = {}
        if erro:
            self._log.registrar('erro_evento', pedido=tipo, erro=erro)
            self._recalcular()
            forms.alert(u'Não concluí:\n\n{}'.format(erro[:1500]), title='Unit Mapper')
            return
        if tipo == 'aplicar':
            self._manuais = {}
            self._recalcular()
            self._mostrar_resultado(resultado)
        elif tipo == 'liberar':
            liberados, falhas = resultado
            self._log.registrar('liberar_resultado', liberados=liberados,
                                falhas=falhas)
            self._recalcular()
            msg = u'Liberados: {}'.format(', '.join(liberados) if liberados else 'nenhum')
            if falhas:
                msg += u'\n\nFalhas:\n' + u'\n'.join(
                    u'{} → {}'.format(nome, erro_) for nome, erro_ in falhas)
            forms.alert(msg, title=u'Liberar variação por grupo')

    def _mostrar_resultado(self, resultado):
        contagem = resultado['contagem']
        falhas = dict((k, list(v)) for k, v in resultado['falhas'].items())
        for chave, ids in self._pre_falhas.items():
            falhas.setdefault(chave, []).extend(ids)
        calculados = self._calculados_aplicados
        gravados = [(n, contagem.get(n, 0)) for n in calculados] + sorted(
            (n, q) for n, q in contagem.items() if n not in calculados)
        nao_aplicados = [i for i in self._itens_aplicados if not i.gravavel]
        self._ids_falhas = ([eid for ids in falhas.values() for eid, _ in ids]
                            + [i.element_id for i in nao_aplicados])
        total_falhas = sum(len(v) for v in falhas.values())
        self._log.registrar(
            'aplicar_resultado', gravado=gravados,
            falhas=dict((motivo, [get_element_id_value(eid) for eid, _ in ids])
                        for motivo, ids in falhas.items()),
            nao_aplicados=[get_element_id_value(i.element_id) for i in nao_aplicados])
        texto = u'Último Aplicar — gravado: {} · não aplicados: {} · falhas e ' \
                u'bloqueios: {}'.format(
                    u', '.join(u'{} {}'.format(n, q) for n, q in gravados) or u'nada',
                    len(nao_aplicados), total_falhas)
        for chave, ids in sorted(falhas.items())[:6]:
            texto += u'\n• {} — {} elemento(s)'.format(chave, len(ids))
        self.ResultadoLabel.Text = texto
        self.ResultadoPanel.Visibility = VISIVEL
        self.SelecionarFalhasBtn.Visibility = VISIVEL if self._ids_falhas else OCULTO
        try:
            # o output do pyRevit pode nao existir mais depois do comando: o
            # resumo acima e o que vale; o output e bonus com links
            relatorio(self._itens_aplicados, gravados, falhas, self._conflitos)
            self._conflitos = {}
        except Exception:
            pass

    def _selecionar(self, ids, zoom=False):
        if not ids or not self._mesmo_documento() or self._evento is None:
            return
        self._log.registrar('zoom' if zoom else 'selecionar',
                            ids=[get_element_id_value(i) for i in ids])
        self._handler.pedido = ('zoom' if zoom else 'selecionar', list(ids))
        self._evento.Raise()

    def btn_selecionar_revit_click(self, sender, e):
        itens = [i for i in self.PreviewGrid.SelectedItems]
        if not itens:
            forms.alert(u'Marque uma ou mais linhas na preview.', title='Unit Mapper')
            return
        self._selecionar([i.element_id for i in itens], zoom=True)

    def preview_duplo_clique(self, sender, e):
        """Duplo clique numa linha: navega e da zoom no elemento (pedido de
        15/09). Nas colunas editaveis (Floor, Unit ID, Type) o duplo clique
        continua sendo para editar."""
        celula = _ancestral(e.OriginalSource, DataGridCell)
        if celula is None:
            return          # cabecalho, barra de rolagem
        coluna = celula.Column
        if coluna is not None and not coluna.IsReadOnly:
            return
        item = celula.DataContext
        if not isinstance(item, PreviewItem):
            return
        e.Handled = True
        # o elemento inteiro vai ao log: e o que se olha quando algo parece errado
        self._log.registrar('duplo_clique', item=self._descrever_item(item))
        self._selecionar([item.element_id], zoom=True)

    def btn_selecionar_falhas_click(self, sender, e):
        self._selecionar(self._ids_falhas)

    def btn_reler_click(self, sender, e):
        """Janela aberta: a selecao e o modelo mudam — relê tudo."""
        if not self._mesmo_documento():
            return
        self.PreviewGrid.CommitEdit()
        self._absorver_edicoes()
        self._fatos = {}
        self._params_lidos = {}
        self._cache_diag = {}
        self._diag_regras = {}
        self._nomes_grupo = {}
        self._rooms = None
        self._coletar_escopo()
        self._log.registrar('reler', escopo=self.escopo, normais=len(self.normais),
                            membros=len(self.membros))
        self._atualizar_rodape()
        self._recalcular()

    # ── config DA OBRA (21/10/2026) ───────────────────────────────────────────

    def _carregar_obra(self):
        """A parte compartilhada vem do `DAT` da obra e MANDA sobre o APPDATA.

        Decisao do Thiago: obra nova COMECA LIMPA — o que cada um tem no
        APPDATA nao e semeado, para a config pessoal de quem abrir primeiro nao
        virar o padrao de todos. Floor sem valor na obra mantem o ordinal
        automatico, que e default de fabrica, nao config de ninguem.

        Modelo que nunca foi salvo nao tem pasta: segue so no APPDATA.
        """
        self._obra_base = wobra.vazia()
        self._obra_caminho = None
        try:
            dados, caminho = um_obra.ler(doc)
        except Exception as erro:
            self._log.registrar('obra_erro', onde='ler', erro=str(erro))
            return
        self._obra_caminho = caminho
        self._obra_base = wobra.copia(dados)
        if not caminho:
            self.CfgProjetoLabel.Text += u'  ·  sem pasta no disco: config só neste computador'
            return

        self.rp_items = [RegraParamItem(r)
                         for r in rp.normalizar_regras(dados['regras_param'])]
        self._refresh_rp()

        self.tip_items = [TipItem(k, dados['tipologia'][k])
                          for k in sorted(dados['tipologia'], key=self._ordem_chave)]
        self._refresh_tip_grid()

        self._amb_offsets = dict(dados['amb_offsets'])

        por_nome = dict((i.get('name'), i) for i in dados['levels'] if i.get('name'))
        for item in self.level_items:
            salvo = por_nome.get(item.Name)
            if salvo is None:
                continue
            item.WbsValue = salvo.get('wbs') or ''
            centena = wcfg.normalizar_centena(salvo.get('centena'))
            item.Centena = u'' if centena is None else str(centena)
        self.FloorGrid.ItemsSource = None
        self.FloorGrid.ItemsSource = self.level_items

        for combo, chave in ((self.ParamDetailBox, 'detail'),
                             (self.ParamWbsBox, 'wbs'),
                             (self.ParamTipologiaBox, 'tipologia')):
            nome = (dados['params'].get(chave) or '').strip()
            if nome:
                combo.Text = nome

        self.CfgProjetoLabel.Text += u'  ·  config da obra: {}'.format(caminho)
        self._log.registrar('obra_lida', caminho=caminho,
                            regras=len(dados['regras_param']),
                            tipos=len(dados['tipologia']),
                            floors=len(dados['levels']))

    def _obra_atual(self):
        """O que esta janela tem agora, no formato do arquivo da obra."""
        nome_detail, nome_wbs, nome_tipologia = self._nomes_params()
        return {
            'regras_param': [dict(i.regra, ativa=bool(i.Ativa))
                             for i in self.rp_items],
            'tipologia': self.tabela_tipologia(),
            'levels': [{'name': i.Name, 'wbs': i.WbsValue or '',
                        'centena': getattr(i, 'Centena', '')}
                       for i in self.level_items],
            'params': {'detail': nome_detail, 'wbs': nome_wbs,
                       'tipologia': nome_tipologia},
            'amb_offsets': dict(self._amb_offsets),
        }

    def _gravar_obra(self):
        """Mescla com o arquivo da obra e grava. Falha nao derruba a janela.

        A pasta costuma ser um Drive compartilhado: sem permissao ou com o
        arquivo em sync, a gravacao falha e o usuario precisa SABER — senao
        acha que configurou a obra e nao configurou.
        """
        if not self._obra_caminho:
            return
        try:
            ok, erro, gravada = um_obra.gravar(doc, self._obra_base,
                                               self._obra_atual())
        except Exception as e:
            ok, erro, gravada = False, str(e), None
        if ok:
            mudou = wobra.diferencas(self._obra_base, gravada)
            self._obra_base = wobra.copia(gravada)
            self._log.registrar('obra_gravada', caminho=self._obra_caminho,
                                mudou=mudou)
        else:
            self.StatusLabel.Text = u'Config da obra NÃO salva: {}'.format(erro)
            self._log.registrar('obra_erro', onde='gravar', erro=erro)

    def salvar_config(self):
        """Tudo que a janela guarda — no Aplicar e ao fechar."""
        cfg, projeto, prefs = self.cfg, self.projeto, self.cfg['prefs']
        nome_detail, nome_wbs, nome_tipologia = self._nomes_params()
        wcfg.definir_regras_param_do_projeto(
            cfg, projeto, [dict(i.regra, ativa=bool(i.Ativa)) for i in self.rp_items])
        wcfg.mesclar_levels(cfg, [{'name': i.Name, 'wbs': i.WbsValue or '',
                                   'centena': getattr(i, 'Centena', '')}
                                  for i in self.level_items])
        wcfg.definir_tipologia_do_projeto(cfg, projeto, self.tabela_tipologia())
        wcfg.definir_regras_do_projeto(cfg, projeto, self.regras_como_dicts())
        prefs['escopo'] = self.escopo
        prefs['calcular'] = bool(self.ChkCalcular.IsChecked)
        prefs['so_mudancas'] = bool(self.ChkSoMudancas.IsChecked)
        prefs['mostrar_bloqueados'] = bool(self.ChkMostrarBloqueados.IsChecked)
        prefs['categorias_excluidas'] = sorted(self._categorias_excluidas)
        prefs['amb_usar'] = bool(self.ChkUsarAmbientes.IsChecked)
        prefs['unit_fonte'] = 'ambiente' if self._unit_pelo_ambiente() else 'sufixo'
        prefs['amb_param_unit'] = (self.ParamUnitRoomBox.Text or '').strip() or 'Unit ID'
        prefs['amb_links'] = bool(self.ChkRoomsLinks.IsChecked)
        prefs['amb_vista'] = bool(self.ChkRoomsVista.IsChecked)
        prefs['amb_auto'] = bool(self.ChkAutoUnit.IsChecked)
        prefs['grupo_nao_migrar'] = sorted(self._nao_migrar)
        prefs['amb_auto_limite_ft'] = self._parse_auto_limite()
        wcfg.definir_offsets_de_ambiente_do_projeto(cfg, projeto, self._amb_offsets)
        prefs['amb_copiar'] = self._amb_copiar()
        prefs['sufixo'] = self._parse_sufixo()
        prefs['offset_ft'] = self._parse_offset()
        prefs['incrementar'] = bool(self.ChkIncrement.IsChecked)
        prefs['reiniciar_por_pavimento'] = bool(self.ChkReiniciar.IsChecked)
        prefs['param_detail'] = nome_detail
        prefs['param_wbs'] = nome_wbs
        prefs['param_tipologia'] = nome_tipologia
        linhas_fixos = self._linhas_fixos()
        prefs['fixos_csv'] = self.csv_fixos
        prefs['fixos_valores'] = dict((n, v) for n, v, _ in linhas_fixos if n)
        prefs['fixos_ativos'] = [n for n, _, marcado in linhas_fixos if marcado and n]
        prefs['fixos_em_grupo'] = bool(self.ChkFixosGrupo.IsChecked)
        ok, erro = wcfg.salvar(cfg)
        if not ok:
            self.StatusLabel.Text = u'Config não salva: {}'.format(erro)
        # a parte compartilhada vai para o DAT da obra, mesclada com o que os
        # outros gravaram de la para ca (21/10/2026)
        self._gravar_obra()
        return ok

    def ao_fechar(self, sender, args):
        try:
            self._commit_grids()
            self.salvar_config()
            self._log.configuracao(self._config_para_log())
            self._log.registrar('fechar', falhas_de_disco_do_log=um_log.SAUDE)
        except Exception:
            pass
        if self._handler is not None:
            self._handler.janela = None
        if sys.modules.get(_CHAVE_JANELA) is self:
            sys.modules.pop(_CHAVE_JANELA, None)


# ── relatorio ─────────────────────────────────────────────────────────────────

def _linkify(items, limite=25):
    """Lista de links clicaveis para os elementos (o motivo perde a graca se
    nao der para achar o elemento no modelo)."""
    for item in items[:limite]:
        output.print_md("  - {}".format(output.linkify(item.element_id, title=item.ElemId)))
    if len(items) > limite:
        output.print_md("  - _... e mais {}_".format(len(items) - limite))


def relatorio(itens, gravados, falhas_escrita, conflitos):
    output.print_md("## Unit Mapper")

    for nome, quantos in gravados:
        output.print_md("- **{}**: {} elemento(s)".format(nome, quantos))

    descartados = {}
    for item in itens:
        if item.gravavel:
            continue
        motivo = item.linha['motivo']
        chave = weng.MOTIVO_TEXTO.get(motivo, motivo) if motivo else item.Situacao
        descartados.setdefault(chave, []).append(item)

    if descartados:
        output.print_md("### Nao aplicados")
        for chave in sorted(descartados):
            grupo = descartados[chave]
            output.print_md("**{}** — {} elemento(s)".format(chave, len(grupo)))
            _linkify(grupo)

    if falhas_escrita:
        output.print_md("### Falhas na gravacao")
        for chave in sorted(falhas_escrita):
            ids = falhas_escrita[chave]
            output.print_md("**{}** — {} elemento(s)".format(chave, len(ids)))
            for eid, titulo in ids[:25]:
                output.print_md("  - {}".format(output.linkify(eid, title=titulo)))
            if len(ids) > 25:
                output.print_md("  - _... e mais {}_".format(len(ids) - 25))

    sem_tip = [i for i in itens if i.calc_gravavel and not i.linha['tipologia']]
    if sem_tip:
        chaves = sorted(set(str(i.linha['wbs']) for i in sem_tip))
        output.print_md("### Sem Type")
        output.print_md("{} elemento(s). Unit ID ausentes na tabela: `{}`".format(
            len(sem_tip), ', '.join(chaves[:40])))

    if conflitos:
        output.print_md("### Migracao da config — conflitos resolvidos")
        output.print_md("Valores diferentes entre os configs antigos. "
                        "Venceu o primeiro (WBSTipologia):")
        for chave in sorted(conflitos):
            output.print_md("- `{}`: **{}** (descartado: {})".format(
                chave, conflitos[chave][0], ', '.join(conflitos[chave][1:])))


# ── gravacao (roda DENTRO do ExternalEvent) ───────────────────────────────────

#: Guarda de janela unica em sys.modules — cada clique roda num modulo novo,
#: um global comum voltaria a None (licao do ZoneSync v1.1).
_CHAVE_JANELA = '__PYAMBAR_UnitMapper_instance__'


def aplicar_no_modelo(documento, trabalho):
    """{'contagem': {param: n}, 'falhas': {motivo: [(id, rotulo)]}}.

    `trabalho`: [{'id', 'rotulo', 'valores': [(param, valor)]}] montado pela
    janela. O diagnostico e refeito aqui: entre a preview e o clique o
    modelo pode ter mudado.
    """
    contagem = {}
    falhas = {}

    def registrar(nome, erro, tarefa):
        falhas.setdefault(u'{}: {}'.format(nome, erro), []).append(
            (tarefa['id'], tarefa['rotulo']))

    def fazer():
        for tarefa in trabalho:
            elemento = documento.GetElement(tarefa['id'])
            if elemento is None:
                registrar('-', u'elemento não existe mais', tarefa)
                continue
            em_grupo = esta_em_grupo(elemento)
            for nome, valor in tarefa['valores']:
                if valor is None or valor == '':
                    continue
                param, problema, _ = diagnosticar_param(elemento, nome, em_grupo)
                if problema:
                    registrar(nome, problema, tarefa)
                    continue
                gravou, erro = gravar_param(param, valor)
                if gravou:
                    contagem[nome] = contagem.get(nome, 0) + 1
                else:
                    registrar(nome, erro, tarefa)

    executar_em_transacao("Unit Mapper", fazer, documento)
    return {'contagem': contagem, 'falhas': falhas}


def selecionar_no_modelo(uidoc_ativo, ids):
    """v3.4: o log de 15/09 teve 2x "Member of elementIds is not valid for
    this document" — elemento apagado depois da preview. So vai o que ainda
    existe, e o ShowElements nao derruba a selecao."""
    documento = uidoc_ativo.Document
    lista = List[ElementId]()
    for eid in ids:
        if documento.GetElement(eid) is not None:
            lista.Add(eid)
    uidoc_ativo.Selection.SetElementIds(lista)
    if lista.Count:
        try:
            uidoc_ativo.ShowElements(lista)
        except Exception:
            pass
    return lista.Count


#: pes em volta do elemento no zoom — o mesmo do Fluxo ARN
FOLGA_ZOOM = 1.0


def selecionar_e_zoom(uidoc_ativo, ids):
    """Seleciona, mostra e centraliza na vista ativa — o _selecionar_e_zoom do
    Fluxo ARN (af_evento). ShowElements sozinho nao aproxima o bastante."""
    selecionar_no_modelo(uidoc_ativo, ids)
    documento = uidoc_ativo.Document
    minimos, maximos = [], []
    for eid in ids:
        elemento = documento.GetElement(eid)
        bb = elemento.get_BoundingBox(None) if elemento is not None else None
        if bb is not None:
            minimos.append((bb.Min.X, bb.Min.Y, bb.Min.Z))
            maximos.append((bb.Max.X, bb.Max.Y, bb.Max.Z))
    envolve = caixa_que_envolve(minimos, maximos, FOLGA_ZOOM)
    if envolve is None:
        return
    ativa = get_element_id_value(uidoc_ativo.ActiveView.Id)
    for uiview in uidoc_ativo.GetOpenUIViews():
        if get_element_id_value(uiview.ViewId) == ativa:
            uiview.ZoomAndCenterRectangle(XYZ(*envolve[0]), XYZ(*envolve[1]))


class UnitMapperHandler(IExternalEventHandler):
    """Um pedido por vez: ('aplicar', trabalho) | ('liberar', definicoes) |
    ('selecionar', [ElementId])."""

    def __init__(self, titulo_documento):
        self.titulo = titulo_documento
        self.pedido = None
        self.janela = None

    def Execute(self, uiapp):
        pedido, self.pedido = self.pedido, None
        if pedido is None:
            return
        tipo, dados = pedido
        resultado = erro = None
        try:
            uidoc_ativo = uiapp.ActiveUIDocument
            documento = uidoc_ativo.Document
            if documento.Title != self.titulo:
                raise Exception(u'o modelo ativo ("{}") não é o do Unit Mapper '
                                u'("{}")'.format(documento.Title, self.titulo))
            if tipo == 'aplicar':
                resultado = aplicar_no_modelo(documento, dados)
            elif tipo == 'liberar':
                resultado = executar_em_transacao(
                    "Liberar variacao por grupo",
                    lambda: liberar_variacao_por_grupo(dados, documento), documento)
            elif tipo == 'selecionar':
                selecionar_no_modelo(uidoc_ativo, dados)
            elif tipo == 'zoom':
                selecionar_e_zoom(uidoc_ativo, dados)
        except Exception as ex:
            erro = u'{}\n{}'.format(ex, traceback.format_exc())
        janela = self.janela
        if janela is None:
            return
        try:
            janela.Dispatcher.BeginInvoke(System_Action(
                lambda: janela.depois_do_evento(tipo, resultado, erro)))
        except Exception:
            pass

    def GetName(self):
        return "PYAMBAR_UnitMapper"


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    aberta = sys.modules.get(_CHAVE_JANELA)
    if aberta is not None:
        try:
            if aberta.IsVisible:
                aberta.Activate()
                return
        except Exception:
            pass
        sys.modules.pop(_CHAVE_JANELA, None)

    try:
        cfg, migrou, conflitos = wcfg.carregar(fontes_legado=FONTES_LEGADO)
        projeto = wcfg.nome_projeto(doc.Title)

        aviso = None
        if migrou:
            aviso = "Config unificada criada"
            if conflitos:
                aviso += " ({} conflito(s) resolvido(s))".format(len(conflitos))

        # com selecao, trabalha nela; sem, o ultimo escopo que nao era selecao
        if uidoc.Selection.GetElementIds().Count:
            escopo = um_escopo.SELECAO
        elif cfg['prefs'].get('escopo') in (um_escopo.VISTA, um_escopo.PROJETO):
            escopo = cfg['prefs']['escopo']
        else:
            escopo = um_escopo.VISTA

        handler = UnitMapperHandler(doc.Title)
        evento = ExternalEvent.Create(handler)
        janela = WBSCompletoWindow(cfg, projeto, aviso, escopo,
                                   conflitos if migrou else {}, handler, evento)
        handler.janela = janela
        sys.modules[_CHAVE_JANELA] = janela
        janela.Show()

    except OperationCanceledException:
        return
    except Exception as e:
        output.print_md("**Erro:** {}".format(str(e)))
        output.print_md("```\n{}\n```".format(traceback.format_exc()))
        um_log.LogDeSessao().registrar('erro_ao_abrir', erro=str(e),
                                       rastro=traceback.format_exc())


if __name__ == "__main__":
    main()
