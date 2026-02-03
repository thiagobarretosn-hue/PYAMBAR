# Slab Passes v4.0

## 🎯 Visão Geral

**Slab Passes** (Passagens de Laje) é uma ferramenta avançada para aplicar acessórios de tubulação em tubos verticais que atravessam lajes, com filtros inteligentes por parâmetros de projeto.

---

## ✨ Funcionalidades Principais

### 🆕 **Novidade v4.0: Filtro por Parâmetro**
- Agrupe tubos por **diâmetro + parâmetro de projeto**
- Aplique **acessórios diferentes** para categorias específicas
- Exemplos: Riser vs Vent, Sistema A vs Sistema B

### 🔍 **Detecção Automática**
- Tubos **verticais** são detectados automaticamente
- Parâmetros disponíveis são **listados dinamicamente**
- Proteção contra **duplicidade** de acessórios

### 🔗 **Suporte para Vínculos**
- Selecione tubos **locais** (no projeto atual)
- Selecione tubos em **Revit Links** (vínculos)
- Transformação automática de coordenadas

---

## 📖 Como Usar

### **Workflow Básico:**

1. **Execute o script** clicando no botão "Slab Passes"

2. **Escolha o tipo de tubos:**
   - Tubos LOCAIS (no projeto atual)
   - Tubos em VÍNCULOS (Revit Links)

3. **Selecione os tubos verticais**
   - Apenas tubos verticais serão permitidos
   - Clique em "Concluir" quando terminar

4. **[OPCIONAL] Filtro Avançado:**
   - Janela mostra parâmetros disponíveis
   - Escolha um parâmetro (ex: Stage, System)
   - OU clique em "Pular" para usar apenas diâmetro

5. **Configure os acessórios:**
   - Cada grupo mostra: `Diâmetro` ou `Diâmetro | Parâmetro`
   - Selecione o acessório desejado para cada grupo
   - Configure nível de referência e ajuste fino (m)

6. **Aplicar:**
   - Barra de progresso mostra andamento
   - Relatório final exibe resultado

---

## 💡 Exemplos de Uso

### **Exemplo 1: Diferentes Acessórios para Riser e Vent**

**Cenário:** Tubos de 2" com categorias diferentes (Riser = água sobe, Vent = ventilação)

**Passos:**
1. Selecione todos os tubos de 2" verticais
2. Escolha parâmetro: **"Stage"**
3. Grupos criados automaticamente:
   - `2" | Riser` → 15 tubos
   - `2" | Vent` → 8 tubos
4. Configure:
   - `2" | Riser` → Sleeve A
   - `2" | Vent` → Sleeve B
5. Aplicar

**Resultado:** Acessórios corretos em cada tipo!

### **Exemplo 2: Apenas por Diâmetro (Modo Simples)**

**Cenário:** Não precisa de filtros avançados

**Passos:**
1. Selecione tubos
2. Clique "Pular (Apenas Diâmetro)"
3. Configure acessórios por diâmetro
4. Aplicar

---

## 🎨 Interface

### **Janela 1: Filtro Avançado (Opcional)**
- Lista de parâmetros detectados
- Radio buttons para seleção
- Botão "Pular" ou "Continuar"

### **Janela 2: Configuração de Acessórios**
- Grupos organizados por diâmetro [+ parâmetro]
- Dropdown para escolher acessório
- Configuração de nível + elevação
- Status detalhado (modo, filtro, contadores)
- Cores: Verde (LOCAL), Azul (VÍNCULOS)

---

## ⚙️ Configurações

### **Filtro de Verticalidade**
- Tolerância: **1.5cm** de diferença horizontal
- Apenas tubos com variação X,Y < 0.05 pés

### **Proteção de Duplicidade**
- Tolerância: **3cm** de distância
- Não cria acessório se já existe outro no mesmo local

### **Ajuste de Elevação**
- Input em **metros**
- Conversão automática para **pés** (Revit API)
- Soma ao nível de referência escolhido

---

## 🔧 Snippets Disponíveis

Use as funções auxiliares em seus próprios scripts:

```python
from Snippets.slab_passes_helpers import (
    get_vertical_pipes,
    group_pipes_by_diameter_and_param,
    create_accessory_at_pipe_center,
    is_vertical_pipe,
    get_pipe_diameter_formatted,
    get_parameter_value_safe,
    check_duplicate_accessory
)
```

**Veja exemplos completos em:** `Snippets/slab_passes_helpers.py`

---

## 📋 Requisitos

- **Revit:** 2020 ou superior
- **pyRevit:** Instalado e configurado
- **Famílias:** Acessórios de tubulação carregados no projeto
- **Parâmetros:** (Opcional) Parâmetros compartilhados ou de projeto nos tubos

---

## 🐛 Limitações Conhecidas

1. **Seleção Mista:**
   - Não é possível selecionar tubos locais E em vínculos simultaneamente
   - Escolha um tipo por vez

2. **Detecção de Parâmetros:**
   - Apenas parâmetros compartilhados e de projeto
   - Parâmetros com valores vazios não aparecem

3. **Performance:**
   - Projetos com >10.000 tubos podem demorar
   - Recomendação: Filtrar seleção por vista/workset

---

## 📚 Documentação Adicional

- **CHANGELOG.md** - Histórico detalhado de versões
- **Snippets/slab_passes_helpers.py** - Funções reutilizáveis com exemplos

---

## 👤 Autor

**Thiago Barreto Sobral Nunes**
- Eng. Civil BIM
- PYAMBAR(lab)

---

## 📅 Versão

**v4.0** - 2025-12-16

---

## 🎓 Suporte

Para dúvidas ou problemas:
1. Consulte o CHANGELOG.md
2. Veja exemplos em Snippets/slab_passes_helpers.py
3. Entre em contato com o desenvolvedor
