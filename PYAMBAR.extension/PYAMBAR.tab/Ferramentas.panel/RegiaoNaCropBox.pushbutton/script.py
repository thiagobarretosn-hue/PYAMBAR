# -*- coding: utf-8 -*-
"""
Região na Crop Box v3.1
Cria região preenchida com tamanho exato da Crop Box em múltiplas vistas

Autor: Thiago Barreto Sobral Nunes
Versão: 3.1
Data: 2026-01-19

CHANGELOG:
v3.1 - Padronizacao: usar revit.doc/uidoc em vez de __revit__

DESCRIÇÃO:
Cria automaticamente uma FilledRegion (região preenchida) que preenche
exatamente o contorno da Crop Box em uma ou várias vistas selecionadas.
Detecta automaticamente se a Crop Box foi modificada manualmente e usa a forma customizada.

WORKFLOW:
1. Execute o comando
2. Selecione uma ou mais vistas para aplicar
3. Selecione o tipo de preenchimento desejado
4. Regiões são criadas automaticamente
5. Veja relatório detalhado no console

FUNCIONALIDADES v3.0:
- [NOVO] Seleção de múltiplas vistas
- [NOVO] Região criada individualmente por vista (não aparece em dependentes)
- [NOVO] Não exige Crop Box ativa (cria mesmo se estiver oculta)
- Detecção inteligente de Crop Box:
  • Forma customizada (se foi modificada manualmente)
  • Forma retangular padrão (se não modificada)
- Seleção de tipo de FilledRegion
- Validação de vista e Crop Box
- Relatório detalhado no console

APLICAÇÕES:
- Criar máscara de fundo em múltiplas vistas simultaneamente
- Delimitar área de trabalho visualmente
- Preparar vistas para impressão
- Criar molduras e bordas
- Destacar área da Crop Box
- Trabalhar com vistas dependentes sem interferência
"""

__title__ = "Região na\nCrop Box"
__author__ = "Thiago Barreto Sobral Nunes"
__version__ = "3.3"
# __persistentengine__ removido - usa pyrevit forms (modal)

# ============================================================================
# IMPORTAÇÕES
# ============================================================================

from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.DB import *
from pyrevit import revit, forms, script
from System.Collections.Generic import List

# ============================================================================
# VARIÁVEIS GLOBAIS
# ============================================================================

doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()

# ============================================================================
# FUNÇÕES AUXILIARES - CROP BOX
# ============================================================================

def get_crop_region_curves(view):
    """
    Obtém contorno da região de corte da vista.

    Args:
        view (View): Vista do Revit

    Returns:
        List[CurveLoop]: Lista de contornos da crop region ou None

    Note:
        Tenta duas abordagens:
        1. GetCropRegionShapeManager() - forma customizada exata
        2. CropBox - retângulo padrão (fallback)
    """
    try:
        # ABORDAGEM 1: Forma customizada (se foi modificada)
        shape_manager = view.GetCropRegionShapeManager()

        if shape_manager and shape_manager.CanHaveShape:
            crop_curves = shape_manager.GetCropShape()

            if crop_curves and crop_curves.Count > 0:
                output.print_md("✅ Forma customizada da Crop Region detectada")
                return crop_curves

    except Exception as e:
        output.print_md("⚠️ Forma customizada não disponível: {}".format(str(e)))

    # ABORDAGEM 2: FALLBACK - Retângulo padrão
    try:
        crop_box = view.CropBox

        if not crop_box:
            return None

        # Extrair coordenadas min/max
        min_pt = crop_box.Min
        max_pt = crop_box.Max

        # Criar 4 pontos do retângulo (Z=0 para vista 2D)
        p0 = XYZ(min_pt.X, min_pt.Y, 0)
        p1 = XYZ(max_pt.X, min_pt.Y, 0)
        p2 = XYZ(max_pt.X, max_pt.Y, 0)
        p3 = XYZ(min_pt.X, max_pt.Y, 0)

        # Criar CurveLoop retangular
        curve_loop = CurveLoop()
        curve_loop.Append(Line.CreateBound(p0, p1))
        curve_loop.Append(Line.CreateBound(p1, p2))
        curve_loop.Append(Line.CreateBound(p2, p3))
        curve_loop.Append(Line.CreateBound(p3, p0))

        # Adicionar à lista .NET
        list_boundary = List[CurveLoop]()
        list_boundary.Add(curve_loop)

        output.print_md("✅ Crop Box retangular padrão obtida")
        return list_boundary

    except Exception as e:
        output.print_md("❌ Erro ao obter CropBox: {}".format(str(e)))
        return None

# ============================================================================
# FUNÇÕES AUXILIARES - VIEW SELECTION
# ============================================================================

