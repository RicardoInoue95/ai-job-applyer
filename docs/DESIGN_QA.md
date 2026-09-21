# DESIGN QA REPORT — 21/09/2026

Auditoria de UI/UX com Playwright: 6 páginas (Início, Vagas, Revisar,
Candidaturas, Configurações, Documentos) × 6 viewports (1440×900, 1600×900,
1920×1080, 1024×768, 390×844, 360×800), com inspeção de DOM, computed styles,
medições e interação (filtros, expanders, seleção de linha, navegação por
teclado). Capturas em `data/screenshots/qa/<largura>/`, medições em
`data/screenshots/qa/medidas.json` e `overflow.json`. Script:
`scripts/auditoria_ui.py` (a pasta `qa_antes/` guarda a primeira rodada).

Toda recomendação segue **problema → evidência → impacto → recomendação**.
Severidade: P0 crítico · P1 alto · P2 médio · P3 polimento.

---

## Resumo executivo

**Pontos fortes (medidos, não opinião).**

- **Um sistema, não seis páginas.** H1 29,6px/700 em todas; descrição 14px;
  rótulo de seção 12,5px/650 caixa-alta; primeiro bloco sempre em y=160 após
  o cabeçalho; gap entre blocos de topo 16px em 100% das medições; largura de
  conteúdo 1180px (1600/1920) e 1140px (1440), centrada. Um único índigo
  (`rgb(79,70,229)`) em 5 das 6 páginas.
- **Hierarquia de ação clara.** Uma primária por tela (Início: "Revisar 42
  vagas"; Revisar: "Abrir candidatura" 580×40), secundárias em par,
  terciária como link. Todos os botões 40px, raio 8px.
- **Contraste.** Nenhum texto abaixo de 4,5:1 em Início, Vagas, Revisar,
  Candidaturas e Documentos (menor medido: 4,68 em metadados 12,8px).
- **Sem overflow horizontal** em nenhum viewport (`scrollWidth == clientWidth`
  na seção de rolagem em 36/36 medições).
- **Mobile funciona sem estratégia dedicada**: colunas empilham, botões
  ocupam a largura, nada é cortado.

**Principais problemas.**

1. **Dois defeitos visuais confirmados por medição** (sobreposição): no
   cartão "Próximo passo" do Início a linha "✓ Currículo · ✓ Carta" invade o
   link "Revisar candidatura" em 10px (bottom 496 > top 486, em 1600 e 390);
   em Vagas › Detalhes os chips de tecnologia cobrem a última linha de eixo
   ("Localização") em 16px (chip top 621 < eixo bottom 637).
2. **Configurações › Preferências contradiz a si mesma**: "Pretensão salarial
   mínima R$ 8.000" no topo e, 1.900px abaixo, outro bloco "Pretensão
   salarial — Mínimo 7.000 / Alvo 10.000 / Máximo 13.000". Dois mínimos,
   dois botões "Salvar", uma seção de 2.522px com três formulários.
3. **Resíduos do assistente no modo ajuste**: "Voltar / Avançar / Pular" em
   6 das 9 seções, com "Avançar" em índigo competindo com a ação real, e uma
   legenda que pede para ignorá-los.
4. **Textos que prometem o que o produto não faz**: "LinkedIn Easy Apply —
   automatizar o Easy Apply (até 10 vagas/dia)" (o produto trata LinkedIn
   como manual por invariante); Currículo bloqueado por "Configure um
   provedor de IA na Etapa 1" (o sistema roda sem IA por desenho).
5. **Tablet (1024) quebra o workspace de Revisar**: barra lateral fixa de
   300px deixa 724px; a coluna "Sua candidatura" fica com 195px, os
   checklists quebram em 3 linhas e "Já me candidatei" vira botão de 59px em
   duas linhas.
6. **Mobile abre com a barra lateral por cima do conteúdo**
   (`initial_sidebar_state="expanded"`): em 12/12 capturas a 390/360 a
   sidebar (300px) cobre a página e intercepta cliques até ser fechada.

**Maiores oportunidades.** Vagas com 100 cartões (16.800px, 148px cada) sem
paginação; Candidaturas › Histórico com 300 registros dos quais 11 são
envios; Detalhes repete a lista de tecnologias em chips e em texto; Revisar
repete o ponto de atenção duas vezes na mesma tela.

**Inconsistências sistêmicas.** Três estilos de "cartão de vaga" (padding
16/24, 16/18,4 e 12/16; raio 8 e 10; borda `rgba(71,84,103,.2)` e
`#E4E7EC`); botão de formulário 16px/400 contra 14px/550 dos demais; chips
de multiselect em índigo (cor de ação usada em 143 itens que não são ação);
nenhum heading semântico (`h1`–`h3`) em cinco páginas.

