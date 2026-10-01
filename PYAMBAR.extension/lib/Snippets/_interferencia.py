# -*- coding: utf-8 -*-
"""O relatorio de interferencia do Revit, lido e acompanhado — logica pura.

Sem clr/Autodesk: roda identico em IronPython 3 e CPython (testes em
`dev-tools/tests/test_interferencia.py`).

O QUE O REVIT EXPORTA (lido no MIIQLUX-SEW-RSR, 16/09/2026)
-----------------------------------------------------------
A API nao expoe o resultado da Interference Check. O unico caminho e o HTML
do botao "Exportar...": UTF-8 com BOM, uma tabela `n | A | B`, e cada celula

    [arquivo.rvt : ]Categoria : Familia : Tipo : ID n

O prefixo `.rvt` so aparece no lado que vem de um vinculo. As 290 linhas do
relatorio real terminam em `ID n`, sem excecao. Nomes podem ter aspas
(`9"x7"`) — por isso o ID sai do FIM da celula e a categoria do comeco.

A CHAVE DO CONFLITO NAO E O NUMERO DA LINHA
-------------------------------------------
O Revit renumera a cada exportacao. A chave e `vinculo#id` dos dois lados,
em ordem alfabetica — trocar A com B na proxima checagem nao perde o status.

O REGISTRO
----------
Um JSON ao lado do HTML (`<relatorio>.status.json`), um item por chave:

    a, b            os lados (para mostrar mesmo depois que sair do HTML)
    status          pendente | resolvido | ignorar
    comentario, por, quando        a ultima marca de alguem
    no_relatorio    esta no HTML carregado por ultimo
    visto_em        quando a presenca foi atualizada

Reexportar com o mesmo nome e recarregar mostra o que SAIU do relatorio —
o progresso aparece sem ninguem marcar nada.
"""
import json
import re

from Snippets._passes_laje import REGRAS as _REGRAS_PASSES

PENDENTE = 'pendente'
RESOLVIDO = 'resolvido'
IGNORAR = 'ignorar'
STATUS = (PENDENTE, RESOLVIDO, IGNORAR)

# filtros da lista
F_PENDENTES = 'pendentes'
F_TODOS = 'todos'
F_RESOLVIDOS = 'resolvidos'
F_IGNORADOS = 'ignorados'
F_SAIRAM = 'sairam'

VERSAO_REGISTRO = 1

_RE_ID = re.compile(r'^(.*?)\s*:\s*ID\s+(\d+)\s*$', re.S)
_RE_TR = re.compile(r'<tr[^>]*>(.*?)</tr>', re.S | re.I)
_RE_TD = re.compile(r'<td[^>]*>(.*?)</td>', re.S | re.I)
_RE_TAG = re.compile(r'<[^>]+>')
_RE_RVT = re.compile(r'>\s*([^<>]*?\.rvt)\s*<', re.I)
_ENTIDADES = (('&quot;', '"'), ('&#39;', "'"), ('&lt;', '<'), ('&gt;', '>'),
              ('&nbsp;', ' '), ('&amp;', '&'))


# ------------------------------------------------------------------ leitura

def decodificar(dados):
    """bytes -> texto. UTF-8 (com ou sem BOM); senao cp1252, sem quebrar."""
    if not isinstance(dados, bytes):
        return dados
    try:
        return dados.decode('utf-8-sig')
    except UnicodeDecodeError:
        return dados.decode('cp1252', 'replace')


def _limpar(celula):
    texto = _RE_TAG.sub('', celula or '')
    for entidade, caractere in _ENTIDADES:
        texto = texto.replace(entidade, caractere)
    return ' '.join(texto.split())


