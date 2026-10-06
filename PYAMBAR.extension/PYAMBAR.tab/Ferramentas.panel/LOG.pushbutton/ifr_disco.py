# -*- coding: utf-8 -*-
"""O disco da ferramenta: o HTML, o registro de status e as preferencias.

REGISTRO AO LADO DO HTML (decisao do Thiago, 16/09/2026)
--------------------------------------------------------
`<relatorio>.status.json` na mesma pasta do relatorio — no drive H: o time
inteiro ve as marcas, e o modelo nao e tocado (sem Transaction, sem dono de
elemento no central).

Duas pessoas gravando: `gravar_registro` RELE o disco, mescla item a item
(`Snippets._interferencia.mesclar`) e so entao grava — num .tmp trocado por
`File.Move(.., True)` ([[ironpython-os-replace-nao-existe]]), para ninguem
ler um JSON pela metade.

PREFERENCIAS em `%APPDATA%\\pyRevit\\PYAMBAR\\Interferencias\\config.json`
(Secao 8 do CLAUDE.md): o ultimo relatorio e o que fazer ao escolher.

v1.5: o relatorio da verificacao de passes (`<modelo> - passes.json`) mora
ao lado do .rvt, com o seu `.status.json` — igual ao HTML.
v1.7: mora em `DAT\\` (pasta do projeto) — `realocar` leva os antigos.
v3.1: REPOSITORIO — `DAT\\RELATORIOS\\<id>.json`, um arquivo por PERGUNTA
(N pessoas, N relatorios), e `status_do_projeto.json` com o status de cada
par. A regra mora em `Snippets._repositorio`; aqui so o disco.
"""
import codecs
import io
import json
import os

from System.IO import File

from Snippets import _repositorio as repo
from Snippets._interferencia import mesclar, registro_vazio

_DIR = os.path.join(os.getenv('APPDATA', ''), 'pyRevit', 'PYAMBAR',
                    'Interferencias')
_CONFIG = os.path.join(_DIR, 'config.json')


def ler_html(caminho):
    """Os bytes do relatorio — a decodificacao e do snippet."""
    with io.open(caminho, 'rb') as arquivo:
        return arquivo.read()


def caminho_do_registro(caminho_html):
    return os.path.splitext(caminho_html)[0] + '.status.json'


def _ler_json(caminho):
    if not os.path.exists(caminho):
        return None
    with codecs.open(caminho, 'r', encoding='utf-8') as arquivo:
        return json.load(arquivo)


def _gravar_json(caminho, dados):
    temporario = caminho + '.tmp'
    with codecs.open(temporario, 'w', encoding='utf-8') as arquivo:
        json.dump(dados, arquivo, indent=1, ensure_ascii=False, sort_keys=True)
    File.Move(temporario, caminho, True)


def ler_registro(caminho_html):
    """(registro, aviso). Arquivo corrompido nao impede de navegar."""
    caminho = caminho_do_registro(caminho_html)
    try:
        dados = _ler_json(caminho)
    except Exception as erro:
        return registro_vazio(), u'Não foi possível ler {} ({}). A lista foi iniciada ' \
            u'sem marcações; o arquivo só será substituído na próxima marcação.'.format(
                os.path.basename(caminho), erro)
    if not isinstance(dados, dict) or \
            not isinstance(dados.get('conflitos'), dict):
        return registro_vazio(), ''
    return dados, ''


def gravar_registro(caminho_html, registro):
    """(registro_mesclado, erro). Nao levanta: sem gravar, a lista segue util.

    Relatorio do repositorio (v3.1): a marca sobe tambem para o status do
    PROJETO — resolver aqui resolve nos outros relatorios com o mesmo par.
    """
    caminho = caminho_do_registro(caminho_html)
    try:
        try:
            disco = _ler_json(caminho)
        except Exception:
            disco = None    # corrompido: o da janela e o que vale
        junto = mesclar(disco, registro)
        _gravar_json(caminho, junto)
    except Exception as erro:
        return registro, str(erro)
    if no_repositorio(caminho_html):
        erro = gravar_status_do_projeto(os.path.dirname(caminho_html), junto)
        if erro:
            return junto, u'status do projeto: {}'.format(erro)
    return junto, None


SUFIXO_PASSES = u' - passes.json'
#: v2.4 — o clash entre vinculos mora ao lado, na mesma DAT
SUFIXO_CLASH = u' - interferencias.json'
PASTA_DAT = 'DAT'


