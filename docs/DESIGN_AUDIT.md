# DESIGN AUDIT

Auditoria de design, UI/UX, layout, responsividade e consistência visual —
21/09/2026, sobre o estado **depois** do lote de correções de `DESIGN_QA.md`.
Feita com Playwright: screenshots, DOM, computed styles, bounding boxes,
detecção automática de colisão entre irmãos, clipping, z-index, teclado
(Tab, Shift+Tab, Enter, Space, Esc), hover, conteúdo real (590 documentos,
100 vagas por lista, títulos de até 86 caracteres) e estados vazio/erro/
carregando.

Evidências: `data/screenshots/design-audit/{desktop,tablet,mobile}/` e
`data/screenshots/design-audit/metricas.json` (por página e viewport:
viewport, largura da barra e do conteúdo, blocos e gaps, botões, inputs,
cartões, badges, expanders, links, alertas, tabelas, colisões, clipping,
elementos fora da tela, z-index, contraste, alvos, histogramas de fonte,
raio, borda, sombra e cor, sequência de foco, hover). Script:
`scratchpad/design_audit.py` (fora do repositório, por regra desta etapa).

Classificação de cada achado: **BUG · INCONSISTÊNCIA · UX · RESPONSIVIDADE ·
ACESSIBILIDADE · DESIGN SYSTEM · MELHORIA OPCIONAL**, com prioridade P0–P3,
impacto, frequência, esforço e risco.

---

## 1. Executive Summary

**O que a medição confirma como sólido** (não é opinião):

- Zero overflow horizontal em 36/36 combinações página × viewport
  (`scrollWidth == clientWidth` na seção de rolagem).
- Zero colisões entre irmãos consecutivos em 36/36 (o detector varre todo
  contêiner vertical do `main`). As duas sobreposições da rodada anterior
  não voltaram.
- Cabeçalho idêntico nas seis páginas: H1 29,6px/700, descrição 14px/400,
  primeiro bloco em y=160; gap de 16px entre blocos de topo em 29 das 32
  transições medidas (as 3 exceções são os `stPageLink` do Início, 10px).
- Uma ação primária por página da jornada; todos os botões com 40px, raio
  8px, 14px/550, inclusive os de formulário.
- Contraste ≥ 4,68:1 em todo texto medido; h1/h2 semânticos em todas as
  páginas; anel de foco na barra lateral e em botões, summaries e checkbox.
- Tablet 1024: Revisar empilha (564+564px), filtros de Vagas quebram em duas
  linhas sem truncar, botões a 40px.

**O que ainda seria percebido por um usuário real hoje** (em ordem):

1. **Mobile — a linha de filtros de Vagas trunca**: "Aguard…", "Aderên…"
   (clientWidth 56px para scrollWidth 102px a 390; 46px a 360). *Regressão
   introduzida pela correção de tablet* — a regra `flex: 1 1 30%` vale para
   qualquer largura ≤ 1280 e força três controles por linha no celular. (BUG,
   P1)
2. **Mobile — a barra lateral cobre o conteúdo na primeira abertura** da
   sessão (`aria-expanded=true`, 300px sobre 390, `sidebarCobreMain=true` em
   Início a 390 e 360; nas páginas seguintes da mesma sessão já vem fechada).
   Primeira impressão do produto no celular é a navegação, não a página.
   (RESPONSIVIDADE, P1 — depende de decisão sobre `initial_sidebar_state`)
3. **Foco invisível nos `st.page_link`** — inclusive o CTA principal do
   Início, "Revisar 42 vagas": `outline none`, sem `box-shadow`, medido na
   sequência de Tab. Botões, summaries e a barra têm anel; o link de página
   não. (ACESSIBILIDADE, P1)
4. **1280×800 — Revisar empilha as colunas sem necessidade**: a regra de
   tablet usa `max-width: 1280px` e pega o 1280 exato; o conteúdo tem 980px e
   as colunas caberiam (≈570/380). Resultado: página de 1.289 → 1.732px,
   "Sua candidatura" sai da dobra e o CTA fica em y≈770 de 800. (RESPONSIVIDADE,
   P2 — também introduzido pela correção anterior)
5. **Chips do multiselect continuam índigo por dentro** (`#EEF2FF`/`#4F46E5`)
   com borda cinza — a correção pegou só a borda. O estado misto é pior que
   o original. (INCONSISTÊNCIA / DESIGN SYSTEM, P2)
6. **Candidaturas › "Ver detalhes"** expõe JSON cru num aviso amarelo
   (`["Qual é a sua pretensão salarial?", "Como você conheceu…"]`) e status
   "Perguntas pendentes (legado)" — vocabulário de sistema para o usuário.
   (UX / COPY, P2)
7. **Documentos**: a ordenação por data não muda nada na prática — 273 dos
   590 documentos foram gerados no mesmo minuto de 21/09, na ordem de
   aderência crescente, então a lista continua começando em 65%. Falta o
   desempate por aderência. (UX, P2)
8. **Quatro cinzas de borda** na mesma tela (`#E4E7EC` ×435, `#D0D5DD` ×172,
   `rgba(71,84,103,.2)` ×107, `rgb(118,118,118)` ×45) e **dois raios** para
   contêineres (expander 10px, cartão 8px). (DESIGN SYSTEM, P2)

**Inconsistências no nível do sistema** que continuarão gerando problemas
em telas novas se não virarem token: cor de borda (4 valores), raio de
contêiner (8 vs 10), altura de controle (36/38/40), tamanho de corpo
(14 vs 15,2 vs 16px — três "body"), e a ausência de um componente único
de "lista de valores" (chips em Preferências, textarea em Plataformas e
LinkedIn).

---

## 2. Pages Audited

| Rota | Página | Componentes principais |
|---|---|---|
| `/` (`/inicio`) | Início | cabeçalho, CTA `page_link`, cartão protagonista, 3 seções |
| `/vagas` | Vagas | 5 filtros + "Mais filtros", contagem + chips, 100 cartões com expander |
| `/revisar` | Revisar | filtros, cartão HTML, 1 primário + 2 secundários + 1 terciário, checklist, evidência, "A seguir" |
| `/candidaturas` | Candidaturas | resumo, 11 linhas com selectbox, filtros, dataframe, expander de detalhe |
| `/configuracoes` | Configurações | nav lateral (radio) + 9 seções: Preferências (3 formulários), Automação, Plataformas, LinkedIn, Currículo, Documentos, Respostas, Provedor de IA, Notificações |
| `/documentos` | Currículos e cartas | filtros, dataframe 590 linhas, detalhe com downloads e carta |
| `/naoexiste` | (erro de rota) | diálogo "Page not found" do Streamlit |

Estados cobertos por página: padrão, filtros abertos, expander aberto,
vazio (busca sem resultado), seleção de linha, seções de Configurações,
editor de chips, carregamento (captura a 350ms), rota inexistente.

