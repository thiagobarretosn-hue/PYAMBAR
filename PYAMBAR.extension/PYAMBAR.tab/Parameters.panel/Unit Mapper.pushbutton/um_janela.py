# -*- coding: utf-8 -*-
__title__ = "Unit\nMapper"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "3.0.2"

# 3.0.2 (15/09/2026) — pedido do Thiago: botao "Vista ativa" (todos os elementos
# de modelo da vista, grupos inteiros, sem linhas de centro) e a dica do offset
# reescrita pelo que o motor faz (o offset e SOMADO ao Z do elemento). Abrir
# sem selecao pega a vista ativa; o offset aceita pes e polegadas (0.1" 0.1'
# 1'-6") pelo Snippets._comprimento_texto; padrao do offset 0.

# 3.0.1 (14/09/2026) — pedido de um usuario: a janela NAO MODAL. E o Unit Mapper
# 3.0 da distribuicao (PYAMBAR v2.14.0) com SO isso mudado — as regras, o escopo
# e os ambientes da v3.2 do lab ficam de fora ate serem validados.
#
# Este arquivo e o um_janela.py, executado como MODULO pelo script.py
# (Snippets._janela_modeless; motivo em [[api-pyrevit-motor]]). A janela abre
# com Show(); Aplicar e Liberar variacao vao por ExternalEvent
# (UnitMapperHandler); o resultado aparece na janela; "Reler selecao" pega a
# selecao nova; as tabelas e preferencias sao salvas no Aplicar e ao fechar.

import os
import sys
import traceback

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import (
    BuiltInCategory, CategoryType, ElementId, FilteredElementCollector, Group,
    Level, LocationCurve, LocationPoint, StorageType, SubTransaction,
)
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI import ExternalEvent, IExternalEventHandler
from pyrevit import HOST_APP, forms, revit, script
from pyrevit.forms import WPFWindow

from System import Action as System_Action
from System.Collections.Generic import List
from System.Windows import Thickness, VerticalAlignment, Visibility
from System.Windows.Controls import (
    Button, CheckBox, ComboBox, Orientation, StackPanel, TabControl,
)

from Snippets import _wbs_config as wcfg
from Snippets import _wbs_engine as weng
from Snippets._comprimento_texto import texto_para_pes
from Snippets.data._csv_utilities import escrever_csv_utf8, ler_csv_utf8

VISIVEL = Visibility.Visible
OCULTO = Visibility.Collapsed

doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()
PATH_SCRIPT = os.path.dirname(__file__)
PATH_PULLDOWN = os.path.dirname(PATH_SCRIPT)


# Configs antigos das 4 ferramentas do pulldown, em ordem de prioridade —
# lidos so na primeira execucao, para montar a config unificada.
FONTES_LEGADO = wcfg.fontes_legado(
    PATH_PULLDOWN, seed_proprio=os.path.join(PATH_SCRIPT, 'config.json'))


# ── helpers Revit ─────────────────────────────────────────────────────────────

def get_element_id_value(eid):
    return eid.Value if hasattr(eid, 'Value') else eid.IntegerValue


# ── vista ativa (3.0.2) ───────────────────────────────────────────────────────
# Copia do um_escopo do lab (v3.1): este botao vai para a distribuicao sozinho,
# sem o modulo. Categorias que nao sao "coisa para parametrizar" — as linhas de
# centro dos tubos sao elemento dependente, tudo read-only, e encheram a preview
# de "Floor read-only" no 1o teste da v3.1.
_NOMES_FORA_DA_VISTA = (
    'OST_Rooms', 'OST_Areas', 'OST_MEPSpaces', 'OST_RvtLinks', 'OST_Cameras',
    'OST_Lines', 'OST_SketchLines', 'OST_Levels', 'OST_Grids',
    'OST_PipeCurvesCenterLine', 'OST_PipeFittingCenterLine',
    'OST_DuctCurvesCenterLine', 'OST_DuctFittingCenterLine',
    'OST_FlexPipeCurvesCenterLine', 'OST_FlexDuctCurvesCenterLine',
    'OST_ConduitCenterLine', 'OST_ConduitFittingCenterLine',
    'OST_CableTrayCenterLine', 'OST_CableTrayFittingCenterLine',
    'OST_ProjectBasePoint', 'OST_SharedBasePoint', 'OST_IOS_GeoSite',
)
_FORA_DA_VISTA = set()
for _nome in _NOMES_FORA_DA_VISTA:
    _bic = getattr(BuiltInCategory, _nome, None)
    if _bic is not None:
        _FORA_DA_VISTA.add(int(_bic))