def ler_lado(celula):
    """Uma celula -> {vinculo, categoria, descricao, id} | None.

    `vinculo` e '' quando o elemento e do proprio projeto.
    """
    texto = _limpar(celula)
    casou = _RE_ID.match(texto)
    if not casou:
        return None
    partes = [p.strip() for p in casou.group(1).split(' : ')]
    vinculo = ''
    if partes and partes[0].lower().endswith('.rvt'):
        vinculo = partes.pop(0)
    if not partes or not partes[0]:
        return None
    return {
        'vinculo': vinculo,
        'categoria': partes[0],
        'descricao': ' : '.join(partes[1:]),
        'id': int(casou.group(2)),
    }


def chave_do_lado(lado):
    return '{}#{}'.format((lado.get('vinculo') or '').lower(), lado['id'])


def chave(a, b):
    return '|'.join(sorted([chave_do_lado(a), chave_do_lado(b)]))


def ler_relatorio(texto):
    """HTML exportado -> {projeto, conflitos, ignoradas}.

    `projeto`: o primeiro caminho .rvt do cabecalho ('' se nao houver).
    `ignoradas`: numeros/trechos de linhas com 3 colunas que nao leram.
    Conflito repetido (mesma chave) entra uma vez so.
    """
    texto = decodificar(texto)
    inicio_tabela = texto.lower().find('<table')
    cabecalho = texto if inicio_tabela < 0 else texto[:inicio_tabela]
    achou = _RE_RVT.search(cabecalho)
    projeto = achou.group(1).strip() if achou else ''

    conflitos = []
    ignoradas = []
    vistas = set()
    for linha in _RE_TR.findall(texto):
        celulas = _RE_TD.findall(linha)
        if len(celulas) != 3:
            continue
        numero = _limpar(celulas[0])
        if not numero.isdigit():
            continue        # o cabecalho "  | A | B"
        a = ler_lado(celulas[1])
        b = ler_lado(celulas[2])
        if a is None or b is None:
            ignoradas.append(numero)
            continue
        k = chave(a, b)
        if k in vistas:
            continue
        vistas.add(k)
        conflitos.append({'numero': int(numero), 'a': a, 'b': b, 'chave': k})
    return {'projeto': projeto, 'conflitos': conflitos,
            'ignoradas': ignoradas}


def nome_do_arquivo(caminho):
    """So o nome, com / ou \\ — o caminho vem do Windows, o teste nao."""
    return re.split(r'[\\/]', caminho or '')[-1]


def mesmo_projeto(projeto_do_relatorio, caminho_do_modelo):
    """None se nao da para dizer; senao compara o nome do arquivo.

    Arquivo local de modelo central tem sufixo (`_thiago`): quem chama passa o
    caminho do CENTRAL quando houver.
    """
    a = nome_do_arquivo(projeto_do_relatorio).lower()
    b = nome_do_arquivo(caminho_do_modelo).lower()
    if not a or not b:
        return None
    return a == b


def arquivo_de(lado, arquivo_do_relatorio):
    """O .rvt onde o elemento mora: o vinculo, ou o modelo do relatorio.

    v1.7: a navegacao deixou de supor que o modelo aberto e o do relatorio —
    o Thiago abre o vinculo (CIQ-PLB-WATER SUPPLY) para corrigir o tubo la.

    v2.5 (bug achado na auditoria, 30/09/2026): o apontamento do LOG guarda
    o arquivo em `arquivo`, com `vinculo` vazio. Sem olhar `arquivo`, todo
    elemento de VINCULO apontado pelo LOG era procurado no modelo aberto —
    "Dutos 9637535 nao existe mais em CIQ-PLB-SEW-RSR.rvt", estando ele no
    MEC-UNIT FN06.rvt. Ja acontecia desde 24/09 (print do Thiago).
    """
    return (lado.get('vinculo') or lado.get('arquivo') or
            arquivo_do_relatorio or '')


def onde_esta(arquivo, modelo_ativo, vinculos_ativos):
    """'modelo' | 'vinculo' | None — onde achar o elemento no modelo ABERTO.

    Sem arquivo conhecido (relatorio sem cabecalho): o modelo, como antes.
    """
    alvo = (arquivo or '').lower()
    if not alvo or alvo == (modelo_ativo or '').lower():
        return 'modelo'
    if alvo in set((v or '').lower() for v in vinculos_ativos):
        return 'vinculo'
    return None


