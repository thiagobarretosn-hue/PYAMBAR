# -*- coding: utf-8 -*-
"""Vincula varios arquivos RVT como Revit Link de uma vez, com o mesmo
posicionamento e o mesmo tipo de caminho para todo o lote."""
__title__ = "Vincular\nLinks"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "1.0"

import os
import traceback

from Autodesk.Revit.DB import (
    Transaction, TransactionGroup, FilteredElementCollector,
    RevitLinkType, RevitLinkInstance, RevitLinkOptions,
    ModelPathUtils, ImportPlacement, LinkLoadResultType,
    AttachmentType, ElementId
)
from pyrevit import revit, forms, script

doc = revit.doc
output = script.get_output()

# Create() so aceita estes dois — Centered e Site levantam ArgumentException
PLACEMENTS = {
    "Origem para Origem": ImportPlacement.Origin,
    "Coordenadas Compartilhadas": ImportPlacement.Shared,
}

PATH_TYPES = {
    "Relativo": True,
    "Absoluto": False,
}


def normalizar(caminho):
    """Caminho comparavel entre si (case e separadores)."""
    try:
        return os.path.normcase(os.path.normpath(caminho))
    except Exception:
        return (caminho or "").lower()


def links_ja_vinculados():
    """Caminhos absolutos dos links top-level do modelo (ignora nested)."""
    existentes = {}
    collector = FilteredElementCollector(doc).OfClass(RevitLinkType)
    for link_type in collector:
        try:
            if link_type.IsNestedLink:
                continue
            ref = link_type.GetExternalFileReference()
            if ref is None:
                continue
            visivel = ModelPathUtils.ConvertModelPathToUserVisiblePath(
                ref.GetAbsolutePath())
            if visivel:
                existentes[normalizar(visivel)] = os.path.basename(visivel)
        except Exception:
            continue
    return existentes


def motivo_load_result(load_result):
    """Traducao dos codigos de LinkLoadResultType que importam ao usuario."""
    mapa = {
        LinkLoadResultType.LinkNotFound: "arquivo nao encontrado",
        LinkLoadResultType.LinkNotOpenable: "arquivo nao pode ser aberto (corrompido ou em uso)",
        LinkLoadResultType.LinkOpenAsHost: "o arquivo esta aberto como modelo host",
        LinkLoadResultType.SameModelAsHost: "e o proprio modelo atual",
        LinkLoadResultType.SameCentralModelAsHost: "mesmo modelo central do host",
        LinkLoadResultType.LinkMayBeUpgraded: "precisa ser atualizado para a versao do Revit",
        LinkLoadResultType.ExternalServerMissing: "servidor externo indisponivel",
        LinkLoadResultType.LinkNotLoadedOtherError: "erro nao especificado ao carregar",
    }
    return mapa.get(load_result, str(load_result))


def vincular_um(caminho, placement, relativo):
    """Cria type + instancia de um arquivo. Levanta excecao em falha."""
    model_path = ModelPathUtils.ConvertUserVisiblePathToModelPath(caminho)
    resultado = RevitLinkType.Create(doc, model_path, RevitLinkOptions(relativo))

    if resultado.LoadResult != LinkLoadResultType.LinkLoaded:
        raise Exception(motivo_load_result(resultado.LoadResult))

    type_id = resultado.ElementId
    if type_id is None or type_id == ElementId.InvalidElementId:
        raise Exception("Revit nao devolveu um tipo de link valido")

    link_type = doc.GetElement(type_id)
    if link_type is not None:
        try:
            link_type.AttachmentType = AttachmentType.Overlay
        except Exception:
            pass  # Overlay ja e o padrao; nao vale derrubar o vinculo por isso

    instancia = RevitLinkInstance.Create(doc, type_id, placement)
    return os.path.basename(caminho), instancia.Id


