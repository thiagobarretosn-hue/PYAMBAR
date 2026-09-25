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

ERRO = 'erro'
ATENCAO = 'atencao'

#: a tabela do SlabPasses (`WPS_SIZES_INCHES` / `WPS_TYPE_NAMES`)
WPS_POLEGADAS = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0,
                 12.0]
WPS_NOMES = ['WPS-1/2', 'WPS-3/4', 'WPS-1', 'WPS-1 1/2', 'WPS-2', 'WPS-3',
             'WPS-4', 'WPS-5', 'WPS-6', 'WPS-8', 'WPS-10', 'WPS-12']
#: regra do Thiago (18/09/2026): o passe de 1 a no maximo 2 tamanhos acima
PASSOS_MIN = 1
PASSOS_MAX = 2

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
    """Os WPS aceitos para um tubo: de PASSOS_MIN a PASSOS_MAX acima."""
    base = indice_do_tubo(nominal_pol)
    return [WPS_NOMES[i] for i in range(base + PASSOS_MIN,
                                        min(base + PASSOS_MAX,
                                            len(WPS_NOMES) - 1) + 1)]


# -------------------------------------------------------------------- lajes

def passe_no_nivel(passe, topo):
    """O passe pertence a laje cujo TOPO e a cota do nivel."""
    return abs(passe['zmax'] - topo) <= _TOPO


def espessura_por_nivel(niveis, passes, pisos=(),
                        padrao=PADRAO['espessura']):
    """{nome do nivel: (espessura em pol, de onde veio, n passes)}.

    pisos: [{'topo': pes, 'espessura': pol}] dos vinculos/projeto.
    """
    geral = _mediana([(p['zmax'] - p['zmin']) * 12.0 for p in passes
                      if p['zmax'] - p['zmin'] > 1e-6]) or padrao
    resultado = {}
    for nivel in niveis:
        daqui = [p for p in passes if passe_no_nivel(p, nivel['topo'])]
        medida = _mediana([(p['zmax'] - p['zmin']) * 12.0 for p in daqui
                           if p['zmax'] - p['zmin'] > 1e-6])
        if medida:
            resultado[nivel['nivel']] = (medida, ESP_PASSES, len(daqui))
            continue
        piso = _mediana([p['espessura'] for p in pisos
                         if abs(p['topo'] - nivel['topo']) <= _TOPO
                         and p.get('espessura')])
        if piso:
            resultado[nivel['nivel']] = (piso, ESP_PISO, 0)
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
        pares = []
        for passe in da_laje:
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
        passe_do_tubo = {}
        for d, pid, indice in pares:
            if pid in tubo_do_passe or indice in passe_do_tubo:
                continue
            tubo_do_passe[pid] = (indice, d)
            passe_do_tubo[indice] = pid

        for passe in da_laje:
            a = _lado_passe(passe)
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