---

## Início

**Objetivo**: "o que eu faço agora?". **Ação principal**: "Revisar 42
vagas". Identificável em < 3 s: sim — é o único índigo acima da dobra e o
número está no botão. Nível 1 (saudação, número, CTA, cartão) domina; nível 2
(candidaturas, automação) abaixo; nível 3 ausente. Correto.

**P1**

- **Sobreposição no cartão protagonista.** Evidência: última linha do
  markdown ("✓ Currículo · ✓ Carta") ocupa y 476–496 e o `stPageLink`
  começa em 486 — 10px de invasão, medido a 1600 e a 390. Causa: o container
  `.st-key-proximo` tem `gap: 4px` e o markdown do Streamlit carrega margem
  negativa no fim. Impacto: o único link do cartão fica visualmente colado
  ao texto; em mobile o toque acerta os dois. Recomendação: separar o link
  do texto com margem própria (`margin-top: var(--e3)` no link e sem
  depender do gap do container).

**P2**

- **"Ver candidaturas" e "Configurar automação" com 10px de folga** contra
  16px em todo o resto (blocos em y=681 e 852, `gapAntes: 10`). Impacto:
  ritmo vertical quebra só nos dois links. Recomendação: mesmo espaçamento
  dos demais blocos.
- **Cartão de 237px para seis linhas de conteúdo.** Evidência: padding
  16/24 + gap 4 + margens de parágrafo. Comparado ao cartão de Revisar
  (212px com badge e meta a mais). Recomendação: aproximar dos 200px —
  eliminar a margem negativa e a linha vazia entre "✓" e o link (mesma
  correção do P1).

**P3**

- Ponto âmbar em "Ativa" (Automação) — deliberado (envio em seu nome pede
  atenção), mas é a única vez que âmbar significa "ligado" e não "cuidado".
  Registrar; não mudar sem decisão.

---

## Vagas

**Objetivo**: descoberta e triagem. **Ação principal**: escanear e abrir
Detalhes / Revisar. Hierarquia empresa → cargo → local/modalidade →
conclusão → ação: correta e consistente nos 100 cartões (16,8px/600 cargo,
14px empresa, 12,8px meta).

**P1**

- **Chips sobrepõem a última linha de "Detalhes".** Evidência: com o
  expander aberto, eixo "Localização" em y 605–637 e primeiro chip em
  621–646 (`sobrepoe: true`, a 1600). Causa: `.st-key-lista … { gap: 0 }`
  também zera o gap do bloco interno do expander, e o markdown sem `<p>`
  não reserva altura. Impacto: texto ilegível na única área de evidência da
  página. Recomendação: restringir o `gap: 0` ao cartão (não aos filhos do
  expander) e dar margem superior ao bloco de chips.
- **21 vagas com "motivos" em frase viram chips de tecnologia.** Evidência:
  `score_breakdown_json.motivos_positivos` de versão antiga do scorer contém
  frases ("Forte alinhamento tecnológico com Databricks, SQL, …"); `aderencia`
  as trata como tecnologias → chips com 869px de largura (`largos` a 390 e
  1024: right=1233 em main de 724) e `porque` = "Forte aderência em Forte
  alinhamento tecnológico…". Impacto: overflow horizontal dentro do cartão e
  frase quebrada — hoje só em status `erro`/antigos, mas aparece ao escolher
  "Todas". Recomendação: em `aderencia.analisar`, tratar motivo com espaço
  e mais de ~30 caracteres como frase (vai para `porque`, não para
  `cobertas`), ou re-pontuar as 21.

**P2**

- **100 cartões sem paginação.** Evidência: lista de 16.801px, 148px por
  cartão, `limit(100)` na consulta e legenda "100 vagas" quando o acervo tem
  mais. Impacto: 18 telas de rolagem; o número mente por omissão. Recomendação:
  "Mostrar mais" a cada 25 e legenda "100 de N".
- **Estado vazio esconde os filtros ativos e não oferece saída.** Evidência:
  com busca "zzzzqqq" + 80%+, a caixa diz "Tente afrouxar a busca, o status
  ou a aderência" — os chips de filtro ativo não são renderizados (o
  `st.stop()` vem antes) e não há "Limpar filtros". Recomendação: renderizar
  a linha de filtros ativos antes do vazio e um link "Limpar filtros".
- **Detalhes repete a lista de tecnologias.** Evidência: chips "✓ Python ✓
  SQL ✓ Snowflake…" e, logo abaixo, "A vaga pede: Python, SQL, Snowflake,
  BigQuery…" — 9 dos 12 itens iguais. Recomendação: manter só os chips
  (cobertas) + "Não cita" (faltam); remover a linha "A vaga pede".