def eh_de_modelo(elemento):
    try:
        categoria = elemento.Category
        if categoria is None or categoria.CategoryType != CategoryType.Model:
            return False
        if elemento.ViewSpecific:
            return False
        return get_element_id_value(categoria.Id) not in _FORA_DA_VISTA
    except Exception:
        return False


def _grupo_mais_externo(documento, elemento):
    atual = elemento
    for _ in range(20):
        gid = getattr(atual, 'GroupId', None)
        if gid is None or get_element_id_value(gid) <= 0:
            return atual
        pai = documento.GetElement(gid)
        if pai is None:
            return atual
        atual = pai
    return atual


def elementos_da_vista(documento, vista):
    """Elementos de modelo visiveis na vista — membro de grupo entra pelo grupo
    mais externo, e `coletar_selecao` desce nos membros (o mesmo caminho da
    selecao, entao grupo e membro sao tratados igual)."""
    vistos = set()
    saida = []
    coletor = FilteredElementCollector(documento, vista.Id) \
        .WhereElementIsNotElementType()
    for elemento in coletor.ToElements():
        if not eh_de_modelo(elemento):
            continue
        topo = _grupo_mais_externo(documento, elemento)
        chave = get_element_id_value(topo.Id)
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(topo)
    return saida


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


# ── itens de UI (atributos simples: o binding TwoWay do WPF escreve neles) ─────

class LevelItem(object):
    def __init__(self, name, elev_ft, wbs_value):
        self.Name = name
        self.ElevDisplay = weng.format_elevation(elev_ft)
        self.WbsValue = wbs_value
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


class PreviewItem(object):
    """Linha da preview. As tres colunas de valor sao editaveis: guardamos o
    calculado ao lado para saber, na hora do recalculo, o que o usuario mexeu."""

    def __init__(self, linha, element, problemas, de_grupo=False, manual=None):
        self.element = element
        self.element_id = element.Id
        self.linha = linha
        self.problemas = problemas
        self.de_grupo = de_grupo

        self.ElemId = str(linha['id'])
        self.Origem = 'membro de grupo' if de_grupo else ''
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
        if motivo and not manual:
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
    def gravavel(self):
        if self.problemas:
            return False
        # linha editada a mao vale mesmo quando o calculo nao resolveu o
        # pavimento: e exatamente para esses casos que a edicao existe
        if self.linha['motivo'] and not self.edicoes():
            return False
        return any(v is not None for v in self.valores_finais())


# ── janela ────────────────────────────────────────────────────────────────────