def arquivos_do_registro(registro, arquivo_do_relatorio):
    """Os .rvt que aparecem no relatorio (para dizer se o aberto e um deles)."""
    arquivos = set()
    for item in registro.get('conflitos', {}).values():
        for lado in (item.get('a'), item.get('b')):
            if lado:
                arquivo = arquivo_de(lado, arquivo_do_relatorio)
                if arquivo:
                    arquivos.add(arquivo.lower())
    return arquivos


def nome_do_vinculo(nome_da_instancia):
    """'MIIIQLUX-MEC.rvt : 33 : localização <...>' -> 'miiiqlux-mec.rvt'."""
    return (nome_da_instancia or '').split(' : ')[0].strip().lower()


# ---------------------------------------------------------------- registro

def registro_vazio():
    return {'versao': VERSAO_REGISTRO, 'conflitos': {}}


#: o que um achado de verificacao propria traz alem dos lados (v1.5) —
#: a medida muda a cada execucao; a chave, nao
EXTRAS = ('regra', 'medida', 'nivel', 'gravidade', 'valor')


def _copiar_extras(origem, destino):
    for campo in EXTRAS:
        if campo in origem:
            destino[campo] = origem[campo]


#: relatorios em JSON que a janela abre: os que NOS geramos e, desde o
#: repositorio (30/09/2026), o HTML do Revit ja convertido
#: (`_repositorio.html_para_relatorio`)
FONTES_PROPRIAS = ('passes', 'clash', 'html')
#: a identidade no repositorio passa adiante para a janela
_DO_REPOSITORIO = ('id', 'escopo', 'autor', 'criado_por', 'criado_em',
                   'historico', 'titulo')


def ler_relatorio_passes(texto):
    """O JSON de uma verificacao NOSSA -> a mesma forma do `ler_relatorio`.

    Serve para os passes de laje e para o clash entre vinculos (v2.4): o
    formato e o mesmo, muda a `fonte`. `b` pode ser None (passe sem tubo).
    """
    dados = json.loads(decodificar(texto))
    if not isinstance(dados, dict) or dados.get('fonte') not in FONTES_PROPRIAS:
        raise ValueError(u'não é um relatório gerado por nós')
    conflitos = []
    for numero, achado in enumerate(dados.get('achados', []), 1):
        conflito = {'numero': numero, 'a': achado['a'],
                    'b': achado.get('b'), 'chave': achado['chave']}
        _copiar_extras(achado, conflito)
        conflitos.append(conflito)
    return {'projeto': dados.get('projeto', ''), 'conflitos': conflitos,
            'ignoradas': [], 'fonte': dados['fonte'],
            'lajes': dados.get('lajes', []),
            'parametros': dados.get('parametros', {}),
            'gerado_em': dados.get('gerado_em', ''),
            'repositorio': dict((c, dados[c]) for c in _DO_REPOSITORIO
                                if c in dados)}