def collect_valid_views():
    """
    Coleta vistas válidas que podem ter FilledRegion.

    Returns:
        dict: {nome_vista: View} - Dicionário de vistas válidas

    Note:
        Filtra apenas vistas que suportam anotações 2D:
        - FloorPlan, CeilingPlan, EngineeringPlan
        - Section, Elevation
        - AreaPlan, DetailView
    """
    valid_view_types = [
        ViewType.FloorPlan,
        ViewType.CeilingPlan,
        ViewType.EngineeringPlan,
        ViewType.Section,
        ViewType.Elevation,
        ViewType.AreaPlan,
        ViewType.Detail
    ]

    all_views = FilteredElementCollector(doc)\
        .OfClass(View)\
        .ToElements()

    views_dict = {}

    for view in all_views:
        # Filtrar por tipo válido
        if view.ViewType not in valid_view_types:
            continue

        # Ignorar templates
        if view.IsTemplate:
            continue

        # Verificar se tem CropBox válida
        try:
            if not view.CropBox:
                continue
        except Exception as e:
            continue

        # Adicionar ao dicionário
        view_name = view.Name
        views_dict[view_name] = view

    return views_dict

# ============================================================================
# FUNÇÕES AUXILIARES - FILLED REGION
# ============================================================================

def collect_filled_region_types():
    """
    Coleta tipos de FilledRegion disponíveis no documento.

    Returns:
        dict: {nome: FilledRegionType} - Dicionário de tipos

    Note:
        Ordena os tipos alfabeticamente para exibição
    """
    all_types = FilteredElementCollector(doc)\
        .OfClass(FilledRegionType)\
        .ToElements()

    types_dict = {}

    for fr_type in all_types:
        # Obter nome do tipo
        type_name = fr_type.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)

        if type_name and type_name.HasValue:
            name = type_name.AsString()
            types_dict[name] = fr_type

    return types_dict


def create_filled_region_from_curves(view, curves, filled_type_id):
    """
    Cria FilledRegion a partir de CurveLoops.

    Args:
        view (View): Vista onde criar a região
        curves (List[CurveLoop]): Contornos da região
        filled_type_id (ElementId): ID do tipo de FilledRegion

    Returns:
        FilledRegion: Região preenchida criada

    Note:
        Usa FilledRegion.Create() da API do Revit
    """
    filled_region = FilledRegion.Create(doc, filled_type_id, view.Id, curves)
    return filled_region

# ============================================================================
# EXECUÇÃO PRINCIPAL
# ============================================================================

