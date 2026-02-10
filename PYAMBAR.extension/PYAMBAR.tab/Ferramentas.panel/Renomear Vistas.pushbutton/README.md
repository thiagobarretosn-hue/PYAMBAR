# Renomear Sheets/Views - v3.0

## 📋 Descrição

Ferramenta WPF avançada para renomeação em lote de Sheets e Views do Revit com preview em tempo real, validação automática, filtros inteligentes e múltiplos modos de operação.

## ✨ Novidades v3.0

### 🔧 Correções Críticas
- ✅ **PropertyChanged corrigido**: Implementação adequada de `INotifyPropertyChanged` para Python 2 / IronPython
- ✅ **Compatibilidade Revit 2024+**: Suporte correto para `ElementId.Value`
- ✅ **TransactionGroup**: Melhor gerenciamento de transações com undo/redo

### 🚀 Novas Funcionalidades

#### 1. Suporte a Expressões Regulares (Regex)
- Checkbox para habilitar/desabilitar regex no modo Find & Replace
- Validação em tempo real de padrões regex
- Exemplos de uso:
  - `^Floor` - Começa com "Floor"
  - `\d+` - Qualquer número
  - `[A-Z]` - Letras maiúsculas
  - `(.+)_OLD` - Captura grupos

#### 2. Filtro de Busca Inteligente
- Campo de busca para filtrar items em tempo real
- Busca em: Nome Original, Novo Nome e Número
- Atualização instantânea da lista

#### 3. Modo Numeração Avançado
Suporte a múltiplas variáveis no padrão:
- `{0}` ou `{counter}` - Contador sequencial
- `{name}` - Nome original do elemento
- `{number}` - Número (apenas para sheets)
- `{type}` - Tipo do elemento (Sheet/View)

**Exemplos:**
```
{0:03d}_{name}           → 001_Floor Plan, 002_Elevation, ...
SHEET-{number}-{0}       → SHEET-A101-1, SHEET-A102-2, ...
{type}_{0:04d}_{name}    → Sheet_0001_Cover, View_0002_Plan, ...
```

#### 4. Ações Rápidas
- **Marcar Todos** (Ctrl+A): Seleciona todos os items visíveis
- **Desmarcar Todos** (Ctrl+D): Remove seleção de todos
- **Desfazer Preview** (Ctrl+Z): Restaura nomes originais
- **Contador Dinâmico**: Mostra "X de Y selecionados"

#### 5. Atalhos de Teclado
| Atalho | Ação |
|--------|------|
| `Ctrl+P` | Preview |
| `Ctrl+Enter` | Aplicar renomeação |
| `Ctrl+Z` | Desfazer preview |
| `Ctrl+A` | Marcar todos |
| `Ctrl+D` | Desmarcar todos |

#### 6. Validações Aprimoradas
- ✅ Nomes vazios
- ✅ Duplicatas no documento
- ✅ Duplicatas no lote
- ✅ Nomes sem alteração
- ✅ Padrões de numeração inválidos
- ✅ Regex inválido

#### 7. Relatório de Erros Detalhado
- Mensagem na UI com até 5 erros
- Log completo no Output do pyRevit
- Indicação clara do tipo de erro em cada item

### 🎨 Melhorias de Interface
- Tooltips informativos em todos os controles
- Emojis para melhor visualização
- Cores diferenciadas para botões (verde=aplicar, azul=preview, laranja=desfazer)
- Grid redimensionável
- Fonte e espaçamento otimizados
- Informações de atalhos sempre visíveis

## 📖 Como Usar

### 1. Seleção Básica
1. Escolha o **Tipo**: Sheets ou Views
2. Escolha o **Modo**: Find & Replace, Prefix/Suffix ou Numeração
3. Configure os parâmetros conforme o modo escolhido

### 2. Find & Replace
- **Find**: Texto ou padrão regex a buscar
- **Replace**: Texto de substituição
- **Regex**: Marque para usar expressões regulares

**Exemplos:**
```
Find: "Floor Plan"    Replace: "FP"       → Floor Plan 01 → FP 01
Find: "_OLD$"         Replace: "_NEW"     → Sheet_OLD → Sheet_NEW (com regex)
Find: "\s+"           Replace: "_"        → My Sheet → My_Sheet (com regex)
```

### 3. Prefix/Suffix
- **Prefixo**: Texto a adicionar no início
- **Sufixo**: Texto a adicionar no final

