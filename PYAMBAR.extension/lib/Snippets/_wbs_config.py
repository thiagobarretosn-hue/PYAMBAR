# -*- coding: utf-8 -*-
"""
_wbs_config.py
Config unica do pulldown WBS (WBSCompleto, WBSFloor, WBSTipologia).

Antes cada pushbutton tinha o seu %APPDATA%\\pyRevit\\PYAMBAR\\<Tool>\\config.json
com um schema proprio ("floors" / "levels" / "mapping"). As copias divergiram na
pratica (WBS 415 e 515 tinham tipologia diferente entre WBSCompleto e
WBSTipologia). Aqui existe uma fonte so:

    %APPDATA%\\pyRevit\\PYAMBAR\\WBS\\config.json

    {
      "version": 3,
      "levels":   [{"name": "1st Ground FL", "wbs": "1st"}, ...],
      "projetos": {"Torre A": {"tipologia": {"915": "A1 - L", ...}}},
      "prefs":    {"sufixo": 1, "offset_ft": 0.0, ...}
    }

Na primeira execucao os configs antigos sao lidos, fundidos por prioridade e
gravados no novo caminho — nada e apagado, o legado fica onde esta.

A tabela de tipologia e POR MODELO (chave = doc.Title sem extensao): a mesma
numeracao (504, 915) significa apartamentos diferentes em predios diferentes,
entao um projeto novo comeca com a tabela vazia em vez de herdar a do anterior.
Os niveis continuam globais, casados por nome — ver mesclar_levels(). A tabela
unica dos schemas antigos vira o acervo CHAVE_LEGADO, de onde a UI copia.

Sem clr / sem Autodesk: testavel em CPython.

AUTHOR: Thiago Barreto Sobral Nunes
VERSION: 1.0 (03/09/2026)
NOTES:
    - Escrita SEMPRE via codecs.open(utf-8) + ensure_ascii=False. open() nativo
      do IronPython nao aceita encoding= e grava cp1252 (nome de Level acentuado
      viraria lixo) — ver memoria ironpython-file-encoding.
"""

import codecs
import json
import os

from Snippets._regras_param import normalizar_regras as _normalizar_regras_param
from Snippets._ambiente_match import (
    normalizar_direcao as _normalizar_direcao,
    normalizar_offsets as _normalizar_offsets,
)

# v4 (14/09/2026): cada projeto ganha 'regras_param' — as regras de parametros
# (orientacao, grupo, categoria...) do Unit Mapper. Por MODELO, decisao do
# Thiago, com exportar/importar para levar de um modelo a outro.
SCHEMA_VERSION = 4

PASTA_APPDATA = os.path.join('pyRevit', 'PYAMBAR', 'WBS')
NOME_ARQUIVO = 'config.json'

# Acervo onde cai a tabela unica dos schemas antigos. Nao pertence a modelo
# nenhum: existe para o usuario copiar dela quando reconhecer o projeto.
CHAVE_LEGADO = '(importado)'

PARAM_DETAIL_PADRAO = 'WBS Detail'
PARAM_WBS_PADRAO = 'WBS'
PARAM_TIPOLOGIA_PADRAO = 'Tipologia UH'

#: identificacao do ELEMENTO (IFC) e descricao da peca nao sao atributo da
#: unidade — nomes em ingles e no Revit em portugues
NAO_MIGRAR_PADRAO = (
    'IfcGUID', 'Exportar para IFC', 'Exportar para IFC como', 'Export to IFC',
    'Export to IFC As', 'IFC Predefined Type', 'Tipo predefinido de IFC',
    'Item Description',
)