## 3. Viewports

| Viewport | Classe | Barra | Conteúdo útil | Observação |
|---|---|---|---|---|
| 1600×900 | desktop (referência do projeto) | 300px | 1180px | — |
| 1440×900 | desktop | 300px | 1140px | — |
| 1280×800 | desktop | 300px | 980px | Revisar empilha (indevido) |
| 1024×768 | tablet | 300px (29%) | 724px | empilhado por CSS |
| 390×844 | mobile | overlay 300px | 390px | barra aberta no 1º load |
| 360×800 | mobile | overlay 300px | 360px | idem |

Breakpoints do projeto: só o `@media (max-width: 1280px)` de `_ui.py`
(workspace e filtros). O Streamlit colapsa a barra lateral abaixo de 768px.

---

## 4. Critical Findings

Nenhum P0. Os P1:

| # | Tipo | Página | Achado | Evidência |
|---|---|---|---|---|
| C1 | BUG (regressão) | Vagas, mobile | Filtros truncados: 3 por linha | 390: "Aguardando você" cw 56 / sw 102; "Aderência" 56/59; 360: 46/102. `mobile/390_vagas.png` |
| C2 | RESPONSIVIDADE | todas, mobile | Barra lateral aberta cobre o conteúdo na 1ª abertura | `sidebarCobreMain: true` em 390/inicio e 360/inicio; `aria-expanded=true`, w=300, z 999991; nas páginas seguintes `false` |
| C3 | ACESSIBILIDADE | Início (CTA), Revisar, Candidaturas | `st.page_link` sem indicador de foco | Tab → `stPageLink-NavLink` "Revisar 42 vagas": outline `none 0px`, shadow `none` (4 links no Início) |
| C4 | RESPONSIVIDADE (regressão) | Revisar, 1280 | Colunas empilham a 1280 | H 1289 → 1732; CTA em y≈770/800; `desktop/1280_revisar.png` |

---

## 5. Findings by Page

### Início

Objetivo, ação e hierarquia: corretos. H1 → lede 15,2px → CTA índigo →
`h2.sec` → cartão único (253px, padding 16/24) → duas seções de texto.

| Prio | Tipo | Achado | Evidência | Recomendação |
|---|---|---|---|---|
| P1 | ACESSIBILIDADE | CTA "Revisar 42 vagas" e os 3 `page_link` seguintes sem anel de foco | `teclado.tab[6..9]`: `anel: false` | `[data-testid="stPageLink"] a:focus-visible { outline: 2px solid var(--acao); outline-offset: 2px }` — mesma regra da barra |
| P2 | INCONSISTÊNCIA | `page_link` com 10px acima, contra 16px de todos os outros blocos | `gapsTopo: {10: 3, 16: 8}` — a regra `[data-testid="stPageLink"] { margin-top }` não altera o gap do bloco | aplicar a margem no `stElementContainer` que contém o link, ou aceitar 10 como valor de "link colado ao texto" e registrar como token |
| P2 | RESPONSIVIDADE | 1ª abertura no celular com a barra por cima (C2) | `sidebarCobreMain: true` | `initial_sidebar_state="auto"` (aberta em desktop, fechada em mobile) — decisão |
| P3 | MELHORIA OPCIONAL | Cartão de 253px: `gap: 8px` + `margin-bottom: 0` no markdown deram 6px de folga ao link, mas o cartão cresceu 16px em relação à rodada anterior | `cards[0].h = 253` (antes 237) | se quiser recuperar altura, `gap: 4px` no cartão mantém a folga (6 → 2px é pouco; ficar em 8) — não recomendo mexer |

### Vagas

Objetivo (descoberta) e hierarquia (empresa → cargo → meta → porquê →
conclusão → Detalhes) corretos e uniformes nos 100 cartões (152px, 12/16,
raio 8). Títulos de até 86 caracteres cabem em uma linha a 1440; a 1280 e
1024 quebram em duas (3 casos em 100) sem cortar.

| Prio | Tipo | Achado | Evidência | Recomendação |
|---|---|---|---|---|
| P1 | BUG | Filtros truncados no mobile (C1) | 390: 3 controles por linha, "Aguard…"/"Aderên…" | a regra `.st-key-filtros .stColumn { flex: 1 1 30% }` deve valer só entre 768 e 1280px; abaixo de 768 os controles voltam a 100% |
| P2 | UX | 100 cartões, sem paginação; "100 vagas" quando há mais | H 17.229px; `limit(100)` | "Mostrar mais" (decisão pendente da rodada anterior) |
| P2 | UX (mobile) | Conclusão "97% · Excelente" fica abaixo do porquê, alinhada à direita, em 4ª posição | `mobile/390_vagas.png` | decisão de design mobile (ordem das colunas) |
| P3 | ACESSIBILIDADE | "Detalhes" com 30px de altura no mobile (alvo < 40) | `alvos<40: 114/221` a 390 — 100 summaries + selects | `min-height: 40px` no summary abaixo de 768 |
| P3 | UX | Ícone "?" do checkbox "Incluir descartadas" com 16×16 | `alvosPequenos` | limitação do Streamlit; registrar |
| P3 | DESIGN SYSTEM | Expander "Mais filtros" com raio 10px ao lado de inputs e cartões com 8px | `expanders: radius 10px`, `cards: 8px` | `[data-testid="stExpander"] details { border-radius: var(--raio-p) }` |

Interação: Enter abre o expander (`antes false → depois true`); "Limpar
filtros" restaura o estado (`limpou: true`); estado vazio mostra os chips
ativos e o botão. O teste de "Todas" (conteúdo longo com 400+ vagas) não
completou — o dropdown do selectbox não abriu pelo clique automatizado —
e fica registrado como não verificado, não como aprovado.

### Revisar

A página mais consistente: uma primária (580×40 a 1440), duas secundárias,
uma terciária, checklist em grid, evidência em palavra + número.

| Prio | Tipo | Achado | Evidência | Recomendação |
|---|---|---|---|---|
| P1 | RESPONSIVIDADE (regressão) | Empilha a 1280 (C4) | H 1732 vs 1289 a 1440; conteúdo 980px | `@media (max-width: 1199px)` (ou 1100) para o workspace; manter 1280 só para os filtros de Vagas se necessário |
| P2 | RESPONSIVIDADE | Multiselect de plataformas (dentro de Filtros) trunca "greenhouse" a 17px em 1024 | `clipping: gupy 17/29, greenhouse 17/69` | coluna do multiselect mais larga no expander ou quebra em duas linhas < 1280 |
| P3 | UX | Link `dpo@mtp.com.br` dentro da descrição com 20px de altura | `alvosPequenos` | conteúdo da vaga; registrar |
| P3 | INCONSISTÊNCIA | Expander "Descrição completa"/"Ler carta" com raio 10 vs cartão 8 | `expanders radius 10px` | token único de raio de contêiner |

