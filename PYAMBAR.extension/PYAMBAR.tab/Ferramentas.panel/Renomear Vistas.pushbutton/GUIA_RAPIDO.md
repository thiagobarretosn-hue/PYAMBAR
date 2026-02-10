# 🚀 Guia Rápido - Renomear Sheets/Views v3.0

## ⌨️ Atalhos Principais

```
Ctrl + P      → Preview (visualizar antes de aplicar)
Ctrl + Enter  → Aplicar renomeação
Ctrl + Z      → Desfazer preview (restaurar originais)
Ctrl + A      → Marcar todos os items
Ctrl + D      → Desmarcar todos os items
```

---

## 📝 Exemplos Rápidos

### 1️⃣ Find & Replace Simples
```
Find: "Floor Plan"
Replace: "FP"
Regex: [ ] Desmarcado

Resultado:
"Floor Plan 01" → "FP 01"
"Floor Plan - Level 1" → "FP - Level 1"
```

### 2️⃣ Find & Replace com Regex
```
Find: "^DRAFT_"
Replace: ""
Regex: [✓] Marcado

Resultado:
"DRAFT_Plan" → "Plan"
"DRAFT_Section" → "Section"
"Plan" → "Plan" (sem mudança)
```

### 3️⃣ Adicionar Prefixo
```
Modo: Prefix/Suffix
Prefixo: "PROJ_"
Sufixo: ""

Resultado:
"Cover Sheet" → "PROJ_Cover Sheet"
"Floor Plan" → "PROJ_Floor Plan"
```

### 4️⃣ Adicionar Sufixo
```
Modo: Prefix/Suffix
Prefixo: ""
Sufixo: "_REV01"

Resultado:
"Sheet A101" → "Sheet A101_REV01"
"Plan" → "Plan_REV01"
```

### 5️⃣ Numeração Simples
```
Modo: Numeração
Padrão: "{0:03d}_{name}"
Início: 1

Resultado:
"Cover" → "001_Cover"
"Plan" → "002_Plan"
"Section" → "003_Section"
```

### 6️⃣ Numeração com Sheet Number
```
Modo: Numeração
Padrão: "SHEET-{number}-{0:02d}"
Início: 1

Resultado (se sheet number = A101):
"Cover" → "SHEET-A101-01"
"Plan" → "SHEET-A102-02" (se sheet number = A102)
```

### 7️⃣ Numeração com Tipo
```
Modo: Numeração
Padrão: "{type}_{counter:04d}_{name}"
Início: 100

Resultado:
Sheet "Cover" → "Sheet_0100_Cover"
View "Plan" → "View_0101_Plan"
Sheet "Detail" → "Sheet_0102_Detail"
```

---

## 🔤 Variáveis de Numeração

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `{0}` ou `{counter}` | Contador sequencial | 1, 2, 3, ... |
| `{name}` | Nome original | "Floor Plan" |
| `{number}` | Número do sheet | "A101" |
| `{type}` | Tipo | "Sheet" ou "View" |

### Formatação de Números
```
{0:03d}     → 001, 002, 003, ...
{0:04d}     → 0001, 0002, 0003, ...
{0:02d}     → 01, 02, 03, ...
{counter:05d} → 00001, 00002, ...
```

---

## 🔍 Regex Úteis

| Padrão | Significado | Exemplo |
|--------|-------------|---------|
| `^texto` | Começa com | `^DRAFT` encontra "DRAFT Plan" |
| `texto$` | Termina com | `_OLD$` encontra "Plan_OLD" |
| `\d+` | Números | `\d+` encontra "123" em "Plan123" |
| `\s+` | Espaços | `\s+` encontra espaços em "Plan  01" |
| `[A-Z]` | Maiúsculas | `[A-Z]+` encontra "ABC" |
| `[0-9]` | Dígitos | `[0-9]+` = `\d+` |
| `.` | Qualquer char | `Plan.01` encontra "Plan 01" ou "Plan_01" |
| `.*` | Zero ou mais | `DRAFT.*` encontra tudo que começa com DRAFT |

### Exemplos de Regex

#### Remover prefixo numérico
```
Find: "^\d+_"
Replace: ""
Regex: [✓]

Resultado:
"01_Floor Plan" → "Floor Plan"
"999_Section" → "Section"
```