def prefs_padrao():
    return {
        'sufixo': 1,
        'offset_ft': 0.0,           # 15/09/2026: padrao 0 (era -0.3), pedido do Thiago
        'incrementar': False,
        'reiniciar_por_pavimento': False,
        'param_detail': PARAM_DETAIL_PADRAO,
        'param_wbs': PARAM_WBS_PADRAO,
        'param_tipologia': PARAM_TIPOLOGIA_PADRAO,
        'target_param_floor': 'Floor',
        # aba "Parametros fixos" — CSV no formato da Paleta de Parametros
        'fixos_csv': '',
        'fixos_valores': {},        # {nome_do_parametro: valor escolhido}
        'fixos_ativos': [],         # nomes com o toggle ligado
        'fixos_em_grupo': True,     # fixos descem para membros de Model Group
        # v4 (14/09/2026) — escopo e regras de parametros
        'escopo': 'selecao',        # selecao | vista | projeto
        'calcular': True,           # calcular Floor / Unit ID / Type
        'so_mudancas': False,       # preview so com o que muda por regra
        'mostrar_bloqueados': False,  # v3.3: linha sem nada gravavel some
        'categorias_excluidas': [],  # nomes de categoria fora do escopo
        # aba Ambientes
        'unit_fonte': 'sufixo',     # sufixo | ambiente (aba Elementos)
        'amb_usar': False,          # casar elementos com rooms
        'amb_unit': True,           # Unit ID pelo ambiente, no lugar do sufixo
        'amb_param_unit': 'Unit ID',
        'amb_links': True,          # incluir rooms dos vinculos
        'amb_vista': False,         # so rooms visiveis na vista ativa
        'amb_offset_ft': 0.0,       # medido: offset piora o acerto no MIIQLUX
        'amb_direcao': 'base',      # base | topo | ambos (16/09/2026)
        'amb_auto': True,           # fora de room: projecao/grupo/rede/proximo
        # 16/09/2026: parametros que NAO sobem dos membros para a instancia do
        # grupo (1o uso: IfcGUID e a descricao do tubo iam parar no grupo)
        'grupo_nao_migrar': list(NAO_MIGRAR_PADRAO),
        'amb_auto_limite_ft': 3.0,  # medido: proximidade 86% a 3 ft
        'amb_copiar': [],           # parametros do room copiados (fonte A)
    }


def config_padrao():
    return {
        'version': SCHEMA_VERSION,
        'levels': [],
        'projetos': {},
        'prefs': prefs_padrao(),
    }


# ── caminhos ──────────────────────────────────────────────────────────────────

def pasta_config(base_dir=None):
    """Pasta da config unificada. base_dir sobrescreve o APPDATA (testes)."""
    if base_dir:
        return base_dir
    return os.path.join(os.getenv('APPDATA', ''), PASTA_APPDATA)


def caminho_config(base_dir=None):
    return os.path.join(pasta_config(base_dir), NOME_ARQUIVO)


# Pushbuttons do pulldown que tinham config propria, em ORDEM DE PRIORIDADE na
# migracao — a primeira fonte com a chave vence. WBSTipologia na frente por
# decisao do usuario: nos WBS 415/515 as duas copias divergiam e a dela e a boa.
LEGADO_APPDATA = ['WBSTipologia', 'WBSCompleto', 'WBSFloor', 'wbsBox']
LEGADO_SEEDS = ['WBSTipologia.pushbutton', 'WBSCompleto.pushbutton',
                'WBSFloor.pushbutton', 'wbsBox.pushbutton']


def fontes_legado(path_pulldown, appdata_base=None, seed_proprio=None):
    """Caminhos dos configs antigos, ja ordenados por prioridade.

    Intercala APPDATA e semente por ferramenta: o que o usuario editou na
    maquina vence a semente versionada da MESMA ferramenta, mas nao a
    ferramenta de maior prioridade.

    seed_proprio: config.json da PROPRIA ferramenta, pelo caminho. Entra por
    ultimo (menor prioridade). Existe porque na distribuicao o .pushbutton
    e renomeado (Unit Mapper) e o nome fixo de LEGADO_SEEDS nao o acharia.
    """
    raiz = appdata_base or os.path.join(os.getenv('APPDATA', ''), 'pyRevit', 'PYAMBAR')
    caminhos = []
    for ferramenta, pushbutton in zip(LEGADO_APPDATA, LEGADO_SEEDS):
        caminhos.append(os.path.join(raiz, ferramenta, NOME_ARQUIVO))
        if path_pulldown:
            caminhos.append(os.path.join(path_pulldown, pushbutton, NOME_ARQUIVO))

    if seed_proprio:
        alvo = os.path.normcase(os.path.abspath(seed_proprio))
        ja = [os.path.normcase(os.path.abspath(c)) for c in caminhos]
        if alvo not in ja:
            caminhos.append(seed_proprio)
    return caminhos


