# ParameterPalette - CHANGELOG

## v5.6.0 (2026-09-04) - Escolha da base de parâmetros

Existem hoje **duas** bases de parâmetros com esquemas diferentes, então a
ferramenta não pode mais presumir qual usar num projeto novo.

### ✨ Novidades

- **Projeto sem paleta agora pergunta.** Ao abrir num modelo que ainda não tem
  paleta, aparece um diálogo com quatro caminhos:
  - **Base NOVA** (`data_NEW.csv`) — *Padrão atual — ARN, Filter, Unit ID*
  - **Base ANTIGA** (`data_OLD.csv`) — *Projetos legados — WBS, Módulo Montagem*
  - **Copiar de outro projeto** — só aparece se houver paletas registradas
  - **Importar CSV de uma pasta…**
- **O resumo de cada base é lido do próprio arquivo** — "11 parâmetros — Floor,
  PHASE, Room, Stage…". Se a base mudar de colunas, o texto muda junto; só a
  nota de uma linha é fixa (editável em `BASES_SEMENTE`, no topo do script).
- Cancelar deixa a paleta vazia sem criar nada. Dá para montar do zero pelo
  **➕ Parâmetro**, ou usar os botões de importar/copiar da barra.
- Base de fábrica ausente na pasta da ferramenta vira aviso no diálogo, em vez
  de sumir da lista em silêncio.

### 🔧 Mudanças

- **`data.csv` removido** — era cópia byte a byte do `data_OLD.csv`. Duas
  cópias da mesma base acabariam divergindo.
- O diálogo abre depois que a paleta aparece na tela (timer de 250 ms): modal
  disparado antes do `Show()` nasce sem dono e vai para trás do Revit.
- `_limpar_parametros()` extraído do `load_csv` — desliga os handlers dos
  controles antes de esvaziar a lista, evitando vazamento a cada recarga.

---

## v5.5.0 (2026-09-04) - A paleta é do projeto

Foco: deixar claro **de quem é a paleta** e tirar da tela o que quase não se usa.

### ✨ Novidades

- **Barra de contexto no topo.** Sempre visível: de qual projeto é a paleta,
  quantos parâmetros ela tem e onde está salva (`DAT`, `APPDATA` ou "arquivo
  externo"). Some a dúvida de estar editando a paleta errada.
- **📋 Copiar de outro projeto.** Lista os projetos onde a ferramenta já foi
  usada — nome e quantidade de parâmetros — e traz a paleta pronta. O índice
  vive em `%APPDATA%\...\ParameterPalette\palettes_index.json` e cresce sozinho
  a cada projeto aberto. Se o projeto atual já tem paleta, pede confirmação e
  faz backup antes de substituir. Mesmo padrão do "Copiar de outro projeto" do
  WBS Completo.
- **A paleta vira do projeto sozinha.** Adicionar um parâmetro ou digitar um
  valor novo grava `<projeto>_data.csv` no DAT na hora. O botão
  "💾 Paleta do Projeto" saiu — não era mais preciso.
- **🔤 A-Z** ordena parâmetros e valores dos dropdowns. Ordenação **natural**:
  `Nível 2` antes de `Nível 10`, `99` antes de `101`. Começa ligado; desligado,
  vale a ordem do CSV. A escolha fica gravada por projeto.
- **Templates recolhido** num Expander. Aberto ou fechado, fica gravado.

### 🔧 Melhorias

- Botões com nome por extenso (`➕ Parâmetro`, `📥 Importar CSV`, …) no lugar
  de `📂 CSV` / `💾 Paleta do Projeto`.
- Tooltip do Importar CSV explica o formato: cada coluna é um parâmetro, os
  valores da coluna são as opções. O tooltip do botão no ribbon foi reescrito
  com o fluxo de uso e a regra da paleta por projeto.
- Snippet novo `Snippets/data/_ordenacao.py` (ordenação natural, com testes).

---

## v5.4.0 (2026-09-04) - Seletor de CSV + integridade do dado

### 🐞 Correções

- **Botão 📂 CSV não abria o seletor.** `forms.pick_file()` chama
  `System.Windows.Forms.OpenFileDialog.ShowDialog()` **sem owner**; com a paleta
  escondida por `Hide()` e `Topmost=True`, o diálogo nascia atrás do Revit e o
  usuário só via o Revit travar. Agora é o `Microsoft.Win32.OpenFileDialog` do
  WPF com `ShowDialog(self)` — owner explícito, sem esconder a janela. Cancelar
  passou a dizer que cancelou (antes era silêncio total, indistinguível de falha).
- **CSV vazio no DAT matava a ferramenta.** Projeto sem CSV ganhava um
  `<projeto>_data.csv` vazio que passava a mascarar o `data.csv` de fábrica: a
  paleta abria com zero parâmetros e não havia saída pela UI. O CSV de trabalho
  inexistente ou sem cabeçalho agora é semeado do padrão.
- **Escrita dentro da pasta do script.** Se o CSV em uso vinha de lá, os valores
  novos eram gravados no repositório e sumiam no próximo update. `data.csv` da
  pasta do script virou semente somente-leitura; o CSV de trabalho vive no DAT do
  projeto ou, sem projeto salvo, em `%APPDATA%`.
- **Parser CSV RFC 4180** (`Snippets/data/_csv_rfc.py`, com testes). O
  `split(',')` antigo comia a aspa de polegada (`1/2"`) e partia valores com
  vírgula, em silêncio.
- **State por projeto.** Havia um único `palette_state.json`: ao trocar de
  projeto, o novo herdava os valores do anterior. O state antigo é migrado uma
  vez, e só quando pertence ao projeto.
- **Escrita de parâmetro por `StorageType`.** `param.Set(str)` estourava em
  Double/Integer/ElementId e virava "erro" genérico; agora Double passa por
  `SetValueString` (respeita a unidade do projeto) e o que não couber aparece no
  status como "valor incompatível".

### 🔧 Melhorias

- Modais (template, adicionar e remover parâmetro) não escondem mais a paleta —
  só desligam o `Topmost` enquanto aparecem.
- Watcher de documento congelado durante modais: ele reconstrói a UI e não pode
  rodar dentro do message loop aninhado de um diálogo.
- State com debounce de 400 ms (era um `fsync` a cada clique).
- Toggles e valores sobrevivem a adicionar/remover parâmetro.
- Exceções silenciosas passaram a ser logadas.

---

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