class WBSCompletoWindow(WPFWindow):

    def __init__(self, normais, membros, cfg, projeto, aviso_migracao,
                 conflitos=None, handler=None, evento=None):
        # caminho absoluto: rodando como modulo, o relativo seria resolvido
        # pela pasta do comando em execucao
        WPFWindow.__init__(self, os.path.join(PATH_SCRIPT, 'ui.xaml'))
        self.result = None
        self._conflitos = conflitos or {}
        self._handler = handler
        self._evento = evento
        self._doc_titulo = doc.Title
        self._ids_falhas = []
        self._itens_aplicados = []
        self._gravados_nomes = []
        self.Closing += self.ao_fechar
        self.normais = normais
        self.membros = membros
        self.elementos = list(normais) + list(membros)
        self.cfg = cfg
        self.projeto = projeto
        self.prefs = cfg['prefs']
        self.itens = []
        self._cache_diag = {}
        self._defs_travadas = {}
        self._fixos = []            # [(combo_nome, combo_valor, check)]
        self._manuais = {}          # {element_id: {campo: texto digitado}}
        self._pronto = False

        # pavimentos: nivel do modelo + valor salvo (ou ordinal automatico)
        salvos = wcfg.levels_como_mapa(cfg)
        self.level_items = [
            LevelItem(nome, elev, salvos.get(nome, weng.auto_ordinal(nome)))
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
        nomes_disponiveis = collect_param_names(self.elementos)
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
        self.OffsetBox.Text = str(self.prefs['offset_ft'])
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
        self.CfgArquivoLabel.Text = wcfg.caminho_config()

        self._aviso = aviso_migracao
        self._atualizar_rodape()
        self.ConfigLabel.ToolTip = wcfg.caminho_config()

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

        sufixo = self._parse_sufixo()
        offset = self._parse_offset()
        if sufixo is None or offset is None:
            campo = 'Sufixo' if sufixo is None else 'Offset'
            self.StatusLabel.Text = "{} inválido — corrija para continuar.".format(campo)
            self.PreviewGrid.ItemsSource = None
            self.ApplyBtn.IsEnabled = False
            self.ApplyBtn.Content = "Aplicar"
            return

        self._defs_travadas = {}
        ranges = self._ranges()
        if not ranges:
            self.StatusLabel.Text = ("Nenhum nível com Floor preenchido — "
                                     "veja a aba Floors.")
            self.PreviewGrid.ItemsSource = None
            self.ApplyBtn.IsEnabled = False
            self.ApplyBtn.Content = "Aplicar"
            return

        registros = []
        for el in self.elementos:
            span = get_element_span(el)
            registros.append({
                'id': get_element_id_value(el.Id),
                'z_min': span[0] if span else None,
                'z_max': span[1] if span else None,
            })

        linhas = weng.atribuir(
            registros, ranges,
            sufixo=sufixo,
            incrementar=bool(self.ChkIncrement.IsChecked),
            reiniciar_por_pavimento=bool(self.ChkReiniciar.IsChecked),
            offset_ft=offset,
            tipologia=self.tabela_tipologia(),
            regras=self.regras_como_dicts(),
        )

        self._absorver_edicoes()

        qtd_normais = len(self.normais)
        self.itens = []
        for i, (linha, el) in enumerate(zip(linhas, self.elementos)):
            problemas = self._problemas_do_elemento(el) if linha['motivo'] is None else []
            self.itens.append(PreviewItem(
                linha, el, problemas,
                de_grupo=i >= qtd_normais,
                manual=self._manuais.get(linha['id'])))

        self.PreviewGrid.ItemsSource = self.itens

        resumo = weng.resumir(linhas)
        gravaveis = sum(1 for i in self.itens if i.gravavel)
        # uma linha editada a mao pode ser gravavel sem ter pavimento calculado,
        # entao a subtracao pode passar de zero — nao existe bloqueio negativo
        bloqueados = max(0, sum(1 for i in self.itens if i.problemas))

        partes = ["{} com Floor".format(resumo['com_pavimento'])]
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

        if self.membros:
            partes.append("{} membros de grupo".format(len(self.membros)))
        if self._manuais:
            partes.append("{} editados à mão".format(len(self._manuais)))

        self.StatusLabel.Text = "  |  ".join(partes)
        self.ApplyBtn.IsEnabled = gravaveis > 0
        self.ApplyBtn.Content = "Aplicar ({})".format(gravaveis)

        self.LimparManuaisBtn.Visibility = VISIVEL if self._manuais else OCULTO

        travados = sorted(self._defs_travadas)
        self.LiberarBtn.Visibility = VISIVEL if travados else OCULTO
        if travados:
            self.LiberarBtn.ToolTip = (
                "Liga 'Values can vary by group instance' para: {}.\n"
                "Altera o parametro no PROJETO INTEIRO.".format(', '.join(travados)))

    # ── eventos: aba Elementos ────────────────────────────────────────────────

    def campo_alterado(self, sender, e):
        if not self._pronto:
            return
        self.ChkReiniciar.IsEnabled = bool(self.ChkIncrement.IsChecked)
        self._recalcular()

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
        # janela nao modal: a Transaction so pode rodar dentro do ExternalEvent
        self._pedir(('liberar', travados), u'Liberando a variação por grupo...')

    def tab_changed(self, sender, e):
        # o SelectionChanged dos DataGrids internos borbulha ate aqui
        if not self._pronto or not isinstance(e.OriginalSource, TabControl):
            return
        if self.Abas.SelectedIndex == 0:
            self._recalcular()
        else:
            self._atualizar_info_fixos()

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

        nome_detail, nome_wbs, nome_tipologia = self._nomes_params()
        fixos = self.valores_fixos()
        fixos_em_grupo = self.valores_fixos_para_grupo()
        trabalho = []
        for item in aplicaveis:
            detail, wbs, tipo = item.valores_finais()
            valores = [(nome_detail, detail), (nome_wbs, wbs), (nome_tipologia, tipo)]
            # o checkbox decide se os fixos descem para os membros de grupo
            escopo = fixos_em_grupo if item.de_grupo else fixos
            valores.extend(sorted(escopo.items()))
            trabalho.append({'id': item.element_id, 'rotulo': item.ElemId,
                             'valores': valores})
        self._itens_aplicados = list(self.itens)
        self._gravados_nomes = [nome_detail, nome_wbs, nome_tipologia] + sorted(fixos)
        self._pedir(('aplicar', trabalho),
                    u'Aplicando em {} elemento(s)...'.format(len(trabalho)))

    def btn_cancel_click(self, sender, e):
        self.Close()

    # ── nao modal (3.0.1) ─────────────────────────────────────────────────────

    def _atualizar_rodape(self):
        rodape = "{} elemento(s)  ·  {}".format(len(self.elementos),
                                                self.projeto or '(sem nome)')
        if self._aviso:
            rodape = "{}  ·  {}".format(self._aviso, rodape)
        self.ConfigLabel.Text = rodape

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
        if tipo == 'selecionar':
            if erro:
                forms.alert(u'Não selecionei: {}'.format(erro[:800]),
                            title='Unit Mapper')
            return
        self._cache_diag = {}
        if erro:
            self._recalcular()
            forms.alert(u'Não concluí:\n\n{}'.format(erro[:1500]), title='Unit Mapper')
            return
        if tipo == 'aplicar':
            self._manuais = {}
            self._recalcular()
            self._mostrar_resultado(resultado)
        elif tipo == 'liberar':
            liberados, falhas = resultado
            self._recalcular()
            msg = u'Liberados: {}'.format(', '.join(liberados) if liberados else 'nenhum')
            if falhas:
                msg += u'\n\nFalhas:\n' + u'\n'.join(
                    u'{} → {}'.format(nome, erro_) for nome, erro_ in falhas)
            forms.alert(msg, title=u'Liberar variação por grupo')

    def _mostrar_resultado(self, resultado):
        contagem = resultado['contagem']
        falhas = resultado['falhas']
        gravados = [(nome, contagem.get(nome, 0)) for nome in self._gravados_nomes]
        nao_aplicados = [i for i in self._itens_aplicados if not i.gravavel]
        self._ids_falhas = ([eid for ids in falhas.values() for eid, _ in ids]
                            + [i.element_id for i in nao_aplicados])
        total_falhas = sum(len(v) for v in falhas.values())
        texto = u'Último Aplicar — {} · não aplicados: {} · falhas de gravação: ' \
                u'{}'.format(u', '.join(u'{}: {}'.format(n, q) for n, q in gravados),
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

    def btn_selecionar_falhas_click(self, sender, e):
        if not self._ids_falhas or not self._mesmo_documento() or self._evento is None:
            return
        self._handler.pedido = ('selecionar', list(self._ids_falhas))
        self._evento.Raise()

    def btn_reler_click(self, sender, e):
        """Janela aberta: o usuario seleciona outra coisa no Revit."""
        if not self._mesmo_documento():
            return
        brutos = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
        brutos = [el for el in brutos if el is not None]
        normais, membros = coletar_selecao(brutos)
        if not normais and not membros:
            forms.alert(u'Selecione elementos no Revit e clique em "Reler seleção".',
                        title='Unit Mapper')
            return
        self._aviso = None
        self._trocar_elementos(normais, membros)

    def btn_vista_ativa_click(self, sender, e):
        """3.0.2: todos os elementos de modelo da vista ativa de AGORA — a
        janela fica aberta enquanto o usuario troca de vista."""
        if not self._mesmo_documento():
            return
        uidoc_ativo = HOST_APP.uiapp.ActiveUIDocument
        brutos = elementos_da_vista(uidoc_ativo.Document, uidoc_ativo.ActiveView)
        normais, membros = coletar_selecao(brutos)
        # a descida no grupo traz as linhas de centro dos tubos: filtrar tambem
        membros = [el for el in membros if eh_de_modelo(el)]
        if not normais and not membros:
            forms.alert(u'A vista ativa ("{}") não tem elementos de modelo.'.format(
                uidoc_ativo.ActiveView.Name), title='Unit Mapper')
            return
        self._aviso = u'Vista ativa "{}"'.format(uidoc_ativo.ActiveView.Name)
        self._trocar_elementos(normais, membros)

    def _trocar_elementos(self, normais, membros):
        self.PreviewGrid.CommitEdit()
        self._absorver_edicoes()
        self.normais = normais
        self.membros = membros
        self.elementos = list(normais) + list(membros)
        self._cache_diag = {}
        self._atualizar_rodape()
        self._recalcular()

    def salvar_config(self):
        """O que o main() da 3.0 salvava depois do ShowDialog — agora no
        Aplicar e ao fechar."""
        cfg, projeto, prefs = self.cfg, self.projeto, self.cfg['prefs']
        nome_detail, nome_wbs, nome_tipologia = self._nomes_params()
        wcfg.mesclar_levels(cfg, [{'name': i.Name, 'wbs': i.WbsValue or ''}
                                  for i in self.level_items])
        wcfg.definir_tipologia_do_projeto(cfg, projeto, self.tabela_tipologia())
        wcfg.definir_regras_do_projeto(cfg, projeto, self.regras_como_dicts())
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
        return ok

    def ao_fechar(self, sender, args):
        try:
            self._commit_grids()
            self.salvar_config()
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

    sem_tip = [i for i in itens if i.gravavel and not i.linha['tipologia']]
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
#: um global comum voltaria a None (licao do ZoneSync v1.1). Chave propria:
#: convive com o Unit Mapper do lab.
_CHAVE_JANELA = '__PYAMBAR_UnitMapper_instance__'


def aplicar_no_modelo(documento, trabalho):
    """{'contagem': {param: n}, 'falhas': {motivo: [(id, rotulo)]}} — a mesma
    gravacao do main() da 3.0, com o diagnostico refeito na hora."""
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
            # membro de grupo so aceita parametro que varia entre grupos
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
                lista = List[ElementId]()
                for eid in dados:
                    lista.Add(eid)
                uidoc_ativo.Selection.SetElementIds(lista)
                if lista.Count:
                    uidoc_ativo.ShowElements(lista)
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
        sel = uidoc.Selection.GetElementIds()
        origem = None
        if sel.Count:
            brutos = [doc.GetElement(i) for i in sel]
            brutos = [el for el in brutos if el is not None]
            normais, membros = coletar_selecao(brutos)
        else:
            # 3.0.2 (pedido do Thiago): sem selecao, abre com a vista ativa
            normais, membros = coletar_selecao(
                elementos_da_vista(doc, uidoc.ActiveView))
            membros = [el for el in membros if eh_de_modelo(el)]
            origem = u'Sem seleção: vista ativa "{}"'.format(uidoc.ActiveView.Name)
        if not normais and not membros:
            forms.alert("Nada para mapear: selecione elementos ou abra uma vista "
                        "com elementos de modelo.", exitscript=True)

        cfg, migrou, conflitos = wcfg.carregar(fontes_legado=FONTES_LEGADO)
        projeto = wcfg.nome_projeto(doc.Title)

        aviso = None
        if migrou:
            aviso = "Config unificada criada"
            if conflitos:
                aviso += " ({} conflito(s) resolvido(s))".format(len(conflitos))
        if origem:
            aviso = origem if not aviso else u'{}  ·  {}'.format(origem, aviso)

        handler = UnitMapperHandler(doc.Title)
        evento = ExternalEvent.Create(handler)
        janela = WBSCompletoWindow(normais, membros, cfg, projeto, aviso,
                                   conflitos if migrou else {}, handler, evento)
        handler.janela = janela
        sys.modules[_CHAVE_JANELA] = janela
        janela.Show()

    except OperationCanceledException:
        return
    except Exception as e:
        output.print_md("**Erro:** {}".format(str(e)))
        output.print_md("```\n{}\n```".format(traceback.format_exc()))


if __name__ == "__main__":
    main()