# ── io ────────────────────────────────────────────────────────────────────────

def ler_json(caminho):
    """Le JSON em utf-8 (tolera BOM). Arquivo ausente ou invalido -> None."""
    if not caminho or not os.path.exists(caminho):
        return None
    for encoding in ('utf-8-sig', 'utf-8', 'latin-1'):
        try:
            with codecs.open(caminho, 'r', encoding=encoding) as f:
                return json.load(f)
        except (ValueError, UnicodeDecodeError):
            continue
        except Exception:
            return None
    return None


def escrever_json(caminho, dados):
    """Grava JSON utf-8 com acentos preservados. Devolve (ok, erro)."""
    try:
        pasta = os.path.dirname(caminho)
        if pasta and not os.path.exists(pasta):
            os.makedirs(pasta)
        with codecs.open(caminho, 'w', encoding='utf-8') as f:
            texto = json.dumps(dados, indent=2, ensure_ascii=False, sort_keys=False)
            f.write(texto)
        return True, None
    except Exception as e:
        return False, str(e)


# ── normalizacao ──────────────────────────────────────────────────────────────

def _normalizar_levels(bruto):
    """Aceita [{'name','wbs'}], [{'name','value'}] ou {'nome': 'wbs'}.

    'centena' (24/09/2026) e opcional e so aparece quando foi dita — schema
    antigo continua valendo, e nivel sem centena nao ganha a chave.
    """
    levels = []
    vistos = set()

    def add(nome, wbs, centena=None):
        if not nome or nome in vistos:
            return
        vistos.add(nome)
        item = {'name': nome, 'wbs': '' if wbs is None else str(wbs)}
        numero = normalizar_centena(centena)
        if numero is not None:
            item['centena'] = numero
        levels.append(item)

    if isinstance(bruto, dict):
        for nome in sorted(bruto.keys()):
            add(nome, bruto[nome])
    elif isinstance(bruto, list):
        for item in bruto:
            if isinstance(item, dict):
                add(item.get('name') or item.get('level'),
                    item.get('wbs', item.get('value', '')),
                    item.get('centena'))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                add(item[0], item[1])
    return levels


def _normalizar_tipologia(bruto):
    """{chave: tipologia} com chaves str e sem entradas vazias."""
    tabela = {}
    if isinstance(bruto, dict):
        for chave, valor in bruto.items():
            if chave is None:
                continue
            k = str(chave).strip()
            if not k:
                continue
            tabela[k] = '' if valor is None else str(valor)
    return tabela


CAMPOS_REGRA = ('pavimento', 'wbs_min', 'wbs_max', 'wbs', 'tipologia')


def _normalizar_regras_cfg(bruto):
    """Regras especiais como texto/None — a validacao semantica (criterio e
    acao obrigatorios) fica no motor, em Snippets._wbs_engine.normalizar_regras.
    Aqui so garantimos o formato que vai para o JSON."""
    regras = []
    if not isinstance(bruto, (list, tuple)):
        return regras
    for item in bruto:
        if not isinstance(item, dict):
            continue
        regra = {}
        for campo in CAMPOS_REGRA:
            valor = item.get(campo)
            regra[campo] = '' if valor is None else str(valor).strip()
        if any(regra[campo] for campo in CAMPOS_REGRA):
            regras.append(regra)
    return regras