#### Trocar espaços por underscores
```
Find: "\s+"
Replace: "_"
Regex: [✓]

Resultado:
"Floor Plan Level 1" → "Floor_Plan_Level_1"
```

#### Remover sufixo entre parênteses
```
Find: "\s*\(.*\)$"
Replace: ""
Regex: [✓]

Resultado:
"Plan (old)" → "Plan"
"Section (draft)" → "Section"
```

---

## 📊 Status dos Items

| Símbolo | Significado | Ação |
|---------|-------------|------|
| ✅ OK | Pronto para aplicar | Pode aplicar |
| ⚠️ Sem alteração | Nome não mudou | Pode aplicar (opcional) |
| ❌ Nome vazio | Campo vazio | Corrigir antes |
| ❌ Já existe | Duplicado no doc | Corrigir antes |
| ❌ Duplicado no lote | Repetido na seleção | Corrigir antes |
| ❌ Regex inválido | Padrão errado | Corrigir padrão |

---

## 💡 Dicas de Uso

### 1. Sempre use Preview primeiro
```
1. Configure os parâmetros
2. Clique em Preview (Ctrl+P)
3. Verifique os status
4. Ajuste se necessário
5. Aplique (Ctrl+Enter)
```

### 2. Use o filtro para grandes quantidades
```
Se tem 500 sheets:
1. Digite "Floor" no campo Buscar
2. Veja apenas os que contêm "Floor"
3. Trabalhe apenas neles
4. Limpe o filtro para ver todos
```

### 3. Teste regex em poucos items
```
1. Use o filtro para mostrar 2-3 items
2. Teste seu padrão regex
3. Se funcionar, remova o filtro
4. Aplique em todos
```

### 4. Use Desfazer Preview para experimentar
```
1. Configure Find & Replace
2. Preview
3. Não gostou? Ctrl+Z (Desfazer Preview)
4. Mude para Numeração
5. Preview novamente
```

### 5. Combine modos em etapas
```
Etapa 1: Use Find & Replace para limpar
Etapa 2: Use Prefix/Suffix para padronizar
Etapa 3: Use Numeração para ordenar
```

---

## ⚠️ Cuidados Importantes

### ❌ NÃO faça
- ❌ Aplicar sem fazer Preview
- ❌ Ignorar erros ❌ na validação
- ❌ Usar regex complexo sem testar
- ❌ Renomear sem backup do arquivo

### ✅ SEMPRE faça
- ✅ Backup antes de renomeações em massa
- ✅ Preview antes de aplicar
- ✅ Teste em poucos items primeiro
- ✅ Verifique o status de todos items
- ✅ Use nomes descritivos e claros

---

## 🆘 Problemas Comuns

### "Nome vazio" após preview
**Causa**: Replace vazio no Find & Replace  
**Solução**: Preencha o campo Replace ou use outro modo

### "Regex inválido"
**Causa**: Padrão de regex incorreto  
**Solução**: Verifique a sintaxe ou desmarque Regex

### "Já existe"
**Causa**: Nome duplicado no documento  
**Solução**: Mude o padrão para criar nomes únicos

### Numeração não funciona como esperado
**Causa**: Variáveis incorretas no padrão  
**Solução**: Use `{0}`, `{counter}`, `{name}`, `{number}`, `{type}`

### Não consigo aplicar
**Causa**: Existem erros ❌ nos items  
**Solução**: Corrija todos os erros antes de aplicar

---

## 📞 Ajuda Rápida

**Versão**: 3.0  
**Autor**: Thiago Barreto Sobral Nunes  
**Data**: 08/11/2024

**Arquivos**:
- `script.py` - Código principal
- `UI.xaml` - Interface
- `README.md` - Documentação completa
- `CHANGELOG.md` - Histórico de mudanças
- `GUIA_RAPIDO.md` - Este guia

**Atalhos no pyRevit**:
- Aba: PYAMBAR(lab)
- Painel: Ferramentas
- Botão: Renomear Sheets

---

**🎯 Dica Final**: Experimente! Use Ctrl+Z (Desfazer Preview) quantas vezes quiser para testar diferentes configurações. Nada será alterado até você clicar em Aplicar!