Hover: primário escurece (`#4F46E5 → #4338CA`), secundário ganha fundo
`rgba(150,176,202,.15)`, summary muda. Foco: anel em todos os controles da
página. Título limpo em "A seguir" confirmado (`titulo_limpo`).

### Candidaturas

| Prio | Tipo | Achado | Evidência | Recomendação |
|---|---|---|---|---|
| P2 | UX / COPY | "Ver detalhes de uma candidatura" mostra o campo `erro` cru: `["Qual é a sua pretensão salarial?", "Como você conheceu…"]` num `st.warning` | `alertas[0]`, `desktop/1440_candidaturas_detalhes.png` | quando `erro` for uma lista JSON de perguntas, renderizar como "N perguntas ficaram sem resposta: …" em lista; texto técnico só em nível 3 |
| P2 | COPY | Status "Perguntas pendentes (legado)" e "Enviada (legado)" aparecem no filtro padrão "Envios e atenção" | 6 de 11 linhas visíveis no histórico | ou tirar os legados do filtro padrão, ou rótulo sem "(legado)" na tabela e a explicação no detalhe |
| P2 | UX | Mesma vaga duas vezes no histórico (Stone 21/09 e 16/09, ambas "Envio não confirmado") | tabela | agrupar por vaga ou marcar "2 registros" |
| P3 | ACESSIBILIDADE | 11 selectbox com label colapsada; nome acessível vem do valor ("Selected Sem resposta ainda") | `labelsColapsadas: 15` | `aria-label` já existe; registrar |
| P3 | INCONSISTÊNCIA | Único lugar com `box-shadow` (`rgba(0,0,0,.08) 1px 2px 8px`, a toolbar do dataframe) | `sombras` | Streamlit; registrar |
| P3 | RESPONSIVIDADE | A 360 o valor do selectbox de detalhe trunca (241/271) | `clipping` 360 | aceitável (ellipsis), registrar |

Estado vazio da busca: `_ui.vazio` ("Nenhuma candidatura com esses filtros")
sem ação de limpar — inconsistente com Vagas, que ganhou "Limpar filtros". (P3)

### Configurações