def _normalizar_projetos(bruto):
    """{'Nome do modelo': {'tipologia': {...}, 'regras': [...]}}."""
    projetos = {}
    if not isinstance(bruto, dict):
        return projetos
    for nome, dados in bruto.items():
        if nome is None:
            continue
        chave = str(nome).strip()
        if not chave:
            continue
        regras_param = []
        offsets = {}
        if isinstance(dados, dict) and ('tipologia' in dados or 'regras' in dados
                                        or 'regras_param' in dados
                                        or 'amb_offsets' in dados):
            tabela = _normalizar_tipologia(dados.get('tipologia'))
            regras = _normalizar_regras_cfg(dados.get('regras'))
            regras_param = _normalizar_regras_param(dados.get('regras_param'))
            offsets = _normalizar_offsets(dados.get('amb_offsets'))
        else:
            tabela = _normalizar_tipologia(dados)   # {'projeto': {wbs: tip}}
            regras = []
        projetos[chave] = {'tipologia': tabela, 'regras': regras,
                           'regras_param': regras_param}
        if offsets:
            projetos[chave]['amb_offsets'] = offsets
    return projetos


def normalizar(bruto):
    """Qualquer schema conhecido (v1 das 3 ferramentas, v2 ou v3) -> v3 completo."""
    cfg = config_padrao()
    if not isinstance(bruto, dict):
        return cfg

    # levels: v3/v2 "levels" | WBSCompleto "floors" | WBSFloor/wbsBox "levels"
    for chave in ('levels', 'floors'):
        if bruto.get(chave):
            cfg['levels'] = _normalizar_levels(bruto[chave])
            break

    # v3: tabela por modelo
    cfg['projetos'] = _normalizar_projetos(bruto.get('projetos'))

    # v2/WBSCompleto "tipologia" e WBSTipologia "mapping" eram uma tabela unica
    # para todos os modelos. Vira o acervo CHAVE_LEGADO: nenhum projeto novo o
    # herda em silencio, mas da para copiar dele pela UI.
    for chave in ('tipologia', 'mapping'):
        if bruto.get(chave):
            herdada = _normalizar_tipologia(bruto[chave])
            if herdada:
                atual = cfg['projetos'].get(CHAVE_LEGADO, {}).get('tipologia', {})
                for wbs, valor in herdada.items():
                    atual.setdefault(wbs, valor)
                cfg['projetos'][CHAVE_LEGADO] = {'tipologia': atual}
            break

    prefs = cfg['prefs']
    brutas = bruto.get('prefs') if isinstance(bruto.get('prefs'), dict) else {}
    for chave in prefs:
        if chave in brutas:
            prefs[chave] = brutas[chave]

    # WBSFloor guardava o parametro destino na raiz
    if bruto.get('target_param'):
        prefs['target_param_floor'] = str(bruto['target_param'])

    prefs['sufixo'] = _para_int(prefs.get('sufixo'), 1)
    prefs['offset_ft'] = _para_float(prefs.get('offset_ft'), 0.0)
    prefs['incrementar'] = bool(prefs.get('incrementar'))
    prefs['reiniciar_por_pavimento'] = bool(prefs.get('reiniciar_por_pavimento'))
    prefs['fixos_csv'] = str(prefs.get('fixos_csv') or '')
    if not isinstance(prefs.get('fixos_valores'), dict):
        prefs['fixos_valores'] = {}
    if not isinstance(prefs.get('fixos_ativos'), list):
        prefs['fixos_ativos'] = []
    prefs['fixos_em_grupo'] = bool(prefs.get('fixos_em_grupo', True))
    if prefs.get('escopo') not in ('selecao', 'vista', 'projeto'):
        prefs['escopo'] = 'selecao'
    prefs['calcular'] = bool(prefs.get('calcular', True))
    prefs['so_mudancas'] = bool(prefs.get('so_mudancas'))
    prefs['mostrar_bloqueados'] = bool(prefs.get('mostrar_bloqueados'))
    if not isinstance(prefs.get('categorias_excluidas'), list):
        prefs['categorias_excluidas'] = []
    for chave in ('amb_usar', 'amb_links', 'amb_vista'):
        prefs[chave] = bool(prefs.get(chave))
    prefs['amb_unit'] = bool(prefs.get('amb_unit', True))
    if prefs.get('unit_fonte') not in ('sufixo', 'ambiente'):
        prefs['unit_fonte'] = 'sufixo'
    prefs['amb_param_unit'] = str(prefs.get('amb_param_unit') or 'Unit ID')
    prefs['amb_offset_ft'] = _para_float(prefs.get('amb_offset_ft'), 0.0)
    prefs['amb_direcao'] = _normalizar_direcao(prefs.get('amb_direcao'))
    prefs['amb_auto'] = bool(prefs.get('amb_auto', True))
    if not isinstance(prefs.get('grupo_nao_migrar'), list):
        prefs['grupo_nao_migrar'] = list(NAO_MIGRAR_PADRAO)
    prefs['amb_auto_limite_ft'] = abs(_para_float(prefs.get('amb_auto_limite_ft'), 3.0))
    if not isinstance(prefs.get('amb_copiar'), list):
        prefs['amb_copiar'] = []

    return cfg


