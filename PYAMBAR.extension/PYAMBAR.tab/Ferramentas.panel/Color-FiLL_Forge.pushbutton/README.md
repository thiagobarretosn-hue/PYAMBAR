# Color-FiLL Forge - Gerenciador Visual de Cores e Criador de Legendas

**Versão**: 1.0.0
**Última Atualização**: 05.01.2026

## 📖 Descrição

**Color-FiLL Forge** é um gerenciador visual completo de cores que permite colorir elementos usando **FilledRegions** e criar legendas inteligentes com tags automáticas e bordas adaptativas.

O nome reflete sua essência:
- **Color**: Gerenciamento de cores
- **FiLL**: Uso de FilledRegions (elemento central)
- **Forge**: Forja/criação de visualizações e legendas

## ✨ Recursos Principais

### Coloração com FilledRegions
- ✅ Colore elementos por valores de parâmetros (Instance ou Type)
- ✅ Usa FilledRegions para visualização precisa
- ✅ Cores aleatórias distintas para cada valor
- ✅ Gradientes automáticos entre primeira e última cor
- ✅ Ordenação inteligente (numérica quando possível)

### Legendas Inteligentes (v1.0)
- 📊 **Tags Automáticas**: Usa família "TAG Legenda items" (auto-importada)
- 🎯 **Bordas Adaptativas**: Calcula automaticamente baseado em BoundingBox real
- 🧠 **Comparação Inteligente**: Borda se adapta ao título ou tags (o que for maior)
- ⚙️ **Totalmente Configurável**:
  - Dimensões das caixas (1/4" a 2")
  - Espaçamentos personalizáveis
  - Margem inferior configurável (padrão 2")
  - Margem lateral com simetria automática

### Criação Automática
- 🎨 **Filtros de Vista**: Gera filtros parametrizados com cores
- 💾 **Esquemas**: Salva/carrega esquemas de cores (.cschn)

### Interface Moderna
- 🔍 Busca de parâmetros em tempo real
- 🌈 Seletor de cores por valor
- 🔄 Atualização automática ao mudar de vista
- 🌐 Suporte multi-idioma (PT-BR, EN, FR, DE, RU)

## 🚀 Como Usar

### 1. Colorir Elementos

1. Abra uma vista 3D, planta, corte ou elevação
2. Execute **PYAMBAR(lab) > Ferramentas > Color-FiLL Forge**
3. Selecione uma **Categoria** (ex: Walls, Doors, MEP)
4. Marque um **Parâmetro** (ex: Family, Type, Mark)
5. Ajuste cores clicando nos valores listados
6. Clique **Set Colors** para aplicar

### 2. Criar Legenda Inteligente

1. Após colorir elementos
2. Clique **Create Legend**
3. Configure na janela:
   - Nome da legenda
   - Dimensões das caixas (padrão 1" x 1")
   - Espaçamentos (padrão 1")
   - Margem da borda (padrão 1")
   - Margem inferior (padrão 2")
   - Ordenação (Original, Alfabética, por Quantidade)
4. A legenda será criada automaticamente com:
   - FilledRegions coloridos
   - Tags "TAG Legenda items" com textos
   - Título centralizado
   - Borda CS_Border_White adaptativa
   - Cálculo inteligente:
     - Se título maior → margem = border_offset (simetria)
     - Se tags maiores → margem = 1" padrão

### 3. Criar Filtros de Vista

1. Após colorir elementos
2. Clique **Create View Filters**
3. Filtros serão criados automaticamente com:
   - Regras baseadas no parâmetro selecionado
   - Overrides de cor aplicados
   - Nome formatado: `Categoria Parâmetro - Valor`

### 4. Gerenciar Cores

#### Cores Aleatórias
- Clique **Random Colors** para gerar novas cores

#### Gradiente
1. Defina cor do primeiro valor
2. Defina cor do último valor
3. Clique **Gradient Colors**
4. Cores intermediárias serão interpoladas

#### Salvar/Carregar Esquema
1. Configure cores desejadas
2. Clique **Save / Load Color Scheme**
3. Escolha **Save** e selecione local
4. Para carregar: **Load** e escolha arquivo .cschn
5. Opções de carregamento:
   - **Por Valor**: Aplica cor ao mesmo valor
   - **Por Posição**: Aplica cor pela ordem na lista

### 5. Resetar Cores

- Clique **Reset** para:
  - Remover todos os overrides gráficos
  - Deletar filtros criados pelo Color-FiLL Forge

## 🎯 Características Técnicas v1.0

### Sistema de Legendas Inteligentes

**Cálculo de Bordas Adaptativo:**
1. Cria borda temporária
2. Cria tag temporária do título
3. Obtém BoundingBox real da tag do título
4. Compara `title_right_x` vs `max_tag_x`
5. Se título maior: `border_right = title_right_x + border_offset` (simetria)
6. Se tags maiores: `border_right = max_tag_x + 1"` (margem padrão)
7. Deleta borda temporária
8. Recria borda com dimensões finais precisas
9. Cria tag final do título na posição correta

**Tecnologias:**
- FilledRegions para elementos coloridos
- IndependentTag (TAG Legenda items.rfa)
- BoundingBox real para cálculos precisos
- CS_Border_White (máscara desabilitada)
- Auto-import de família se não existir

## 📋 Categorias Suportadas

Todas as categorias visíveis na vista, exceto:
- Linhas de separação
- Câmeras e vistas
- Grids e níveis
- Sistemas MEP
- Elementos analíticos

## 💡 Dicas

### Parâmetros Recomendados

**Análise Espacial:**
- Rooms: Department, Name, Number
- Spaces: Space Name, Zone
- Areas: Area Type, Name

**MEP:**
- Ducts/Pipes: System Name, Size, Flow
- Equipment: Mark, Family

**Estrutural:**
- Structural Framing: Material, Profile
- Foundations: Mark, Type

**Arquitetônico:**
- Walls: Function, Type, Fire Rating
- Doors: Fire Rating, Type, Mark

### Performance

Para modelos grandes:
1. Use vistas filtradas (elementos visíveis)
2. Limite categorias a analisar
3. Use filtros de vista em vez de overrides diretos
4. Evite parâmetros com muitos valores únicos

## 🎨 Formato de Arquivo .cschn

Arquivo de texto simples:
```
Nome do Valor::R255G128B64
Outro Valor::R100G200B50
```

Pode ser editado manualmente em qualquer editor de texto.

## 📜 Créditos e Evolução

**Desenvolvimento Original:**
- BIMOne Inc. (2021) - MIT License
- Versão inicial ColorSplasher para Revit

**Versão Dynamo/Python:**
- Nonica - Jaime Alonso Candau (2023)
- Estudio Alonso Candau SLP

**Versão pyRevit:**
- Jean-Marc Couffin (2023)
- Adição de criação de filtros de vista

**Integração PYAMBAR(lab):**
- Thiago Barreto Sobral Nunes (2025)
- Documentação PT-BR e melhorias

**Evolução para Color-FiLL Forge v1.0:**
- Thiago Barreto Sobral Nunes (Janeiro 2026)
- Legendas com tags inteligentes
- Bordas adaptativas com BoundingBox
- Sistema de comparação título vs tags
- Auto-import de família TAG Legenda items
- Margem inferior configurável
- Remoção de TextNote fallback
- Zero prints em operação normal

## 📄 Licença

MIT License - Veja créditos acima para autores específicos.

## 🆘 Suporte

Para problemas ou sugestões, reporte no repositório PYAMBAR(lab).

---

**Parte do PYAMBAR(lab) v2.0** - Extensão pyRevit para Revit MEP e BIM
