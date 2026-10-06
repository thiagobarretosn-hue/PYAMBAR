# -*- coding: utf-8 -*-
"""Passes de laje x tubos verticais — a verificacao, sem Revit.

Sem clr/Autodesk: testado em CPython (`dev-tools/tests/test_passes_laje.py`).
Quem coleta (passes, tubos, pisos, niveis) e o `ifr_passes` da ferramenta
Interferencias; o resultado vira um relatorio que a mesma janela abre.

O QUE O MODELO MOSTROU (CIQ-PLB-SLAB PASSES, MCP 18/09/2026)
-----------------------------------------------------------
- Passe WPS: eixo vertical no `LocationPoint`, Ø no parametro de tipo
  `Size Diameter`, SEM conectores — o casamento com o tubo e geometrico.
- A caixa do passe em Z e a espessura da laje (8 1/8" no L2), com o topo na
  cota do nivel.
- 121 passes: 85 com desvio <= 1/8", 92 <= 1/4", 104 <= 1", 6 acima de 2".
- Os vinculos do CIQ nao tem pisos.

UM TUBO, UM PASSE (por laje)
----------------------------
O casamento e guloso pela menor distancia no conjunto todo, nao "o tubo mais
perto de cada passe": no modelo, o tubo 9664908 era o mais perto de DOIS
passes (0,55" e 6,8"). O segundo passe tem de sair como sem tubo, nao como
um desvio de 6,8" para um tubo que ja tem passe.

AS REGRAS (Thiago, 18/09/2026 — escolhidas no dialogo)
-----------------------------------------------------
    Fora do eixo     desvio > tolerancia (atencao); desvio > folga fisica
                     (Ø passe - Ø ext tubo)/2, o tubo na parede: erro
    Diâmetro         o passe de 1 a 2 tamanhos WPS acima do tubo; tubo
                     maior que o passe: erro
    Passe sem tubo   nenhum tubo livre a `raio` (padrao 12")
    Tubo sem passe   tubo atravessa a laje escolhida sem passe casado

v1.6: "Fora do eixo" era duas regras (encosta / tolerancia) — virou uma, e a
gravidade fica na medida. O diametro era "o padrao do modelo" (tubo + 2,
nunca menor que WPS-3); agora e a regra dele: de 1 a 2 acima.

A ESPESSURA E POR LAJE, AUTOMATICA (v1.6)
----------------------------------------
    1. os passes daquela laje (mediana da altura) — o que o modelo mostra
    2. pisos dos vinculos com o topo na cota do nivel (FLOOR_ATTR_THICKNESS)
    3. a mediana de TODOS os passes, marcada como "padrao"
O passe pertence a laje pelo TOPO (= cota do nivel), nao pela espessura —
senao a espessura dependeria dela mesma.

Premissa nao conferida no catalogo Watts: `Size Diameter` = Ø interno util.
"""
import math

FORA_DO_EIXO = u'Fora do eixo'
DIAMETRO = u'Diâmetro'
PASSE_SEM_TUBO = u'Passe sem tubo'
TUBO_SEM_PASSE = u'Tubo sem passe'
REGRAS = (FORA_DO_EIXO, DIAMETRO, PASSE_SEM_TUBO, TUBO_SEM_PASSE)

#: Nao e erro: lista TODOS os passes da laje, um a um, para percorrer o
#: modelo passe a passe (Thiago, 25/09/2026: "lista de todos os passes para
#: que eu possa navegar por todos os passes daquela laje"). Nasce pendente de
#: proposito: marcar resolvido vira "ja conferi este" e a barra da janela
#: mostra quanto da laje ja foi visto. Fica DESLIGADA por padrao — numa laje
#: com 400 passes sao 400 linhas.
INVENTARIO = u'Todos os passes'
#: o que o dialogo oferece; `REGRAS` continua sendo so o que acusa erro
TODAS_AS_REGRAS = REGRAS + (INVENTARIO,)

ERRO = 'erro'
ATENCAO = 'atencao'
OK = 'ok'

#: a tabela do SlabPasses (`WPS_SIZES_INCHES` / `WPS_TYPE_NAMES`)
WPS_POLEGADAS = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0,
                 12.0]
WPS_NOMES = ['WPS-1/2', 'WPS-3/4', 'WPS-1', 'WPS-1 1/2', 'WPS-2', 'WPS-3',
             'WPS-4', 'WPS-5', 'WPS-6', 'WPS-8', 'WPS-10', 'WPS-12']