- **Tablet 1024: cinco filtros em colunas de 80–145px.** Evidência:
  `truncados`: "Aguardando você" (scrollWidth 102 / clientWidth 50),
  "Aderência" (59/27), "Modalidade", "Plataforma" — todos com reticências.
  Recomendação: abaixo de ~1200px, quebrar a linha de filtros em 2+3 (CSS
  em `.stHorizontalBlock`, sem mudar o código da página).
- **Mobile: conclusão "97% · Excelente" cai para depois do "porquê".**
  Evidência: coluna direita empilha abaixo da esquerda; o número que decide
  fica em 4ª posição, alinhado à direita. Exige decisão de design (não há
  estratégia mobile definida) — registrar.

**P3**

- Alvo de clique de "Detalhes" com 22px de altura (mínimo recomendado 24).
- Ao abrir, o `summary` ganha fundo cinza em toda a largura (estado
  aberto/hover padrão do Streamlit) — destoa do link discreto fechado.
- Ícone de ajuda do checkbox "Incluir descartadas" com 16×16px.

---

## Revisar

**Objetivo**: decidir. **Ação principal**: "Abrir candidatura" (580×40,
índigo, única). As cinco perguntas (qual vaga, por que combina, problema,
pronta?, o que faço) respondidas acima da dobra a 1440+. É a melhor página.

**P1**

- **Tablet 1024 quebra o workspace.** Evidência: sidebar fixa 300px; main
  724px; colunas 1,5/1 → coluna direita 195px; "adaptado para esta vaga" em
  2 linhas, "nenhuma pergunta adicional" em 3, "Carta gerada" desalinhado
  (larguras fixas 6,5rem no checklist); "Já me candidatei"/"Não tenho
  interesse" com 59px de altura em duas linhas (`botoes: h 59`). Impacto: a
  prova de "está pronto" vira ruído justamente na tela de decisão.
  Recomendação: abaixo de ~1200px empilhar as duas colunas (CSS na
  `stHorizontalBlock` da página) e trocar as larguras fixas do checklist
  por grid flexível.

**P2**

- **Ponto de atenção duas vezes na mesma tela.** Evidência: cartão "⚠ Pede
  PySpark, que não está no seu currículo." (y 436) e, em "Por que combina",
  "⚠ Não cita: PySpark" (y 552). Recomendação: em "Por que combina" listar
  só o que o cartão não disse (os demais itens de `faltam`), ou suprimir
  quando for o mesmo.
- **"A seguir" mostra o código de requisição.** Evidência: "94% · 12473727 |
  Analista de Dados PL — Almaviva" — usa `prox['titulo']` cru, enquanto o
  cartão usa `titulo_limpo`. Recomendação: `fila.titulo_exibicao` também ali.
- **"Descrição completa da vaga" colada ao "⚠ Não cita".** Evidência:
  expander a 8px do aviso, 32px abaixo dos chips; mesmo peso visual de
  "Filtros" no topo. Recomendação: espaçamento de seção (24px) antes do
  expander.

**P3**

- "Por que combina": palavra em x=560 e percentual em x=1020 — 460px de
  distância entre as duas metades da mesma informação. Aproximar o número
  da palavra (`grid-template-columns: 110px 120px 1fr` com número à
  esquerda) reduz o vai-e-vem do olho.
- Filtros (multiselect de plataformas) truncam "greenhouse" a 17px em 1024.

---

## Candidaturas