def sincronizar(registro, conflitos, agora):
    """Atualiza a presenca pelo relatorio carregado.

    -> (registro, novos, sairam, voltaram) — listas de chaves. `novos` so
    conta quando o registro ja tinha algo (a primeira carga nao e "novidade").
    """
    itens = registro.setdefault('conflitos', {})
    tinha = bool(itens)
    atuais = set()
    novos, sairam, voltaram = [], [], []
    for c in conflitos:
        k = c['chave']
        atuais.add(k)
        item = itens.get(k)
        if item is None:
            itens[k] = {'a': c['a'], 'b': c['b'], 'status': PENDENTE,
                        'comentario': '', 'por': '', 'quando': '',
                        'no_relatorio': True, 'visto_em': agora}
            _copiar_extras(c, itens[k])
            if tinha:
                novos.append(k)
            continue
        item['a'], item['b'] = c['a'], c['b']
        _copiar_extras(c, item)
        if not item.get('no_relatorio', True):
            voltaram.append(k)
            # VOLTOU A APARECER: "resolvido" nao vale mais (25/09/2026).
            # O achado sumiu do relatorio, alguem marcou resolvido e ele
            # reapareceu numa verificacao nova — o problema esta de volta no
            # modelo. Ficar resolvido some da lista de Abertos e passa batido.
            # `ignorar` NAO reabre: ignorar e decisao consciente de que aquilo
            # nao e problema, e continuar aparecendo nao muda isso.
            if item.get('status') == RESOLVIDO:
                item['status'] = PENDENTE
                item['reaberto_em'] = agora
                item['resolvido_antes_em'] = item.get('quando') or ''
                # a reabertura e uma MARCA nova (30/09/2026): sem data nova,
                # o status do projeto (`_repositorio`) acharia o "resolvido"
                # dos outros relatorios tao novo quanto e nao o desfaria
                item['quando'] = agora
        if not item.get('no_relatorio', True) or not item.get('visto_em'):
            item['visto_em'] = agora
        item['no_relatorio'] = True
    for k, item in itens.items():
        if k not in atuais and item.get('no_relatorio', True):
            item['no_relatorio'] = False
            item['visto_em'] = agora
            sairam.append(k)
    return registro, novos, sairam, voltaram


def marcar(registro, k, status=None, comentario=None, por='', agora=''):
    """Muda status e/ou comentario de uma chave. False se a chave nao existe."""
    item = registro.get('conflitos', {}).get(k)
    if item is None:
        return False
    if status is not None:
        if status not in STATUS:
            raise ValueError('status invalido: {}'.format(status))
        item['status'] = status
    if comentario is not None:
        item['comentario'] = comentario
    item['por'] = por
    item['quando'] = agora
    return True


def mesclar(disco, meu):
    """Junta o registro do disco com o da janela, item a item.

    Duas pessoas no mesmo JSON: a marca (status/comentario) mais recente vence
    pelo `quando`; a presenca, pelo `visto_em`. Datas em ISO comparam como
    texto. Empate fica com o meu.
    """
    resultado = registro_vazio()
    d_itens = (disco or {}).get('conflitos', {})
    m_itens = (meu or {}).get('conflitos', {})
    for k in set(d_itens) | set(m_itens):
        d, m = d_itens.get(k), m_itens.get(k)
        if d is None or m is None:
            resultado['conflitos'][k] = dict(m or d)
            continue
        item = dict(m)
        if (d.get('quando') or '') > (m.get('quando') or ''):
            for campo in ('status', 'comentario', 'por', 'quando'):
                item[campo] = d.get(campo, item.get(campo))
        if (d.get('visto_em') or '') > (m.get('visto_em') or ''):
            item['no_relatorio'] = d.get('no_relatorio', True)
            item['visto_em'] = d.get('visto_em')
        resultado['conflitos'][k] = item
    return resultado


# ------------------------------------------------------------------- lista

def passa_no_filtro(item, filtro):
    presente = item.get('no_relatorio', True)
    status = item.get('status', PENDENTE)
    if filtro == F_SAIRAM:
        return not presente
    if not presente:
        return False
    if filtro == F_PENDENTES:
        return status == PENDENTE
    if filtro == F_RESOLVIDOS:
        return status == RESOLVIDO
    if filtro == F_IGNORADOS:
        return status == IGNORAR
    return True     # F_TODOS


def texto_do_lado(lado):
    partes = [lado.get('vinculo') or '', lado.get('categoria') or '',
              lado.get('descricao') or '', 'ID {}'.format(lado.get('id'))]
    return ' : '.join(p for p in partes if p)