#: regra do Thiago (18/09/2026): o passe de 1 a no maximo 2 tamanhos acima
PASSOS_MIN = 1
PASSOS_MAX = 2
#: o menor sleeve do mercado (Thiago, 05/10/2026): nada abaixo de WPS-1 1/2
WPS_MINIMO = 'WPS-1 1/2'
_I_MINIMO = WPS_NOMES.index(WPS_MINIMO)

PADRAO = {
    'tolerancia': 0.25,     # pol — desvio de projeto
    'raio': 12.0,           # pol — busca de tubo em volta do passe
    'espessura': 8.125,     # pol — laje, quando nada mede
    'vertical': 0.99,       # |dir.Z| minimo para tubo "vertical"
}

#: de onde veio a espessura de cada laje
ESP_PASSES = 'passes'
ESP_PISO = 'piso'
ESP_PADRAO = 'padrao'

_EPS_Z = 0.01               # pes
_TOPO = 0.1                 # pes — passe/piso "no nivel" (1,2")


# ---------------------------------------------------------------- medidas

def polegadas_texto(valor, denominador=16):
    """1.375 -> '1 3/8"'   0.03 -> '0"'   None -> ''."""
    if valor is None:
        return ''
    passos = int(round(abs(valor) * denominador))
    inteiro, fracao = divmod(passos, denominador)
    sinal = u'-' if valor < 0 and passos else u''
    if not fracao:
        return u'{}{}"'.format(sinal, inteiro)
    divisor = _mdc(fracao, denominador)
    fr = u'{}/{}'.format(fracao // divisor, denominador // divisor)
    return u'{}{}"'.format(sinal, fr) if not inteiro else \
        u'{}{} {}"'.format(sinal, inteiro, fr)


def _mdc(a, b):
    while b:
        a, b = b, a % b
    return a


def arredondar(valor, denominador=64):
    """Ruido de modelagem fora: 0,2502" contra 1/4" nao e desvio (no CIQ,
    tres passes davam 'desvio 1/4" (tolerancia 1/4")')."""
    return round(valor * denominador) / float(denominador)


def _mediana(valores):
    valores = sorted(valores)
    return valores[len(valores) // 2] if valores else None


def eh_vertical(p0, p1, minimo=PADRAO['vertical']):
    dx, dy, dz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    comprimento = math.sqrt(dx * dx + dy * dy + dz * dz)
    return comprimento > 1e-9 and abs(dz) / comprimento >= minimo


def ponto_em_z(tubo, z):
    """(x, y) do eixo do tubo na cota z; None se o tubo nao chega la."""
    p0, p1 = tubo['p0'], tubo['p1']
    if z < min(p0[2], p1[2]) - _EPS_Z or z > max(p0[2], p1[2]) + _EPS_Z:
        return None
    dz = p1[2] - p0[2]
    if abs(dz) < 1e-9:
        return None
    s = (z - p0[2]) / dz
    return (p0[0] + (p1[0] - p0[0]) * s, p0[1] + (p1[1] - p0[1]) * s)


def folga(diametro_passe, externo_tubo):
    """Quanto o eixo pode andar ate o tubo encostar no passe (pol)."""
    return (diametro_passe - externo_tubo) / 2.0


# ----------------------------------------------------------------- diametro

def indice_do_tubo(nominal_pol):
    """Posicao do tubo na tabela WPS (arredonda para cima: 1 1/4" -> 1 1/2")."""
    for i, tamanho in enumerate(WPS_POLEGADAS):
        if tamanho >= nominal_pol - 0.01:
            return i
    return len(WPS_POLEGADAS) - 1


def indice_do_passe(tipo, diametro_pol):
    """Posicao do passe na tabela: pelo nome do tipo, ou pelo Ø."""
    if tipo in WPS_NOMES:
        return WPS_NOMES.index(tipo)
    for i, tamanho in enumerate(WPS_POLEGADAS):
        if abs(tamanho - diametro_pol) < 0.01:
            return i
    return None


def tamanhos_acima(tipo, diametro_pol, nominal_pol):
    """Quantos tamanhos WPS o passe esta acima do tubo (None se nao sei)."""
    passe = indice_do_passe(tipo, diametro_pol)
    return None if passe is None else passe - indice_do_tubo(nominal_pol)


def faixa_permitida(nominal_pol):
    """Os WPS aceitos para um tubo: de PASSOS_MIN a PASSOS_MAX acima, nunca
    abaixo de WPS_MINIMO (tubo de 3/4" aceita so WPS-1 1/2)."""
    base = indice_do_tubo(nominal_pol)
    ultimo = len(WPS_NOMES) - 1
    if base + PASSOS_MIN > ultimo:
        return []
    inicio = max(base + PASSOS_MIN, _I_MINIMO)
    fim = max(min(base + PASSOS_MAX, ultimo), _I_MINIMO)
    return [WPS_NOMES[i] for i in range(inicio, fim + 1)]


# ----------------------------------------------------------------- criacao
# O SlabPasses cria o passe com a mesma regra que a verificacao cobra.

def passe_para_tubo(nominal_pol, passos=PASSOS_MIN):
    """Nome do WPS `passos` tamanhos acima do tubo (piso WPS_MINIMO, teto o
    maior WPS)."""
    i = min(indice_do_tubo(nominal_pol) + max(passos, 0), len(WPS_NOMES) - 1)
    return WPS_NOMES[max(i, _I_MINIMO)]


def chave_do_grupo(categoria, nominal_pol, valor=None):
    """(categoria, Ø em 1/16", valor do parametro) — o Ø fica numero, nunca
    texto: o SlabPasses v5.1 lia o Ø de volta do rotulo e 3/4" virava 1"."""
    return (categoria, arredondar(nominal_pol, 16), valor)


def texto_do_grupo(chave):
    categoria, nominal, valor = chave
    texto = u'[{}] {}'.format(categoria, polegadas_texto(nominal))
    return texto if valor is None else u'{} | {}'.format(texto, valor)


def ordem_do_grupo(chave):
    """Ordena por categoria, Ø numerico (2" antes de 10") e valor."""
    categoria, nominal, valor = chave
    return (categoria, nominal, valor or u'')


# ----------------------------------------------------- laje sob o passe

#: lajes "encostadas": topo de uma a ate ~5/8" do fundo da outra (pes)
CONTATO_LAJES = 0.05


def laje_no_ponto(lajes, cota, tol_topo=_TOPO, contato=CONTATO_LAJES):
    """(topo, fundo) da laje que o passe atravessa; None sem laje na cota.

    lajes: [(topo, fundo)] em pes, todas as que estao sob o XY do passe.
    - entre as de topo na cota do nivel, vale a MAIS FUNDA (duas sobrepostas);
    - desce enquanto houver outra encostada embaixo (drop panel / engrossamento
      modelado como laje separada) — o topo dela no fundo da atual.
    Thiago, 06/10/2026: no mesmo pavimento pode haver 8", 16" e 21".
    """
    no_nivel = [l for l in lajes if abs(l[0] - cota) <= tol_topo]
    if not no_nivel:
        return None
    topo = min(no_nivel, key=lambda l: abs(l[0] - cota))[0]
    fundo = min(l[1] for l in no_nivel)
    mudou = True
    while mudou:
        mudou = False
        for t, f in lajes:
            if f < fundo - 1e-9 and fundo - contato <= t <= topo + tol_topo:
                fundo = f
                mudou = True
    return topo, fundo


# ------------------------------------------------- pilha (Concrete Sleeve)
# Medido 06/10/2026 (CIQ, 12 tamanhos): altura = primeiro + (Qtt-1) * offset,
# primeiro = 8 1/8", offset = `Sleeve Offset` da familia (C - B do spec).
# Origem no TOPO; Qtt = 0 some com a geometria.

def altura_pilha(qtt, primeiro_pol, offset_pol):
    return primeiro_pol + (max(qtt, 1) - 1) * offset_pol


def qtt_para_laje(espessura_pol, primeiro_pol, offset_pol):
    """O menor Qtt cuja pilha cobre a laje (nunca menos que 1)."""
    falta = espessura_pol - primeiro_pol
    if falta <= 1e-6 or offset_pol <= 1e-6:
        return 1
    return 1 + int(math.ceil(falta / offset_pol - 1e-9))


def elevacao_pelo_fundo(fundo_pes, altura_pol, cota_nivel_pes):
    """`Elevacao do nivel` (pes) que poe o fundo da pilha no fundo da laje —
    a origem e o topo, entao o topo fica em fundo + altura."""
    return fundo_pes + altura_pol / 12.0 - cota_nivel_pes


def tem_passe_perto(ponto, existentes, tol_xy=0.1, tol_z=0.1):
    """Ja ha passe em `existentes` [(x, y, z) em pes] no mesmo eixo e cota?"""
    x, y, z = ponto
    for ex, ey, ez in existentes:
        if abs(ez - z) <= tol_z and math.hypot(ex - x, ey - y) <= tol_xy:
            return True
    return False


# -------------------------------------------------------------------- lajes

def passe_no_nivel(passe, topo):
    """O passe atravessa a laje cujo TOPO e a cota do nivel: a caixa dele
    contem essa cota.

    Ate 06/10/2026 era |zmax - topo| <= 1,2": vale para a Watts antiga (topo
    rente ao nivel), mas a pilha do Concrete Sleeve tem o fundo no fundo da
    laje e sobra 2 1/8" a 2 7/8" acima do nivel — o L2 do CIQ perdia os 121.
    """
    return passe['zmin'] - _TOPO <= topo <= passe['zmax'] + _TOPO


def espessura_por_nivel(niveis, passes, pisos=(),
                        padrao=PADRAO['espessura']):
    """{nome do nivel: (espessura em pol, de onde veio, n medidas)}.

    Ordem: a laje lida sob cada passe (`passe['laje']`, pol) -> pisos com
    topo no nivel -> altura dos passes -> geral. A altura do passe e o ultimo
    recurso: a pilha do Concrete Sleeve passa da laje (18,4" numa de 16").
    pisos: [{'topo': pes, 'espessura': pol}] dos vinculos/projeto.
    """
    # a geral (nivel sem passe e sem piso) tambem prefere a laje lida
    geral = _mediana([p['laje'] for p in passes if p.get('laje')]) or \
        _mediana([(p['zmax'] - p['zmin']) * 12.0 for p in passes
                  if p['zmax'] - p['zmin'] > 1e-6]) or padrao
    resultado = {}
    for nivel in niveis:
        daqui = [p for p in passes if passe_no_nivel(p, nivel['topo'])]
        lidas = [p['laje'] for p in daqui if p.get('laje')]
        if lidas:
            resultado[nivel['nivel']] = (_mediana(lidas), ESP_PISO,
                                         len(lidas))
            continue
        piso = _mediana([p['espessura'] for p in pisos
                         if abs(p['topo'] - nivel['topo']) <= _TOPO
                         and p.get('espessura')])
        if piso:
            resultado[nivel['nivel']] = (piso, ESP_PISO, 0)
            continue
        medida = _mediana([(p['zmax'] - p['zmin']) * 12.0 for p in daqui
                           if p['zmax'] - p['zmin'] > 1e-6])
        if medida:
            resultado[nivel['nivel']] = (medida, ESP_PASSES, len(daqui))
        else:
            resultado[nivel['nivel']] = (geral, ESP_PADRAO, 0)
    return resultado


def lajes_com_passe(passes, niveis):
    """Os nomes dos niveis que ja tem passe — o padrao da escolha."""
    return [n['nivel'] for n in niveis
            if any(passe_no_nivel(p, n['topo']) for p in passes)]


# ---------------------------------------------------------------- verificar

def _lado_passe(passe):
    return {'vinculo': '', 'categoria': passe.get('categoria', u'Passe'),
            'descricao': passe['tipo'], 'id': passe['id']}


def _lado_tubo(tubo):
    return {'vinculo': tubo.get('vinculo', ''),
            'categoria': tubo.get('categoria', u'Tubo'),
            'descricao': tubo.get('descricao') or polegadas_texto(
                tubo['nominal']), 'id': tubo['id']}


def _achado(regra, laje, a, b, medida, valor, gravidade):
    return {'regra': regra, 'nivel': laje['nivel'], 'a': a, 'b': b,
            'medida': medida, 'valor': valor, 'gravidade': gravidade}


def _plural(n, palavra):
    return u'{} {}{}'.format(n, palavra, u'' if abs(n) == 1 else u's')


def casar(passes, verticais, raio=PADRAO['raio']):
    """{id do passe: (indice do tubo em `verticais`, desvio em pol)}.

    Guloso pela menor distancia no conjunto todo: um tubo, um passe. O tubo
    e medido na meia altura do passe. Quem ficou de fora nao casou.
    """
    pares = []
    for passe in passes:
        z = (passe['zmin'] + passe['zmax']) / 2.0
        for indice, tubo in enumerate(verticais):
            ponto = ponto_em_z(tubo, z)
            if ponto is None:
                continue
            d = math.hypot(ponto[0] - passe['x'],
                           ponto[1] - passe['y']) * 12.0
            if d <= raio:
                pares.append((d, passe['id'], indice))
    pares.sort(key=lambda par: (par[0], par[1], par[2]))
    tubo_do_passe = {}
    usados = set()
    for d, pid, indice in pares:
        if pid in tubo_do_passe or indice in usados:
            continue
        tubo_do_passe[pid] = (indice, d)
        usados.add(indice)
    return tubo_do_passe


def verificar(passes, tubos, lajes, tolerancia=PADRAO['tolerancia'],
              raio=PADRAO['raio'], regras=REGRAS):
    """-> [achado]. Distancias em pol; coordenadas em pes (as da API).

    passe: {id, tipo, diametro (pol), x, y, zmin, zmax}
    tubo:  {vinculo, id, p0, p1, nominal (pol), externo (pol), descricao}
    laje:  {nivel, topo (pes), espessura (pol)} — so as ESCOLHIDAS
    regras: as que entram no relatorio (o casamento roda sempre: "tubo sem
            passe" depende dele mesmo com "fora do eixo" desligado)
    """
    regras = set(regras)
    verticais = [t for t in tubos if eh_vertical(t['p0'], t['p1'])]
    achados = []
    for laje in lajes:
        espessura_pes = laje.get('espessura', PADRAO['espessura']) / 12.0
        da_laje = [p for p in passes if passe_no_nivel(p, laje['topo'])]
        tubo_do_passe = casar(da_laje, verticais, raio)
        passe_do_tubo = dict((indice, pid) for pid, (indice, _)
                             in tubo_do_passe.items())

        for passe in da_laje:
            a = _lado_passe(passe)
            if INVENTARIO in regras:
                achados.append(_inventario(passe, verticais, tubo_do_passe,
                                           laje, a))
            if passe['id'] not in tubo_do_passe:
                if PASSE_SEM_TUBO in regras:
                    perto = _tubo_mais_perto(passe, verticais)
                    achados.append(_achado(
                        PASSE_SEM_TUBO, laje, a, None,
                        u'nenhum tubo livre a {}{}'.format(
                            polegadas_texto(raio),
                            u' — tubo mais perto a {}'.format(
                                polegadas_texto(perto)) if perto else u''),
                        perto, ERRO))
                continue
            indice, desvio = tubo_do_passe[passe['id']]
            tubo = verticais[indice]
            b = _lado_tubo(tubo)
            if FORA_DO_EIXO in regras:
                achado = _fora_do_eixo(passe, tubo, arredondar(desvio),
                                       tolerancia, laje, a, b)
                if achado:
                    achados.append(achado)
            if DIAMETRO in regras:
                achado = _diametro(passe, tubo, laje, a, b)
                if achado:
                    achados.append(achado)

        if TUBO_SEM_PASSE not in regras:
            continue
        z_meio = laje['topo'] - espessura_pes / 2.0
        vistos = []
        for indice, tubo in enumerate(verticais):
            if indice in passe_do_tubo:
                continue
            ponto = ponto_em_z(tubo, z_meio)
            if ponto is None:
                continue
            # dois trechos que se encontram na laje = um tubo so
            if any(math.hypot(ponto[0] - x, ponto[1] - y) * 12.0 < 0.1
                   for x, y in vistos):
                continue
            vistos.append(ponto)
            perto = min([math.hypot(ponto[0] - p['x'], ponto[1] - p['y'])
                         * 12.0 for p in da_laje] or [None])
            achados.append(_achado(
                TUBO_SEM_PASSE, laje, _lado_tubo(tubo), None,
                u'tubo {} atravessa a laje{}'.format(
                    polegadas_texto(tubo['nominal']),
                    u' — passe mais perto a {}'.format(polegadas_texto(perto))
                    if perto is not None and perto <= 48 else u''),
                perto, ERRO))
    return achados


def _inventario(passe, verticais, tubo_do_passe, laje, a):
    """Um item por passe da laje — a lista para percorrer no modelo.

    Nao julga nada: diz o diametro do passe e com qual tubo ele casou (ou
    que nao casou com nenhum). O que estiver errado aparece TAMBEM nas
    regras de erro, com a medida.
    """
    if passe['id'] in tubo_do_passe:
        indice, desvio = tubo_do_passe[passe['id']]
        tubo = verticais[indice]
        return _achado(
            INVENTARIO, laje, a, _lado_tubo(tubo),
            u'passe {} · tubo {} · desvio {}'.format(
                polegadas_texto(passe['diametro']),
                polegadas_texto(tubo['nominal']),
                polegadas_texto(arredondar(desvio))),
            arredondar(desvio), OK)
    return _achado(INVENTARIO, laje, a, None,
                   u'passe {} · sem tubo casado'.format(
                       polegadas_texto(passe['diametro'])),
                   None, OK)


def _fora_do_eixo(passe, tubo, desvio, tolerancia, laje, a, b):
    """Uma regra so (v1.6): a gravidade vai na medida."""
    limite = arredondar(folga(passe['diametro'], tubo['externo']))
    if desvio > limite:
        return _achado(FORA_DO_EIXO, laje, a, b,
                       u'desvio {} — encosta no passe (folga {})'.format(
                           polegadas_texto(desvio), polegadas_texto(limite)),
                       desvio, ERRO)
    if desvio > tolerancia:
        return _achado(FORA_DO_EIXO, laje, a, b,
                       u'desvio {} (tolerância {})'.format(
                           polegadas_texto(desvio),
                           polegadas_texto(tolerancia)),
                       desvio, ATENCAO)
    return None


def _diametro(passe, tubo, laje, a, b):
    """De 1 a 2 tamanhos acima (v1.6); tubo maior que o passe e erro."""
    if tubo['externo'] >= passe['diametro']:
        return _achado(DIAMETRO, laje, a, b,
                       u'tubo Ø ext {} não cabe no {}'.format(
                           polegadas_texto(tubo['externo']), passe['tipo']),
                       tubo['externo'], ERRO)
    acima = tamanhos_acima(passe['tipo'], passe['diametro'], tubo['nominal'])
    if acima is None or PASSOS_MIN <= acima <= PASSOS_MAX:
        return None
    indice = indice_do_passe(passe['tipo'], passe['diametro'])
    if WPS_NOMES[indice] in faixa_permitida(tubo['nominal']):
        return None             # acima do normal so por causa do WPS_MINIMO
    if acima < PASSOS_MIN:
        situacao = u'mesmo tamanho do tubo' if acima == 0 else \
            _plural(-acima, u'tamanho') + u' abaixo do tubo'
    else:
        situacao = _plural(acima, u'tamanho') + u' acima'
    return _achado(DIAMETRO, laje, a, b,
                   u'{} para tubo {} — {} (aceito: {})'.format(
                       passe['tipo'], polegadas_texto(tubo['nominal']),
                       situacao, u' ou '.join(faixa_permitida(
                           tubo['nominal']))),
                   acima, ERRO if acima < PASSOS_MIN else ATENCAO)


def _tubo_mais_perto(passe, verticais):
    """Distancia (pol) ao tubo mais perto na meia altura, casado ou nao."""
    z = (passe['zmin'] + passe['zmax']) / 2.0
    distancias = []
    for tubo in verticais:
        ponto = ponto_em_z(tubo, z)
        if ponto is not None:
            distancias.append(math.hypot(ponto[0] - passe['x'],
                                         ponto[1] - passe['y']) * 12.0)
    return min(distancias) if distancias else None


# --------------------------------------------------------------- relatorio

def chave_do_achado(achado):
    """Estavel entre execucoes: regra + laje + os ids (nao a medida)."""
    partes = [achado['regra'], achado['nivel'],
              u'{}#{}'.format((achado['a'].get('vinculo') or '').lower(),
                              achado['a']['id'])]
    if achado.get('b'):
        partes.append(u'{}#{}'.format(
            (achado['b'].get('vinculo') or '').lower(), achado['b']['id']))
    return u'|'.join(partes)


def montar_relatorio(achados, projeto, gerado_em, lajes, parametros):
    return {
        'fonte': 'passes',
        'versao': 2,
        'projeto': projeto,
        'gerado_em': gerado_em,
        'lajes': [l['nivel'] for l in lajes],
        'parametros': parametros,
        'achados': [dict(a, chave=chave_do_achado(a)) for a in achados],
    }


def resumo(achados):
    """[(regra, quantidade)] na ordem de REGRAS, so as que aparecem."""
    contagem = {}
    for achado in achados:
        contagem[achado['regra']] = contagem.get(achado['regra'], 0) + 1
    return [(r, contagem[r]) for r in REGRAS if r in contagem]