**Objetivo**: acompanhar. Linguagem honesta confirmada ("Nenhuma resposta
identificada ainda"). Lista de enviadas: 77px por linha, traço entre linhas,
data presente. Correto.

**P2**

- **Histórico mostra 300 registros para 11 envios.** Evidência: tabela com
  "300 registros (máx. 300)", filtro padrão "Todos os status"; 11 primeiras
  linhas visíveis: 2 "Envio não confirmado", 1 "Não conseguimos concluir",
  8 "Preparada, não enviada" de 18/08 (simulações). Impacto: a página de
  acompanhamento vira registro de sistema; o número contradiz "11 enviadas"
  três seções acima. Recomendação: filtro padrão em "enviadas + atenção";
  "Todos" continua disponível.
- **Mesma vaga duas vezes no histórico** (Stone, 21/09 e 16/09, ambas
  "Envio não confirmado"). É dado (dois registros de candidatura), mas na
  tela parece duplicata. Recomendação: agrupar por vaga na tabela ou
  mostrar só o último registro por vaga, com contagem.
- **"Ver detalhes de uma candidatura"**: expander com selectbox de 300
  opções. Recomendação: seleção pela própria tabela (`on_select`), como em
  Documentos — mesma interação para a mesma tarefa.

**P3**

- Selectbox "Resposta obtida" com 318px a 1600 para textos de ≤ 40
  caracteres; a coluna 3,4/1,6 está bem, mas o campo poderia ter largura
  fixa menor.
- Toolbar do dataframe (colunas/CSV/busca/fullscreen) com botões de 22px —
  padrão do Streamlit; registrar.

---

## Configurações

**Objetivo**: gerenciar. Navegação lateral funciona (9 seções, 12,5px
apoio, selecionada em índigo suave). O problema está dentro das seções.

**P1**

- **Duas pretensões salariais na mesma seção, com valores diferentes.**
  Evidência: "Pretensão salarial mínima (R$ por mês) 8000" em y≈540 e
  "Pretensão salarial — Mínimo 7000 · Alvo 10000 · Máximo 13000 · Conversão
  CLT→PJ 1,30" em y≈2.100 (`config_fim.png`), cada uma com seu "Salvar".
  Impacto: o usuário não sabe qual vale (a suíte também não: os dois testes
  de `test_prompts.py` falham por isso). Recomendação: uma pretensão só —
  a faixa (mín/alvo/máx) é a que o prompt e o `salario.responder` usam;
  o campo simples de `coleta.salario_esperado` vira leitura da faixa ou some
  da tela. Exige confirmação do usuário sobre qual fonte é a verdadeira.
- **Botões do assistente no modo ajuste.** Evidência: "Voltar/Avançar"
  (Preferências, Plataformas, Provedor), "Voltar" (Currículo), "Voltar/Pular"
  (Notificações); "Avançar" é `primary` índigo — em Preferências há então
  dois índigos ("Salvar preferências" e "Avançar") a 300px um do outro; e a
  legenda "os botões Voltar/Próximo pertencem ao assistente inicial e podem
  ser ignorados" aparece em 6 seções. Impacto: ação principal ambígua e
  interface que se desculpa. Recomendação: as funções de etapa recebem um
  parâmetro `modo` e não desenham os botões de navegação fora do assistente.
- **Copy que promete automação do LinkedIn.** Evidência: seção "LinkedIn
  Easy Apply — Configure o LinkedIn para automatizar o Easy Apply (até 10
  vagas/dia)". O produto trata LinkedIn como manual (invariante 6, tabela de
  plataformas). Impacto: confiança — a tela contradiz o comportamento.
  Recomendação: "LinkedIn — sessão salva para coletar vagas; o envio é seu"
  e retirar "até 10 vagas/dia".
- **Currículo bloqueado por IA.** Evidência: "Configure um provedor de IA na
  Etapa 1 primeiro." em vermelho, sem mostrar o currículo atual (nome,
  data, nº de experiências). O projeto roda sem chave por desenho. Impacto:
  a seção parece quebrada, e "Etapa 1" não existe na navegação. Recomendação:
  mostrar o mestre atual (arquivo, atualizado em, N experiências) sempre;
  a *substituição* pode exigir IA, e a mensagem deve dizer "Provedor de IA"
  (nome da seção), não "Etapa 1".

**P2**