def _casa_texto(item, busca):
    if not busca:
        return True
    partes = [texto_do_lado(item['a']),
              texto_do_lado(item['b']) if item.get('b') else '',
              item.get('regra') or '', item.get('medida') or '',
              item.get('comentario') or '']
    alvo = ' '.join(partes).lower()
    return all(pedaco in alvo for pedaco in busca.lower().split())


#: niveis de agrupamento — o "Agrupar por" do relatorio do Revit (v1.1)
CAT_A = 'cat_a'
CAT_B = 'cat_b'
ELEM_A = 'elem_a'
AGRUPAMENTOS = (
    ((CAT_A, CAT_B), u'Categoria A › Categoria B'),
    ((CAT_B, CAT_A), u'Categoria B › Categoria A'),
    ((CAT_A, ELEM_A), u'Categoria A › Elemento A'),
    # v1.2: o agrupamento da v1.0, agora recolhivel, e os dois juntos
    ((ELEM_A,), u'Elemento A'),
    ((CAT_A, CAT_B, ELEM_A), u'Categoria A › Categoria B › Elemento A'),
)
#: v1.5 — verificacao de passes: laje por laje (decisao do Thiago)
REGRA = 'regra'
LAJE = 'laje'
AGRUPAMENTOS_PASSES = (
    ((LAJE, REGRA), u'Laje › Regra'),
    ((REGRA, LAJE), u'Regra › Laje'),
    ((LAJE, REGRA, ELEM_A), u'Laje › Regra › Elemento'),
)
#: v1.8 — LOG da obra: o recado mora num modelo e e para alguem
MODELO = LAJE          # o mesmo campo `nivel` do item, outro nome na UI
PARA_QUEM = REGRA
#: v2.4 — clash proprio: o par de MODELOS e o par de CATEGORIAS
#: 01/10/2026 (Thiago: "agrupar categoria x categoria e poder escolher a
#: ordem, tubo x duto ou duto x tubo"): A = coluna "Verificar estes"
AGRUPAMENTOS_CLASH = (
    ((CAT_A, CAT_B), u'Categoria A › Categoria B'),
    ((CAT_B, CAT_A), u'Categoria B › Categoria A'),
    ((LAJE, CAT_A, CAT_B), u'Modelos › Categoria A › Categoria B'),
    ((LAJE, REGRA), u'Modelos › Categorias'),
    ((REGRA, LAJE), u'Categorias › Modelos'),
    ((LAJE, REGRA, ELEM_A), u'Modelos › Categorias › Elemento'),
)
AGRUPAMENTOS_LOG = (
    ((MODELO, PARA_QUEM), u'Modelo › Para quem'),
    ((PARA_QUEM, MODELO), u'Para quem › Modelo'),
    ((MODELO,), u'Modelo'),
)
SEM_PAR = u'(sem par)'
SEPARADOR = u'\x1f'


def agrupamentos(fonte):
    if fonte == 'passes':
        return AGRUPAMENTOS_PASSES
    if fonte == 'clash':
        return AGRUPAMENTOS_CLASH
    if fonte == 'log':
        return AGRUPAMENTOS_LOG
    return AGRUPAMENTOS


def indice_do_agrupamento(opcoes, salvo):
    """A escolha salva -> posicao na lista atual.

    Salva pelo NOME desde 01/10/2026: opcao nova no comeco da lista nao pode
    trocar o agrupamento de quem ja tinha escolhido. Indice (antigo) ainda
    vale; o que nao existe mais volta para a primeira.
    """
    for indice, (_, rotulo) in enumerate(opcoes):
        if salvo == rotulo:
            return indice
    if isinstance(salvo, int) and not isinstance(salvo, bool) and             0 <= salvo < len(opcoes):
        return salvo
    return 0


def valor_do_nivel(item, nivel):
    if nivel == CAT_A:
        return item['a'].get('categoria', '')
    if nivel == CAT_B:
        return item['b'].get('categoria', '') if item.get('b') else SEM_PAR
    if nivel == REGRA:
        return item.get('regra') or ''
    if nivel == LAJE:
        return item.get('nivel') or ''
    return chave_do_lado(item['a'])


