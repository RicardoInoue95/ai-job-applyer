# UX AUDIT

Auditoria de UX/produto — 21/09/2026, sobre o estado depois da rodada 1 de
correções visuais (`DESIGN_AUDIT.md`). Pergunta central: **uma pessoa usando
o AI Job Applier no dia a dia acha o produto fácil, rápido e coerente?**
Diferente da auditoria visual, aqui o objeto é o fluxo: o que a pessoa vê
primeiro, o que decide, o que acontece depois de agir, e o que muda quando o
volume cresce.

Método: navegação com Playwright em 1440×900 e 390×844 (mais as capturas de
360×800 e 1024×768 da auditoria anterior), medição do que fica acima da
dobra, distância entre ação e resultado, tempos, o estado "Todas" de Vagas,
seleção em Documentos, as nove seções de Configurações; leitura do código
dos fluxos que gravam (decisões em Revisar, desfecho em Candidaturas) sem
executá-los — a auditoria não altera dados. Volumes reais do banco:
16.242 vagas (15.316 filtradas, 808 elegíveis em "Todas", 394 na fila,
42 em "precisam de você"), 590 documentos, 356 registros de candidatura,
0 respostas aprendidas. Evidências: `data/screenshots/ux-audit/` e
`medidas_ux.json`.

Sem notas, sem ranking. Cada achado é P0 (impede uso), P1 (atrapalha o fluxo
principal), P2 (fricção relevante) ou P3 (melhoria futura), e cada um diz se
é **técnico** (dá para corrigir sem decidir nada) ou **decisão de produto**.

---

## Executive Summary

O fluxo principal — abrir o sistema → ver quantas vagas pedem decisão →
decidir uma por uma em Revisar → abrir a candidatura no site → marcar o que
fez → acompanhar — está **inteiro e legível**. Em desktop, cada etapa tem uma
tela com uma ação dominante acima da dobra (CTA do Início em y=175, "Abrir
candidatura" em y=481), e a linguagem é a mesma do começo ao fim ("Revisar",
"Preparada", "Enviada", "Sem resposta identificada").

O que atrapalha o dia a dia hoje não está na jornada principal; está nas
**bordas** dela:

1. **"Todas" em Vagas é uma armadilha silenciosa.** Mostra 100 de 808 vagas
   elegíveis, a legenda diz "100 vagas", e as quatro primeiras — todas "100%
   · Excelente" — são **encerradas ou descartadas**, sem nenhum sinal na
   lista (40 das 100 são `encerrada`). Quem abre "Detalhes → Abrir vaga
   original" cai num 404. O status saiu do cartão porque no filtro padrão
   ele é redundante; em "Todas" ele era a única defesa.
2. **Depois de selecionar um documento, o resultado fica fora da tela.** A
   tabela tem 560px; o detalhe (botão "Baixar currículo") aparece em y=918 a
   1440×900 e y=1121 a 390 — abaixo da dobra nos dois. A pessoa marca a
   caixa e nada visível acontece.
3. **Configurações › Preferências é três formulários numa página de 2,6
   telas** (4,1 no celular), com 27 controles, três botões "Salvar" e duas
   pretensões salariais que discordam (8.000 no topo, 7.000–13.000 no fim).
   Quem procura "onde ponho meu salário?" acha dois lugares.
4. **A arquitetura de Configurações tem nomes que não batem com o conteúdo**:
   "Plataformas" só tem Gupy (as empresas do Greenhouse estão em
   Preferências); "Automação" é uma tela de ações (ativar, coletar agora,
   varrer), não de configuração; o corte de 85% que governa o envio automático
   mora em Preferências › Filtros avançados como "Autoaprovação", longe da
   seção Automação que o cita; LinkedIn mistura sessão, busca e uma análise
   de perfil que é funcionalidade, não ajuste.
5. **Mobile é utilizável, mas Revisar inverte a ordem da prova.** A 390 o
   checklist "Sua candidatura" (currículo ✓, carta ✓, formulário ✓) só
   aparece em y=1278 — depois de "Por que combina" (769) e de "A seguir"
   (737). A pessoa decide sem ver que o material está pronto.
6. **Feedback depois de agir é discreto demais nas duas ações que mais
   importam.** Em Revisar, "Já me candidatei" troca a vaga e acrescenta "1
   revisada nesta sessão" + um botão "Desfazer" — não diz *o que* fez com
   *qual* vaga. Em Candidaturas, marcar o desfecho grava sem nenhuma
   confirmação visível (só o valor do seletor muda).

Escala: com os volumes de hoje (42/394/590) tudo responde em ~2–3,5s. Os
tetos silenciosos (`limit(100)` em Vagas, `limit(300)` em Candidaturas) já
são atingidos e a interface não diz. A partir de ~50 candidaturas enviadas,
a lista de seletores "O que aconteceu com cada uma" vira uma tela de 4.000px
sem busca nem ordenação. Documentos escala bem até ~1.000 pela tabela; o que
não escala é a *descoberta* (não há "meus melhores", "desta empresa",
"reaproveitar").

Decisões de produto pendentes (não são bugs): paginação/teto de Vagas,
representação de status em "Todas", divisão de Preferências, componente único
de "lista de valores", o que fazer com 165 registros "Perguntas pendentes" de
junho, e a fonte de verdade da pretensão salarial.

---

## User Journey

