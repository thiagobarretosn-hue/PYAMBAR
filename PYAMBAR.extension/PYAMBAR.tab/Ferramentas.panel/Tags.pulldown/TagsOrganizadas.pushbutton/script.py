# -*- coding: utf-8 -*-
"""
Tags Organizadas
Etiqueta a vista ativa (projeto e vinculos) e arruma as tags para nao se
sobreporem: chamada a 45 ou 90 graus com ombro horizontal, tags empilhadas em
coluna, longe do desenho. Passes, caixas e stubs ganham uma tag cada;
conduites ganham uma por trecho e mais uma a cada X pes, com a ponta da
chamada deslizando ao longo do trecho ate achar espaco.

COMO (motor puro com testes em lib/Snippets/_tag_arranjo.py e _tag_trechos.py):
  1. janela: categorias, tipo de tag, ponta de seta, X dos lineares, arranjo
  2. grava a ponta de seta no PROPRIO tipo de tag (igual a edicao manual)
  3. coleta; peca aninhada nao ganha tag; elemento/trecho que ja tem tag e
     pulado — as tags existentes ficam e viram obstaculo
  4. mede a caixa REAL de cada tag numa Transaction DESFEITA
  5. obstaculos: conduites e tubos com largura real, conexoes, DWG de fundo
  6. o motor escolhe a posicao de cada tag
  7. cria as tags numa Transaction so (um Ctrl+Z desfaz)

Une tags so quando o texto e 100% igual (nunca em conduite).
Categoria nova: acrescentar em categorias.py.

VERSAO: 0.30 (27/10/2026) — Installation Plans, conexoes como o ajuste manual do PH3 B5:
ramificacoes ortogonais, 90 graus (60/45 so para quem ficou cruzando algo),
seta no centro do te e na borda so quando a perna cairia sobre o ramal, perna
que nao cruza o outro te da mesma tag, tag unida que nao se desfaz por somar a
tinta das chamadas e varias ordens de colocacao (a vizinha sobe e a outra cabe).
0.29 (26/10/2026) — tag de tubo alinhada: o motor le o label visivel
do tipo escolhido (altura da letra) e calcula o texto igual nos 4 lados, em
qualquer tamanho de letra; o ajuste manual por lado ficou opcional e recolhido.
0.28 (26/10/2026) — Installation Plans com a familia de tag nova (2026-,
1,5 mm): ajuste fino no menu com a distancia do texto POR LADO do tubo
(acima/abaixo, esquerda/direita); altura do texto medida na familia.
0.27 (23/10/2026) — pulldown Tags + atalhos por template (Installation
Plans, Wall FAC, Slab Passes); texto do tubo a 1,4 mm, par quente/frio e filas
na mesma estacao, respiro das conexoes, uniao de te igual, polimento; saida
silenciosa na distribuicao (prefs.json: balao, selecao e relatorio em arquivo).
0.26 (23/10/2026) — Installation Plans em planta (PH3 UNIT B5): tag de
tubo ALINHADA ao tubo, sem chamada, ao lado dele (texto no topo da caixa do
rotulo); chamada so onde nao cabe, 90 graus primeiro; paredes (cortina do
steel frame, espessura pelos paineis) e folga ate tubo vizinho como obstaculo.
0.25 (12/10/2026) — auditoria: motor 2-3x mais rapido no estilo margem
com o MESMO resultado (parte fixa do custo em cache e no piso da poda); Refazer
apaga so o que recria (tag manual de Elbow/Cap em planta sumia); AUTO.json
quebrado nao trava mais o botao; tag sem caixa nao derruba a vista; barra de
progresso cobre todas as fases e tem Cancelar (desfaz tudo); relatorio com
links para selecionar as tags com conflito e os elementos sem tag; janela:
margem desliga o que nao usa, ajuste fino recolhido, busca Rapida/Completa,
rodape com a contagem real. Pesos do estilo margem em cfg_margem (snippet).
0.24 — abrir espaco tenta antes mover SO a tag que corta tubo (F10: 0 corte).
0.23 — seta SEMPRE sobre a peca; cota evitada quando ha espaco.
Historico completo: git log -- "<esta pasta>" lib/Snippets/_tag_arranjo.py
AUTOR: Thiago Barreto Sobral Nunes
"""
__title__ = "Tags\nOrganizadas"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "0.30"

import io
import json
import os
import sys
import time
import traceback

from Autodesk.Revit.DB import (ElementId, SpecTypeId, TransactionGroup, UnitUtils, ViewDrafting,
                               ViewPlan, ViewSection)
from System import Int64
from System.Collections.Generic import List

from pyrevit import revit, forms, script

LIB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib')
if LIB_PATH not in sys.path:
    sys.path.append(LIB_PATH)

# Descartar os modulos DESTA ferramenta ja carregados, ANTES de importar.
# O pyRevit 6.5 usa um engine IronPython por extensao e guarda os modulos entre
# cliques (conferido no codigo do pyRevit, 13/10/2026). Depois de trocar de
# branch sem Reload o script novo rodava com coleta/motor velhos — e o Refazer
# da v0.24 com a coleta da v0.25 nao apagava nada, em silencio. Recarregar do
# disco a cada clique (padrao do BancadaAuto) custa a importacao e garante que
# o botao roda o que esta no disco. Tirar de sys.modules nao basta: o pacote
# Snippets guarda o submodulo como atributo e 'from Snippets import x' o
# devolveria velho — por isso o delattr.
_PROPRIOS = ('coleta', 'janela', 'categorias', 'Snippets._tag_arranjo', 'Snippets._tag_trechos',
             'Snippets._tag_templates', 'Snippets._tag_regras')
