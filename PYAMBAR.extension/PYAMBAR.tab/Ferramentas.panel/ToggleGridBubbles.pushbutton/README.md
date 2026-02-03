# Toggle Grid Bubbles - PYAMBAR(lab)

## Descrição

Ferramenta para alternar a visibilidade de bolhas (bubbles) de grids por direção na vista ativa.

**Adaptado do pyRevit** para a extensão PYAMBAR(lab).

## Autor Original
- **Mohamed Asli** (pyRevit)

## Adaptação
- **Thiago Barreto Sobral Nunes** (PYAMBAR(lab))

## Funcionalidades

- ✅ **[NOVO] Aplicar em múltiplas vistas simultaneamente**
- ✅ Alternar bolhas de grid por direção (Top, Bottom, Left, Right)
- ✅ Funciona com seleção prévia de grids ou todos os grids da vista
- ✅ Suporte a múltiplos sistemas de coordenadas:
  - **All Grids**: Todos os grids sem filtro de orientação
  - **True North**: Orientação pelo norte verdadeiro
  - **Project North**: Orientação pelo norte do projeto
  - **View/Scope Box Orientation**: Orientação pela vista ou scope box
- ✅ Tolerância angular configurável (1° a 40°)
- ✅ Compatível com:
  - Floor Plans
  - Ceiling Plans
  - Engineering Plans
  - Elevations
  - Sections
- ✅ Relatório detalhado de sucessos/falhas

## Estrutura de Arquivos

```
ToggleGridBubbles.pushbutton/
├── script.py                      # Script principal
├── coordinate_selector.py         # Seletor de sistema de coordenadas
├── ui.xaml                        # Interface principal
├── coordinate_selector_ui.xaml    # Interface de seleção de coordenadas
├── bundle.yaml                    # Configuração do botão
├── icon.png                       # Ícone do botão
└── README.md                      # Esta documentação
```

## Como Usar

### Modo Vista Única

1. **Abra uma vista válida** (planta, elevação, corte ou teto)
2. **(Opcional)** Selecione grids específicos para processar apenas eles
3. **Execute o comando** "Toggle Grid Bubbles"
4. **Escolha "Vista Ativa Apenas"** no diálogo inicial
5. **Configure o sistema de coordenadas** e tolerância angular
6. **Use os controles**:
   - **Show All / Hide All**: Mostrar/ocultar todas as bolhas
   - **Top / Bottom / Left / Right**: Alternar bolhas por direção
7. **Clique em OK** para aplicar as mudanças

### Modo Múltiplas Vistas (NOVO!)

1. **Abra uma vista válida** (planta, elevação, corte ou teto)
2. **Execute o comando** "Toggle Grid Bubbles"
3. **Escolha "Múltiplas Vistas"** no diálogo inicial
4. **Selecione as vistas** onde deseja aplicar as mudanças (multiselect)
5. **Configure o sistema de coordenadas** e tolerância angular
6. **Use os controles na primeira vista**:
   - **Show All / Hide All**: Mostrar/ocultar todas as bolhas
   - **Top / Bottom / Left / Right**: Alternar bolhas por direção
7. **Clique em OK** para aplicar
8. **As mesmas configurações serão aplicadas automaticamente** em todas as vistas selecionadas
9. **Veja o relatório** de sucessos e falhas

## Dependências

### Bibliotecas Python
- `math` - Cálculos trigonométricos
- `clr` - Common Language Runtime

### pyRevit
- `pyrevit.HOST_APP` - Acesso ao documento ativo
- `pyrevit.DB` - API do Revit
- `pyrevit.script` - Utilitários de script
- `pyrevit.forms` - Formulários WPF
- `pyrevit.revit.db.transaction` - Gerenciamento de transações
- `pyrevit.compat` - Compatibilidade entre versões

### Arquivos Auxiliares
- `coordinate_selector.py` - Módulo de seleção de coordenadas
- `ui.xaml` - Interface XAML principal
- `coordinate_selector_ui.xaml` - Interface XAML de configuração

## Sistemas de Coordenadas

### All Grids
Processa todos os grids sem filtro de orientação. Ideal para mostrar/ocultar todas as bolhas rapidamente.