- **Preferências é uma página de 2.522px com três formulários** ("Salvar
  preferências", "Salvar dados pessoais", "Salvar pretensão") e dois
  divisores. Recomendação: "Dados pessoais" e "Pretensão" viram seções da
  navegação lateral (a estrutura já existe) — Preferências fica com cargos,
  cidades, modalidade e filtros avançados.
- **Editor de chips: 40/103 itens em índigo com rolagem interna.** Evidência:
  `config_editar.png` — caixa de 156px, chips truncados ("Analista de
  Busines…"), todos na cor de ação. Recomendação: chips neutros (cinza) com
  o "×" visível, caixa sem limite de altura dentro do expander; para 103
  cidades, campo de busca acima (já existe: digitar filtra).
- **"Cidades onde você aceita presencial ou híbrido: São Paulo, Remoto,
  Remote, Barueri…"** — "Remoto"/"Remote" não são cidades (ficam na lista
  por compatibilidade e `locais_alvo()` os descarta). Recomendação: ocultá-los
  do resumo e do editor (filtrar na tela; não mudar o dado).
- **Nomenclatura**: nav "Plataformas" → título "Gupy"; nav "LinkedIn" →
  "LinkedIn Easy Apply"; nav "Notificações" → "Notificações por E-mail";
  nav "Currículo" → "Currículo" (ok). Recomendação: título da seção igual ao
  item da navegação.
- **Plataformas usa textarea "um por linha"**, Preferências usa chips —
  dois padrões para "lista de valores" a 1 clique de distância.
  Recomendação: chips (resumo + Editar) também em Plataformas e LinkedIn.
- **Dados pessoais exibem CPF, RG e nome dos pais em texto claro** na tela
  e em captura. Uso pessoal, mas qualquer screenshot vaza. Recomendação:
  `type="password"` para CPF/RG com "mostrar", como já é feito para senha.
- **Truncamento no multiselect "Setores de interesse"** (Descobrir
  empresas): "Banco / Serviços Financeiros" 166px em 128px, reticências em
  5 de 8 opções. Padrão do Streamlit; registrar.

**P3**

- 8 botões sem nome acessível (os "−/+" do `number_input` e limpar
  multiselect) — Streamlit.
- Ícones de ajuda (?) com 16px; "Link to heading" âncora invisível com foco
  em azul `rgb(0,84,163)` — segundo azul da paleta.
- "Refazer configuração" desabilitado com texto a 40% de opacidade
  (`rgba(71,84,103,.4)`) — abaixo de 3:1 quando desabilitado; aceitável
  para disabled, registrar.

---

## Documentos

Fora da barra (acessível por Configurações › Documentos e por URL). Tabela
densa (35px/linha, 16 linhas visíveis), busca + plataforma + "só com carta"
na mesma linha. Coerente com "área de suporte".

**P2**

- **Ordenação crescente por aderência.** Evidência: primeiras linhas 65%,
  65%, 66%… (`documentos_sel.png`). Impacto: o que mais se reaproveita (as
  melhores, as mais recentes) está no fim. Recomendação: ordenar por
  `gerado_em` desc (ou aderência desc), mantendo o cabeçalho clicável.
- **Carta em `text_area` editável sem ação de salvar.** Evidência: campo
  com alça de redimensionar e cursor de edição; nada grava. Impacto: parece
  que se edita e se perde. Recomendação: exibição só-leitura (`_ui.previa`
  ou `st.code`/markdown) + "Baixar carta".

**P3**

- "Baixar currículo" em índigo: é a única ação, aceitável — mas é a única
  tela onde *download* é primário. Registrar para consistência (em Revisar
  é link terciário).

---

## Design System (transversal)

| Tema | Evidência | Recomendação |
|---|---|---|
| **Cartão de vaga: três variantes** | Início `16px 24px`/raio 8/borda `rgba(71,84,103,.2)`; Revisar `.cartao` `16px 18.4px`/raio 10/borda `#E4E7EC`; Vagas `12px 16px`/raio 8 | Um token de cartão (`--raio` 8 ou 10, borda única) e duas densidades nomeadas: protagonista (16/24) e lista (12/16) |
| **Título do protagonista** | Início `.destaque-titulo` 20,8px/650; Revisar `.vaga-titulo` inline 20,48px/600 | Uma classe só |
| **Botão de formulário** | `primaryFormSubmit`/`secondaryFormSubmit` 16px/400; demais 14px/550 | Regra CSS cobrindo os dois `kind` |
| **Segundo azul** | `rgb(0,84,163)` em links de markdown (Provedor: "OpenAI (ChatGPT)") e âncoras de heading | `a { color: var(--acao) }` no markdown |
| **Índigo em não-ação** | 143 chips de multiselect (Configurações › Editar), 1.554 ocorrências medidas na página | Chips neutros; índigo só em botão/seleção/foco |
| **Expander aberto** | `summary` ganha fundo cinza em toda a largura (Vagas › Detalhes, Configurações › Editar); fechado é link discreto | Neutralizar o fundo do `summary` aberto nas listas |
| **Espaçamento** | 16px entre blocos em 100% das medições; exceções: `stPageLink` com 10px (Início ×2); "Descrição completa" a 8px do aviso (Revisar) | Alinhar os três casos a 16/24 |
| **Inputs** | `text_input` 38px vs `selectbox` 40px na mesma linha (Vagas, Documentos) | 2px de diferença visível na linha de filtros; igualar por CSS |
| **Empty state** | Vagas e Configurações › Respostas usam `_ui.vazio` (tracejado); Candidaturas usa `st.caption("Nenhuma candidatura…")` | Um componente |
| **Headings semânticos** | 0 `h1`/`h2` em 5 páginas; Configurações tem só `h4` | `.pg-titulo` como `<h1>`, `.sec` como `<h2>` (mesmo CSS) |

---

## Responsividade

| Viewport | Estado | Problemas |
|---|---|---|
| **1920×1080** | ok | Conteúdo 1180px centrado (x=520); 220px de margem de cada lado; nada a corrigir |
| **1600×900** | ok | Referência |
| **1440×900** | ok | Conteúdo 1140px; filtros de Vagas em colunas 149–268px sem truncar |
| **1024×768** | **P1** | Sidebar fixa 300px (29% da tela). Revisar: coluna direita 195px, botões em 2 linhas (59px). Vagas: 4 dos 5 filtros truncados com reticências. Configurações: nav 105px + conteúdo 395px |
| **390×844** | **P1 / decisão** | Sidebar aberta por cima do conteúdo ao carregar (`initial_sidebar_state="expanded"`), interceptando cliques; fechada, o layout empilha bem. Vagas: 5 controles empilhados = 300px antes da lista; conclusão do cartão cai abaixo do "porquê". Início: sobreposição ✓/link (mesma do desktop). Configurações: nav vira lista de 350px acima do conteúdo |
| **360×800** | idem 390 | Sem cortes; mesmos pontos |

Não há estratégia mobile definida no projeto. Os itens de 390/360 além da
sidebar e da sobreposição **exigem decisão de design** (ordem dos filtros,
posição da conclusão no cartão, nav de Configurações como select) e não
devem ser resolvidos por conta própria.

---

## Accessibility

- **Sem headings semânticos**: `.pg-titulo`, `.sec`, `.destaque-titulo` são
  `<div>`. Leitor de tela não tem estrutura. (P2)
- **Foco invisível nos links da barra lateral**: `outline: none`, sem
  `box-shadow` (`foco[0..4]` em todas as páginas). Botões têm anel
  `rgba(79,70,229,.5)`; inputs mudam a borda. (P2)
- **Alvos < 24px**: "Detalhes" (22px de altura), ícones de ajuda (16×16),
  toolbar do dataframe (22×22). (P3)
- **Botões sem nome acessível**: 8 em Configurações (Streamlit). (P3)
- **Labels colapsadas**: 5 filtros em Vagas, 15 selects em Candidaturas, 2
  em Documentos usam placeholder como rótulo; há `aria-label`, então leitor
  de tela lê — mas ao escolher um valor o rótulo visual some (mitigado em
  Vagas pelos chips de filtro ativo). (P3)
- **Contraste**: ok (≥ 4,68) em todo texto normal; disabled a 40% de
  opacidade (aceitável).
- **Navegação por teclado**: Tab percorre barra → conteúdo na ordem visual;
  atalhos do painel React ignoram campos de texto (testado). (ok)

---

## Cross-page consistency

- Vagas e Revisar mostram a cidade curta; **o painel React mostra "São
  Paulo, São Paulo, Brasil"** (`painel_ev_topo.png`). Causa verificada: o
  `run.py` em execução é anterior ao commit que encurta em `fila.local_exibicao`
  (`curl /fila` ainda devolve o formato longo). Some ao reiniciar; o
  "híbrido" minúsculo no painel, não. (P3, operacional)
- Título limpo em Vagas/Revisar/Início; **"A seguir" (Revisar) e o Histórico
  (Candidaturas) mostram o título cru** ("12473727 | …"). (P2)
- "Preparada" aparece como ponto verde em Vagas e como badge "Preparada, não
  enviada" no histórico — mesma coisa, dois desenhos; aceitável (contextos
  diferentes), registrar.