| Etapa | Objetivo da pessoa | Tela | Ação principal | Fricções observadas |
|---|---|---|---|---|
| **Descobrir** | "Apareceu algo bom?" | Início → Vagas | ler o número ("42") e o próximo passo; em Vagas, escanear | Início responde em 1 tela (1,2 telas de altura). Vagas: 100 cartões de 152px = 19 telas; sem paginação; "100 vagas" quando há mais; em "Todas", encerradas sem sinal (P1). Busca funciona (Radix → 48 em 1,7s), mas por título/empresa só — não por tecnologia. |
| **Avaliar** | "Combina comigo? Tem pegadinha?" | Revisar (cartão) | ler "96% · Excelente", o porquê, o ⚠ | Decisão rápida em desktop: título, conclusão, atenção e CTA em 298–481px. O ⚠ diz *o que* falta ("Pede PySpark") mas não *quanto pesa* (eliminatório ou desejável?) — a pessoa tem que abrir "Por que combina" para ver que Tecnologias está em 89%. Eixos com 100% em tudo menos um não distinguem "vaga excelente" de "scorer antigo com nota cheia" (as 7 vagas com 100% em "Todas" são exatamente isso). |
| **Preparar** | "Está tudo pronto?" | Revisar (coluna direita) | conferir ✓✓✓, baixar currículo, ler carta | Em desktop a prova está ao lado do cartão (y=286). No celular está em y=1278, depois da evidência e de "A seguir" (P1 mobile). "Ler carta completa" abre um `text_area` editável cujas edições **não são salvas** — parece que se pode ajustar a carta antes de enviar, e não se pode (P2). |
| **Candidatar** | "Vou lá e envio" | site externo (nova aba) + Revisar | "Abrir candidatura" (`target=_blank`), depois "Já me candidatei" | Dois cliques deliberados (abrir e registrar) — honesto, documentado. A fricção é de retorno: ao voltar à aba do produto, a vaga continua na tela sem indicar que foi "aberta"; quem abriu três e voltou não sabe qual marcou. A extensão resolve isso na Gupy (vínculo por aba), o webapp não. |
| **Acompanhar** | "Alguém respondeu? O que ficou pendente?" | Candidaturas | marcar o desfecho por vaga; ver "3 precisam de atenção" | 11 seletores funcionam. "3 precisam de atenção" é texto, não link — onde estão as 3? Só achando "Envio não confirmado" no histórico (y=1284, segunda tela). Marcar desfecho não confirma nada. Histórico traz 165 "Perguntas pendentes" de junho que ninguém vai resolver, misturados aos 11 envios reais. |

Fluxo secundário — **Configurar**: "Uma pessoa que nunca viu o sistema
saberia onde configurar cada coisa?" Parcialmente. Cargos, cidades, provedor,
e-mail e currículo estão onde se espera. Salário, empresas do Greenhouse,
corte de automação e "coletar agora" não.

---

## Page-by-page Analysis

### Início

