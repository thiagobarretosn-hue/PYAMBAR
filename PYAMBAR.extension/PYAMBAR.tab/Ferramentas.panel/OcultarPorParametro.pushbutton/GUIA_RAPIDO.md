# 🚀 Guia Rápido - Ocultar por Parâmetro

## ⚡ Início Rápido (3 passos)

1. **Escolha um PARÂMETRO** (ex: "Family", "Type", "Mark")
2. **Selecione o VALOR** que deseja ocultar
3. **Defina ONDE** ocultar (vista atual, específicas ou todas)

## 💡 Exemplos Práticos

### Caso 1: Ocultar elementos demolidos
```
Parâmetro: Comments
Valor: DEMOLIR
Vista: Todas as vistas
```
**Resultado:** Todos os elementos marcados como "DEMOLIR" ficarão ocultos

---

### Caso 2: Ocultar tubulação específica em plantas
```
Parâmetro: Type
Valor: Pipe - 100mm
Vista: Selecionar vistas (escolher plantas desejadas)
```
**Resultado:** Tubulações de 100mm ocultadas apenas nas plantas selecionadas

---

### Caso 3: Ocultar família específica na vista atual
```
Parâmetro: Family
Valor: Mesa - Escritório
Vista: Vista Atual
```
**Resultado:** Todas as mesas de escritório ocultadas na vista ativa

---

## 🎯 Dicas Pro

### ✅ Use para:
- Ocultar elementos temporários (demolições, futuras)
- Simplificar vistas complexas
- Criar apresentações limpas
- Documentação por fases

### ⚠️ Atenção:
- Use "Vista Atual" para testes rápidos
- Use "Vistas Específicas" para controle preciso
- Use "Todas as Vistas" com cuidado (afeta o projeto inteiro!)
- O script mostra quantos elementos serão afetados ANTES de executar

## 📊 Interface

```
┌─────────────────────────────────────┐
│ 1. PARÂMETRO  [▼ Escolha]          │
│    ℹ️ 150 parâmetros disponíveis    │
├─────────────────────────────────────┤
│ 2. VALOR      [▼ Escolha]          │
│    ℹ️ 12 valores únicos             │
├─────────────────────────────────────┤
│ 3. ONDE       [▼ Vista Atual]      │
│    ○ Vista Atual                    │
│    ○ Selecionar Vista(s)            │
│    ○ Todas as Vistas                │
├─────────────────────────────────────┤
│ 📋 Parâmetro: Type = Pipe - 100mm  │
│ ✅ 25 elemento(s) encontrado(s)     │
├─────────────────────────────────────┤
│ [Ocultar Elementos] [Cancelar]      │
└─────────────────────────────────────┘
```

## 🔄 Processo

1. **Carrega** todos os parâmetros do projeto
2. **Busca** valores únicos do parâmetro escolhido
3. **Filtra** elementos com esse valor
4. **Mostra** quantos elementos serão afetados
5. **Executa** ocultação nas vistas escolhidas
6. **Gera** relatório completo no output

## 📈 Relatório de Saída

Após executar, você verá no output do pyRevit:

```markdown
## Ocultando Elementos
**Parâmetro:** Type = Pipe - 100mm
**Elementos encontrados:** 25
**Vistas a processar:** 8
---
✓ **Planta Nível 1**: 8 elementos ocultados
✓ **Planta Nível 2**: 7 elementos ocultados
✓ **Planta Nível 3**: 10 elementos ocultados
---
## Resumo
✓ **Total de elementos ocultados:** 25
✓ **Vistas modificadas:** 3
✓ **Operação concluída com sucesso!**
```

## 🛠️ Solução de Problemas

### "Nenhum elemento encontrado"
- Verifique se o parâmetro está preenchido nos elementos
- Confirme que o valor está correto (case-sensitive)

### "Não foi possível ocultar"
- Alguns elementos não podem ser ocultados em certas vistas
- Verifique se a categoria pode ser ocultada na vista

### "Operação cancelada"
- Normal se clicar em "Cancelar"
- Nenhuma alteração foi feita no projeto

## 📞 Suporte

Desenvolvido por **PYAMBAR Lab**
Versão: 1.0.0
Data: Dezembro 2025

---

**Boa sorte com seus projetos! 🎉**