def _para_int(valor, padrao):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return padrao


def _para_float(valor, padrao):
    try:
        return float(str(valor).replace(',', '.'))
    except (TypeError, ValueError, AttributeError):
        return padrao


# ── fusao ─────────────────────────────────────────────────────────────────────

def fundir(configs):
    """Funde configs v2 por prioridade: a PRIMEIRA ocorrencia de cada chave vence.

    Usado na migracao do legado — a ordem da lista decide os conflitos (ex.:
    tipologia da WBSTipologia antes da do WBSCompleto).
    """
    resultado = config_padrao()
    levels_vistos = set()
    prefs_definidas = set()

    for cfg in configs:
        if not cfg:
            continue
        for item in cfg.get('levels', []):
            nome = item.get('name')
            if nome and nome not in levels_vistos:
                levels_vistos.add(nome)
                resultado['levels'].append({'name': nome, 'wbs': item.get('wbs', '')})

        for projeto, dados in cfg.get('projetos', {}).items():
            destino = resultado['projetos'].setdefault(
                projeto, {'tipologia': {}, 'regras': [], 'regras_param': []})
            for chave, valor in dados.get('tipologia', {}).items():
                if chave not in destino['tipologia']:
                    destino['tipologia'][chave] = valor
            if dados.get('regras') and not destino['regras']:
                destino['regras'] = [dict(r) for r in dados['regras']]
            if dados.get('regras_param') and not destino.get('regras_param'):
                destino['regras_param'] = [dict(r) for r in dados['regras_param']]
            if dados.get('amb_offsets') and not destino.get('amb_offsets'):
                destino['amb_offsets'] = _normalizar_offsets(dados['amb_offsets'])

        for chave, valor in (cfg.get('prefs') or {}).items():
            if chave not in prefs_definidas:
                prefs_definidas.add(chave)
                resultado['prefs'][chave] = valor

    return resultado


def conflitos_tipologia(configs):
    """Onde as fontes discordam: {'projeto · wbs': [valor_por_fonte, ...]}.

    Serve de diagnostico da migracao — quem vence e a ordem passada a fundir().
    """
    conflitos = {}
    vistos = {}
    for cfg in configs:
        if not cfg:
            continue
        for projeto, dados in cfg.get('projetos', {}).items():
            for wbs, valor in dados.get('tipologia', {}).items():
                chave = "{} · {}".format(projeto, wbs)
                if chave in vistos and vistos[chave] != valor:
                    conflitos.setdefault(chave, [vistos[chave]]).append(valor)
                elif chave not in vistos:
                    vistos[chave] = valor
    return conflitos


# ── api de alto nivel ─────────────────────────────────────────────────────────

