# Changelog

Todas as mudancas notaveis neste projeto serao documentadas neste arquivo.

## [2.3.0] - 2026-04-09

### Adicionado

- **Secoes Comerciais** (SnapMEP) — divide tubulacoes selecionadas em secoes de comprimento comercial inserindo unioes nos pontos de corte
  - Suporta multiplos tipos de tubo (CPVC 10ft, PVC 20ft) configurados individualmente
  - Override de uniao por tipo via RPM (Routing Preference Manager)
  - Distancia de seguranca e tolerancia configuravies
  - Copia parametros de texto do pipe para cada uniao inserida

---

## [2.2.0] - 2026-02-24

### Melhoria - Vista 3D com Section Box

O botao "Vista 3D" agora cria uma **Section Box** ao redor dos elementos selecionados
em vez de isolar temporariamente. Isso permite visualizar o contexto do modelo (paredes,
pisos, estrutura) ao redor dos elementos, oferecendo uma experiencia muito melhor para
analise espacial.

**Ferramentas atualizadas:**

- ParamForge — botao "3D" usa Section Box
- Color-FiLL Forge — botao "3D" usa Section Box
- ByParam (Isolar/Ocultar por Parametro) — acao "Vista 3D" usa Section Box
- Schedule Plumbing — preview "Vista 3D" usa Section Box

> O botao "Isolar" na vista ativa continua funcionando com isolamento temporario (comportamento esperado para vistas 2D).

### Adicionado

- Novo snippet `lib/Snippets/views/_view3d_helpers.py` — funcoes centralizadas:
  - `find_3d_view(doc, uidoc)` — encontra vista 3D (ativa > {3D} > qualquer)
  - `compute_bounding_box(doc, ids, padding)` — calcula bounding box unificado com margem
  - `set_section_box(view3d, bbox)` — aplica e ativa Section Box na vista

---

## [2.1.0] - 2026-02-22

### Adicionado
- **ParamForge v1.1** — ferramenta unificada que combina Color-FiLL Forge + SchedulePlumbing
  - Pipeline: Categorias → Parametros → Valores → ElementIds → Acoes
  - Visualizar: cores, filtros de vista, legenda (FilledRegion + IndependentTag)
  - Documentar: schedules filtrados, mapeamento dinamico de templates, Schedule Category por grupo
  - Filtro por disciplina (Arch/Struct/Mech/Elec/Piping)
  - 3 modos: Selecionar / Vista Ativa / Projeto
  - Presets de cores, gradiente, busca de categorias e parametros
- **ByParam pulldown v1.0** — Isolar, Ocultar, Selecionar e Resetar por parametro

### Atualizado
- Color-FiLL Forge v1.3.0 — botoes preview (Selecionar/Isolar/Vista 3D)
- SchedulePlumbing v4.1 — modo toggle, verificacao, tabelas hidrossanitarias

---

## [2.0.0] - 2026-02-03

### Adicionado
- Sistema de distribuicao via GitHub
- Instalador com interface grafica
- Biblioteca lib/Snippets completa
- Todas as ferramentas estaveis

### Ferramentas Incluidas
- CoordenadasnXYZ v9.10
- ParameterPalette v4.2.0 (MODELESS)
- Color-FiLL Forge v1.2.2
- E mais 19 ferramentas

### Melhorias
- Compatibilidade total com Revit 2026
- Correcoes para IronPython 3
- Biblioteca de snippets reutilizaveis

---

## [1.0.0] - Versao inicial

- Primeira versao distribuida via Google Drive