_pacote = sys.modules.get('Snippets')
for _nome_mod in _PROPRIOS:
    sys.modules.pop(_nome_mod, None)
    if _pacote is not None and _nome_mod.startswith('Snippets.'):
        try:
            delattr(_pacote, _nome_mod.split('.', 1)[1])
        except AttributeError:
            pass

from Snippets._tag_arranjo import (Cena, arranjar, auditar, cfg_da_escala, cfg_margem,  # noqa: E402
                                   regiao_do_desenho, silhueta, unir_iguais)
from Snippets._tag_trechos import itens_lineares, pentes, trechos  # noqa: E402
from Snippets import _tag_templates as tag_templates  # noqa: E402
from Snippets._tag_regras import centro_do_texto, ler_pedido_auto, limitar_selecao  # noqa: E402
from Snippets import _tag_arranjo as _motor  # noqa: E402

import categorias as reg  # noqa: E402
import coleta  # noqa: E402
from janela import Janela, MANTER, NENHUMA  # noqa: E402

doc = revit.doc
uidoc = revit.uidoc
PATH_SCRIPT = os.path.dirname(__file__)


def _tela_ligada():
    """prefs.json de fabrica: no lab a tela fica ligada (relatorio na janela
    de output, para investigar); na distribuicao desligada — balao, selecao e
    arquivo (regra do Thiago, 14/10/2026: ferramenta distribuida nao abre
    janela). Sem o arquivo: desligada."""
    try:
        with io.open(os.path.join(PATH_SCRIPT, 'prefs.json'), 'r', encoding='utf-8') as f:
            return bool(json.load(f).get('relatorio_na_tela'))
    except Exception:
        return False


class _Relatorio(object):
    """Output mudo: guarda o texto do relatorio para o arquivo e nao abre nada."""

    def __init__(self):
        self.linhas = []

    def print_md(self, texto):
        self.linhas.append(texto)

    def linkify(self, *args, **kwargs):
        return u''

    def __getattr__(self, nome):
        return lambda *args, **kwargs: None


TELA = _tela_ligada()
output = script.get_output() if TELA else _Relatorio()

_APPDATA_DIR = os.path.join(os.getenv('APPDATA', ''), 'pyRevit', 'PYAMBAR', 'TagsOrganizadas')
_RELATORIO = os.path.join(_APPDATA_DIR, 'ultimo_relatorio.txt')
_ERROS = os.path.join(_APPDATA_DIR, 'erros.log')


def aviso(texto):
    """forms.alert no lab; balao na distribuicao."""
    if TELA:
        forms.alert(texto, title=u'Tags Organizadas')
        return
    try:
        forms.show_balloon(u'Tags Organizadas', texto)
    except Exception:
        pass


def _gravar(caminho, texto, modo='w'):
    try:
        if not os.path.isdir(_APPDATA_DIR):
            os.makedirs(_APPDATA_DIR)
        with io.open(caminho, modo, encoding='utf-8') as f:
            f.write(texto)
        return True
    except Exception:
        return False
_APPDATA_CONFIG = os.path.join(_APPDATA_DIR, 'config.json')
#: templates de atuacao gravados pelo usuario (os de fabrica estao no snippet)
_APPDATA_TEMPLATES = os.path.join(_APPDATA_DIR, 'templates.json')
#: modo automatico (bancada em larga escala, acionada de longe): arquivo-senha
#: de uso unico — o botao le, APAGA e roda sem janela (ver auto())
_APPDATA_AUTO = os.path.join(_APPDATA_DIR, 'AUTO.json')

#: Janela de deslize da ponta da chamada no linear (pes) e o passo da varredura
JANELA_PES = 5.0
PASSO_PES = 1.0


class Cancelado(Exception):
    """O usuario apertou Cancelar na barra de progresso: tudo e desfeito."""


# ============================================================================
# CONFIG
# ============================================================================