def carregar(base_dir=None, fontes_legado=None):
    """Config unificada. Migra do legado na primeira execucao.

    Args:
        base_dir: sobrescreve a pasta APPDATA (testes).
        fontes_legado: caminhos de config antigos, JA em ordem de prioridade
                       (o primeiro vence os conflitos).

    Returns:
        (cfg, migrou, conflitos) — migrou=True quando a config unificada acabou
        de ser criada a partir do legado.
    """
    atual = ler_json(caminho_config(base_dir))
    if atual is not None:
        return normalizar(atual), False, {}

    normalizadas = []
    for caminho in (fontes_legado or []):
        bruto = ler_json(caminho)
        if bruto is not None:
            normalizadas.append(normalizar(bruto))

    if not normalizadas:
        return config_padrao(), False, {}

    conflitos = conflitos_tipologia(normalizadas)
    cfg = fundir(normalizadas)
    salvar(cfg, base_dir)
    return cfg, True, conflitos


def salvar(cfg, base_dir=None):
    """Grava a config unificada. Devolve (ok, erro)."""
    dados = normalizar(cfg)
    dados['version'] = SCHEMA_VERSION
    return escrever_json(caminho_config(base_dir), dados)


def nome_projeto(titulo):
    """Chave do modelo na config, a partir de doc.Title.

    Tira a extensao e o sufixo de arquivo local de modelo workshared, para que
    'Torre A.rvt' e 'Torre A_thiago.rvt' caiam na MESMA tabela.
    """
    if not titulo:
        return ''
    nome = str(titulo).strip()
    for ext in ('.rvt', '.RVT'):
        if nome.endswith(ext):
            nome = nome[:-len(ext)]
            break
    return nome.strip()


def tipologia_do_projeto(cfg, projeto):
    """Copia da tabela do modelo. Projeto sem tabela ainda -> {} (nunca herda
    a de outro modelo em silencio)."""
    dados = cfg.get('projetos', {}).get(projeto)
    if not dados:
        return {}
    return dict(dados.get('tipologia', {}))


def regras_do_projeto(cfg, projeto):
    """Copia das regras especiais do modelo (ex.: 1st -> WBS e Tipologia 'CA')."""
    dados = cfg.get('projetos', {}).get(projeto)
    if not dados:
        return []
    return [dict(regra) for regra in dados.get('regras', [])]


def _limpar_projeto_vazio(projetos, projeto):
    dados = projetos.get(projeto)
    if dados and not dados.get('tipologia') and not dados.get('regras') \
            and not dados.get('regras_param') and not dados.get('amb_offsets'):
        del projetos[projeto]


def definir_tipologia_do_projeto(cfg, projeto, tabela):
    """Grava a tabela do modelo, preservando as regras dele."""
    if not projeto:
        return cfg
    projetos = cfg.setdefault('projetos', {})
    dados = projetos.setdefault(projeto, {})
    dados['tipologia'] = _normalizar_tipologia(tabela)
    _limpar_projeto_vazio(projetos, projeto)
    return cfg


def definir_regras_do_projeto(cfg, projeto, regras):
    """Grava as regras do modelo, preservando a tabela de tipologia dele."""
    if not projeto:
        return cfg
    projetos = cfg.setdefault('projetos', {})
    dados = projetos.setdefault(projeto, {})
    dados['regras'] = _normalizar_regras_cfg(regras)
    _limpar_projeto_vazio(projetos, projeto)
    return cfg


def regras_param_do_projeto(cfg, projeto):
    """Copia das regras de parametros do modelo. Modelo sem regras -> []:
    nunca herda as de outro modelo em silencio (use importar)."""
    dados = cfg.get('projetos', {}).get(projeto)
    if not dados:
        return []
    return [dict(regra) for regra in dados.get('regras_param', [])]


def definir_regras_param_do_projeto(cfg, projeto, regras):
    """Grava as regras de parametros do modelo, preservando o resto dele."""
    if not projeto:
        return cfg
    projetos = cfg.setdefault('projetos', {})
    dados = projetos.setdefault(projeto, {})
    dados['regras_param'] = _normalizar_regras_param(regras)
    _limpar_projeto_vazio(projetos, projeto)
    return cfg