def chaves_filtradas(registro, ordem, filtro=F_PENDENTES, busca=''):
    """As chaves que passam, na ordem do relatorio; as que sairam, depois."""
    itens = registro.get('conflitos', {})
    no_html = set(ordem)
    sequencia = list(ordem) + sorted(k for k in itens if k not in no_html)
    return [k for k in sequencia
            if k in itens and passa_no_filtro(itens[k], filtro)
            and _casa_texto(itens[k], busca)]


def caminho_de(item, niveis, ate=None):
    """'Tubulação\\x1fDutos' — o id de um grupo (texto: cabe num set)."""
    niveis = niveis[:ate] if ate is not None else niveis
    return SEPARADOR.join(valor_do_nivel(item, n) for n in niveis)


def arvore(registro, chaves, niveis):
    """Grupos aninhados: [{nivel, valor, caminho, chaves, filhos, item}].

    Categoria em ordem alfabetica (como o Revit); elemento A na ordem do
    relatorio. `chaves` ja filtradas e ordenadas; no ultimo nivel, `filhos`
    e [] e as chaves sao as folhas. `item` e o primeiro conflito do grupo —
    de onde a janela tira o rotulo do elemento A.
    """
    itens = registro.get('conflitos', {})

    def montar(chaves_do_nivel, profundidade, prefixo):
        nivel = niveis[profundidade]
        grupos = {}
        sequencia = []
        for k in chaves_do_nivel:
            valor = valor_do_nivel(itens[k], nivel)
            if valor not in grupos:
                grupos[valor] = []
                sequencia.append(valor)
            grupos[valor].append(k)
        if nivel == REGRA:
            # na ordem de gravidade das regras, nao alfabetica
            sequencia.sort(key=_ordem_da_regra)
        elif nivel != ELEM_A:
            sequencia.sort(key=lambda v: v.lower())
        nos = []
        for valor in sequencia:
            caminho = prefixo + SEPARADOR + valor if prefixo else valor
            ultimo = profundidade == len(niveis) - 1
            nos.append({
                'nivel': nivel,
                'valor': valor,
                'caminho': caminho,
                'chaves': grupos[valor],
                'item': itens[grupos[valor][0]],
                'filhos': [] if ultimo else montar(grupos[valor],
                                                   profundidade + 1, caminho),
            })
        return nos

    return montar(list(chaves), 0, '') if niveis and chaves else []


def _ordem_da_regra(regra):
    return (_REGRAS_PASSES.index(regra) if regra in _REGRAS_PASSES
            else len(_REGRAS_PASSES), regra)


def achatar(nos, abertos, tudo_aberto=False, profundidade=0):
    """A arvore como linhas da lista, respeitando o que esta aberto.

    -> [{'tipo': 'grupo', 'no', 'profundidade', 'aberto'}
        | {'tipo': 'conflito', 'chave', 'profundidade'}]
    """
    linhas = []
    for no in nos:
        aberto = tudo_aberto or no['caminho'] in abertos
        linhas.append({'tipo': 'grupo', 'no': no, 'aberto': aberto,
                       'profundidade': profundidade})
        if not aberto:
            continue
        if no['filhos']:
            linhas.extend(achatar(no['filhos'], abertos, tudo_aberto,
                                  profundidade + 1))
        else:
            linhas.extend({'tipo': 'conflito', 'chave': k,
                           'profundidade': profundidade + 1}
                          for k in no['chaves'])
    return linhas


def caminhos_ate(item, niveis):
    """Os grupos a abrir para a folha de `item` aparecer."""
    return [caminho_de(item, niveis, i + 1) for i in range(len(niveis))]


