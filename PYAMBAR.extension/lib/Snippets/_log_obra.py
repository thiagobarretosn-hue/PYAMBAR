# -*- coding: utf-8 -*-
"""O LOG aberto em OUTRA obra: de onde abrir o modelo do apontamento.

O PEDIDO (Thiago, 06/10/2026)
-----------------------------
> "eu estou na bancada sanitaria e recebi uma notificacao em outro projeto.
>  Quando eu clico na notificacao, ele abre o log daquela obra. Mas eu nao
>  estou com aquela obra aberta... preciso de um botao de abrir o modelo"

ONDE ESTAO OS MODELOS
--------------------
Todos os modelos da obra moram no mesmo `03-MODELING`, a pasta-mae da DAT:

    <obra>/03-MODELING/<modelo>.rvt
    <obra>/03-MODELING/DAT/LOG/<apontamento>.json

O apontamento diz em que modelo foi feito (`modelo`) e de que arquivos sao
os elementos (`alvos[].arquivo`) — sao esses que se oferece abrir.

MODELO WORKSHARED: NUNCA ABRIR O CENTRAL
---------------------------------------
Abre-se a copia local, como o Revit faz com "Criar novo local":
`Documentos/<modelo>_<usuario do Revit>.rvt`. As obras de hoje (IQ LUX) nao
sao workshared — abrem direto.

Puro: sem `clr`, sem Revit — testado em `dev-tools/tests/test_log_obra.py`.
"""
import os


def pasta_dos_modelos(pasta_log):
    """`<obra>/03-MODELING` a partir de `<obra>/03-MODELING/DAT/LOG`."""
    pasta = (pasta_log or '').rstrip('/\\')
    return os.path.dirname(os.path.dirname(pasta)) if pasta else ''


def modelos_do_apontamento(item):
    """Os .rvt citados pelo apontamento, sem repetir: o modelo onde foi
    feito primeiro, depois os dos elementos, na ordem em que aparecem."""
    nomes = [item.get('modelo') or '']
    nomes += [alvo.get('arquivo') or '' for alvo in item.get('alvos') or []]
    saida = []
    for nome in nomes:
        nome = os.path.basename((nome or '').strip())
        if nome.lower().endswith('.rvt') and \
                nome.lower() not in [n.lower() for n in saida]:
            saida.append(nome)
    return saida


def caminhos_existentes(pasta_log, nomes, existe=os.path.exists):
    """[(nome, caminho)] dos modelos que estao de fato na pasta da obra."""
    pasta = pasta_dos_modelos(pasta_log)
    if not pasta:
        return []
    saida = []
    for nome in nomes:
        caminho = os.path.join(pasta, nome)
        if existe(caminho):
            saida.append((nome, caminho))
    return saida


def nome_da_copia_local(caminho_central, usuario):
    """'CIQ-PLB-DRAINAGE.rvt' + 'thiago.nunes' -> 'CIQ-PLB-DRAINAGE_thiago.nunes.rvt'
    (a convencao do Revit para a copia local)."""
    base = os.path.splitext(os.path.basename(caminho_central or ''))[0]
    return u'{}_{}.rvt'.format(base, (usuario or u'usuario').strip())