def offsets_de_ambiente_do_projeto(cfg, projeto):
    """{chave do room: {'offset_ft', 'direcao'}} do modelo — copia. O room sem
    entrada usa o offset padrao da aba Ambientes (16/09/2026)."""
    dados = cfg.get('projetos', {}).get(projeto)
    if not dados:
        return {}
    return _normalizar_offsets(dados.get('amb_offsets'))


def definir_offsets_de_ambiente_do_projeto(cfg, projeto, offsets):
    if not projeto:
        return cfg
    projetos = cfg.setdefault('projetos', {})
    dados = projetos.setdefault(projeto, {})
    normalizados = _normalizar_offsets(offsets)
    if normalizados:
        dados['amb_offsets'] = normalizados
    else:
        dados.pop('amb_offsets', None)
    _limpar_projeto_vazio(projetos, projeto)
    return cfg


def projetos_com_tipologia(cfg, excluir=None):
    """[(nome, quantas_entradas)] ordenado, para o 'Copiar de...' da UI."""
    itens = []
    for nome, dados in cfg.get('projetos', {}).items():
        if excluir and nome == excluir:
            continue
        total = len(dados.get('tipologia', {}))
        if total:
            itens.append((nome, total))
    itens.sort(key=lambda par: par[0].lower())
    return itens


def mesclar_levels(cfg, levels_do_modelo):
    """Atualiza os niveis do modelo aberto PRESERVANDO os dos outros projetos.

    A config e unica para todos os modelos: sobrescrever a lista inteira com os
    niveis do documento atual apagaria o mapeamento dos demais. Os nomes vistos
    agora vao para o topo, na ordem recebida; o resto fica logo abaixo.

    Args:
        cfg: config v2 (alterada in place).
        levels_do_modelo: [{'name': ..., 'wbs': ..., 'centena': ...}, ...] do
            documento atual. 'centena' (24/09/2026) e opcional: o numero que
            forma o Unit ID quando o texto do Floor nao tem numero ("UDG").
    """
    atuais = []
    nomes = set()
    for item in levels_do_modelo:
        nome = item.get('name')
        if not nome or nome in nomes:
            continue
        nomes.add(nome)
        novo = {'name': nome, 'wbs': item.get('wbs') or ''}
        centena = normalizar_centena(item.get('centena'))
        if centena is not None:
            novo['centena'] = centena
        atuais.append(novo)

    antigos = [item for item in cfg.get('levels', [])
               if item.get('name') not in nomes]

    cfg['levels'] = atuais + antigos
    return cfg


def levels_como_mapa(cfg):
    """{'nome do level': 'wbs'} — lookup rapido ao montar a grade."""
    return dict((item['name'], item.get('wbs', '')) for item in cfg.get('levels', []))


def normalizar_centena(valor):
    """Texto digitado -> inteiro da centena, ou None quando em branco/invalido.

    Em branco e o normal: a centena so e dita quando o texto do Floor nao
    resolve. Negativo nao serve (Unit ID nasceria negativo).
    """
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    try:
        numero = int(float(texto))
    except (TypeError, ValueError):
        return None
    return numero if numero >= 0 else None


def centenas_por_nivel(cfg):
    """{'nome do level': centena} — o que a grade da aba Floors mostra."""
    mapa = {}
    for item in cfg.get('levels', []):
        centena = normalizar_centena(item.get('centena'))
        if centena is not None and item.get('name'):
            mapa[item['name']] = centena
    return mapa


def centenas_como_mapa(cfg):
    """{'texto do Floor': centena} — o que `_wbs_engine.atribuir` consome.

    A chave e o Floor (o texto gravado), nao o nome do Level: dois niveis podem
    compartilhar o mesmo Floor, e quem numera o Unit ID e o Floor.
    """
    mapa = {}
    for item in cfg.get('levels', []):
        centena = normalizar_centena(item.get('centena'))
        floor = (item.get('wbs') or '').strip()
        if centena is not None and floor:
            mapa[floor] = centena
    return mapa