**Exemplos:**
```
Prefixo: "PROJ_"    Sufixo: "_2024"     → Plan → PROJ_Plan_2024
Prefixo: "[DRAFT]"  Sufixo: ""          → Sheet A101 → [DRAFT]Sheet A101
```

### 4. Numeração Avançada
- **Padrão**: Template com variáveis
- **Início**: Número inicial do contador

**Exemplos:**
```
Padrão: "{0:03d}_{name}"           Início: 1    → 001_Floor Plan
Padrão: "SHEET-{0:02d}"            Início: 10   → SHEET-10, SHEET-11...
Padrão: "{type}_{number}_{0}"      Início: 1    → Sheet_A101_1
Padrão: "{name}_{counter:04d}"     Início: 100  → Plan_0100
```

### 5. Filtros e Busca
- Digite no campo **Buscar** para filtrar a lista
- Busca em tempo real (nome, número, novo nome)
- Útil para documentos com centenas de sheets/views

### 6. Preview e Aplicação
1. Clique em **Preview** (ou Ctrl+P) para visualizar
2. Verifique o Status de cada item:
   - ✅ OK - Pronto para aplicar
   - ⚠️ Sem alteração - Nome não mudou
   - ❌ Nome vazio - Preencha o nome
   - ❌ Já existe - Nome duplicado no documento
   - ❌ Duplicado no lote - Nome repetido na seleção
3. Ajuste conforme necessário
4. Clique em **Aplicar** (ou Ctrl+Enter)

### 7. Desfazer
- Use **Desfazer Preview** (Ctrl+Z) para restaurar nomes originais
- Após aplicar, use Ctrl+Z no Revit para desfazer a transação

## ⚠️ Avisos Importantes

1. **Backup**: Sempre faça backup antes de renomeações em massa
2. **Preview**: Use sempre o Preview antes de Aplicar
3. **Validação**: Corrija todos os erros ❌ antes de aplicar
4. **Regex**: Teste padrões regex complexos em poucos items primeiro
5. **Undo**: A renomeação pode ser desfeita com Ctrl+Z no Revit

## 🐛 Problemas Conhecidos

- Alguns tipos especiais de views podem não permitir renomeação
- Nomes muito longos podem ser truncados pelo Revit
- Caracteres especiais podem não ser aceitos dependendo da configuração

## 📝 Exemplos Práticos

### Exemplo 1: Padronizar Sheets
```
Modo: Numeração
Padrão: "PROJ_{0:03d}_{name}"
Início: 1

Resultado:
Cover Sheet         → PROJ_001_Cover Sheet
First Floor Plan    → PROJ_002_First Floor Plan
Elevations          → PROJ_003_Elevations
```

### Exemplo 2: Remover Prefixo
```
Modo: Find & Replace
Find: "^DRAFT_"  (com Regex marcado)
Replace: ""

Resultado:
DRAFT_Plan          → Plan
DRAFT_Section       → Section
```

### Exemplo 3: Adicionar Revisão
```
Modo: Prefix/Suffix
Prefixo: ""
Sufixo: "_REV01"

Resultado:
Floor Plan          → Floor Plan_REV01
Site Plan           → Site Plan_REV01
```

### Exemplo 4: Renumerar com Info
```
Modo: Numeração
Padrão: "{type}_{number}_{counter:02d}"
Início: 1

Resultado:
(Sheet A101)        → Sheet_A101_01
(Sheet A102)        → Sheet_A102_02
(View N/A)          → View__01
```

## 🔧 Desenvolvimento

### Estrutura de Arquivos
```
RenomearSheets.pushbutton/
├── script.py           # Código principal v3.0
├── UI.xaml            # Interface WPF v3.0
├── README.md          # Esta documentação
├── CHANGELOG.md       # Histórico de mudanças
└── obsoleto/          # Versões anteriores
    ├── script_v2.0.py
    └── UI_v2.0.xaml
```

### Requisitos
- pyRevit
- Revit 2020 ou superior
- Python 2.7 (IronPython)
- .NET Framework 4.7+

### Compatibilidade
Testado em:
- ✅ Revit 2020
- ✅ Revit 2021
- ✅ Revit 2022
- ✅ Revit 2023
- ✅ Revit 2024
- ✅ Revit 2025

## 👤 Autor

**Thiago Barreto Sobral Nunes**

## 📅 Versões

- **v3.0** (08/11/2024) - Versão avançada com Regex, filtros e atalhos
- **v2.0** (07/11/2024) - Versão com WPF e preview
- **v1.0** - Versão inicial

## 📄 Licença

Uso interno. Todos os direitos reservados.