def load_config():
    if os.path.exists(_APPDATA_CONFIG):
        try:
            with io.open(_APPDATA_CONFIG, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            # v0.3 guardava 'categorias' como lista e 'tipos' a parte
            if isinstance(cfg.get('categorias'), list):
                cfg = {}
            return cfg
        except Exception:
            pass
    return {}


def save_config(data):
    if not os.path.exists(_APPDATA_DIR):
        os.makedirs(_APPDATA_DIR)
    with io.open(_APPDATA_CONFIG, 'w', encoding='utf-8') as f:
        f.write(json.dumps(data, indent=2, ensure_ascii=False))


# ============================================================================
# LEVANTAMENTO (antes da janela, para mostrar as contagens)
# ============================================================================

def levantar(view, R, U, cats=None, faixa=None):
    """Por categoria: tipos de tag, seta atual de cada tipo, e o que ha na
    vista para etiquetar (ja coletado — reaproveitado depois da janela).
    cats: so estas (depois do 'Refazer' basta levantar as marcadas).
    faixa: so a trama (Installation Plans) — (z_min, z_max) em pes."""
    feitos = coleta.ja_etiquetados(doc, view)
    info = {}
    dados = {}
    for cat in (cats or reg.CATEGORIAS):
        tipos = coleta.tipos_de_tag(doc, cat['tag_bic'])
        seta_atual = dict((n, coleta.seta_do_tipo(doc, s)) for n, s in tipos.items())
        extra = {}
        if cat['modo'] == 'ponto':
            lista, pulados = coleta.alvos_pontuais(doc, view, cat, feitos, faixa=faixa)
            dados[cat['chave']] = {'lista': lista}
            cont = u'{} sem tag na vista'.format(len(lista))
            if pulados:
                cont += u' ({} já tinham)'.format(pulados)
            n, ja = len(lista), pulados
        elif cat['modo'] == 'tubo':
            lista, pulados = coleta.alvos_tubos(doc, view, cat, feitos, R, U, faixa=faixa)
            dados[cat['chave']] = {'tubos': lista}
            cont = u'{} sem tag na vista'.format(len(lista))
            if pulados:
                cont += u' ({} já tinham)'.format(pulados)
            n, ja = len(lista), pulados
        else:
            retos, lig, cx, elem = coleta.rede_linear(doc, view, cat, R, U)
            comps, _adj = trechos(retos, lig, cx)
            livres = [c for c in comps if not any(k in feitos for k in c)]
            usados = set(k for c in livres for k in c)
            retos_livres = dict((k, v) for k, v in retos.items() if k in usados)
            dados[cat['chave']] = {'retos': retos_livres, 'ligacoes': lig, 'conexoes': cx,
                                   'elementos': elem}
            cont = u'{} trechos sem tag'.format(len(livres))
            if len(comps) > len(livres):
                cont += u' ({} já tinham)'.format(len(comps) - len(livres))
            n = len(livres)
            # 'ja' do Refazer: so trecho com RETO etiquetado e nenhuma conexao
            # etiquetada e certamente refeito; com conexao (stub) etiquetada,
            # so se a categoria dela tambem for refeita (janela soma se Stubs
            # estiver ligado). Antes contava todo trecho com qualquer tag
            # e prometia refazer o que o Refazer deixa (revisao 13/10/2026)
            com_reto = [c for c in comps if any(k in feitos and k in retos for k in c)]
            ja = sum(1 for c in com_reto if not any(k in feitos and k not in retos for k in c))
            # o resto do que nao estava livre (inclusive trecho cuja UNICA tag
            # e a do stub): refeito so se a categoria da conexao tambem for
            extra['ja_conexao'] = len(comps) - len(livres) - ja
        info[cat['chave']] = dict(extra, tipos=tipos, seta_atual=seta_atual, contagem=cont, n=n, ja=ja)
    return info, dados


# ============================================================================
# MAIN
# ============================================================================

def projeto_imperial():
    """Unidade de comprimento do projeto e pe/polegada? (1 pe interno -> 1 ou 12)"""
    try:
        uid = doc.GetUnits().GetFormatOptions(SpecTypeId.Length).GetUnitTypeId()
        f = UnitUtils.ConvertFromInternalUnits(1.0, uid)
        return abs(f - 1.0) < 1e-6 or abs(f - 12.0) < 1e-6
    except Exception as ex:
        coleta.avisar(u'unidade do projeto nao lida, usando imperial', ex)
        return True


def ler_rotulo_tubo(info, escolha):
    """Tag de tubo alinhada: le na familia o rotulo VISIVEL do tipo escolhido
    (altura da letra, posicao, alinhamento) e guarda em
    escolha['arranjo']['rotulo_tubo'] — o executar calcula dali onde fica o
    texto, para qualquer tamanho de letra. EditFamily: tem de rodar ANTES do
    TransactionGroup (26/10/2026)."""
    arr = escolha['arranjo']
    esc = escolha['categorias'].get('tubo') or {}
    if not arr.get('tubo_alinhado') or not esc.get('ativo') or not esc.get('tipo'):
        return
    sym = info.get('tubo', {}).get('tipos', {}).get(esc['tipo'])
    if sym is not None:
        arr['rotulo_tubo'] = coleta.rotulo_da_tag(doc, sym)


def _escolha_do_template(info, nome, tipos_forcados):
    """Escolha no formato da janela a partir de um template, sem janela."""
    t = tag_templates.todos(_APPDATA_TEMPLATES)[nome]
    cats = {}
    for c in reg.CATEGORIAS:
        tc = dict(t['categorias'].get(c['chave']) or {'ativo': False})
        nomes = list(info[c['chave']]['tipos'])
        tipo = tipos_forcados.get(c['chave']) or tc.get('tipo') or c.get('tipo_padrao')
        if tipo not in nomes:
            tipo = nomes[0] if nomes else None
        cats[c['chave']] = {'ativo': bool(tc.get('ativo')) and tipo is not None, 'tipo': tipo,
                            'seta': tc.get('seta', MANTER), 'unir': tc.get('unir', True),
                            'x_pes': tc.get('x_pes')}
    arr = dict(tag_templates.FABRICA[u'Slab Passes']['arranjo'])
    arr.update(t.get('arranjo', {}))
    arr['refazer'] = True
    return {'categorias': cats, 'arranjo': arr}


def auto():
    """Bancada em larga escala (09/10/2026): roda o botao, SEM janela, nas
    vistas do AUTO.json e grava um relatorio por vista. O arquivo e apagado
    antes de rodar (uso unico). Formato: {"vistas": [id, ...], "template":
    "Cortes Water Supply", "tipos": {chave: "Familia : Tipo"}, "relatorio":
    "caminho.json"}"""
    try:
        pedido = ler_pedido_auto(_APPDATA_AUTO)
    except Exception as ex:
        # apagado mesmo quebrado: o proximo clique abre a janela normal
        aviso(u'Modo automático ignorado: {}'.format(ex))
        return
    saida = pedido.get('relatorio') or os.path.join(_APPDATA_DIR, 'auto_relatorio.json')
    resultados = []
    for vid in pedido['vistas']:
        r = {'vista': vid, 'versao': versao_rodando()}
        t0 = time.time()
        parar = False
        try:
            view = doc.GetElement(ElementId(Int64(vid)))
            r['nome'] = view.Name
            R, U = view.RightDirection, view.UpDirection
            del coleta.AVISOS[:]
            info, dados = levantar(view, R, U)
            setas = coleta.listar_setas(doc)
            escolha = _escolha_do_template(info, pedido.get('template', u'Cortes Water Supply'),
                                           pedido.get('tipos') or {})
            # variante de teste: sobrepoe chaves do arranjo do template
            escolha['arranjo'].update(pedido.get('arranjo') or {})
            alinhamentos = {}
            if escolha['arranjo'].get('estilo_arranjo') == 'margem':
                for c in reg.CATEGORIAS:
                    esc = escolha['categorias'][c['chave']]
                    if esc['ativo']:
                        alinhamentos[c['chave']] = coleta.alinhamento_do_texto(
                            doc, info[c['chave']]['tipos'][esc['tipo']])
            ler_rotulo_tubo(info, escolha)
            grupo = TransactionGroup(doc, u'Tags Organizadas (auto)')
            grupo.Start()
            try:
                despejo = None
                if pedido.get('so_coleta'):
                    despejo = os.path.join(pedido['despejo_dir'], 'cena_{}.json'.format(vid))
                r.update(executar(view, R, U, info, dados, setas, escolha, alinhamentos, auto=True,
                                  despejo=despejo) or {})
            except Exception:
                if grupo.HasStarted() and not grupo.HasEnded():
                    grupo.RollBack()
                raise
            if grupo.HasStarted() and not grupo.HasEnded():
                # so coleta: a vista volta como estava (o 'refazer' apagou tags)
                if pedido.get('so_coleta'):
                    grupo.RollBack()
                else:
                    grupo.Assimilate()
            r['avisos'] = list(coleta.AVISOS[:20])
        except Cancelado:
            # Cancelar na barra para o LOTE (antes so a vista; eram 20
            # cliques para parar 20 cortes). O grupo da vista ja foi desfeito
            r['erro'] = u'cancelado pelo usuário (lote interrompido)'
            parar = True
        except Exception as ex:
            r['erro'] = u'{}'.format(ex) or type(ex).__name__
            r['traceback'] = traceback.format_exc()
        r['segundos'] = round(time.time() - t0, 1)
        resultados.append(r)
        # grava a cada vista: se o Revit travar no meio, o que rodou fica
        with io.open(saida, 'w', encoding='utf-8') as f:
            f.write(json.dumps(resultados, indent=1, ensure_ascii=False))
        if parar:
            break
    output.print_md(u'## Tags Organizadas v{} (auto) — {} vistas, relatório em {}'.format(
        versao_rodando(), len(resultados), saida))


def main():
    if os.path.exists(_APPDATA_AUTO):
        return auto()
    view = doc.ActiveView
    if not isinstance(view, (ViewPlan, ViewSection, ViewDrafting)) or view.IsTemplate:
        aviso(u'Abra uma planta, corte ou elevação.')
        return
    R, U = view.RightDirection, view.UpDirection
    # o pyRevit mantem os modulos em cache entre cliques (memoria api-pyrevit-motor)
    del coleta.AVISOS[:]

    info, dados = levantar(view, R, U)
    setas = coleta.listar_setas(doc)
    cfg = load_config()
    nome_vista = u'{}  ·  escala 1:{}'.format(view.Name, view.Scale)
    em_planta = isinstance(view, ViewPlan)
    jan = Janela(reg.CATEGORIAS, info, [n for n, _i in setas], cfg, nome_vista,
                 imperial=projeto_imperial(),
                 arranjo_padrao='perto' if em_planta else 'margem',
                 templates=tag_templates.todos(_APPDATA_TEMPLATES),
                 caminho_templates=_APPDATA_TEMPLATES,
                 # primeiro uso (sem config): o template do tipo de vista, nao
                 # as categorias de slab passes num corte de water supply
                 template_inicial=None if cfg else tag_templates.padrao_para('planta' if em_planta else 'corte'))
    jan.ShowDialog()
    escolha = jan.resultado
    if not escolha:
        return
    save_config(escolha)

    # estilo margem: alinhamento do texto de cada tipo de tag (uma caixa por
    # linha — a vizinha encaixa no vazio da 2a linha curta). Abre a familia so
    # para ler, e o EditFamily nao roda com o grupo aberto: vem ANTES dele
    alinhamentos = {}
    if escolha['arranjo'].get('estilo_arranjo') == 'margem':
        for c in reg.CATEGORIAS:
            esc = escolha['categorias'][c['chave']]
            if esc['ativo']:
                alinhamentos[c['chave']] = coleta.alinhamento_do_texto(
                    doc, info[c['chave']]['tipos'][esc['tipo']])
    ler_rotulo_tubo(info, escolha)

    # tudo num grupo: refazer + setas + criacao = um Ctrl+Z so
    # erro no meio DESFAZ tudo: com 'Refazer' a vista ficaria sem as tags
    # antigas e sem as novas (auditoria 08/10/2026)
    grupo = TransactionGroup(doc, u'Tags Organizadas')
    grupo.Start()
    try:
        executar(view, R, U, info, dados, setas, escolha, alinhamentos)
    except Cancelado:
        if grupo.HasStarted() and not grupo.HasEnded():
            grupo.RollBack()
        aviso(u'Cancelado — a vista ficou como estava.')
        return
    except Exception:
        if grupo.HasStarted() and not grupo.HasEnded():
            grupo.RollBack()
        raise
    if grupo.HasStarted() and not grupo.HasEnded():
        grupo.Assimilate()


def versao_rodando():
    """'0.25', ou a versao com o aviso de modulo velho. Com o descarte de
    modulos no topo deste arquivo nao deveria acontecer; fica como alarme
    (ex.: alguem tira o descarte, ou um modulo novo entra sem estar em
    _PROPRIOS)."""
    motor = getattr(_motor, 'VERSAO_MOTOR', None)
    coleta_nova = hasattr(coleta, 'chaves_recriaveis')
    if motor == __version__ and coleta_nova:
        return __version__
    return u'{} (MOTOR {}, coleta {} — recarregue o pyRevit)'.format(
        __version__, motor or u'0.24 ou anterior', u'nova' if coleta_nova else u'ANTIGA')


def _links_de_revisao(cena, rotulos, postos, ids_tags, sem_lugar):
    revisar = []
    for i, g in postos.items():
        _c, conta = cena.custo(i, g, rotulos[i], detalhe=True)
        if (conta['tag'] or conta['cruza'] or conta['cruza_tubo'] or conta['chamada_tag']) and i in ids_tags:
            revisar.append(ids_tags[i])
    if revisar:
        ids, rotulo = limitar_selecao(revisar)
        output.print_md(u'**Revisar {} tag(s) com conflito:** {}'.format(
            len(revisar), output.linkify(List[ElementId](ids), rotulo)))
    sem_tag = [ElementId(Int64(int(it['id'].split(':')[1]))) for it in sem_lugar
               if it['id'].split(':')[0] == '0']
    if sem_tag:
        ids, rotulo = limitar_selecao(sem_tag)
        output.print_md(u'**{} elemento(s) sem lugar para a tag:** {}'.format(
            len(sem_tag), output.linkify(List[ElementId](ids), rotulo)))
    return revisar, sem_tag


def _fechar_sem_tela(view, criadas, por_cat, revisar, sem_tag):
    """Distribuicao: balao com o placar, o que pede olho humano SELECIONADO
    (acha sem janela) e o relatorio inteiro em arquivo."""
    partes = u', '.join(u'{} {}'.format(n, reg.por_chave(k)['rotulo'].lower()) for k, n in sorted(por_cat.items()))
    texto = u'{} tags criadas ({}).'.format(criadas, partes)
    selecao = list(revisar) + list(sem_tag)
    if selecao:
        try:
            uidoc.Selection.SetElementIds(List[ElementId](selecao))
            texto += u' Selecionados para revisar: {} com conflito, {} sem lugar.'.format(len(revisar), len(sem_tag))
        except Exception:
            texto += u' {} para revisar.'.format(len(selecao))
    if _gravar(_RELATORIO, u'Tags Organizadas v{} — {}\n\n{}\n'.format(
            versao_rodando(), view.Name, u'\n'.join(output.linhas))):
        texto += u' Relatório em TagsOrganizadas\\ultimo_relatorio.txt.'
    aviso(texto)


def _caixa_dos_itens(itens):
    xs = [i['ax'] for i in itens] or [0.0]
    ys = [i['ay'] for i in itens] or [0.0]
    return (min(xs), min(ys), max(xs), max(ys))


def executar(view, R, U, info, dados, setas, escolha, alinhamentos=None, auto=False, despejo=None):
    alinhamentos = alinhamentos or {}
    t0 = time.time()
    ativas = [c for c in reg.CATEGORIAS if escolha['categorias'][c['chave']]['ativo']]
    simbolos = dict((c['chave'], info[c['chave']]['tipos'][escolha['categorias'][c['chave']]['tipo']])
                    for c in ativas)
    setas_id = dict(setas)
    apagadas = 0
    # Installation Plans: so a TRAMA recebe tag — o que desce nas paredes
    # (tubo vertical, te da descida, CPVC, peca, caixa) e dos cortes (Thiago,
    # 14/10/2026). A mesma faixa vale para o Refazer: tag de elemento da
    # parede nunca e apagada
    faixa = None
    if escolha['arranjo'].get('so_trama'):
        faixa = coleta.faixa_da_trama(doc, view, escolha['arranjo'].get('trama_tol_mm', 300.0))
    if escolha['arranjo'].get('refazer'):
        # apaga SO o que o botao recria (auditoria 12/10/2026: apagava por
        # categoria e a tag manual de Elbow/Cap em planta sumia de vez)
        recriaveis = coleta.chaves_recriaveis(doc, view, ativas, R, U, faixa=faixa)
        with revit.Transaction(u'Tags Organizadas - apagar para refazer'):
            apagadas = coleta.apagar_tags(doc, view, recriaveis)
        _info, dados = levantar(view, R, U, ativas, faixa=faixa)
    elif faixa is not None:
        _info, dados = levantar(view, R, U, ativas, faixa=faixa)

    # ponta de seta no proprio tipo + ativar os tipos
    with revit.Transaction(u'Tags Organizadas - tipos e setas'):
        for c in ativas:
            sym = simbolos[c['chave']]
            if not sym.IsActive:
                sym.Activate()
            seta = escolha['categorias'][c['chave']]['seta']
            if seta == NENHUMA:
                coleta.gravar_seta(sym, None)
            elif seta != MANTER and seta in setas_id:
                coleta.gravar_seta(sym, setas_id[seta])

    # o que medir
    margem = escolha['arranjo'].get('estilo_arranjo') == 'margem'
    a_medir = []
    elementos = {}
    pontos = {}
    livres = {}
    lados = {}             # estilo margem: agua quente a esquerda, fria a direita
    tubos = []
    for c in ativas:
        d = dados[c['chave']]
        if c['modo'] == 'ponto':
            for chave_cat, link, e, p, r, k in d['lista']:
                a_medir.append((chave_cat, link, e, p, k))
                elementos[k] = (link, e)
                pontos[k] = (chave_cat, p, r)
                if c.get('lado_livre'):
                    livres[k] = coleta.direcao_livre(link, e, p, R, U)
                if margem:
                    lados[k] = coleta.lado_do_sistema(e)
        elif c['modo'] == 'tubo':
            for chave_cat, link, e, p, k, alts in d['tubos']:
                a_medir.append((chave_cat, link, e, p, k))
                elementos[k] = (link, e)
                tubos.append((chave_cat, k, alts))
                if margem:
                    lados[k] = coleta.lado_do_sistema(e)
        else:
            for k in d['retos']:
                link, e, meio = d['elementos'][k]
                a_medir.append((c['chave'], link, e, meio, k))
                elementos[k] = (link, e)
    if not a_medir:
        if auto:
            return {'nada': True, 'apagadas': apagadas}
        aviso(u'Nada a etiquetar nesta vista.')
        return

    medidas, fixas, linhas_ext = coleta.medir(doc, view, a_medir, simbolos, R, U)
    limites = coleta.limites_da_vista(view, R, U)
    # chamada de tag existente ganha meia-largura minima: linha SEM largura e
    # fundo (DWG), que o motor cobra barato desde a calibracao de 08/10/2026
    l_mep = coleta.linhas_mep(doc, view, R, U)
    linhas = (l_mep + coleta.linhas_dwg(doc, view, R, U, limites)
              + [tuple(s) + (0.002,) for s in linhas_ext])
    l_vinculo = []
    if margem:
        # montantes e travessas do vinculo (corte de parede): a chamada nao
        # pode correr em cima deles
        l_vinculo = coleta.linhas_vinculo(doc, view, R, U, limites)
        linhas += l_vinculo
    if escolha['arranjo'].get('evitar_parede'):
        linhas += coleta.linhas_paredes(doc, view, R, U)

    itens = []
    corpos = {}
    for k, (chave_cat, p, r) in pontos.items():
        m = medidas.get(k)
        if m is None:           # nao mediu (motivo nos avisos)
            continue
        au, av = coleta.uv(p, R, U)
        # a seta cai SOBRE a peca: o LocationPoint do tampao e o conector, na
        # borda — puxar para o miolo (DEM 57, 12/10/2026)
        corpo = None
        try:
            corpo = coleta.corpo_na_vista(elementos[k][0], elementos[k][1], R, U)
        except Exception as ex:
            coleta.avisar(u'{}: caixa da peca'.format(k), ex)
        meio = None
        if corpo is not None:
            corpos[k] = corpo
            # Installation Plans: 0,35 (seta do Pex Tee a ~0,6 mm do centro, como
            # o ajuste manual); cortes: 0,25 (tampao — DEM 57)
            meio = coleta.miolo(corpo, escolha['arranjo'].get('miolo_frac', 0.25))
            au, av = coleta.para_dentro((au, av), meio)
        itens.append(dict(m, id=k, grupo=chave_cat, ax=au, ay=av, r=r, livre=livres.get(k), miolo=meio,
                          lado_pref=lados.get(k),
                          lado_fraco=bool((reg.por_chave(chave_cat) or {}).get('lado_fraco')),
                          silhueta=silhueta(m['texto'], alinhamentos.get(chave_cat))))
    for chave_cat, k, alts in tubos:
        m = medidas.get(k)
        if m is None:
            continue
        itens.append(dict(m, id=k, grupo=chave_cat, ax=alts[0]['ax'], ay=alts[0]['ay'], r=0.0,
                          alternativas=alts, lado_pref=lados.get(k),
                          lado_fraco=bool((reg.por_chave(chave_cat) or {}).get('lado_fraco')),
                          alinhar=bool(escolha['arranjo'].get('tubo_alinhado')),
                          silhueta=silhueta(m['texto'], alinhamentos.get(chave_cat))))
    # lineares: depois da medicao, porque o pente precisa do TEXTO de cada
    # conduite (so junta 100% igual — 3/4" e 1" juntos viram '<varia>')
    n_pentes = 0
    for c in ativas:
        if c['modo'] != 'linear':
            continue
        d = dados[c['chave']]
        esc = escolha['categorias'][c['chave']]
        x_pes = esc['x_pes'] or c.get('x_pes', 25.0)
        quantos = evitar = None
        estacoes = []
        if esc['unir']:
            textos = dict((k, medidas[k]['texto']) for k in d['retos'] if k in medidas)
            pts, quantos, evitar = pentes(d['retos'], d['ligacoes'], d['conexoes'], textos, x_pes,
                                          max_pente=int(escolha['arranjo'].get('max_pente', 8)),
                                          passo=PASSO_PES, janela=JANELA_PES)
            estacoes.extend(pts)
            n_pentes += len(pts)
        estacoes.extend(itens_lineares(d['retos'], d['ligacoes'], d['conexoes'], x_pes,
                                       JANELA_PES, PASSO_PES, quantos=quantos, evitar=evitar))
        for it in estacoes:
            m = medidas.get(it['id'])
            if m is None:
                continue
            itens.append(dict(m, id=it['id'], grupo=c['chave'], ax=it['ax'], ay=it['ay'], r=0.0,
                              alternativas=it['alternativas'],
                              silhueta=silhueta(m['texto'], alinhamentos.get(c['chave']))))
    t_coleta = time.time() - t0

    arr = escolha['arranjo']
    if margem:
        # estilo MARGEM (installation plans): texto fora do desenho, em coluna
        # de cada lado, chamada so a 90 graus ou reta. O desenho e o recorte da
        # vista recortado na largura do desenho real (frame + tubos + ancoras:
        # o recorte sobrava 28 mm de um lado no DEM 105); sem recorte, a caixa
        # dos elementos etiquetados.
        if limites:
            regiao = regiao_do_desenho(limites, l_mep + l_vinculo, [(i['ax'], i['ay']) for i in itens])
        else:
            regiao = _caixa_dos_itens(itens)
        # pesos e calibracao do estilo: Snippets._tag_arranjo.cfg_margem (a
        # bancada fora do Revit usa a mesma funcao)
        ecfg = cfg_margem(view.Scale, regiao, folga_mm=arr['folga_mm'], raio_uniao_mm=arr['raio_mm'])
        if arr.get('modo') == 'rapido':
            # uma ordem de colocacao so (o completo tenta 6 e fica a melhor)
            ecfg['reinicios'] = 0
        limites = None          # o texto vai FORA do recorte, de proposito
    else:
        ecfg = cfg_da_escala(view.Scale, alcance_mm=arr['alcance_mm'], folga_mm=arr['folga_mm'],
                             raio_uniao_mm=arr['raio_mm'], angulos=arr['angulos'])
        if arr.get('tubo_alinhado'):
            # Installation Plans em planta (PH3, 23/10/2026): tag de tubo sem
            # chamada, no sentido do tubo; chamada a 45 so onde nao cabe
            ecfg['alinhar_tubos'] = True
            ecfg['alinhada_gap'] = arr.get('alinhada_gap_mm', 1.0) * view.Scale / 304.8
            # altura da letra da tag de tubo (o tipo "1,5 mm"): a caixa do texto
            # real e bem menor que a do rotulo da familia
            mm = view.Scale / 304.8
            # texto da tag: CALCULADO pelo rotulo visivel do tipo escolhido
            # (altura da letra, posicao e alinhamento lidos na familia antes do
            # grupo — rotulo_tubo). Sem rotulo lido ou caso nao medido: os
            # valores fixos do template (Thiago, 26/10/2026: "a aplicacao deve
            # calcular, nao o usuario")
            texto = centro_do_texto(arr.get('rotulo_tubo'))
            if texto:
                ecfg['alinhada_texto'] = texto['altura'] * mm
                ecfg['alinhada_centro'] = texto['centro_h'] * mm
                ecfg['alinhada_centro_v'] = texto['centro_v'] * mm
                ecfg['alinhada_dist'] = texto['dist'] * mm
            else:
                ecfg['alinhada_texto'] = arr.get('altura_texto_tubo_mm', 1.5) * mm
                if arr.get('alinhada_centro_mm') is not None:
                    ecfg['alinhada_centro'] = arr['alinhada_centro_mm'] * mm
                    ecfg['alinhada_centro_v'] = arr.get('alinhada_centro_v_mm', arr['alinhada_centro_mm']) * mm
                if arr.get('alinhada_dist_mm'):
                    ecfg['alinhada_dist'] = arr['alinhada_dist_mm'] * mm
            # distancia por lado (ajuste MANUAL do menu, opcional): lado +1 = acima no
            # horizontal e a direita no vertical
            lados = {}
            for chave, (ori, lado) in (('acima', ('H', 1)), ('abaixo', ('H', -1)),
                                       ('direita', ('V', 1)), ('esquerda', ('V', -1))):
                v = arr.get('alinhada_dist_{}_mm'.format(chave))
                if v is not None:
                    lados[(ori, lado)] = v * mm
            if lados:
                ecfg['alinhada_dist_lados'] = lados
            ecfg['par_max'] = arr.get('par_max_mm', 3.0) * mm
            ecfg['par_sobre'] = arr.get('par_sobre_mm', 4.0) * mm
            ecfg['fila_max'] = arr.get('fila_max_mm', 0.0) * mm
            ecfg['respiro_alinhada'] = arr.get('respiro_mm', 0.0) * mm
            ecfg['pesos']['chamada_tubo'] = arr.get('peso_chamada_tubo', 40.0)
        if arr.get('polir'):
            ecfg['polir'] = True
        if arr.get('folga_linha_mm'):
            ecfg['folga_linha'] = arr['folga_linha_mm'] * view.Scale / 304.8
        # pesos proprios do template (Installation Plans: 90 graus primeiro,
        # 45 so no caso especial — Thiago, 23/10/2026)
        ecfg['pesos'].update(arr.get('pesos') or {})
        # seta da conexao na borda da peca, fora do eixo (ponta_lateral no
        # motor; o miolo de cada peca limita o deslocamento)
        if arr.get('ponta_lateral_mm'):
            ecfg['ponta_lateral'] = arr['ponta_lateral_mm'] * view.Scale / 304.8
        # varias ordens de colocacao (a vizinha sobe para a outra caber)
        if arr.get('reinicios'):
            ecfg['reinicios'] = int(arr['reinicios'])
        # tag unida paga o comprimento longo pela chamada mais longa
        if arr.get('comp_por_chamada'):
            ecfg['comp_por_chamada'] = True
        # 90 graus; outros angulos so para a tag que ficou cruzando algo, com
        # as vizinhas podendo mudar junto (fase abrir espaco)
        if arr.get('abrir_espaco'):
            ecfg['abrir_espaco'] = int(arr['abrir_espaco'])
            ecfg['angulos_libera'] = tuple(arr.get('angulos_libera') or (90, 60, 45))
    simb =[(i['ax'], i['ay'], i['r'], i['id']) for i in itens if i['r'] > 0]
    # pontual: coluna "Unir" de cada categoria; linear e tubo nunca unem por
    # texto (o feixe ja resolveu; tubo traz o comprimento no texto)
    sem_uniao = tuple(c['chave'] for c in reg.CATEGORIAS
                      if c['modo'] in ('linear', 'tubo') or not escolha['categorias'][c['chave']]['unir'])
    if despejo:
        # bancada fora do Revit (09/10/2026): grava a cena e nao roda o motor —
        # no F10 o motor levou ate 639 s por corte no Revit e o derrubou duas
        # vezes; em CPython a mesma cena roda em segundos
        cena_json = {'vista': view.Name, 'escala': view.Scale, 'itens': itens, 'linhas': linhas,
                     'simbolos': simb, 'fixas': fixas, 'limites': limites, 'cfg': ecfg,
                     'sem_uniao': sem_uniao, 'max_uniao': int(arr.get('max_uniao', 12)),
                     'estilo_uniao': arr.get('estilo_uniao', 'ramos')}
        with io.open(despejo, 'w', encoding='utf-8') as f:
            f.write(json.dumps(cena_json, ensure_ascii=False))
        return {'despejo': despejo, 'itens': len(itens), 'linhas': len(linhas), 'fixas': len(fixas),
                'coleta_s': round(t_coleta, 1)}
    # grupo espalhado alem do alcance nao cabe numa tag: e cortado no maior vao
    rotulos = unir_iguais(itens, ecfg['raio_uniao'], max_chamadas=int(arr.get('max_uniao', 12)),
                          sem_uniao=sem_uniao, estilo=arr.get('estilo_uniao', 'ramos'),
                          espalho_max=ecfg['alcance'])
    cena = Cena(ecfg, linhas=linhas, simbolos=simb, caixas_fixas=fixas, limites=limites)
    t1 = time.time()
    # porcentagem: o motor conta em unidades internas (fases x tags) e
    # '163 de 320' com 40 tags parecia contagem errada (revisao 13/10/2026)
    with forms.ProgressBar(title=u'Organizando {} tags... {{value}}%'.format(len(rotulos)),
                           cancellable=True) as pb:
        ultimo = [0.0]

        def progresso(n, total):
            # a barra do pyRevit faz 2 Dispatcher.Invoke por atualizacao: no
            # maximo 4 por segundo (o motor chama a cada tag em todas as
            # fases). O Cancelar e conferido sempre — ler o atributo e barato
            agora = time.time()
            if n >= total or agora - ultimo[0] >= 0.25:
                ultimo[0] = agora
                pb.update_progress(int(100.0 * n / max(1, total)), 100)
            if pb.cancelled:
                raise Cancelado()
        postos = arranjar(rotulos, cena, progresso=progresso)
    t_motor = time.time() - t1
    audit = auditar(rotulos, cena)

    # profundidade do plano da vista: em planta e (0, 0, z); em corte/elevacao
    # U e a vertical e o antigo '+ (0, 0, z)' somava a altura duas vezes
    p0 = a_medir[0][3]
    base = p0.Subtract(R.Multiply(p0.DotProduct(R))).Subtract(U.Multiply(p0.DotProduct(U)))
    with revit.Transaction(u'Tags Organizadas'):
        criadas, falhas, ids_tags = coleta.aplicar(doc, view, rotulos, postos, elementos, simbolos, R, U,
                                                   base, corpos=corpos)
    # elemento que ficou sem tag (o motor nao achou lugar nem separando)
    cobertos = set(k for i in postos for k in rotulos[i]['ids'])
    sem_lugar = [it for it in itens if it['id'] not in cobertos]

    por_cat = {}
    for i in postos:
        por_cat[rotulos[i]['grupo']] = por_cat.get(rotulos[i]['grupo'], 0) + 1
    if auto:
        return {'apagadas': apagadas, 'criadas': criadas, 'por_categoria': por_cat, 'auditoria': audit,
                'itens': len(itens), 'rotulos': len(rotulos),
                'sem_lugar': [u'{} ({})'.format(it['texto'].replace('\n', ' / '), it['id']) for it in sem_lugar],
                'falhas': [u'{}'.format(f) for f in falhas], 'coleta_s': round(t_coleta, 1),
                'motor_s': round(t_motor, 1)}
    # versao no cabecalho: no teste A/B (trocar de branch + Reload) e o que
    # prova qual codigo rodou de fato
    output.print_md(u'## Tags Organizadas v{} — {}'.format(versao_rodando(), view.Name))
    output.print_md(u'| | |\n|---|---|\n'
                    u'| Tags apagadas para refazer | {} |\n'
                    u'| Tags criadas | {} ({}) |\n'
                    u'| Tags unidas (texto igual) / pentes de conduíte | {} / {} |\n'
                    u'| Tag sobre tag | {} |\n'
                    u'| Tag sobre elemento | {} |\n'
                    u'| Chamadas cruzando ou encostando | {} |\n'
                    u'| Tags tocando o desenho | {} |\n'
                    u'| Elementos sem lugar para a tag | {} |\n'
                    u'| Tempo | coleta {:.1f} s, motor {:.1f} s |'.format(
                        apagadas, criadas, u', '.join(u'{} {}'.format(n, reg.por_chave(k)['rotulo'].lower())
                                            for k, n in sorted(por_cat.items())),
                        sum(1 for i in postos if len(rotulos[i]['ids']) > 1), n_pentes,
                        audit['tag'], audit['simbolo'], audit['cruza'], audit['linha'],
                        len(sem_lugar), t_coleta, t_motor))
    # um clique seleciona o que pede olho humano (as tags com conflito e os
    # elementos sem tag) — antes o relatorio so tinha numeros. Roda DENTRO do
    # TransactionGroup: um erro aqui desfaria todas as tags criadas, entao
    # vira aviso (revisao adversarial, 13/10/2026)
    revisar, sem_tag = [], []
    try:
        revisar, sem_tag = _links_de_revisao(cena, rotulos, postos, ids_tags, sem_lugar)
    except Exception as ex:
        output.print_md(u'- aviso: links de revisão não montados ({})'.format(ex))
    for it in sem_lugar[:10]:
        output.print_md(u'- sem lugar: {} ({})'.format(it['texto'].replace('\n', ' / '), it['id']))
    for f in falhas[:10]:
        output.print_md(u'- falhou: {}'.format(f))
    if coleta.AVISOS:
        output.print_md(u'**{} aviso(s) na coleta** (itens pulados, motivo abaixo):'.format(len(coleta.AVISOS)))
        for a in coleta.AVISOS[:10]:
            output.print_md(u'- {}'.format(a))
    if not TELA:
        _fechar_sem_tela(view, criadas, por_cat, revisar, sem_tag)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        if TELA:
            output.print_md("**Erro:** {}".format(str(e)))
            output.print_md("```\n{}\n```".format(traceback.format_exc()))
        else:
            # distribuicao: balao curto; o detalhe vai para o arquivo
            gravou = _gravar(_ERROS, u'{} {}\n{}\n'.format(time.strftime('%Y-%m-%d %H:%M:%S'), e,
                                                          traceback.format_exc()), 'a')
            aviso(u'Não deu certo: {}{}'.format(e, u' — detalhe em TagsOrganizadas\\erros.log' if gravou else u''))