- Terminologia: "Revisar" (nav, botão, cartão) consistente; "Detalhes"
  (Vagas) vs "Ver detalhes de uma candidatura" (Candidaturas) vs "Descrição
  completa" (Revisar) — três rótulos para "nível 2/3". Registrar (P3).
- Modalidade: "Híbrido" capitalizado em Início/Vagas/Revisar; **"híbrido"
  minúsculo no painel React**. (P3)

---

## Matriz de prioridade

Ordenada por impacto × frequência ÷ (esforço + risco). Esforço: S < 1h, M
1–3h, L > 3h.

| # | Prio | Página | Problema | Evidência | Impacto | Recomendação | Esforço |
|---|---|---|---|---|---|---|---|
| 1 | P1 | Vagas | Chips sobrepõem a última linha de eixo em Detalhes | chip top 621 < eixo bottom 637 (1600) | Texto ilegível na única evidência da lista | Limitar `gap:0` ao cartão; margem no bloco de chips | S |
| 2 | P1 | Início | "✓ Currículo · ✓ Carta" invade o link | bottom 496 > top 486 (1600 e 390) | Link colado/ambíguo no protagonista | Margem própria no `stPageLink` | S |
| 3 | P1 | Configurações | Botões Voltar/Avançar/Pular no modo ajuste | 6 seções; "Avançar" índigo a 300px de "Salvar" | Duas primárias; legenda que se desculpa | Etapas não desenham navegação fora do assistente | M |
| 4 | P1 | Configurações | Duas pretensões salariais com valores diferentes | 8.000 (topo) vs 7.000/10.000/13.000 (fim) | Usuário e testes não sabem qual vale | Uma só (a faixa); **exige decisão** | M |
| 5 | P1 | Configurações | Copy "automatizar o Easy Apply (até 10 vagas/dia)" | seção LinkedIn | Contradiz a política do produto | Reescrever: sessão para coleta; envio é seu | S |
| 6 | P1 | Configurações | Currículo bloqueado por IA e sem mostrar o atual | erro vermelho "Etapa 1" | Seção parece quebrada | Mostrar mestre atual; IA só para substituir | M |
| 7 | P1 | Revisar / Vagas | Tablet 1024: colunas e filtros inutilizáveis | col. direita 195px; filtros truncados | Workspace quebra em notebook pequeno | CSS: empilhar < 1200px; checklist flexível | M |
| 8 | P1 | Vagas | Motivos em frase viram chips e quebram o "porquê" | 21 vagas; chip de 869px | Overflow + frase sem sentido | Tratar frase ≠ tecnologia em `aderencia` | S |
| 9 | P1 | Mobile | Sidebar aberta por cima ao carregar | 12/12 capturas 390/360 | Conteúdo inacessível até fechar | `initial_sidebar_state="auto"`; **decisão** (muda desktop? não: auto = expandida em desktop) | S |
| 10 | P2 | Revisar | Ponto de atenção duplicado | y 436 e y 552 | Ruído na tela de decisão | "Não cita" só com o que o cartão não disse | S |
| 11 | P2 | Revisar / Candidaturas | Título cru em "A seguir" e no histórico | "12473727 \| …" | Inconsistência com o resto | `titulo_exibicao` | S |
| 12 | P2 | Vagas | "A vaga pede" repete os chips | 9/12 iguais | Densidade sem informação | Remover a linha | S |
| 13 | P2 | Candidaturas | Histórico com 300 registros para 11 envios | filtro padrão "Todos" | Contradiz o resumo | Padrão "enviadas + atenção" | S |
| 14 | P2 | Vagas | 100 cartões sem paginação; "100 vagas" quando há mais | 16.801px | 18 telas; número enganoso | "Mostrar mais" + "100 de N" | M |
| 15 | P2 | Vagas | Estado vazio sem filtros ativos nem "Limpar" | `vagas_vazio.png` | Beco sem saída | Chips antes do vazio + link limpar | S |
| 16 | P2 | Configurações | Preferências com três formulários (2.522px) | 3 "Salvar" | Qual salva o quê? | Dados pessoais e Pretensão como seções | M |
| 17 | P2 | Configurações | Chips índigo/truncados no editor; "Remoto" em "Cidades" | 143 chips; "Remoto, Remote" | Cor de ação em não-ação; rótulo mente | Chips neutros; ocultar não-cidades | S |
| 18 | P2 | Configurações | Título ≠ item da nav; textarea vs chips | "Gupy", "LinkedIn Easy Apply" | Terminologia | Alinhar títulos; chips em Plataformas | M |
| 19 | P2 | Documentos | Ordem crescente; carta editável sem salvar | 65% primeiro; text_area | Menos útil; engana | Ordenar desc; só-leitura | S |
| 20 | P2 | Sistema | 3 cartões, 2 bordas, 2 raios, 2 títulos de protagonista, botão de form 16/400 | tabela acima | Produto parece 2 sistemas de perto | Tokens: cartão, borda, raio, botão | M |
| 21 | P2 | A11y | Sem headings; foco invisível na nav | 0 h1; outline none | Leitor de tela e teclado | `<h1>/<h2>` com o mesmo CSS; anel de foco na nav | S |
| 22 | P3 | Painel | "híbrido" minúsculo (localização longa some ao reiniciar a API) | `painel_ev_topo.png` | Inconsistente com o webapp | Capitalizar a modalidade no painel | S |
| 23 | P2 | Configurações | CPF/RG em texto claro | `config_meio.png` | Vaza em captura | `type="password"` com mostrar | S |
| 24 | P3 | Vários | Alvos < 24px, summary aberto cinza, 10px em page_links, input 38 vs 40, segundo azul | medições | Polimento | CSS pontual | S |