def main():
    try:
        """
        Função principal de execução do script.

        Workflow:
            1. Coleta vistas válidas do projeto
            2. Usuário seleciona múltiplas vistas
            3. Coleta tipos de FilledRegion
            4. Usuário seleciona tipo
            5. Cria região em cada vista selecionada
            6. Exibe relatório consolidado
        """
        output.print_md("# Região na Crop Box v3.0")
        output.print_md("---")

        # ETAPA 1: Coletar vistas válidas
        output.print_md("## Coletando vistas disponíveis...")

        available_views = collect_valid_views()

        if not available_views:
            forms.alert(
                "Nenhuma vista válida encontrada no projeto.\n\n"
                "Verifique se há plantas, cortes ou elevações disponíveis.",
                title="Sem Vistas Disponíveis",
                warn_icon=True,
                exitscript=True
            )

        output.print_md("- **Vistas disponíveis:** {}".format(len(available_views)))

        # ETAPA 2: Usuário seleciona vistas
        output.print_md("\n## Selecione as vistas...")

        selected_view_names = forms.SelectFromList.show(
            sorted(available_views.keys()),
            title="Selecione as Vistas para Aplicar a Região",
            button_name="Continuar",
            multiselect=True
        )

        if not selected_view_names:
            forms.alert("Seleção cancelada.", exitscript=True)

        selected_views = [available_views[name] for name in selected_view_names]

        output.print_md("- **Vistas selecionadas:** {}".format(len(selected_views)))
        for view_name in selected_view_names:
            output.print_md("  - {}".format(view_name))

        # ETAPA 3: Coletar tipos de FilledRegion
        output.print_md("\n## Coletando tipos de região preenchida...")

        filled_types = collect_filled_region_types()

        if not filled_types:
            forms.alert(
                "Nenhum tipo de FilledRegion encontrado no documento.\n\n"
                "Verifique se há tipos de região preenchida carregados.",
                title="Sem Tipos Disponíveis",
                warn_icon=True,
                exitscript=True
            )

        output.print_md("- **Tipos disponíveis:** {}".format(len(filled_types)))

        # ETAPA 4: Usuário seleciona tipo
        output.print_md("\n## Selecione o tipo de preenchimento...")

        selected_type_name = forms.SelectFromList.show(
            sorted(filled_types.keys()),
            title="Escolha o Tipo de Região Preenchida",
            button_name="Criar Regiões",
            multiselect=False
        )

        if not selected_type_name:
            forms.alert("Seleção cancelada.", exitscript=True)

        selected_type = filled_types[selected_type_name]

        output.print_md("- **Tipo selecionado:** {}".format(selected_type_name))

        # ETAPA 5: Criar FilledRegion em cada vista
        output.print_md("\n## Criando regiões preenchidas...")

        # Contadores de resultado
        success_count = 0
        failed_views = []

        # Dicionário para armazenar: {view_id: filled_region_id}
        view_regions = {}

        # Iniciar transação única
        t = Transaction(doc, "Criar Regiões na Crop Box ({} vistas)".format(len(selected_views)))
        t.Start()

        try:
            # PASSO 1: Criar todas as FilledRegions
            for view in selected_views:
                try:
                    # Obter contorno da Crop Box
                    crop_curves = get_crop_region_curves(view)

                    if not crop_curves or crop_curves.Count == 0:
                        failed_views.append((view.Name, "Crop Box não encontrada"))
                        continue

                    # Criar FilledRegion
                    filled_region = create_filled_region_from_curves(
                        view,
                        crop_curves,
                        selected_type.Id
                    )

                    if filled_region:
                        view_regions[view.Id] = filled_region.Id
                        success_count += 1
                        output.print_md("- ✅ **{}** (ID: {})".format(view.Name, filled_region.Id))
                    else:
                        failed_views.append((view.Name, "FilledRegion não foi criada"))
                        output.print_md("- ❌ **{}**: FilledRegion não foi criada".format(view.Name))

                except Exception as e:
                    failed_views.append((view.Name, str(e)))
                    output.print_md("- ❌ **{}**: {}".format(view.Name, str(e)))

            # PASSO 2: Ocultar cada região nas outras vistas
            output.print_md("\n## Configurando visibilidade (ocultar em vistas dependentes)...")

            for view in selected_views:
                if view.Id not in view_regions:
                    continue

                # Para cada vista, ocultar todas as regiões EXCETO a dela própria
                regions_to_hide = []
                for other_view_id, region_id in view_regions.items():
                    if other_view_id != view.Id:
                        regions_to_hide.append(region_id)

                # Ocultar as regiões das outras vistas nesta vista
                if regions_to_hide:
                    try:
                        view.HideElements(List[ElementId](regions_to_hide))
                        output.print_md("- 🔒 **{}**: {} regiões ocultadas".format(
                            view.Name, len(regions_to_hide)))
                    except Exception as e:
                        output.print_md("- ⚠️ **{}**: Erro ao ocultar regiões - {}".format(
                            view.Name, str(e)))

            t.Commit()

            # Relatório final
            output.print_md("\n---")
            output.print_md("## 📊 RELATÓRIO FINAL")
            output.print_md("---")
            output.print_md("**Vistas processadas:** {}".format(len(selected_views)))
            output.print_md("**Sucessos:** {}".format(success_count))
            output.print_md("**Falhas:** {}".format(len(failed_views)))
            output.print_md("**Tipo aplicado:** {}".format(selected_type_name))
            output.print_md("---")

            # Detalhes das falhas (se houver)
            if failed_views:
                output.print_md("\n### ⚠️ Vistas com Falha:")
                for view_name, error in failed_views:
                    output.print_md("- **{}**: {}".format(view_name, error))

            # Alert final
            if success_count == len(selected_views):
                forms.alert(
                    "✅ Regiões criadas com sucesso em todas as {} vistas!\n\n"
                    "Tipo: {}".format(
                        success_count,
                        selected_type_name
                    ),
                    title="Sucesso Total"
                )
            elif success_count > 0:
                forms.alert(
                    "⚠️ Regiões criadas parcialmente:\n\n"
                    "Sucessos: {}\n"
                    "Falhas: {}\n\n"
                    "Tipo: {}\n\n"
                    "Veja o console para detalhes das falhas.".format(
                        success_count,
                        len(failed_views),
                        selected_type_name
                    ),
                    title="Sucesso Parcial",
                    warn_icon=True
                )
            else:
                forms.alert(
                    "❌ Não foi possível criar regiões em nenhuma vista.\n\n"
                    "Veja o console para detalhes dos erros.",
                    title="Erro",
                    warn_icon=True
                )

        except Exception as e:
            t.RollBack()

            output.print_md("\n---")
            output.print_md("## ❌ ERRO CRÍTICO")
            output.print_md("---")
            output.print_md("**Erro durante processamento:** {}".format(str(e)))

            import traceback
            output.print_md("\n**Traceback:**")
            output.print_md("```\n{}\n```".format(traceback.format_exc()))

            forms.alert(
                "Erro crítico durante processamento:\n\n{}".format(str(e)),
                title="Erro",
                warn_icon=True
            )
    except OperationCanceledException:
        return
    except Exception as e:
        output.print_md("**Erro:** {}".format(str(e)))
        output.print_md("```\n{}\n```".format(traceback.format_exc()))
# ============================================================================
# PONTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    main()