def cadeia(caminho):
    """O grupo e os pais dele: 'A\\x1fB\\x1fC' -> ['A', 'A\\x1fB', 'A\\x1fB\\x1fC'].

    Sanfona (v1.3): abrir um grupo deixa aberta so esta cadeia — os irmaos e
    o que estava aberto antes fecham.
    """
    partes = (caminho or '').split(SEPARADOR)
    return [SEPARADOR.join(partes[:i + 1]) for i in range(len(partes))] \
        if caminho else []


def grupos_no_nivel(nos, profundidade):
    """Os caminhos dos grupos de uma profundidade, na ordem da arvore — as
    setas ‹ › andam por eles, atravessando os pais (v1.4)."""
    if profundidade == 0:
        return [no['caminho'] for no in nos]
    resultado = []
    for no in nos:
        resultado.extend(grupos_no_nivel(no['filhos'], profundidade - 1))
    return resultado


def grupo_vizinho(nos, caminho, passo):
    """O grupo `passo` posicoes adiante no mesmo nivel, dando a volta.

    None se o caminho nao esta na arvore (filtro mudou).
    """
    grupos = grupos_no_nivel(nos, len(cadeia(caminho)) - 1)
    if caminho not in grupos:
        return None
    return grupos[(grupos.index(caminho) + passo) % len(grupos)]


def ordem_da_arvore(registro, ordem, niveis):
    """Todas as chaves no relatorio, na ordem em que a ARVORE as mostra.

    v1.6: "Proxima pendente" e o pulo depois de marcar andavam na ordem do
    HTML — o proximo conflito do relatorio costuma estar em outro grupo, e a
    sanfona fechava o grupo no meio. Na ordem da arvore, o proximo pendente
    e o do mesmo grupo; o grupo seguinte so quando este acaba.
    Sem filtro de status nem busca: o conflito recem-marcado continua na
    lista, e e dele que se conta o "proximo".
    """
    nos = arvore(registro, chaves_filtradas(registro, ordem, F_TODOS),
                 niveis)
    return [l['chave'] for l in achatar(nos, set(), True)
            if l['tipo'] == 'conflito']


def todos_os_caminhos(nos):
    resultado = []
    for no in nos:
        resultado.append(no['caminho'])
        resultado.extend(todos_os_caminhos(no['filhos']))
    return resultado


def contagem(registro):
    """{pendente, resolvido, ignorar, sairam, total} — total = no relatorio."""
    resultado = {PENDENTE: 0, RESOLVIDO: 0, IGNORAR: 0, 'sairam': 0,
                 'total': 0}
    for item in registro.get('conflitos', {}).values():
        if not item.get('no_relatorio', True):
            resultado['sairam'] += 1
            continue
        resultado['total'] += 1
        status = item.get('status', PENDENTE)
        resultado[status] = resultado.get(status, 0) + 1
    return resultado


def proxima_pendente(registro, ordem, atual=None):
    """A proxima chave pendente depois de `atual`, dando a volta. None se nao ha."""
    itens = registro.get('conflitos', {})
    pendentes = [k for k in ordem
                 if k in itens and passa_no_filtro(itens[k], F_PENDENTES)]
    if not pendentes:
        return None
    if atual in ordem:
        depois = ordem.index(atual)
        for k in pendentes:
            if ordem.index(k) > depois:
                return k
    return pendentes[0]


# ---------------------------------------------------------------- geometria

def caixa_transformada(minimo, maximo, transformar):
    """Os 8 cantos de uma caixa passados por `transformar((x,y,z))`.

    -> ((xmin, ymin, zmin), (xmax, ymax, zmax)). O vinculo pode estar girado:
    transformar so Min e Max daria uma caixa errada.
    """
    pontos = [transformar((x, y, z))
              for x in (minimo[0], maximo[0])
              for y in (minimo[1], maximo[1])
              for z in (minimo[2], maximo[2])]
    menor = tuple(min(p[i] for p in pontos) for i in range(3))
    maior = tuple(max(p[i] for p in pontos) for i in range(3))
    return menor, maior