| Prio | Tipo | Achado | Evidência | Recomendação |
|---|---|---|---|---|
| P2 | INCONSISTÊNCIA | Chips do multiselect: fundo `#EEF2FF`, texto índigo, borda cinza — meio corrigido | `chipsMultiselect: bg rgb(238,242,255), color rgb(79,70,229), border rgb(208,213,221)` | a regra precisa cobrir `span[data-baseweb="tag"]` **e** seus filhos com `!important`, ou usar `.stMultiSelect [data-baseweb="tag"] { background: var(--fundo) !important; color: var(--txt-1) !important }` |
| P2 | UX | Preferências: 2.397px com três formulários e duas pretensões (8.000 / 7.000–13.000) | H 2397; `config_fim` | decisão pendente (#4/#16 da rodada anterior) |
| P2 | RESPONSIVIDADE | Documentos (como seção) trunca "Todas as plataformas" a 114px a 1440 e 77px a 1024 | `config_Documentos.clipping`, `1024/documentos clipping 77/124` | a linha de filtros da biblioteca em 3 colunas não cabe na coluna de conteúdo (~700px); quebrar em duas linhas dentro de Configurações |
| P2 | UX | Editor de chips: caixa com rolagem interna de 154px para 40/103 itens; chips truncados a 128px ("Analista de Busines…") | `clipping sh 269 / ch 154` | `max-height: none` no `[data-baseweb=select]` dentro dos expanders "Editar"; chips com `max-width: none` |
| P2 | INCONSISTÊNCIA | Plataformas e LinkedIn usam textarea "um por linha"; Preferências usa resumo + chips | `config_plataformas.png` | um componente de lista de valores |
| P3 | ACESSIBILIDADE | 8 botões sem nome acessível (−/+ do `number_input`) | `botoesSemNome: stNumberInputStepDown/Up ×8` | Streamlit; registrar |
| P3 | ACESSIBILIDADE | "Link to heading" (âncora do `####`) é focável e invisível; ordem de headings h1 → h4 → h2 ("Análise do perfil" em LinkedIn) | `teclado.tab[7]`, `headings` | `h4 a { display: none }` já feito para h1/h2; estender; usar `h2`/`h3` para os títulos de seção |
| P3 | DESIGN SYSTEM | `number_input` com 36px ao lado de `text_input` 40px | `inputs: INPUT 36` | `min-height: 40px` também no `.stNumberInput input` |
| P3 | UX | Multiselect "Setores de interesse" (Descobrir empresas) trunca 8 de 8 opções a 128px quando aberto | `clipping` em 5 viewports | `max-width: none` nas tags |
| P3 | RESPONSIVIDADE (mobile) | Nav de 9 itens vira lista de 350px acima do conteúdo | `mobile/390_configuracoes.png` | selectbox abaixo de 768 — decisão de design |

### Documentos

| Prio | Tipo | Achado | Evidência | Recomendação |
|---|---|---|---|---|
| P2 | UX | Ordem "mais recente primeiro" é inócua: 273 documentos do mesmo minuto (21/09 20:04) em ordem de aderência crescente | `gerado_em` 20:04:25.316 / .205 / .072…; 1ª linha 65% | desempate por aderência desc (`key=(gerado_em.date(), score)`) |
| P2 | UX | Carta em `text_area` editável sem salvar | `inputs: TEXTAREA 318` | só-leitura |
| P2 | RESPONSIVIDADE | Dataframe mostra 2 de 7 colunas a 1024 e a 390, com rolagem horizontal interna sem indicação; a 390 a toolbar do dataframe cobre o fim da legenda ("5 es…") | `tablet/1024_documentos.png`, `mobile/390_documentos.png` | `column_config` com larguras menores; ocultar Plataforma/À mão < 1280 (decisão) |
| P3 | ACESSIBILIDADE | Tab entra 7× na canvas do grid antes de sair | `teclado.tab[13..19]: data-grid-canvas` | Streamlit; registrar |

---

## 6. Cross-page Consistency

| Componente | Início | Vagas | Revisar | Candidaturas | Configurações | Documentos | Inconsistência |
|---|---|---|---|---|---|---|---|
| H1 | 29,6/700 | = | = | = | = | = | nenhuma |
| Descrição | (lede 15,2) | 14/400 | = | = | = | = | Início usa `lede` 15,2px no lugar da descrição — justificado (é a frase de ação) |
| Rótulo de seção | h2 12,48/650 | — | = | = | h4 16,3/600 | — | Configurações usa `####` (h4 16px) para o mesmo papel de `h2.sec` (12,5px caixa-alta) |
| Cartão | 16/24, r8, `rgba(71,84,103,.2)` | 12/16, r8, idem | `.cartao` 16/24, r8, idem | — | — | — | consistente (2 densidades nomeadas) |
| Expander | — | r10, 38px; "Detalhes" sem borda | r10 | r10 | r10 / sem borda ("Editar") | — | raio 10 vs 8 dos cartões; dois estilos (caixa / link) por intenção |
| Botão | — | sec 40 | prim/sec/terc 40 | sec 40 | prim/sec/form 40 | prim/sec 40 | consistente |
| Input | — | 40 | 40 | 40 | **36** (number) / 40 | 40 | number_input |
| Badge | — | 12,8/550 r6 | = | = (âmbar) | — | — | consistente |
| Chip de valor | — | badge cinza | — | — | multiselect índigo | — | dois "chips" |
| Link de texto | page_link cinza | — | `a` índigo sublinhado | page_link | `a` índigo | — | page_link não tem foco; `a` do markdown ganhou índigo |
| Estado vazio | — | `_ui.vazio` + Limpar | — | `_ui.vazio` sem ação | `_ui.vazio` (Respostas) | `_ui.vazio` sem ação | ação de recuperação só em Vagas |
| Alerta | — | — | — | `st.warning` com JSON | `st.success` sem fundo, r0 | — | alerta reestilizado (fundo transparente) em Configurações, amarelo padrão em Candidaturas |
| Lista de valores | — | — | — | — | chips (Pref.) / textarea (Plat., LinkedIn) | — | dois padrões |
| Tabela | — | — | — | dataframe 430px | (Documentos) | dataframe 560px | alturas diferentes (430 vs 560) para a mesma tabela-modelo |

## 7. Responsive Audit

| Viewport | Página | Achado | Tipo | Prio |
|---|---|---|---|---|
| 1280 | Revisar | empilha sem necessidade (C4) | RESPONSIVIDADE | P2 |
| 1280 | Vagas | filtros em duas linhas (3+2) — funciona, mas 1280 caberia os 5 (980px) | MELHORIA | P3 |
| 1024 | Revisar | empilhado; OK. Multiselect de plataformas trunca a 17px | RESPONSIVIDADE | P2 |
| 1024 | Documentos | select 77px "Todas as p…"; tabela 2/7 colunas | RESPONSIVIDADE | P2 |
| 1024 | Configurações | nav 105px + conteúdo 395px; Documentos-seção trunca select | RESPONSIVIDADE | P2 |
| 390/360 | todas | barra aberta no 1º load (C2) | RESPONSIVIDADE | P1 |
| 390/360 | Vagas | filtros truncados (C1) | BUG | P1 |
| 390/360 | Vagas | 114 de 221 alvos < 40px (summaries de 30px) | ACESSIBILIDADE | P3 |
| 390/360 | Documentos | toolbar do dataframe cobre a legenda; 2/7 colunas | RESPONSIVIDADE | P2 |
| 390/360 | Configurações | nav 350px antes do conteúdo | RESPONSIVIDADE | P3 (decisão) |
| 390/360 | Candidaturas | linhas em 3 níveis + select 100%; OK | — | — |
| 390/360 | Início/Revisar | empilham bem; nenhum corte | — | — |

## 8. Accessibility Audit

| Achado | Evidência | Prio |
|---|---|---|
| `st.page_link` sem foco visível (Início ×4, Candidaturas, Configurações) | Tab: `outline none`, `shadow none` | P1 |
| Landmarks: sem `<main>`/`role=main` nem `<nav>` | `landmarks: {main: false, nav: false, header: true}` | P3 (Streamlit) |
| Ordem de headings: h1 → h4 em Configurações; h4 → h2 em LinkedIn | `headings` | P3 |
| Âncora "Link to heading" invisível recebe foco | `teclado.tab[7]` em Configurações | P3 |
| 8 botões sem nome (number_input) | `botoesSemNome` | P3 (Streamlit) |
| Labels colapsadas em filtros (Vagas 5, Candidaturas 15, Documentos 2, Configurações 4) — nome acessível pelo `aria-label`/valor | `labelsColapsadas` | P3 |
| Alvos < 24px: ícones "?" 16px, toolbar do dataframe 22px, link no texto da vaga 20px | `alvosPequenos` | P3 |
| Foco do `text_input`/`selectbox` medido como "sem anel" no próprio `input` — o Streamlit desenha a borda no contêiner; visualmente há indicação (borda índigo) | screenshots de foco | verificado, OK |
| Enter em summary abre; Esc fecha dropdown (`esc_fechou: true`); Space no checkbox alterna (Documentos `false → true`); sem keyboard trap (Tab chega ao `BODY` e reinicia) | `tecladoInteracoes` | OK |
| Contraste: mínimo 4,68 (metadados 12,8px `#667085` sobre `#F7F8FA`) | `contrasteBaixo: []` em 6/6 | OK |
| Diálogo "Page not found" em inglês, produto em português | `rota_inexistente` | P3 (Streamlit) |

## 9. Design System Audit

Componentes encontrados e variações medidas a 1440:

| Componente | Variações | Veredito |
|---|---|---|
| Botão | primary / secondary / tertiary / primaryFormSubmit / secondaryFormSubmit / headerNoPadding (28px, Streamlit) — todos 40px, 14/550, r8, pad 4/12 (tertiary pad 0) | consistente |
| Input | text 40, select 40, number **36**, textarea 130/318, multiselect 40–156 | 1 exceção |
| Cartão | container 12/16 (lista) · container e `.cartao` 16/24 (protagonista) · r8 · borda `rgba(71,84,103,.2)` | consistente, 2 densidades |
| Expander | caixa: borda 1px, **r10**, summary 38px · link: sem borda, summary 30px | raio diverge do cartão |
| Badge `.bdg` | 12,8/550, 24px, r6, neutro/ok/aviso/erro | consistente |
| Chip de multiselect | 28px, r6, **fundo índigo + borda cinza** | fora do sistema |
| Alerta | Configurações: fundo transparente, r0 (reestilizado) · Candidaturas: amarelo padrão | 2 estilos |
| Tabela | dataframe 430 / 560px, toolbar 22px | altura ad hoc |
| Filtro | text_input + selectbox + multiselect na mesma linha, labels colapsadas | consistente; trunca < 1280 |
| Seção | `h2.sec` 12,48/650 caixa-alta, margem 32/12 · Configurações `h4` 16,3/600 | 2 estilos |
| Estado vazio | `_ui.vazio` tracejado, 130px | consistente; ação só em Vagas |
| Link | `a` markdown índigo sublinhado · `page_link` cinza sem sublinhado · link-button | 3 aparências, papéis diferentes — aceitável; foco falta no page_link |
| Nav lateral | Streamlit + radio estilizado em Configurações | consistente |
| Status | ponto colorido (barra, Início, "● Preparada") · badge (histórico) | 2 formas por contexto — aceitável |

## 10. Typography Audit

Histograma de (tamanho/peso) nos textos visíveis, 6 páginas a 1440:

| Token observado | Valor | Ocorrências | Uso |
|---|---|---|---|
| body | 14px/400 | 1.664 | texto corrente, descrições, metadados de cartão |
| meta | 12,8px/400 | 555 | `.vaga-meta`, `.meta-linha`, captions |
| control | 14px/550 | 505 | botões, summaries, badges |
| meta-strong | 12,8px/550 | 429 | badges, palavras de eixo |
| body-st | **15,2px/400** | 228 | `<p>` do markdown do Streamlit (Início "11 enviadas", Revisar, Candidaturas) |
| body-st-2 | **16px/400** | 223 | células/inputs do Streamlit |
| label | 12,8px/600 | 29 | labels de widget |
| card-title | 16,8px/600 | 100 | `.vaga-titulo` (lista) |
| protagonist-title | 20,48/600 (Revisar) · 20,8/650 (Início) | 2 | **duas variantes** |
| section | 12,48px/650 | 8 | `h2.sec` |
| h1 | 29,6px/700 | 6 | `.pg-titulo` |
| h4 | 16,32px/600 | 1/seção | Configurações |
| exceção | 13,12px/400 | 3 | não identificado (provável toolbar) |

Problemas: três tamanhos de "corpo" (14 / 15,2 / 16) na mesma tela;
título de protagonista em duas variantes (600 vs 650, 20,48 vs 20,8);
títulos de seção em dois sistemas (`h2.sec` vs `h4`). Nenhum texto < 12px;
nenhum contraste < 4,5.

## 11. Color Audit

Ocorrências (texto/borda/fundo) somadas nas 6 páginas a 1440:

| Papel | Valor | Ocorrências | Observação |
|---|---|---|---|
| text-2 (corpo) | `#475467` | 9.775 | herdado pela maioria |
| text-3 (meta) | `#667085` | 1.307 | |
| text-1 (título) | `#101828` | 700 | |
| primary | `#4F46E5` | 900 txt / 731 bd / 9 bg | 90% das ocorrências são **chips de multiselect e nav** em Configurações — não ação |
| primary-hover | `#4338CA` | hover | OK |
| primary-soft | `#EEF2FF` | 178 | nav ativa e chips |
| success | `#067647` | 147 | conclusão "Excelente", ✓ |
| warning | `#B54708` | 7 | ⚠, ponto de automação |
| border-1 | `#E4E7EC` | 441 | `.eixo`, `.check-linha`, traços |
| border-2 | `#D0D5DD` | 342 | chips, `.ader-barra` |
| border-container | `rgba(71,84,103,.2)` | 325 | container e `.cartao` |
| border-st | `rgb(118,118,118)` | 47 | inputs do Streamlit (select) |
| surface | `#FFFFFF` | 622 | |
| background | `#F7F8FA` | 14 | |

Problemas: **quatro bordas cinza** para o mesmo papel; índigo em 900
textos que não são ação (chips); segundo azul eliminado (0 ocorrências de
`rgb(0,84,163)`).

## 12. Spacing Audit

| Contexto | Valores medidos | Ocorrências | Exceções |
|---|---|---|---|
| Gap entre blocos de topo | 16px | 29 | 10px (page_link, Início ×3); 17px (Documentos, 1) |
| Padding de cartão | 12/16 (lista), 16/24 (protagonista) | 100 + 2 | — |
| Padding de botão | 4/12 | todos | tertiary 0 |
| Padding do main | 60 / 80 / 160 (top/lado/bottom) | 6 | mobile 60/16/160 |
| Seção (`h2.sec`) | margem 32 acima / 12 abaixo | 8 | — |
| Linha de checklist / eixo | 8px vertical | — | — |
| Linha de candidatura | 12px vertical | 11 | — |
| Cartão → "Detalhes" | 8px | 100 | — |
| Rodapé do main | 160px | 6 | espaço morto de 160px no fim de toda página (Streamlit) — a 390 são 19% da tela |

Escala efetiva: 4 · 8 · 12 · 16 · 24 · 32 · 60 · 80 · 160. As exceções sem
justificativa são o 10px dos `page_link` e o 17px de Documentos (arredondamento
do dataframe).

## 13. Interaction Audit

| Interação | Resultado | Feedback visual |
|---|---|---|
| Hover primário | `#4F46E5 → #4338CA` | sim |
| Hover secundário | fundo `rgba(150,176,202,.15)` | sim |
| Hover nav lateral | muda fundo | sim |
| Hover summary | muda | sim (lista: neutralizado ao abrir) |
| Foco botão/summary/checkbox/barra | anel `rgba(79,70,229,.5)` / outline 2px | sim |
| Foco `page_link` | **nenhum** | não (C3) |
| Foco input/select | borda índigo no contêiner | sim |
| Enter em summary | abre | sim |
| Esc em dropdown | fecha | sim |
| Space em checkbox | alterna | sim |
| "Limpar filtros" | zera 8 chaves e recarrega | sim (lista volta) |
| Selecionar linha (dataframe) | detalhe aparece abaixo | sim, mas a 590 linhas o detalhe fica fora da dobra |
| Marcar desfecho (selectbox) | grava on_change | **sem confirmação visível** — só o valor no select |
| Disabled ("Refazer configuração" sem o checkbox) | texto a 40% de opacidade, cursor `not-allowed` | sim |
| Loading | tela cinza vazia ~0,9–1,3s até o título; sem esqueleto | Streamlit; aceitável nesta latência |

## 14. Empty / Loading / Error States

| Página | Vazio | Loading | Erro |
|---|---|---|---|
| Início | "Nada precisa de você agora." (texto) | cinza 1,3s | `st.error` de banco + `st.info` |
| Vagas | `_ui.vazio` + chips ativos + **Limpar filtros** | cinza 0,9s | — |
| Revisar | `_ui.vazio` (fila vazia) | 1,1s | — |
| Candidaturas | `_ui.vazio` sem ação | 1,0s | detalhe: `st.warning` com JSON cru |
| Configurações | Respostas: `_ui.vazio` explicativo · Currículo: `st.warning` orientando | 0,9s | `st.error` por seção |
| Documentos | `_ui.vazio` "Limpe a busca" sem ação | 0,9–1,2s | — |
| Rota inexistente | — | — | diálogo "Page not found" em inglês, volta ao Início |

Becos sem saída: Candidaturas e Documentos vazios pedem para "limpar" sem
oferecer o botão. Loading sem esqueleto é padrão do Streamlit.

---

## 15. Priority Matrix

| # | Priority | Page | Problem | Evidence | Impact | Frequency | Effort | Risk | Recommendation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | P1 | Vagas (mobile) | Filtros truncados, 3 por linha (regressão) | 390: cw 56 / sw 102 | alto | 1 página, todo mobile | S | baixo | limitar `flex: 1 1 30%` a `min-width: 768px` |
| 2 | P1 | todas (mobile) | Barra aberta sobre o conteúdo no 1º load | `sidebarCobreMain` 390/360 | alto | sistêmico (1ª abertura) | S | baixo | `initial_sidebar_state="auto"` — decisão |
| 3 | P1 | Início, Candidaturas, Config. | `page_link` sem foco visível (inclui o CTA) | Tab: outline none | alto (teclado) | 3 páginas | S | baixo | `:focus-visible` como na barra |
| 4 | P2 | Revisar (1280) | Empilha a 1280 (regressão) | H 1732; CTA y 770/800 | médio | 1 viewport | S | baixo | breakpoint 1199px |
| 5 | P2 | Configurações | Chips índigo com borda cinza (meio corrigido) | `chipsMultiselect` | médio | 1 página, 143 chips | S | baixo | regra com `!important` no tag e filhos |
| 6 | P2 | Candidaturas | JSON cru no aviso; "(legado)" no filtro padrão | `alertas[0]` | médio | 1 página | S | baixo | renderizar lista; rótulo sem "(legado)" |
| 7 | P2 | Documentos | Ordem por data inócua (273 no mesmo minuto) | `gerado_em` | médio | 1 página | S | baixo | desempate por aderência desc |
| 8 | P2 | Sistema | 4 bordas cinza; raio 10 (expander) vs 8 (cartão) | histogramas | médio | sistêmico | S | baixo | tokens `--borda` único + `details { border-radius: var(--raio-p) }` |
| 9 | P2 | Configurações › Documentos, Documentos 1024 | Select "Todas as plataformas" truncado (114 / 77px) | clipping | médio | 2 contextos | S | baixo | quebrar filtros < 1280 |
| 10 | P2 | Configurações | Editor de chips com rolagem interna e chips truncados | sh 269 / ch 154 | médio | 1 página | S | baixo | `max-height: none`; tags sem `max-width` |
| 11 | P2 | Documentos (1024/390) | 2 de 7 colunas visíveis, rolagem sem indicação; toolbar sobre a legenda | screenshots | médio | 2 viewports | M | médio | larguras de coluna / ocultar colunas — decisão |
| 12 | P2 | Revisar (1024) | Multiselect de plataformas trunca a 17px | clipping | baixo | 1 viewport | S | baixo | coluna mais larga no expander |
| 13 | P2 | Configurações | Plataformas/LinkedIn em textarea vs chips | screenshots | médio | 2 seções | M | médio | mesmo componente de lista |
| 14 | P2 | Candidaturas, Documentos | Vazio sem "Limpar" | `vazios` | baixo | 2 páginas | S | baixo | mesmo padrão de Vagas |
| 15 | P2 | Sistema | Três "body" (14 / 15,2 / 16) e dois títulos de protagonista | `fontes` | médio | sistêmico | S | baixo | `p { font-size: var(--txt) }` no markdown; uma classe de título |
| 16 | P3 | Configurações | `h4` como título de seção; ordem h1→h4→h2; âncora focável | headings | baixo | 1 página | S | baixo | `h2.sec`/`h3`; `h4 a { display:none }` |
| 17 | P3 | Configurações | number_input 36px | inputs | baixo | 1 página | S | baixo | `min-height: 40px` |
| 18 | P3 | Início | `page_link` com 10px acima | gapsTopo | baixo | 1 página | S | baixo | margem no contêiner |
| 19 | P3 | Vagas (mobile) | Summary "Detalhes" 30px | alvos<40 | baixo | 1 página | S | baixo | `min-height: 40px` < 768 |
| 20 | P3 | Candidaturas | Vaga duplicada no histórico | tabela | baixo | 1 página | M | médio | agrupar por vaga |
| 21 | P3 | Sistema | Alerta com dois estilos (transparente vs amarelo) | `alertas` | baixo | 2 páginas | S | baixo | um estilo |
| 22 | P3 | Sistema | Rodapé de 160px em toda página | `main.padding` | baixo | sistêmico | S | baixo | reduzir para 64–96 (Streamlit permite via CSS) |
| 23 | P3 | Streamlit | "Page not found" em inglês; landmarks; botões −/+ sem nome; toolbar 22px | — | baixo | — | — | registrar |

## 16. Recommended Fix Order

1. **Regressões da rodada anterior** (#1 mobile filtros, #4 Revisar 1280) —
   são 2 linhas de CSS e desfazem dano que a própria correção causou.
2. **Foco do `page_link`** (#3) — 3 linhas de CSS; o CTA principal precisa
   ser alcançável por teclado com indicação.
3. **Chips índigo** (#5), **raio/borda** (#8), **number_input** (#17),
   **body 15,2/16** (#15) — tokens; resolvem o "sistema implícito" de uma vez.
4. **Candidaturas** (#6, #14) e **Documentos** (#7, #14) — copy e ordenação,
   sem mudar dado.
5. **Truncamentos < 1280** (#9, #10, #12) — CSS local.
6. **Decisões**: barra no mobile (#2), colunas do dataframe (#11), lista de
   valores unificada (#13), nav de Configurações no mobile.

## 17. Design Tokens

Derivados do que existe em `ui/_ui.py` e do que a medição encontrou:

| Token | Valor observado | Ocorrências (1440, 6 páginas) | Exceções |
|---|---|---|---|
| `color.primary` | `#4F46E5` | 900 txt / 731 bd | 90% em chips e nav (não ação) |
| `color.primary.hover` | `#4338CA` | hover | — |
| `color.primary.soft` | `#EEF2FF` | 178 | — |
| `color.text.1` | `#101828` | 700 | — |
| `color.text.2` | `#475467` | 9.775 | — |
| `color.text.3` | `#667085` | 1.307 | — |
| `color.border` | `#E4E7EC` | 441 | `#D0D5DD` (342), `rgba(71,84,103,.2)` (325), `rgb(118,118,118)` (47) — **4 valores para 1 papel** |
| `color.surface` | `#FFFFFF` | 622 | — |
| `color.background` | `#F7F8FA` | 14 | — |
| `color.success` | `#067647` | 147 | — |
| `color.warning` | `#B54708` | 7 | — |
| `color.error` | `#B42318` | (não visível nas capturas) | — |
| `space.xs` | 4 | gap de cartão | — |
| `space.sm` | 8 | linhas, cartão → Detalhes | — |
| `space.md` | 12 | linha de candidatura, seção abaixo | — |
| `space.lg` | 16 | gap entre blocos (29) | 10 (3), 17 (1) |
| `space.xl` | 24 | padding lateral de cartão | — |
| `space.2xl` | 32 | acima de seção | — |
| `radius.sm` | 6 | badges, chips (601) | — |
| `radius.md` | 8 | botões, inputs, cartões (267) | — |
| `radius.lg` | 10 | expanders (112) | **sem papel próprio** |
| `control.height.md` | 40 | botões, inputs, selects | number 36, header 28 |
| `type.h1` | 29,6/700 | 6 | — |
| `type.section` | 12,48/650 caixa-alta | 8 | h4 16,3/600 em Configurações |
| `type.card-title` | 16,8/600 | 100 | — |
| `type.protagonist-title` | 20,8/650 | 1 | 20,48/600 (Revisar) |
| `type.body` | 14/400 | 1.664 | 15,2/400 (228), 16/400 (223) |
| `type.control` | 14/550 | 505 | — |
| `type.meta` | 12,8/400 | 555 | — |
| `type.label` | 12,8/600 | 29 | — |

## 18. Evidence / Measurements

- `data/screenshots/design-audit/metricas.json` — 36 entradas página×viewport
  + 2 blocos de interação (1440 e 390). Campos: `viewport, scroll, main,
  sidebar, sidebarCobreMain, tipo, fontes, headings, landmarks, blocos,
  gapsTopo, colisoes, clipping, foraDaTela, zindex, botoes, inputs, cards,
  cartaoHtml, badges, chipsMultiselect, expanders, links, alertas, tabelas,
  contrasteBaixo, alvosPequenos, alvosMobile, alvosTotal, botoesSemNome,
  labelsColapsadas, cursorPointerFaltando, radii, bordas, sombras, cores,
  azuis, titulosLongos, tituloMaisLongo, vazios, excecoes, teclado,
  tecladoInteracoes, hover, sidebarAoCarregar, semSidebar`.
- Screenshots: `desktop/1600_*`, `1440_*`, `1280_*` (+ `_loading`,
  `_mais_filtros`, `_detalhes`, `_vazio`, `_filtros`, `_perguntas`, `_carta`,
  `_fim`, `config_*`, `config_editar`, `documentos_selecionado`,
  `documentos_vazio`, `rota_inexistente`, `candidaturas_detalhes`),
  `tablet/1024_*`, `mobile/390_*`, `360_*` (+ `_sem_sidebar` no Início).
- Pranchas de comparação: `_prancha_1.png` (chips, filtros mobile, Revisar
  1280), `_prancha_tablet.png`, `_prancha_mobile.png`, `_prancha_estados.png`.
- Tempo até o título/conteúdo (1440, cache quente): Início 1,3s; Vagas 0,9s;
  Revisar 1,1s; Candidaturas 1,0s; Configurações 0,9s; Documentos 1,2s.
- Não verificado (o teste automatizado não completou): lista de Vagas com
  status "Todas" (400+ cartões, títulos mais longos que os 86 caracteres da
  lista padrão). Fica como pendência, não como aprovação.


---

# IMPLEMENTATION ROUND 1 — 21/09/2026

Ordem executada: regressões → foco do `page_link` → barra no mobile → tokens
(borda, raio, altura, corpo) → UX (Candidaturas, Documentos, vazios) →
polish responsivo (truncamentos, editor de chips, chips, dataframe). Sem
redesign, sem mudança de dado ou regra. Cada grupo foi validado com o mesmo
script da auditoria; a pasta `design-audit_antes/` guarda o estado inicial.

| ID | Problema | Alteração | Arquivos | Antes | Depois | Validação |
|---|---|---|---|---|---|---|
| C1 | Filtros de Vagas truncados no mobile (regressão) | Regra de 3 por linha limitada a `768–1159px`; abaixo de 768 o Streamlit empilha a 100% | `ui/_ui.py` | 390: cw 56 / sw 102 | clipping 0 em 390 e 360; controles a 358/328px | `metricas.json` 390/vagas, 360/vagas; `mobile/390_vagas.png` |
| C4 | Revisar empilhava a 1280 (regressão) | Breakpoint calculado pelo conteúdo: 330 + 520 + gap = 880px → `max-width: 1159px` (880 + 300 barra + 160 padding) | `ui/_ui.py` | H 1732, CTA y≈770 | H 1286, duas colunas (≈570/380); 1024 continua empilhado (H 1729) | 1280/revisar, 1024/revisar |
| C3 | `st.page_link` sem foco visível (inclui o CTA) | `:focus-visible` com outline 2px índigo; no CTA (`.st-key-cta`) anel por sombra, como os botões | `ui/_ui.py` | Tab: outline none, shadow none | 8/8 page_links com anel; Shift+Tab volta à barra | `teclado.tab` 1440/inicio; `desktop/1440_inicio_foco_cta.png` |
| C2 | Barra lateral cobria o conteúdo na 1ª carga mobile | `initial_sidebar_state="auto"` (aberta ≥ 768, fechada abaixo). Medido antes: com `"expanded"` **toda** carga nova no celular abria a barra; só fechá-la uma vez a mantinha fechada na sessão | `ui/app.py` | `sidebarCobreMain: true` 390/360 | `false`; desktop segue aberta (w=300) | 390/inicio, 360/inicio, 1440/inicio; navegação por link e por URL |
| DS-1 | 4 cinzas de borda | `theme.borderColor = "#D0D5DD"` (container, input, select, expander, dataframe) — `rgba(71,84,103,.2)` e `rgb(118,118,118)` deixam de existir nos componentes nativos; `.cartao` e expander em `--borda-forte`; `--borda` (#E4E7EC) fica para traços | `.streamlit/config.toml`, `ui/_ui.py` | 4 valores | 2 papéis: contêiner/controle `#D0D5DD`, traço `#E4E7EC` (restam 7–18 `rgb(118,118,118)` em bordas internas do select do baseweb) | histograma `bordas` |
| DS-2 | Raio 10 (expander) vs 8 | `--raio: 8px`, `theme.baseRadius = "8px"`, expander em `--raio-p` | idem | {6, 8, 10} | {6, 8} | histograma `radii` 6/6 páginas |
| DS-3 | `number_input` 36px | `min-height: 40px` no input e no contêiner | `ui/_ui.py` | 36 | 40 | `inputs` 1440/configuracoes |
| DS-4 | Três "body" (14 / 15,2 / 16) e dois títulos de protagonista | `--txt: .875rem` (os `<p>` do markdown passam a 14px); título de Revisar usa `.destaque-titulo`; "A seguir" usa `.meta-linha`. O 16px restante é o ícone Material, não texto. A barra lateral **ficou** em 15,2px por regra própria — a normalização do corpo não é dela | `ui/_ui.py`, `ui/pages/5_Aplicar.py` | 15,2 ×228; 20,48/600 | 14/400 ×1.891; destaque 20,8/650 nas duas páginas; barra 15,2 | `fontes`, `tipo.destaque` |
| UX-1 | JSON cru no aviso de Candidaturas | `_perguntas_do_erro`: lista JSON vira "N perguntas ficaram sem resposta:" + itens; outro texto continua no `st.warning` | `ui/pages/4_Candidaturas.py` | `["Qual é a sua pretensão…"]` em amarelo | lista em markdown; `alertas: []` | `desktop/1440_candidaturas_detalhes_depois.png` |
| UX-2 | "(legado)" no filtro padrão | `_rotulo_usuario` tira o sufixo na tabela, no selectbox e no badge de detalhe. O rótulo do catálogo **não** mudou: `test_todo_legado_esta_catalogado_com_rotulo` exige o sufixo para o relatório do panorama | `ui/pages/4_Candidaturas.py` | "Perguntas pendentes (legado)" | "Perguntas pendentes" | texto da tabela sem "legado" |
| UX-3 | Ordenação de Documentos inócua | Chave `(tem data, data.date(), score)` desc — dentro do mesmo dia, maior aderência primeiro; timestamp intacto | `ui/_documentos.py` | 1ª linha 65% | 1ª linha 97% (Stone), 92%, 88% | `tablet/1024_documentos.png` |
| UX-4 | Vazios sem ação em Candidaturas e Documentos | Filtros com chave + "Limpar filtros" (callback zera), como em Vagas; em Candidaturas só aparece se algum filtro saiu do padrão | `ui/pages/4_Candidaturas.py`, `ui/_documentos.py` | texto "limpe a busca" | botão terciário | `interacoes` 1440 |
| R-1 | Select "Todas as plataformas" truncado (Configurações › Documentos 114px; 1024 77px) | Contêiner `filtros-docs-embutido` (busca em 100%, os outros dois em 45%) quando a biblioteca é seção; `filtros-docs` quebra em 2 no tablet | `ui/_documentos.py`, `ui/_ui.py` | cw 114 / sw 124 | clipping 0 | `config_Documentos.clipping`, 1024/documentos |
| R-2 | Multiselect de plataformas em Revisar a 17px (1024) | Contêiner `filtros-revisar`: 2 por linha entre 768 e 1159 | `ui/pages/5_Aplicar.py`, `ui/_ui.py` | 3 truncados | 0 | 1024/revisar |
| R-3 | Editor de chips com teto de 154px e chips a 128px | `max-height: none` no `[data-baseweb=select] > div` dentro de `.st-key-prefs`; tags sem `max-width` | `ui/_ui.py` | sh 269 / ch 154 | h 337, sem rolagem interna; 0 truncados nos 40 chips | medição direta; `desktop/1440_config_editar_depois.png` |
| R-4 | Chips "meio corrigidos" (fundo índigo, borda cinza) | Removida a regra antiga (linha ~426) que pintava `[data-baseweb=tag]` de índigo — era ela que sobrevivia à primeira correção; chip = `--fundo` / `--txt-1` / `--borda-forte` | `ui/_ui.py` | bg `#EEF2FF`, texto `#4F46E5` | bg `#F7F8FA`, texto `#101828`, borda `#D0D5DD`; × sem sobreposição | `chipsMultiselect`; medição label × ícone |
| R-5 | Toolbar do dataframe sobre a legenda a 390 | `padding-top: 36px` na grade e toolbar em `top: 2px` abaixo de 768 | `ui/_ui.py` | toolbar top 365 < legenda bottom 381 | 383 > 381 (`sobrepoe: false`, contexto com toque) | medição direta 390 |
| R-6 | Dataframe de Documentos com 2 de 7 colunas visíveis | Colunas em ordem de prioridade (empresa, vaga, aderência, data, plataforma, carta, à mão) e larguras numéricas (150/260/80/95/95/60/60) | `ui/_documentos.py` | 2 colunas a 724px | 4 colunas a 724px; a 358px continuam 2 (rolagem da grade) | `tabelas.colunas` 1024/390 |

## Remaining Issues

| Prio | Página | Achado | Motivo de ficar |
|---|---|---|---|
| P2 (decisão) | Vagas | 100 cartões sem paginação; "100 vagas" quando há mais | muda estrutura |
| P2 (decisão) | Configurações | Preferências com três formulários e duas pretensões (8.000 vs 7.000–13.000) | precisa da fonte de verdade |
| P2 (decisão) | Configurações | Plataformas e LinkedIn em textarea; Preferências em chips | componente único de lista |
| P2 (decisão) | Documentos | 2 de 7 colunas a 390 (rolagem interna da grade sem indicador) | representação mobile |
| P3 | Configurações (1024) | Selects de diversidade em 3 colunas truncam a 57px | fora do lote |
| P3 | Configurações | Multiselect "Setores" (dentro de Descobrir, fechado) com teto de 154px e opções a 128px | só aparece ao abrir; fora de `.st-key-prefs` |
| P3 | Candidaturas (360) | Valor do selectbox de detalhe com reticências (241/271) | aceitável |
| P3 | Candidaturas | Mesma vaga duas vezes no histórico | agrupar é mudança do que se apresenta |
| P3 | Início | `page_link` com 9–11px acima (gap dos blocos é 16) | a margem do link não altera o gap do bloco |
| P3 | Configurações | `h4` como título de seção; âncora "Link to heading" focável; ordem h1→h4→h2 | fora do lote |
| P3 | Sistema | Rodapé de 160px; alerta com dois estilos; landmarks; botões −/+ sem nome; "Page not found" em inglês | Streamlit / fora do lote |
| — | Vagas | Lista com status "Todas" (400+ cartões) não verificada pelo automatizado | pendência de teste, não aprovação |

## New Regressions

**0.** Comparação `design-audit_antes` → `design-audit` em 30 combinações
(1440, 1280, 1024, 390, 360 × 6 páginas): colisões 0 → 0, elementos fora da
tela 0 → 0, overflow horizontal 0 → 0, clipping nunca maior que antes,
`sidebarCobreMain` nunca passou de false para true. Alturas: Início −13px,
Revisar −3 (1440) e −446 (1280), Candidaturas −6, Configurações −41,
Vagas e Documentos iguais a 1440.

Dois efeitos intermediários que **não** chegaram ao resultado, porque a
medição pegou antes da rodada final: (1) com `--txt` em 14px os rótulos da
barra lateral (que são `<p>` de markdown) caíram de 15,2 para 14px —
revertido com regra própria da barra; (2) a primeira versão de "chips sem
truncar" (`overflow: visible`) fazia o rótulo passar por cima do × —
substituída por `max-width: none` no rótulo e verificada (0 sobreposições
em 40 chips).

## Validation

- Viewports: 1600×900, 1440×900, 1280×800, 1024×768, 390×844, 360×800.
- Suíte: `ruff check .` limpo; `pytest` (unit + e2e) verde, exceto os dois
  testes de prompt já conhecidos (pretensão salarial, decisão pendente).
- Script de auditoria rodado 3 vezes (após regressões/foco/sidebar, após
  tokens/UX/polish, e final); `metricas.json` e screenshots regenerados;
  comparação com `design-audit_antes/metricas.json`.
- Verificações diretas além do script: sidebar em 1ª carga vs navegação
  (390, 360, 1440); Tab/Shift+Tab em Início, Candidaturas e Configurações;
  toolbar do dataframe com `has_touch`; chips (cor, sobreposição, teto);
  select embutido em Configurações › Documentos.