def realocar(caminho):
    """Relatório de passes gravado ao lado do .rvt (v1.5/v1.6) -> DAT.

    Leva junto o `.status.json` (os comentários do time). Se o destino já
    existe, não sobrescreve: devolve o destino e deixa o antigo onde está.
    -> (caminho a usar, aviso ou '').
    """
    if not caminho or not caminho.endswith(SUFIXO_PASSES):
        return caminho, ''
    pasta = os.path.dirname(caminho)
    if os.path.basename(pasta).upper() == PASTA_DAT:
        return caminho, ''
    destino = os.path.join(pasta, PASTA_DAT, os.path.basename(caminho))
    if os.path.exists(destino) or not os.path.exists(caminho):
        return (destino if os.path.exists(destino) else caminho), ''
    try:
        if not os.path.isdir(os.path.dirname(destino)):
            os.makedirs(os.path.dirname(destino))
        File.Move(caminho, destino)
        status = caminho_do_registro(caminho)
        if os.path.exists(status):
            File.Move(status, caminho_do_registro(destino))
        return destino, u'relatório e status movidos para {}'.format(
            os.path.dirname(destino))
    except Exception as erro:
        return caminho, u'não foi possível mover para DAT ({}); o arquivo ' \
            u'permanece no local original'.format(erro)


def gravar_relatorio(caminho, dados):
    """Grava o relatorio de uma verificacao propria. Levanta: sem o arquivo
    a janela nao tem o que abrir, e quem chama avisa."""
    pasta = os.path.dirname(caminho)
    if pasta and not os.path.exists(pasta):
        os.makedirs(pasta)
    _gravar_json(caminho, dados)


def preferencias():
    try:
        dados = _ler_json(_CONFIG)
    except Exception:
        dados = None
    return dados if isinstance(dados, dict) else {}


def gravar_preferencias(dados):
    try:
        if not os.path.exists(_DIR):
            os.makedirs(_DIR)
        _gravar_json(_CONFIG, dados)
        return None
    except Exception as erro:
        return str(erro)


# ------------------------------------------------------ repositorio (v3.1)

def pasta_repositorio(caminho_do_modelo):
    """`<pasta do central>/DAT/RELATORIOS` — a mesma DAT do LOG."""
    pasta = os.path.dirname(caminho_do_modelo or '')
    if not pasta or not os.path.isdir(pasta):
        return os.path.join(_DIR, repo.PASTA)
    return os.path.join(pasta, PASTA_DAT, repo.PASTA)


def no_repositorio(caminho):
    return os.path.basename(os.path.dirname(caminho or '')).upper() == \
        repo.PASTA


def caminho_no_repositorio(pasta, id_do_relatorio):
    return os.path.join(pasta, id_do_relatorio + '.json')


def _e_relatorio(nome):
    baixo = nome.lower()
    return baixo.endswith('.json') and not baixo.endswith('.status.json') \
        and baixo != repo.STATUS_DO_PROJETO


#: caminho -> (data do arquivo, meta): o dropdown nao rele 20 relatorios
#: inteiros a cada troca de aba
_METAS = {}


def listar(pasta):
    """(metas do mais novo ao mais velho, avisos). Arquivo ruim vira aviso."""
    metas, avisos = [], []
    if not os.path.isdir(pasta):
        return metas, avisos
    for nome in os.listdir(pasta):
        if not _e_relatorio(nome):
            continue
        caminho = os.path.join(pasta, nome)
        try:
            data = os.path.getmtime(caminho)
            guardado = _METAS.get(caminho)
            if guardado is None or guardado[0] != data:
                dados = _ler_json(caminho)
                if not isinstance(dados, dict) or \
                        dados.get('fonte') not in repo.FONTES:
                    avisos.append(u'{} (não é relatório)'.format(nome))
                    continue
                guardado = (data, repo.meta(dados, caminho))
                _METAS[caminho] = guardado
            metas.append(dict(guardado[1]))
        except Exception as erro:
            avisos.append(u'{} ({})'.format(nome, erro))
    return repo.nomes_unicos(repo.ordenar(metas)), avisos


def _ler_ou_nada(caminho):
    try:
        return _ler_json(caminho)
    except Exception as erro:
        print(u'Relatórios: {} ilegível ({})'.format(caminho, erro))
        return None