def imprimir_relatorio(vinculados, pulados, falhos, placement_nome, caminho_nome):
    output.print_md("# Vincular Links — relatorio")
    output.print_md(
        "**Posicionamento:** {} &nbsp;&nbsp;|&nbsp;&nbsp; **Caminho:** {}".format(
            placement_nome, caminho_nome))

    if vinculados:
        output.print_md("## Vinculados ({})".format(len(vinculados)))
        for nome in vinculados:
            output.print_md("- {}".format(nome))

    if pulados:
        output.print_md("## Pulados ({}) — ja vinculados no modelo".format(len(pulados)))
        for nome in pulados:
            output.print_md("- {}".format(nome))

    if falhos:
        output.print_md("## Falhos ({})".format(len(falhos)))
        for nome, motivo in falhos:
            output.print_md("- **{}** — {}".format(nome, motivo))

    if not vinculados and not falhos and not pulados:
        output.print_md("Nada a fazer.")


def main():
    arquivos = forms.pick_file(
        file_ext='rvt',
        multi_file=True,
        title="Selecione os modelos para vincular (Ctrl ou Shift para varios)")

    if not arquivos:
        return
    if isinstance(arquivos, str):
        arquivos = [arquivos]

    placement_nome = forms.CommandSwitchWindow.show(
        sorted(PLACEMENTS.keys()),
        message="Posicionamento para os {} arquivos:".format(len(arquivos)))
    if not placement_nome:
        return

    caminho_nome = forms.CommandSwitchWindow.show(
        sorted(PATH_TYPES.keys()),
        message="Tipo de caminho gravado no modelo:")
    if not caminho_nome:
        return

    placement = PLACEMENTS[placement_nome]
    relativo = PATH_TYPES[caminho_nome]

    existentes = links_ja_vinculados()
    proprio = normalizar(doc.PathName) if doc.PathName else None

    vinculados, pulados, falhos = [], [], []

    grupo = TransactionGroup(doc, "Vincular Links em Lote")
    grupo.Start()
    try:
        for caminho in arquivos:
            nome_arquivo = os.path.basename(caminho)
            chave = normalizar(caminho)

            if proprio and chave == proprio:
                falhos.append((nome_arquivo, "e o proprio modelo atual"))
                continue

            if chave in existentes:
                pulados.append(nome_arquivo)
                continue

            transacao = Transaction(doc, "Vincular {}".format(nome_arquivo))
            transacao.Start()
            try:
                nome_link, _ = vincular_um(caminho, placement, relativo)
                transacao.Commit()
                existentes[chave] = nome_link
                vinculados.append(nome_link)
            except Exception as erro:
                if transacao.HasStarted():
                    transacao.RollBack()
                mensagem = str(erro)
                if "already contains a linked model" in mensagem:
                    # rede de seguranca: a checagem previa nao pegou este caso
                    pulados.append(nome_arquivo)
                    continue
                if "do not share the same coordinate system" in mensagem:
                    mensagem = ("nao compartilha coordenadas com o host — "
                                "use Origem para Origem ou publique/adquira coordenadas")
                elif not mensagem or len(mensagem) < 25:
                    # excecoes do IronPython chegam com mensagem curta e sem contexto
                    mensagem = "{}: {}".format(type(erro).__name__, mensagem)
                falhos.append((nome_arquivo, mensagem))

        if vinculados:
            grupo.Assimilate()
        else:
            grupo.RollBack()
    except Exception:
        if grupo.HasStarted():
            grupo.RollBack()
        raise

    imprimir_relatorio(vinculados, pulados, falhos, placement_nome, caminho_nome)

    if doc.IsWorkshared and vinculados:
        try:
            workset_ativo = doc.GetWorksetTable().GetWorkset(
                doc.GetWorksetTable().GetActiveWorksetId()).Name
            output.print_md(
                "\n> Modelo compartilhado: os links entraram no workset ativo "
                "**{}**.".format(workset_ativo))
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception as erro_geral:
        output.print_md("**Erro:** {}".format(str(erro_geral)))
        output.print_md("```\n{}\n```".format(traceback.format_exc()))