**Clareza.** Responde às cinco perguntas na primeira tela (1440 e 390): o que
fazer ("Você tem 42 vagas para revisar"), quantas (no texto e no botão),
próximo passo (cartão com empresa, cargo, cidade, conclusão, ⚠, ✓✓), o que
está automatizado ("● Ativa — vagas acima de 85% podem ser enviadas
automaticamente"), onde acompanhar ("Ver candidaturas"). Nada compete com o
CTA: é o único índigo.

**Informação de menos.** "11 enviadas" e "Ainda não identificamos respostas"
— correto e honesto, mas a seção não diz que **3 precisam de atenção**, que
é a única coisa acionável em Candidaturas hoje. O Início mostra o que a pessoa
precisa fazer em Revisar e esconde o que precisa fazer em Candidaturas. (P2,
técnico)

**Informação demais.** Nenhuma. O cartão tem 253px para seis linhas; aceito.

**Carga cognitiva.** Baixa: três números (42, 96%, 11) e um botão.

**Descoberta.** "Revisar candidatura" no cartão e "Revisar 42 vagas" no topo
levam ao mesmo lugar — a mesma vaga é a primeira da fila, então não confunde;
mas o cartão não tem "por que esta" (é a de maior aderência com dossiê). (P3)

**Estados.** Vazio ("Nada precisa de você agora. O coletor segue rodando.")
existe e é bom. Erro de banco: `st.error` + `st.info` com o comando para subir
— correto para uso pessoal. Sem loading próprio (tela cinza ~1s do Streamlit).

**Escala.** Não depende de volume.

### Vagas

**Objetivo.** Descoberta e triagem. **Padrão ao abrir**: "Aguardando você" =
`pronta_envio_manual` + `aprovada` + … (394 na fila) — mas a lista mostra
100, e a legenda diz "100 vagas, por aderência". A pessoa não sabe que há
294 escondidas. (P2, técnico — a legenda; o teto é decisão)

**Busca.** Por título e empresa, com Enter. Funciona e é rápida (1,7s). Não
busca por tecnologia ("Databricks"), que é como a pessoa pensa ("quero as de
Databricks"). (P3, decisão)

**Filtros.** Status, aderência (faixas), modalidade, plataforma na linha;
localização, senioridade e "descartadas" em "Mais filtros". Chips de filtro
ativo + "Limpar filtros" (também no vazio). Um problema de descoberta: o
filtro "Status" começa em "Aguardando você" e a lista de opções tem 11
códigos ("filtrada_4a", "aguardando_resposta", …) com rótulos humanizados —
mas a pessoa não sabe qual escolher para "as que eu já mandei" ou "as que
morreram". (P3)

**Ordenação.** Só por aderência, fixa. Não há "mais recente" — e a coleta
roda a cada 2h; a pessoa que abre à tarde não consegue ver "o que chegou
hoje". (P2, decisão)

**Cartões.** Empresa → cargo → cidade·modalidade·nível → porquê → conclusão →
"Detalhes". 152px cada; "Detalhes" é um link de 24px de altura no desktop
(30 no mobile), discreto por intenção — descobre-se no primeiro cartão. Dentro:
eixos, chips, id/data, "Abrir vaga original" e, para `pendente`, Aprovar/
Descartar. **A ação "Aprovar" só existe dentro de Detalhes** e só para
`pendente` — a pessoa que filtra por "Possibilidade" precisa abrir cada um
para aprovar. (P2, decisão: aprovar em lote existe, mas só como "Aprovar
todas".)

**"Preparada".** Ponto verde discreto à direita; 53 dos 100 cartões o têm.
Serve para "esta já tem dossiê", mas não leva a lugar nenhum: o cartão não
tem "Revisar esta" — a pessoa vê que está preparada e vai à página Revisar
procurá-la na fila de 42 (ou 394, baixando o corte). (P2, técnico)

**"Todas" com 400+.** Testado: 808 elegíveis, 100 renderizadas em 2,2s (mesmo
tempo do padrão — o teto protege o tempo), 19 telas. Problemas de natureza
diferente do "só falta paginar":

- **Mistura épocas e estados sem sinal.** 40 `encerrada`, 1 descartada, 2
  `erro` entre as 100, sem status no cartão. As 7 de "100% · Excelente" são
  scores antigos de vagas mortas. (P1, técnico: mostrar status quando o filtro
  não o fixa)
- **Teto silencioso.** "100 vagas" para 808. (P2, técnico na legenda; decisão
  no teto)
- **Ordenação por aderência favorece o passado**: vagas encerradas com nota
  cheia ficam acima das vivas com 92%. (decisão)

Escalabilidade real (o que muda com o volume):

| Volume | O que acontece hoje |
|---|---|
| 10 | uma tela e meia; ótimo |
| 100 | 19 telas; escaneável só pelos 3 primeiros (a pessoa não rola 19 telas) |
| 400+ | não existe: corta em 100 e mente na legenda; a busca vira a única forma de achar algo |

**Estados.** Vazio com chips e "Limpar filtros": bom. Sem loading próprio.
Erro de banco: `st.error`. Sucesso ("N vagas aprovadas") só no lote.

### Revisar

**Fluxo.** vaga → aderência → candidatura preparada → abrir → decidir.

- **A decisão é rápida?** Em desktop, sim: tudo o que decide está entre
  y=298 e y=593, e a prova (checklist) ao lado em y=286. Tempo de leitura
  estimado por vaga: 10–20s. Em mobile, não: a prova está em y=1278 (1,5
  tela abaixo do CTA).
- **Entende por que combina?** "Forte aderência em Python, SQL e Databricks."
  — sim, em uma frase. O que falta é *grau*: "Forte" vs "Excelente" vs "Cobre"
  já existe no vocabulário, mas o cartão sempre diz "Forte aderência em…"
  para ≥ 75 (é o texto fixo). Vagas de 76% e de 97% recebem a mesma frase. (P2,
  técnico)
- **O alerta de requisito ausente é claro?** "⚠ Pede PySpark, que não está no
  seu currículo." — claro no *que*. Não diz se é eliminatório (`missing_required`)
  ou desejável (`gaps`); o texto é o mesmo nos dois casos, e só o detalhe
  (badge "eliminatória" nas perguntas) distingue. (P2, técnico)
- **"Abrir candidatura" é claramente a próxima ação?** Sim: único índigo,
  580px de largura, y=481. `target=_blank` — abre em aba nova sem avisar
  (o ícone de "open in new" avisa). Ao voltar, nada muda no cartão.
- **Ações secundárias têm peso adequado?** "Já me candidatei" e "Não tenho
  interesse" em par, cinza, abaixo; "Deixar para depois" como link. Adequado.
  Um risco: "Não tenho interesse" (descarta) fica ao lado de "Já me
  candidatei" com o mesmo peso e sem confirmação — um clique errado some com
  a vaga; o "Desfazer última decisão" aparece só depois, no topo, como botão
  cinza. (P2, técnico)
- **Informação que deveria vir antes da decisão?** O **prazo/idade da vaga**
  (coletada há 3 dias ou há 40?) e **se ela ainda existe** — a varredura roda
  a cada 6h, mas o cartão não mostra "verificada há Xh". E as **perguntas do
  formulário** com resposta faltando (o "3 suas" do checklist) só aparecem
  no expander da direita; se a Gupy vai pedir o nome da mãe, é bom saber
  antes de abrir. (P2, decisão)
- **Informação que só deveria aparecer depois?** "A seguir" (3 próximas
  vagas) está acima da dobra em y=681 no desktop, entre "Deixar para depois"
  e "Por que combina". Compete com a decisão atual. (P3) "Descrição completa"
  está no lugar certo (fechada, y=952).

**Filtros.** Slider "Aderência mínima" (0–100) começa no corte de atenção
(85). Baixar para 65 traz as 394. Um toggle "Só com dossiê pronto". Está
atrás de "Filtros" (fechado) — bom, não compete.

**Feedback.** Depois de decidir: a próxima vaga aparece, a legenda vira "41
vagas para revisar · 1 revisada nesta sessão" e surge "Desfazer última
decisão". Não diz "Marcada como enviada: Engenheiro de Dados — MTP". Se a
pessoa piscou, não sabe o que aconteceu. (P2, técnico)

**Estados.** Fila vazia → "Revisão concluída — você revisou N nesta sessão"
ou "Nenhuma vaga com esses filtros". Ficha do formulário: "Lendo o
formulário…" (spinner) e três estados (ok / sem suporte / não consegui ler)
no checklist com "?" — correto. Sem dossiê: "ainda não gerado" — mas o
botão "Abrir candidatura" continua igual, e a pessoa pode abrir uma vaga sem
currículo pronto sem perceber (o toggle "Só com dossiê" está ligado por
padrão, então isso só ocorre ao desligá-lo). (P3)

**Escala.** Uma vaga por vez; independe do volume. Com 394 na fila e sem
ordenação alternativa, a pessoa que quer "as da Radix primeiro" não consegue
(o filtro de plataforma ajuda, o de empresa não existe). (P3, decisão)

### Candidaturas

**Acompanhamento.** "11 enviadas" + frase honesta + "3 precisam de atenção"
+ 11 linhas com seletor + histórico + detalhe. A estrutura é boa para 11.

**Status e datas.** "Enviada em 18/08" em cada linha; tabela com data e hora.
Bom. A **hora** no histórico ("18/08/26 02:26") é ruído para quem acompanha —
mas registra que as simulações rodaram de madrugada, o que explica o que são.

**Identificação.** Empresa (via `nome_exibicao`) e cargo limpo em cada
linha. Bom.

**Descoberta de respostas.** O seletor "Sem resposta ainda ▾" é o único
mecanismo — a pessoa precisa *lembrar de vir aqui* depois de receber um
e-mail. Nada a puxa de volta (a leitura de e-mail não existe; o Início não
avisa "N sem resposta há mais de 15 dias"). (P2, decisão — é o funil manual
já documentado; o custo é esse)

**Itens que precisam de atenção.** "3 precisam de atenção — confirme uma
informação ou verifique se o envio saiu. Estão marcadas como *Envio não
confirmado* no histórico." É um parágrafo apontando para outra seção, 900px
abaixo, sem link nem filtro pré-aplicado. (P1, técnico: a frase deveria
levar às 3)

**Histórico.** Padrão "Envios e atenção" traz 11 envios + 165 "Perguntas
pendentes" (junho) + 118 "Erro" — a maioria de uma época anterior do produto,
com rótulos agora limpos de "(legado)", o que os torna *menos* distinguíveis
dos atuais. O filtro padrão precisa decidir o que é "atenção" de verdade. (P2,
decisão)

**Detalhe** ("Ver detalhes de uma candidatura"): um selectbox com todas as
linhas (até 300) para escolher uma — a tabela acima já tem seleção de linha
em Documentos, aqui não. Duas interações para a mesma tarefa em duas páginas.
(P2, técnico)

**Escala.**

| Volume | "O que aconteceu com cada uma" | Histórico |
|---|---|---|
| 11 | 852px, cabe em uma rolagem; funciona | 300 linhas, teto já atingido e não dito |
| 50 | ~3.900px de seletores, sem busca, sem "só as sem resposta", sem ordenação | ok |
| 100 | ~7.800px; ninguém rola 100 seletores para achar a que respondeu | ok |
| 500 | inviável nesse formato | teto de 300 corta |

A lista de seletores não tem filtro nem agrupamento (por mês, por status de
resposta). É o formato que mais cedo deixa de escalar no produto. (P2,
decisão)

**Estados.** Vazio com "Limpar filtros". Sem feedback ao marcar desfecho
(P2, técnico). Erro do applicator no detalhe: lista de perguntas legível
(corrigido na rodada 1); "Tentar novamente" só para `falha_automacao`/`erro`.

### Configurações

**Arquitetura.** Nove seções: Preferências, Automação, Plataformas, LinkedIn,
Currículo, Documentos, Respostas aprendidas, Provedor de IA, Notificações.
Nav lateral com nomes curtos. "Uma pessoa que nunca viu o sistema saberia
onde configurar cada coisa?"

| Quero configurar… | Onde está | Onde a pessoa procuraria | Veredito |
|---|---|---|---|
| cargos, cidades, modalidade | Preferências | Preferências | ✓ |
| pretensão salarial | Preferências (topo, R$ 8.000) **e** Preferências (fim, faixa 7–13 mil + CLT→PJ) | Preferências | dois lugares que discordam — a segunda é a que o sistema usa |
| corte para envio automático (85%) | Preferências › Filtros avançados › "Autoaprovação (score ≥)" | Automação | nome e lugar errados para o conceito |
| empresas do Greenhouse (47 slugs) | Preferências › expander "Empresas monitoradas no Greenhouse" | Plataformas | Plataformas só tem Gupy |
| empresas/palavras da Gupy | Plataformas (título "Plataformas", conteúdo "Gupy") | Plataformas | ✓, mas a seção promete mais do que tem |
| ligar/desligar envio | Automação | Automação | ✓ |
| coletar agora / varrer encerradas | Automação | "Ações"? Início? | é operação, não configuração |
| sessão do LinkedIn, URL do perfil | LinkedIn | LinkedIn | ✓ |
| analisar meu perfil do LinkedIn | LinkedIn (seção "Análise do perfil", 1.610px) | ? — é uma funcionalidade | escondida em Configurações |
| queries de busca do LinkedIn | LinkedIn ("Salvar queries") | Plataformas | terceiro "Salvar" da mesma tela |
| dados pessoais (CPF, RG, pais, diversidade) | Preferências (2º formulário) | "Dados pessoais" / "Perfil" | não é preferência de busca |
| currículo mestre | Currículo | Currículo | ✓ (agora mostra o atual) |
| currículos gerados | Documentos | Documentos / Candidaturas | ✓ como biblioteca; discutível como "configuração" |
| respostas aprendidas | Respostas aprendidas (vazio: 0) | ✓ | seção vazia por enquanto |
| chave de API | Provedor de IA | ✓ | ✓ |
| e-mail de relatório | Notificações | ✓ | ✓ |

**Ordem.** Preferências → Automação → Plataformas → LinkedIn → Currículo →
Documentos → Respostas → Provedor → Notificações. A justificativa
documentada é "o que muda mais vezes primeiro". Para quem chega, a ordem
lógica de montagem seria Currículo → Preferências → Plataformas/LinkedIn →
Provedor → Automação → Notificações; Documentos e Respostas são consulta, não
configuração. Não há erro, mas a mistura de "ajustar", "operar" e "consultar"
na mesma lista é o que torna a arquitetura difícil de prever. (P2, decisão)

**Seções vazias / longas.** Respostas aprendidas: vazia (0 registros) com
estado explicativo — bom. Automação e Currículo: uma tela. Preferências: 2,6
telas (4,1 no celular), 27 controles, 3 formulários, 3 "Salvar" — o único
lugar do produto onde a pessoa pode preencher um campo e clicar no "Salvar"
errado (cada form salva só o seu). (P1, técnico na apresentação; a divisão
em seções é decisão)

**Repetição de conceitos.** Pretensão (2×); "empresas monitoradas" em duas
seções com dois componentes (chips vs textarea); "Salvar" em três estilos na
mesma tela (Preferências: primário; Dados pessoais e Pretensão: secundário;
LinkedIn: "Salvar e fazer login", "Salvar queries", "Salvar").

**Escondidas.** O corte de automação (85%) e o de revisão (70%) — os dois
números que mais mudam o comportamento do sistema — estão atrás de "Filtros
avançados", dentro de Preferências. (P2, decisão)

**Feedback.** `st.success("✓ Preferências salvas!")` aparece abaixo do
botão e some no próximo rerun; em mobile o botão está em y=1310 e a mensagem
abaixo dele — fora da tela no momento do clique se a pessoa rolou de volta.
Aceitável.

**Estados.** Currículo: "✓ Currículo em uso" + "Substituir"; sem provedor:
aviso orientando (corrigido). Provedor: "Testar conexão" com spinner e
sucesso/erro. Notificações: "Testar e-mail". Automação: "Coletar vagas" com
spinner e resultado. LinkedIn: "Verificar se sessão ainda é válida". Todos
com feedback; nenhum estado deixa a pessoa sem saída.

### Documentos

**Papel.** Biblioteca. Acessível por Configurações › Documentos e por URL;
fora da barra. Correto para um acervo.

**Busca.** Por empresa, cargo ou id, sem acento; 1,7s; "1 de 590 documentos".
Boa. **Filtros**: plataforma e "só com carta". **Ordenação**: data desc com
desempate por aderência (rodada 1) — a lista agora começa em 97%. A tabela
permite ordenar por qualquer coluna clicando no cabeçalho (Streamlit), mas
nada na tela diz isso.

**Identificação.** Empresa, vaga, aderência, data, plataforma, carta, à mão.
Suficiente. Falta o que mais distingue documentos: **perfil** (bi_analyst,
data_engineer…) e **se foi enviado** — "qual currículo eu mandei para a
Stone?" não tem resposta na tabela (o perfil só aparece no detalhe). (P2,
decisão)

**Seleção e abertura.** Caixa da primeira coluna → detalhe abaixo da tabela.
O detalhe aparece em y=918 (1440) e y=1121 (390): **abaixo da dobra nos
dois** — a pessoa marca a caixa e não vê nada acontecer (P1, técnico: rolar
até o detalhe, ou detalhe acima/ao lado da tabela). A carta em `text_area`
editável sem salvar induz a editar (P2).

**Descoberta de relevantes.** Não há "meus melhores", "os que enviei", "os
desta empresa" como atalhos; a busca é o único caminho. Com 590, funciona
para quem sabe o que procura; não ajuda quem quer "um bom currículo de BI
para reaproveitar".

**Escala.**

| Volume | Tabela | Busca | Descoberta |
|---|---|---|---|
| 10 | ok | desnecessária | ok |
| 100 | ok (rolagem interna) | ok | ok |
| 500 (hoje 590) | ok; 16 linhas visíveis; rolagem interna de ~37 telas | ok | fraca: só busca; sem "enviados" nem perfil |
| 1.000 | ok técnico (grid virtualizado); `_carregar` lê ~2.000 arquivos do disco a cada 30s de cache | ok | insuficiente |

A biblioteca escala tecnicamente; o que não escala é achar "o certo" sem
saber o nome. (P3, decisão)

---

## Scalability

| Área | 10 | 50 | 100 | 500 | 1.000 | Natureza do limite |
|---|---|---|---|---|---|---|
| Vagas (lista) | ok | ok | 19 telas; só o topo é escaneado | corta em 100, legenda mente | idem | teto silencioso + ausência de "mais recentes" (decisão) |
| Vagas "Todas" | — | — | mistura encerradas sem sinal | 808 hoje: só 100 visíveis | idem | status ausente no cartão (técnico) + teto (decisão) |
| Revisar | ok (uma por vez) | ok | ok | ok; sem "por empresa" | ok | independe do volume; ordenação única |
| Candidaturas › seletores | ok | ~3.900px, sem filtro | ~7.800px | inviável | inviável | formato (decisão) |
| Candidaturas › histórico | ok | ok | ok | teto de 300 | corta | teto silencioso (técnico na legenda) |
| Documentos | ok | ok | ok | ok | ok técnico; descoberta fraca | descoberta (decisão) |
| Respostas aprendidas | vazio hoje | data_editor ok | ok | ok | pesado para editar | fora do horizonte |
| Configurações › chips | ok | ok (40 cargos) | 103 cidades já cabem sem teto | editor de 103 chips é longo | — | ok após rodada 1 |

---

## Mobile UX

Referência: `design-audit/mobile/390_*.png`, `360_*.png`; medições em
`medidas_ux.json` (390).

| Página | Utilizável? | O que atrapalha |
|---|---|---|
| Início | sim | nada acima da dobra falta; 1,3 telas |
| Vagas | sim, para escanear; ruim para triar | 27 telas (Todas: 26); a conclusão "97% · Excelente" fica abaixo do porquê, alinhada à direita; "Detalhes" 30px; 5 filtros empilhados = 300px antes da lista; "Aprovar" só dentro de Detalhes |
| Revisar | parcialmente | a prova (checklist) em y=1278, depois de "Por que combina" e "A seguir"; "Baixar currículo" e "Ler carta" a 1,5 tela do CTA; o restante decide bem (CTA em 481) |
| Candidaturas | sim | 3,5 telas; cada linha 3 níveis + seletor de 100%; histórico em y=2050; tabela 2 de 5 colunas com rolagem interna |
| Configurações | sim, com esforço | nav de 9 itens = 350px antes do conteúdo (toda troca de seção rola de volta); Preferências 4,1 telas; "Salvar" em y=1310, 2485, 3156; "Testar conexão" e "Testar e-mail" abaixo da dobra |
| Documentos | limitado | tabela 2 de 7 colunas (empresa, vaga) — aderência e data exigem rolar a grade; detalhe em y=1121 após selecionar |

Alvos de toque: botões 40px (ok); summaries 30px; ícones "?" 16px; toolbar
do dataframe 22px; caixas de seleção da grade ~20px. Nada é impossível de
tocar; "Detalhes" e a caixa da tabela são os dois que pedem precisão.

Navegação: barra fechada ao carregar (rodada 1), botão de abrir no canto —
padrão do Streamlit, sem rótulo ("»"). A pessoa que nunca viu pode não saber
que ali está a navegação. (P3, Streamlit)

---

## Consistency

Diferenças **justificadas pela função** (não são problemas): cartão único no
Início e em Revisar vs lista com borda por item em Vagas; "Detalhes" como
link em Vagas vs expanders com borda em Revisar ("Filtros", "Descrição");
download primário em Documentos (única ação) vs terciário em Revisar; badge
de status só no histórico.

Inconsistências **sem motivo**:

| Item | Onde | Diferença |
|---|---|---|
| Escolher um item de uma tabela | Documentos vs Candidaturas | caixa de seleção na linha vs selectbox separado com todas as linhas |
| "Limpar filtros" | Vagas, Candidaturas, Documentos | existe nas três (rodada 1); em Revisar não há (o filtro é um slider + toggle, mas "afrouxe um filtro" no vazio não tem botão) |
| Lista de valores | Preferências (chips) vs Plataformas/LinkedIn (textarea "um por linha") | dois componentes para o mesmo conceito |
| "Salvar" | Preferências: 3 formulários, 1 primário + 2 secundários; LinkedIn: 3 botões com nomes diferentes | a pessoa não sabe qual salva o quê |
| Título de seção | `h2.sec` (12,5px caixa-alta) nas páginas; `####` (h4 16px) em Configurações | dois sistemas |
| Frase de conclusão | "Forte aderência em…" para qualquer score ≥ 75 | a palavra da faixa ("Excelente", "Boa") não entra na frase |
| Contagem | Vagas "100 vagas" (teto), Candidaturas "300 registros (máx. 300)", Documentos "1 de 590" | só Documentos diz o total |
| Ação que abre site externo | Revisar "Abrir candidatura" (primário, aba nova), Vagas "Abrir vaga original" (secundário, dentro de Detalhes), Candidaturas "Ver vaga" (link na tabela) e "Abrir vaga" (botão no detalhe) | quatro rótulos para "abrir a vaga no site" |
| "Aguardando você" (filtro) vs "precisam de você" (fila) vs "precisam da sua atenção" (Início, Candidaturas) | Vagas, Revisar, Início | três formas do mesmo conceito, e "Aguardando você" (394) ≠ "precisam de você" (42) |

---

## Accessibility UX

- **Foco.** Visível em tudo que é interativo (rodada 1). Ordem: barra →
  conteúdo na ordem visual; em Candidaturas o Tab passa pelos 11 seletores
  antes dos filtros do histórico — coerente com a leitura. Em Documentos o
  Tab entra na grade (7 paradas na canvas) antes de chegar ao detalhe.
- **Labels.** Filtros usam placeholder como rótulo, com `aria-label`; ao
  escolher um valor, o rótulo visual some — os chips de filtro ativo (Vagas)
  compensam; em Candidaturas › histórico e Documentos, não.
- **Mensagens.** Português, na voz do produto; exceções: "Page not found" do
  Streamlit; "Selected Sem resposta ainda" como nome acessível dos seletores
  (é o valor, não o rótulo "Resposta obtida").
- **Affordances.** "Detalhes" (link com seta) e "Ler carta completa" (expander)
  são reconhecíveis. O que engana: `text_area` da carta (parece editável e
  não salva); "3 precisam de atenção" (parece link, é texto); a caixa da
  primeira coluna da tabela (nada indica que é o gatilho do detalhe, exceto a
  legenda).
- **Headings.** h1/h2 nas páginas; Configurações pula para h4 e tem um h2
  ("Análise do perfil") dentro de uma seção h4.

---

## Findings

| # | Prio | Tipo | Página | Achado | Evidência |
|---|---|---|---|---|---|
| 1 | P1 | técnico | Vagas | "Todas" mostra encerradas/descartadas como "100% · Excelente" sem status; 40/100 são `encerrada`; "Abrir vaga original" → 404 | `ux-audit/1440_vagas_todas.png`; consulta ao banco |
| 2 | P1 | técnico | Documentos | Detalhe aparece fora da tela após selecionar (y=918 a 1440; 1121 a 390) | `medidas_ux.json documentos_sel` |
| 3 | P1 | técnico | Candidaturas | "3 precisam de atenção" não leva às 3 (histórico 900px abaixo, sem filtro aplicado) | `candidaturas.secoes` |
| 4 | P1 | técnico (apresentação) | Configurações › Preferências | 3 formulários / 3 "Salvar" / 27 controles / 2,6–4,1 telas; salvar o formulário errado perde o que se digitou no outro | `configuracoes_secoes` |
| 5 | P1 | mobile | Revisar | Checklist "Sua candidatura" em y=1278, depois da evidência e de "A seguir" | `revisar_pecas` 390 |
| 6 | P2 | técnico | Vagas, Candidaturas | Tetos silenciosos: "100 vagas" (394/808), "300 registros" | legendas |
| 7 | P2 | técnico | Revisar | Sem confirmação nominal após decidir ("Marcada como enviada: …"); "Não tenho interesse" ao lado de "Já me candidatei" sem confirmação, desfazer só depois | código `decidir`/`desfazer` |
| 8 | P2 | técnico | Candidaturas | Marcar desfecho não dá feedback | `_marcar` |
| 9 | P2 | técnico | Revisar | ⚠ não distingue eliminatório de desejável; "Forte aderência em…" para 76% e 97% | `aderencia._ponto_de_atencao`, `porque` |
| 10 | P2 | técnico | Revisar, Documentos | Carta em `text_area` editável sem salvar | `5_Aplicar.py`, `_documentos.py` |
| 11 | P2 | técnico | Início | Não mostra "3 precisam de atenção" (o único acionável de Candidaturas) | `2_Dashboard.py` |
| 12 | P2 | técnico | Vagas | "● Preparada" não leva a Revisar; "Aprovar" só dentro de Detalhes | `3_Vagas.py` |
| 13 | P2 | técnico | Candidaturas | Detalhe por selectbox de 300 itens; Documentos usa seleção na linha | duas interações |
| 14 | P2 | decisão | Configurações | Pretensão em dois lugares com valores diferentes; corte de automação em "Filtros avançados"; Greenhouse em Preferências, Gupy em Plataformas; Automação = ações; Análise do perfil dentro de LinkedIn | tabela da seção |
| 15 | P2 | decisão | Candidaturas | Lista de seletores não escala (50 → 3.900px, sem filtro/agrupamento); histórico padrão traz 165 "Perguntas pendentes" e 118 "Erro" de junho | contagens do banco |
| 16 | P2 | decisão | Vagas | Sem ordenação por data ("o que chegou hoje"); ordenação por aderência favorece scores antigos | — |
| 17 | P2 | decisão | Revisar | Idade/verificação da vaga e perguntas sem resposta não aparecem antes de "Abrir" | — |
| 18 | P2 | decisão | Documentos | Sem perfil nem "enviado" na tabela; descoberta só por busca | — |
| 19 | P3 | técnico | Revisar | "A seguir" acima da dobra compete com a decisão atual | `revisar_pecas` |
| 20 | P3 | técnico | Vagas | Filtro de status com 11 opções sem explicação de qual usar para quê | — |
| 21 | P3 | técnico | Todas | Quatro rótulos para "abrir a vaga no site"; três formas de "precisam de você" | seção Consistência |
| 22 | P3 | decisão | Vagas | Busca não cobre tecnologia | — |
| 23 | P3 | mobile | Configurações | Nav de 350px antes do conteúdo; "Salvar" a 1.310–3.156px | `configuracoes_secoes` 390 |
| 24 | P3 | Streamlit | Mobile | Botão "»" sem rótulo para abrir a navegação; "Page not found" em inglês | — |

Nenhum P0.

---

## Product Decisions

Problemas **técnicos** (corrigíveis sem decidir nada): #1, #2, #3, #4 (a
apresentação: um formulário só, ou um "Salvar" que salve tudo), #5, #6, #7,
#8, #9, #10, #11, #12, #13, #19, #20, #21.

**Decisões de produto** (mudam o que o produto é, precisam de definição):

| Decisão | Opções em jogo | O que depende dela |
|---|---|---|
| Teto e paginação de Vagas | manter 100 e dizer "100 de 808"; "mostrar mais"; paginação; virtualizar | #6, escala da lista |
| Status no cartão em "Todas" | mostrar sempre; mostrar só quando o filtro não fixa; excluir encerradas de "Todas" por padrão | #1 |
| Ordenação de Vagas | aderência fixa; data; escolha da pessoa | #16 |
| Número de candidaturas exibidas e formato | seletores por linha (hoje); tabela editável; agrupar por mês; só "sem resposta" por padrão | #15 |
| Registros de junho no histórico | tratar como arquivo (fora do padrão); marcar em lote como "encerradas"; manter | #15 |
| Tabela vs cards | Vagas em cartões, Candidaturas/Documentos em tabela — manter a divisão | consistência |
| Textarea vs chips | um componente de lista para Plataformas/LinkedIn | #14 |
| Organização das Configurações | separar "ajustar / operar / consultar"; Dados pessoais e Pretensão como seções; corte de automação em Automação; Greenhouse em Plataformas | #14, #4 |
| Pretensão salarial | faixa (7–13 mil, CLT→PJ) ou valor único (8 mil): qual é a fonte | #14 e os 2 testes de prompt |
| Informação antes de abrir a candidatura | idade/verificação da vaga; perguntas sem resposta no cartão | #17 |
| Descoberta em Documentos | colunas perfil/enviado; atalhos "enviados", "melhores" | #18 |
| Busca por tecnologia | ampliar a busca de Vagas | #22 |

---

## Recommended Next Steps

1. **Vagas › "Todas"**: mostrar o status no cartão sempre que o filtro de
   status não o fixar, e escrever "100 de 808" na legenda. (técnico, #1, #6)
2. **Documentos**: ao selecionar uma linha, levar a tela ao detalhe (ou
   colocar o detalhe antes da tabela). (técnico, #2)
3. **Candidaturas**: "3 precisam de atenção" vira link que aplica o filtro
   "Envio não confirmado" no histórico; marcar desfecho dá um `st.toast`.
   (técnico, #3, #8)
4. **Revisar**: toast nominal após decidir ("Marcada como enviada: …");
   "Não tenho interesse" com confirmação leve ou desfazer no mesmo lugar;
   ⚠ com "(eliminatório)" quando vier de `missing_required`. (técnico, #7, #9)
5. **Revisar no celular**: checklist logo abaixo do cartão, antes das ações
   secundárias. (técnico, #5)
6. **Preferências**: um "Salvar" para a página, ou aviso claro de qual
   formulário cada botão salva — enquanto a divisão em seções não é decidida.
   (técnico, #4)
7. **Início**: uma linha "3 precisam de atenção → Candidaturas" quando houver.
   (técnico, #11)
8. **Decidir** as quatro decisões que destravam o resto: teto/ordenação de
   Vagas, formato de Candidaturas em escala, arquitetura de Configurações
   (com a pretensão única), componente de lista de valores.
9. **Carta**: só-leitura nas duas telas até existir "salvar carta editada".
   (técnico, #10)
10. **Vocabulário**: um rótulo para "abrir a vaga no site" e um para
    "precisam de você". (técnico, #21)


---

# IMPLEMENTATION ROUND 2 — 21/09/2026 (lote técnico do UX Audit)

Só os achados marcados como **técnicos**; as decisões de produto continuam
abertas. Validado com Playwright (1440, 1024, 390) e pelo script da auditoria
visual; comparação com `design-audit_r1/` (estado da rodada 1): 0 regressões
em 18 combinações (colisões, clipping, overflow, exceções). Alturas crescem
onde entrou conteúdo (Início +20px pela linha de atenção, Candidaturas +34
pelo botão, Configurações +60 pela legenda de três blocos); Revisar no
celular caiu 57px (checklist da direita escondido, linha compacta no lugar).

| # | Achado | Alteração | Arquivos | Validação |
|---|---|---|---|---|
| 1 | "Todas" mostrava encerradas como "100% · Excelente" sem status | Badge de status no cartão sempre que o filtro não o fixa (`mostrar_status = status == "todas"`) | `ui/pages/3_Vagas.py` | 1º cartão em "Todas" traz "Encerrada" |
| 6 | "100 vagas" quando havia 325/809 | `_get_vagas` devolve `(lista, total)`; legenda "100 de 809 vagas" | `3_Vagas.py` | legenda padrão "100 de 325", "Todas" "100 de 809" |
| 21 | "Aguardando você" (325) confundia com "precisam de você" (42) | filtro renomeado "Na fila"; "Abrir vaga original"/"Ver vaga" → "Abrir vaga" | `3_Vagas.py`, `4_Candidaturas.py` | texto do filtro |
| 12 | "● Preparada" sem destino | vira link "● Preparada · revisar" para `/revisar` | `3_Vagas.py` | — |
| 3 | "3 precisam de atenção" era um parágrafo | botão "Ver as 3 no histórico" aplica o filtro "Envio não confirmado" (callback zera busca e plataforma) | `4_Candidaturas.py` | clique → filtro "Envio não confirmado", "3 registros" |
| 8 | Marcar desfecho sem feedback | `st.toast("Anotado: …")` no callback | `4_Candidaturas.py` | código (não executado: grava dado real) |
| 7 | Decidir em Revisar sem dizer o quê | `decidir_e_avisar`: toast "Marcada como enviada: <vaga> — <empresa>. Dá para desfazer no topo." (idem descartada / deixada para depois) | `5_Aplicar.py` | código (idem) |
| 9 | ⚠ não distinguia eliminatório | requisito obrigatório ausente: "**Exige** PySpark, que não está…"; desejável continua "Não cita…" | `jobapplier/aderencia.py`, `tests/unit/test_aderencia.py` | cartão: "⚠ Exige PySpark…"; testes |
| 5 | Mobile: prova a 1,5 tela do CTA | linha `.so-mobile` "✓ Currículo · ✓ Carta — preparados para esta vaga" sob o cartão (só < 768px); linhas do checklist da direita escondidas no celular, download e carta permanecem | `5_Aplicar.py`, `ui/_ui.py` | 390: linha em y=473, CTA em 509; desktop: `display: none` |
| 2 | Detalhe de Documentos fora da tela após selecionar | `st.container()` reservado antes da tabela; o detalhe renderiza nele | `ui/_documentos.py` | botão "Baixar currículo" em y=277 (tabela em 781) |
| 10 | Carta em `text_area` editável sem salvar | `.carta-leitura` (só leitura, largura de medida) em Revisar e Documentos | `5_Aplicar.py`, `_documentos.py`, `_ui.py` | `textarea: false`, `.carta-leitura: true` |
| 11 | Início não mostrava o que pede atenção em Candidaturas | linha "⚠ 3 precisam de atenção — envio não confirmado." acima de "Ver candidaturas" | `2_Dashboard.py` | texto presente |
| 4 | Três formulários sem aviso | legenda "Esta seção tem três blocos… cada um salva com o próprio botão" (só no modo ajuste) | `1_Setup.py` | — |

Não feito (decisão): teto/paginação, ordenação por data, formato de
Candidaturas em escala, arquitetura de Configurações e pretensão única,
lista de valores, colunas perfil/enviado em Documentos, busca por
tecnologia, "Não tenho interesse" com confirmação (o toast + "Desfazer" no
topo cobrem o erro de clique; uma confirmação a mais é atrito na ação mais
frequente — fica para decisão).

Suíte: `ruff` limpo; `pytest` verde exceto os dois testes de prompt
(pretensão salarial — decisão pendente).


---

# IMPLEMENTATION ROUND 3 — 22/09/2026 (as decisões de produto)

O usuário fechou as 12 decisões e os P3. Implementado e validado (suíte
unit + e2e verde, incluindo os dois testes de prompt; auditoria visual em
1440/1024/390 sem colisão, overflow ou exceção; dois truncamentos de tablet
introduzidos pelas colunas novas foram medidos e corrigidos antes do fecho).

| Decisão | O que foi feito | Onde |
|---|---|---|
| 1. "Mostrar mais" de 25 em 25 | lista começa em 25; botão "Mostrar mais 25 (25 de 340)" sobe o limite; "Limpar filtros" volta a 25 | `3_Vagas.py` |
| 2. Ordenação à escolha | selectbox "Maior aderência / Mais recentes" ao lado da contagem; a legenda diz o critério | `3_Vagas.py` |
| 3. Candidaturas por mês | "O que aconteceu com cada uma" agrupado em expanders por mês de envio ("Agosto de 2026 · 1 enviada · 1 sem resposta"), o mais recente aberto | `4_Candidaturas.py` |
| 4. Legados arquivados em lote | status novo `arquivada` (catálogo); `scripts/arquivar_legados.py --aplicar` fechou 283 registros (165 perguntas pendentes + 118 erro, anteriores a 09/2026); status anteriores em `data/arquivamento_20260922.json`, `--desfazer` reverte. Histórico padrão: 300 → 15 registros | `status.py`, `scripts/` |
| 5. Configurações: ajustar / operar / consultar | nav em três grupos com rótulo; seções novas **Dados pessoais** e **Pretensão** (blocos que eram o 2º e 3º formulário de Preferências); Greenhouse foi para **Plataformas**; os cortes de aderência foram para **Automação** ("Envio automático a partir de" / "Entra na fila a partir de") — e a correção de um bug: o slider antigo "Autoaprovação" gravava `threshold_excelente` (corte da fila) com mínimo 70 e o salvar apagava `threshold_auto`; títulos de seção como `h2` sem âncora | `1_Setup.py`, `_ui.py` |
| 6. Pretensão: a faixa é a fonte | campo simples (R$ 8.000) removido da tela e de `config.json`; `pretensao` = 10.000 / 13.000 / 16.000 × 1,3, igual ao prompt; `test_prompts.py` volta a passar | `1_Setup.py`, `data/config.json` |
| 7. Chips em slugs e queries | Plataformas (Greenhouse, Gupy, palavras-chave) e LinkedIn (buscas) usam o mesmo resumo + "Editar (N)" de Preferências; um "Salvar plataformas" | `1_Setup.py` |
| 8. Documentos: colunas e atalhos | colunas **Perfil** e **Enviado** (Plataforma/Carta/À mão saem: estão no detalhe, no toggle e no atalho); pills "Enviados · Melhores (≥ 85%) · Escritos à mão" | `_documentos.py` |
| 9. Busca por tecnologia | a busca de Vagas também casa com `normalizado_json` ("databricks" → 79) | `3_Vagas.py` |
| 10. Tabela no celular | seis colunas com larguras numéricas (140/240/110/80/95/70): tablet mostra as quatro que decidem; a 390 continuam duas com rolagem da grade — sem representação alternativa (fica em D) | `_documentos.py` |
| 11. "Não tenho interesse" como ícone | botão-ícone (×, 85px) ao lado de "Já me candidatei" largo; o texto fica no DOM (nome acessível + tooltip), só escondido | `5_Aplicar.py`, `_ui.py` |
| 12. Antes de abrir | linha no cartão: "coletada há 35 dias · vista no ar há 5 dias · N perguntas do formulário ficam para você / formulário todo respondido" | `5_Aplicar.py` |
| 13. CPF/RG | `type="password"` — o campo traz o botão "mostrar" e continua editável | `1_Setup.py` |
| 14. "Excelente" | mantido (decisão do usuário) | — |
| C. P3 | selects de diversidade empilham < 1160; multiselect sem teto em toda parte; `h2` nas seções de Configurações; page_link no ritmo de 16px (margem no contêiner); "A seguir" abaixo da descrição; filtro de status com guia (help); histórico com uma linha por vaga e "· 2×"; rodapé 160 → 64px; alertas nos tokens do produto (verde/âmbar/vermelho/índigo-suave); nav de Configurações em chips no celular (350 → 313px); "Todas" verificada (809 elegíveis, badges de status) | vários |

## Extensão nas plataformas (22/09/2026)

Feito depois da rodada 3, a pedido: a extensão preenche o Easy Apply do
LinkedIn (`linkedin.com/jobs/*`, só o diálogo) e anexa o currículo feito
para a vaga no campo de arquivo — na Gupy e no LinkedIn —, tudo no clique,
sem enviar nem avançar. Provado por e2e com fixtures sintéticas.

## Próximos passos (D — fora desta rodada)

1. **Painel da extensão abrir na vaga da aba atual** — a API já resolve o
   vínculo por aba; falta o painel pedir.
2. **Sugerir respostas a partir do currículo** para perguntas sem resposta
   aprendida — precisa de desenho que respeite a invariante 3.
3. **Leitura de e-mail para o funil** (`desfecho.py`).
4. **Enviar os dossiês do lote de set/2026** — Revisar mostra os 42.
5. Representação mobile da tabela de Documentos (hoje 2 colunas + rolagem).
6. Dívidas já registradas no CLAUDE.md: Lever, senioridade no 4B,
   `screenshots_path`, CI, Dockerfile, `structlog`, Fase 1.