def gravar_no_repositorio(pasta, relatorio, autor, autor_id, agora):
    """Uma rodada de uma pergunta. -> (caminho, ja_existia). Levanta.

    A mesma pergunta (tipo + escopo) cai no mesmo arquivo, por quem for:
    `registrar_execucao` guarda quem criou e o historico das rodadas.
    """
    fonte = relatorio['fonte']
    escopo = relatorio.get('escopo') or repo.escopo_de_relatorio(relatorio)
    id_rel = repo.id_do_relatorio(fonte, escopo)
    caminho = caminho_no_repositorio(pasta, id_rel)
    anterior = _ler_ou_nada(caminho) if os.path.exists(caminho) else None
    novo = repo.registrar_execucao(anterior, relatorio, autor, autor_id,
                                   agora)
    novo['id'] = id_rel
    novo['escopo'] = escopo
    novo['titulo'] = repo.titulo(fonte, escopo)
    gravar_relatorio(caminho, novo)
    return caminho, anterior is not None


def importar_html(pasta, caminho_html, lido, projeto, autor, autor_id, agora):
    """O HTML do Revit entra no repositorio. -> (caminho, importou_agora).

    Reimporta so quando o HTML mudou (exportado de novo). Na primeira vez o
    `.status.json` antigo, ao lado do HTML, vem junto com as chaves refeitas.
    """
    relatorio = repo.html_para_relatorio(lido, os.path.basename(caminho_html),
                                         projeto)
    relatorio['parametros']['caminho_html'] = caminho_html
    relatorio['html_modificado_em'] = str(os.path.getmtime(caminho_html))
    destino = caminho_no_repositorio(pasta, relatorio['id'])
    anterior = _ler_ou_nada(destino) if os.path.exists(destino) else None
    if anterior and anterior.get('html_modificado_em') == \
            relatorio['html_modificado_em']:
        return destino, False
    if anterior is None and os.path.exists(caminho_do_registro(caminho_html)):
        antigo, _ = ler_registro(caminho_html)
        if antigo.get('conflitos'):
            gravar_registro(destino,
                            repo.registro_com_projeto(antigo, projeto))
    novo = repo.registrar_execucao(anterior, relatorio, autor, autor_id,
                                   agora)
    gravar_relatorio(destino, novo)
    return destino, True


def migrar_antigos(pasta):
    """`DAT/<modelo> - interferencias.json` e `- passes.json` -> repositorio.

    Os originais FICAM (a v2.x distribuida ainda os le e escreve). Migra de
    novo so o que a v2.x reescreveu depois — e so enquanto ninguem rodou a
    mesma pergunta na v3 (`migrado_de` some na primeira rodada nova).
    -> (quantos, avisos)
    """
    dat = os.path.dirname(pasta)
    if not os.path.isdir(dat):
        return 0, []
    quantos, avisos = 0, []
    for nome in os.listdir(dat):
        if repo.relatorio_antigo(nome) is None:
            continue
        origem = os.path.join(dat, nome)
        try:
            dados = _ler_json(origem)
            if not isinstance(dados, dict) or \
                    dados.get('fonte') not in ('clash', 'passes'):
                continue
            novo = repo.migrar(dados)
            destino = caminho_no_repositorio(pasta, novo['id'])
            if os.path.exists(destino):
                atual = _ler_json(destino) or {}
                if atual.get('migrado_de') != nome or \
                        os.path.getmtime(origem) <= os.path.getmtime(destino):
                    continue
            novo['migrado_de'] = nome
            gravar_relatorio(destino, novo)
            if os.path.exists(caminho_do_registro(origem)):
                registro, _ = ler_registro(origem)
                gravar_registro(destino, registro)
            quantos += 1
        except Exception as erro:
            avisos.append(u'{} ({})'.format(nome, erro))
    return quantos, avisos


def caminho_do_antigo(pasta, caminho_antigo):
    """Onde um relatorio da v2 mora no repositorio ('' se nao der para ler).

    O apontamento da v3.0 guardou o nome antigo como origem.
    """
    dados = _ler_ou_nada(caminho_antigo)
    if not isinstance(dados, dict):
        return ''
    return caminho_no_repositorio(pasta, repo.migrar(dados)['id'])


def caminho_do_status_do_projeto(pasta):
    return os.path.join(pasta, repo.STATUS_DO_PROJETO)


def ler_status_do_projeto(pasta):
    dados = _ler_ou_nada(caminho_do_status_do_projeto(pasta))
    return dados if isinstance(dados, dict) else repo.status_vazio()


def gravar_status_do_projeto(pasta, registro, chaves=None):
    """Rele, sobe as marcas mais novas e grava. -> erro ou None."""
    try:
        disco = ler_status_do_projeto(pasta)
        if not repo.empurrar_status(disco, registro, chaves):
            return None
        _gravar_json(caminho_do_status_do_projeto(pasta), disco)
        return None
    except Exception as erro:
        return str(erro)
