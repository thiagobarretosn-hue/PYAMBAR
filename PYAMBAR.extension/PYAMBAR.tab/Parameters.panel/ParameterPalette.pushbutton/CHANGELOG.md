# ParameterPalette - CHANGELOG

## v5.1.0 (2026-04-13) - Clone de Link + Singleton

### ✨ Novidades
- **Clone de Revit Link**: ativar Clone e selecionar um elemento de link detecta automaticamente e abre o picker para capturar os parâmetros do elemento dentro do link
- **Singleton**: clicar no botão com a paleta já aberta traz a janela para frente em vez de abrir uma segunda instância

### 🔧 Correções
- `PickLinkElementHandler`: novo External Event que oculta a paleta, executa `PickObject(ObjectType.LinkedElement)` e restaura a janela após a seleção
- Singleton via `sys.modules` garante persistência entre re-execuções do script (pattern mais robusto que `try/except NameError`)
- `on_closing` limpa a referência do singleton para permitir reabertura normal após fechar

---

## v3.0 (2025-11-29) - ITERATION 2 Refactoring

### ✨ Refatoração Completa
- Substituídas 5 classes/funções por snippets reutilizáveis
- **Código reduzido de 1,204 → 912 linhas (-292 / -24.3%)**
- Mantida 100% compatibilidade funcional com v2.3.1
- Nenhuma mudança na UI ou comportamento do usuário

### 📦 Snippets Utilizados
- `Snippets.data._csv_utilities` - leitura/escrita CSV UTF-8
  - Funções: `ler_csv_utf8()`, `escrever_csv_utf8()`
  - Novo parâmetro `retornar_tupla=True` para compatibilidade

- `Snippets.project._dat_folder_manager` - gerenciamento pasta DAT
  - Funções: `get_project_folder()`, `get_project_name()`, `get_dat_folder()`, `create_backup()`
  - Gerencia pastas DAT de projetos workshared e locais

- `Snippets.data._csv_templates` - sistema de templates
  - Funções: `load_templates()`, `save_template()`, `get_templates_csv_path()`
  - Busca templates em DAT e raiz do script

- `Snippets.data._state_persistence` - persistência de estado
  - Funções: `save_state()`, `load_state()`, `restore_parameter_controls()`, `restore_combobox_selection()`
  - Salva/restaura estado da janela e controles

- `Snippets.validation._preconditions` - validações pré-execução
  - Função: `validate_all_preconditions()`
  - Valida documento, worksets, vista ativa

### 🔧 Funções Auxiliares Locais (específicas do ParameterPalette)
- `get_data_csv_path_local(doc)` - caminho `DAT/[Projeto]_data.csv`
- `get_csv_to_load_local(doc, script_path)` - busca CSV com prioridade DAT
- `save_palette_state(param_controls, csv, template)` - wrapper para salvar estado

### 📋 Código Removido
- ❌ Class DATFolderManager (121 linhas) → snippets
- ❌ Class TemplateManager (90 linhas) → snippets
- ❌ Class StateManager (73 linhas) → snippets
- ❌ Function validate_preconditions (27 linhas) → snippet
- ❌ Functions ler_csv_utf8 / escrever_csv_utf8 (22 linhas) → snippet

### 🎯 Melhorias
- Imports organizados por categoria (Standard library, .NET, pyRevit, Snippets)
- Funções auxiliares bem documentadas com docstrings
- Código mais limpo e manutenível
- Compartilhamento de lógica com outros scripts do ITERATION 2
- Facilita manutenção futura (bugs fixes em um único local)

### 🧪 Testes de Compatibilidade
- ✅ CSV Operations: carregar, adicionar/remover parâmetros, backup
- ✅ Templates: carregar, salvar, aplicar templates
- ✅ State Persistence: salvar/restaurar estado ao fechar/abrir
- ✅ Validations: pré-condições verificadas
- ✅ Apply Parameters: aplicação em lote com progress bar
- ✅ UI: nenhuma mudança no arquivo ui.xaml

### 📁 Arquivos Afetados
- `script.py`: 1,204 → 912 linhas
- `obsoleto/script_v2.3.1_20251129.py`: backup da versão anterior

---

## v2.3.1 (Data anterior)

### Otimizações
- ⚡ Performance máxima (output.print_md apenas em erros)
- 🔧 Correção: Visibility import
- 🚀 Loops otimizados

---

## Notas de Migração

### Para Desenvolvedores
- Se você personalizou o ParameterPalette v2.3.1, verifique:
  - Classes removidas: DATFolderManager, TemplateManager, StateManager
  - Funções removidas: validate_preconditions, ler_csv_utf8, escrever_csv_utf8
  - Substitua por imports dos snippets correspondentes

### Compatibilidade
- ✅ Formato JSON de state idêntico (state/palette_state.json)
- ✅ Formato CSV de templates idêntico (DAT/templates.csv)
- ✅ Formato CSV de data idêntico (DAT/[Projeto]_data.csv)
- ✅ UI XAML sem alterações

### Performance
- Mantidas todas as otimizações v2.3.1
- Cache de parâmetros preservado
- Progress bar para >100 elementos mantido