---

## Critério de sucesso — onde estamos

| Critério | Estado |
|---|---|
| Cada página com finalidade visual clara | ✓ |
| Ação principal identificável | ✓ (exceto Configurações com "Avançar") |
| Sem excesso de informação | parcial — duplicações em Vagas › Detalhes, Revisar, Histórico |
| Sem inconsistências importantes entre páginas | parcial — cartões/bordas/raios; títulos crus |
| Spacing coerente | ✓ (16px em 100%; 3 exceções pontuais) |
| Tipografia com hierarquia | ✓ |
| CTAs com hierarquia | ✓ nas páginas de jornada; ✗ em Configurações |
| Uso de cor controlado | ✓ na jornada; ✗ chips de Configurações |
| Cards só quando necessário | ✓ |
| Filtros fáceis | ✓ a ≥ 1440; ✗ a 1024 |
| Técnico não compete com decisão | ✓ |
| Sem overflow/responsividade evidente | ✗ tablet e sobreposições |
| Produto único | quase — Configurações é a página que mais destoa |
| Calma e profissional | ✓ na jornada |
| Usuário entende o que fazer | ✓ |


---

## Depois — lote implementado em 21/09/2026

Aprovado pelo usuário: P1 completo, P2 de alto impacto, sem redesign. Fora
do lote, por decisão dele: `type="password"` em CPF/RG (prefere máscara
visual, a avaliar), o rótulo "Excelente" (pede comparação visual), a
pretensão salarial duplicada (#4, decisão pendente), a sidebar no mobile
(#9), paginação (#14) e a divisão de Preferências (#16).

Medido com o mesmo script, mesmos viewports:

| Item | Antes | Depois |
|---|---|---|
| Início: "✓ Currículo · ✓ Carta" × link | invasão de 10px | folga de 6px |
| Vagas › Detalhes: chips × último eixo | invasão de 16px | folga de 12px |
| Causa das duas | `margin-bottom:-1rem` do markdown do Streamlit dentro de contêiner com gap reduzido | zerada só nesses contêineres (a versão global deixou toda página 16px mais aberta e foi revertida) |
| Motivos em frase (21 vagas) | chips de 869px; "Forte aderência em Forte alinhamento…" | `_e_frase` separa; a frase vira o `porque` resumido; elementos fora da tela a 390: 2 → 0 |
| ⚠ duplicado em Revisar | cartão + "Não cita: PySpark" | `evidencia` omite o que o ponto de atenção já nomeou |
| Título cru em "A seguir" | "12473727 \| Analista…" | `titulo_limpo` |
| "A vaga pede" em Detalhes | 9/12 repetidos | removido |
| Histórico de Candidaturas | 300 registros, padrão "Todos" | padrão "Envios e atenção"; "(máx. 300)" só quando bate o teto |
| Estado vazio de Vagas | sem filtros ativos nem saída | chips + "Limpar filtros" (filtros com chave; callback zera) |
| Chips de multiselect | índigo | cinza (`--fundo`/`--borda-forte`) |
| Cidades: resumo | "São Paulo, Remoto, Remote, Barueri…" | "Remoto/Remote/Brasil" fora do resumo (seguem no dado) |
| Documentos | ascendente por aderência | mais recente primeiro |
| Cartão de vaga | 3 paddings, raio 8/10, 2 bordas | `.cartao` = container do Streamlit (raio 8, `rgba(71,84,103,.2)`, 16/24) |
| Botão de formulário | 16px/400 | 14px/550 como os demais |
| Segundo azul (links) | `rgb(0,84,163)` em 2 páginas | 0 |
| Headings semânticos | 0 `h1` em 5 páginas | `h1.pg-titulo`, `h2.sec` (mesmo CSS): Início 4, Revisar 4, Candidaturas 3 |
| Foco na barra lateral | `outline: none` | anel 2px índigo em `:focus-visible` |
| Alvo "Detalhes" | 22px | ≥ 24px (alvos < 24 em Vagas: 8 → 1, o "?" do Streamlit) |
| Input 38 vs select 40 | 2px de degrau | `min-height: 40px` |
| Summary aberto | fundo cinza em toda a largura | transparente nas listas |
| Tablet 1024, Revisar | coluna direita 195px; botões 59px | colunas empilhadas (564+564); botões 40px; checklist em grid flexível |
| Tablet 1024, Vagas | 4 filtros truncados | 0 (linha quebra em duas) |
| Configurações: Voltar/Avançar/Pular | 6 seções | 0 no modo ajuste (`_no_assistente()`); legenda de desculpa removida |
| Configurações: LinkedIn | "automatizar o Easy Apply (até 10 vagas/dia)" | "sessão para coletar e analisar o perfil; o envio é seu" |
| Configurações: Currículo | erro vermelho "Etapa 1"; nada sobre o atual | nome, experiências, tecnologias e data; IA só para substituir |
| Títulos de seção | "Gupy", "LinkedIn Easy Apply", "Notificações por E-mail" | iguais aos itens da navegação |
| Painel React | "híbrido" | "Híbrido" |
| Altura de Configurações › Preferências | 2.522px | 2.375px |

Sem regressão: cabeçalho e primeiro bloco continuam em y=160, gap 16px entre
blocos, zero overflow horizontal, contraste inalterado, suíte verde (exceto
os dois testes de prompt que dependem da decisão #4).
