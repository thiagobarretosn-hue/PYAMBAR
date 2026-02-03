# Copy Parameters - CHANGELOG

## v6.0 (2025-12-01) - Workflow Unificado

### 🎯 Simplificação Total
- **❌ Removido**: Dual Mode (Quick/Interactive)
- **✅ Novo**: Workflow único unificado
- **⚡ Sempre**: Seleção interativa + Config automático

### 🔧 Como Funciona Agora
1. **Execute o script** (sem necessidade de pré-seleção)
2. **Clique** para selecionar elemento FONTE
3. **Clique** para selecionar elemento(s) DESTINO
4. **Automático**: Parâmetros do `config.json` são usados automaticamente
5. **Fallback**: Se `config.json` vazio/ausente, abre dialog de seleção manual

### 📦 Integração com Config Parameters
- `config.json` é gerenciado pelo botão **Config Parameters**
- Configure uma vez, use sempre
- Sem necessidade de pré-selecionar elementos
- Workflow consistente e previsível

### 🗑️ O Que Foi Removido
- ❌ `detect_mode()` - detecção de modo baseada em seleção
- ❌ `quick_copy_workflow()` - workflow Quick Mode
- ❌ `interactive_copy_workflow()` - workflow Interactive Mode
- ❌ Comportamento diferente baseado em quantidade de elementos selecionados

### ✅ O Que Foi Adicionado
- ✅ `unified_copy_workflow()` - único workflow para todos os casos
- ✅ Carregamento automático de `config.json`
- ✅ Fallback gracioso para seleção manual

### 📊 Mudanças de Comportamento

**ANTES (v5.0 - Dual Mode):**
```
Pré-selecione 2+ elementos → QUICK MODE → Usa config.json
Pré-selecione 0-1 elementos → INTERACTIVE MODE → Abre dialogs
```

**DEPOIS (v6.0 - Unified):**
```
Execute → Selecione FONTE → Selecione DESTINOS → Usa config.json automaticamente
(Se config.json vazio → Fallback para dialog manual)
```

### 💡 Vantagens
- ✅ Workflow mais simples e consistente
- ✅ Não precisa lembrar regras de pré-seleção
- ✅ Integração perfeita com Config Parameters
- ✅ Comportamento previsível em todos os casos

### 🔧 Código
- **Linhas**: 381 → 315 (-66 linhas / -17.3%)
- **Funções**: 3 workflows → 1 workflow unificado
- **Complexidade**: Reduzida significativamente

---

## v5.0 (2025-11-29) - ITERATION 2 Unified

### ✨ Unificação Completa
- **Merge**: Copy Parameters v2.0 + Copy N EDIT v4.1
- **Código reduzido**: 778 → 381 linhas (-397 / -51.0%)
- **Dual Mode**: Detecção automática Quick/Interactive

### 🚀 QUICK MODE (2+ elementos pré-selecionados)
- Usa `config.json` para listar parâmetros
- Output mínimo (só erros)
- Otimizado para uso repetitivo
- Workflow: Pré-selecione → Execute → Pronto
- Equivalente ao antigo "Copy N EDIT v4.1"

**Como usar QUICK MODE:**
1. Selecione 2+ elementos no Revit
2. Execute o script
3. Primeiro elemento = ORIGEM
4. Demais elementos = DESTINOS
5. Parâmetros copiados conforme `config.json`

### 🎯 INTERACTIVE MODE (0-1 elementos)
- Dialogs para escolher fonte e destinos
- Seleção de parâmetros via UI
- Relatório detalhado com estatísticas
- Workflow guiado em 4 passos
- Equivalente ao antigo "Copy Parameters v2.0"

**Como usar INTERACTIVE MODE:**
1. Execute o script (sem pré-seleção)
2. Clique para escolher elemento FONTE
3. Clique para escolher DESTINO(S)
4. Selecione parâmetros via dialog
5. Aguarde processamento

### 📦 Snippets Utilizados
- `Snippets.validation._preconditions` - validação de pré-condições
- `Snippets.parameters._parameter_operations` - cópia em lote de parâmetros

### 🔧 Arquivos
- `script.py` - Script unificado v5.0 (381 linhas)
- `config.json` - Configuração para QUICK MODE
- `obsoleto/script_v2.0_20251129.py` - Backup Copy Parameters v2.0

### 🗑️ Scripts Removidos
- ❌ **Copy Parameters N EDIT v4.1** (integrado em v5.0 como QUICK MODE)
  - Backup disponível: `Copy Parameters N EDIT.pushbutton/bkp/script_v4.1_20251129.py`

### 🎯 Melhorias Técnicas
- Detecção automática de modo baseada em seleção
- Uso de snippets para reduzir duplicação
- Mantida compatibilidade total com Revit 2026
- Progress bar para operações >100 elementos
- Tratamento robusto de erros

### 📊 Comparação de Linhas
```
ANTES (2 scripts):
  Copy Parameters v2.0:     545 linhas
  Copy N EDIT v4.1:         233 linhas
  TOTAL:                    778 linhas

DEPOIS (1 script unificado):
  Copy Parameters v5.0:     381 linhas
  config.json:               14 linhas
  TOTAL:                    395 linhas

REDUÇÃO:                    -383 linhas (-49.2%)
```

---

## v2.0 (2025-10-20) - Copy Parameters

### Melhorias
- Compatibilidade total com Revit 2026 API
- Suporte para System.Int64 em ElementId
- Progress bar para operações em lote
- Relatório detalhado com estatísticas
- Tratamento robusto de erros
- Validação de tipos de parâmetros
- Interface aprimorada com feedback visual
- Workflow interativo em 5 passos

---

## v4.1 (2025-XX-XX) - Copy N EDIT

### Características
- Workflow rápido sem UI
- Configuração JSON externa
- Output mínimo (apenas erros)
- Shortcut keyboard 'CP'
- Otimizado para uso repetitivo
- Cache de parâmetros origem
- Batch processing eficiente

---

## Notas de Migração

### De Copy Parameters v2.0 para v5.0:
✅ **Nenhuma ação necessária** - funcionalidade mantida em INTERACTIVE MODE
- Execute sem pré-seleção para usar o workflow antigo
- Todos os recursos preservados (dialogs, relatórios, etc.)

### De Copy N EDIT v4.1 para v5.0:
⚠️ **Ação necessária**:
1. **config.json** já foi criado automaticamente com os parâmetros padrão
2. Edite `config.json` se necessário (adicione/remova parâmetros)
3. ❌ **Shortcut 'CP' removido** (não suportado em modo dual)
   - Se desejar, configure manualmente no pyRevit

### Configurando config.json:
```json
{
  "parameters_to_copy": [
    "Módulo Montagem",
    "WBS",
    "WBS Detail",
    "Comments",
    "Mark"
  ]
}
```

Adicione os nomes **exatos** dos parâmetros que você deseja copiar no QUICK MODE.