### True North
Usa a orientação do norte verdadeiro do projeto. Útil quando o projeto está rotacionado em relação ao norte verdadeiro.

### Project North
Usa o sistema de coordenadas do projeto (aplica o "Angle to True North"). Padrão para a maioria dos projetos.

### View/Scope Box Orientation
Usa a orientação da vista ativa ou scope box. Ideal para vistas rotacionadas ou scope boxes customizados.

## Tolerância Angular

Controla quão próximo os grids devem estar alinhados com o sistema de coordenadas escolhido:

- **1°**: Muito rigoroso - apenas grids perfeitamente alinhados
- **5°**: Rígido - bom para layouts de grid precisos
- **10°**: Moderado - bom para a maioria dos casos
- **15°**: Relaxado - inclui grids levemente angulados
- **25°**: Permissivo - inclui mais grids angulados
- **35°**: Muito permissivo - inclui maioria das orientações
- **40°**: Tolerância máxima - inclui grids fortemente angulados

## Classes Principais

### GridsCollector
Coleta e filtra grids da vista ativa ou seleção.

**Métodos:**
- `check_validity()` - Valida se há grids válidos
- `get_grid_chain_count()` - Conta grids multi-segmento
- `get_status_text()` - Retorna texto de status

### CustomGrids
Gerencia grids e suas bolhas com base no sistema de coordenadas.

**Métodos:**
- `get_vertical_grids()` - Retorna grids verticais
- `get_horizontal_grids()` - Retorna grids horizontais
- `toggle_bubbles_by_direction()` - Alterna bolhas por direção
- `show_all_bubbles()` - Mostra todas as bolhas
- `hide_all_bubbles()` - Oculta todas as bolhas

### ToggleGridWindow
Interface WPF para controle das bolhas.

**Métodos:**
- `update_checkboxes()` - Atualiza estado dos checkboxes
- `toggle_bubbles()` - Alterna bolhas baseado em checkbox
- `go_back()` - Volta para seleção de coordenadas
- `confirm()` - Confirma e aplica mudanças

## Requisitos

- **Revit**: 2016 ou superior
- **pyRevit**: Qualquer versão compatível
- **Vista Ativa**: Floor Plan, Ceiling Plan, Engineering Plan, Elevation ou Section

## Notas Técnicas

1. **Grids Curvos**: Não são suportados pela ferramenta
2. **Grids Segmentados**: Multi-segment grids não são processados
3. **Grids Ocultos**: Não são incluídos no processamento
4. **Transações**: Usa TransactionGroup para permitir rollback completo
5. **Seleção Visual**: Grids ativos são destacados durante a operação

## Modificações Realizadas - PYAMBAR(lab)

### v2.0 - Suporte a Múltiplas Vistas (2025-12-30)

**Funcionalidades Adicionadas:**

1. **Modo de Operação Dual**
   - Vista Ativa Apenas (comportamento original)
   - Múltiplas Vistas (novo)

2. **Seleção de Múltiplas Vistas**
   - Interface de seleção com multiselect
   - Filtra apenas vistas válidas (Floor Plans, Ceiling Plans, etc.)
   - Ignora templates automaticamente

3. **Aplicação em Lote**
   - Configuração interativa na primeira vista
   - Aplicação automática nas demais vistas selecionadas
   - Mantém as mesmas configurações de direção (Top/Bottom/Left/Right)

4. **Relatório Detalhado**
   - Contagem de sucessos e falhas
   - Lista de vistas com erro
   - Mensagem de erro específica por vista

**Funções Adicionadas:**
- `collect_valid_views()` - Coleta vistas válidas do projeto
- `apply_grid_changes_to_views()` - Aplica mudanças em múltiplas vistas

**Modificações no Código:**
- [script.py:923-949](script.py) - Função `collect_valid_views()`
- [script.py:952-987](script.py) - Função `apply_grid_changes_to_views()`
- [script.py:990-1103](script.py) - Modificação da função `main()` com seleção de modo
- [script.py:1121-1157](script.py) - Aplicação em múltiplas vistas após confirmação

---

**Data de Adaptação**: 2025-12-23
**Última Modificação**: 2025-12-30
**Versão**: 2.0 (Múltiplas Vistas - PYAMBAR(lab))
