# AI Job Applier — Dossiê técnico

**Agosto 2026**

Automação de busca e candidatura a vagas de dados no Brasil. Coleta em Greenhouse, Lever e Gupy, pontua aderência contra o currículo, otimiza o currículo para ATS, gera cover letter e preenche o formulário. Ferramenta pessoal, construída para permitir monetização futura.

> **O que este projeto é hoje:** um copiloto avançado em construção, não um candidato autônomo. A arquitetura está madura; a confiabilidade da candidatura automática, não. O sistema está em **modo sombra por padrão** — prepara tudo e não envia.

| | |
|---|---|
| Linhas (domínio) | 7.302 |
| Módulos | 51 |
| Testes | 293 |
| Linhas de teste | 2.233 |
| Achados de lint | 0 |
| Commits | 10 |

---

## O pipeline

O desenho central: **gastar LLM o mais tarde possível**. Cada etapa descarta vagas antes da etapa mais cara, e filtros determinísticos cercam a chamada de modelo dos dois lados.

| # | Etapa | O que faz | Custo |
|---|---|---|---|
| 01 | Coleta | APIs REST de Greenhouse, Lever e Gupy; LinkedIn por sessão salva | HTTP |
| 02 | Filtro 4A | Cargo alvo, palavra bloqueada, localização — sobre texto bruto | grátis |
| 03 | Normalização | Extrai senioridade, stack, idioma, setor, anos exigidos | **custa** |
| 04 | Filtro 4B | Tecnologias obrigatórias, teto de experiência — sobre JSON | grátis |
| 05 | Scoring | 0–100 · skills 40, senioridade 20, setor 15, idioma 15, local 10 | **custa** |
| 06 | Controle de risco | Limite 24h, disjuntor, duplicidade, lease — antes de gastar nada | grátis |
| 07 | Preparação | Currículo otimizado para ATS, PDF verificado, cover letter | **custa** |
| 08 | Candidatura | Playwright — hoje interrompido pelo modo sombra | Playwright |

---

## Estado por área

| Área | Estado | Observação |
|---|---|---|
| Pipeline e separação de responsabilidades | **sólido** | Domínio isolado da UI; provedor de LLM, plataforma e interface são trocáveis sem tocar no núcleo. |
| Controle de risco | **sólido** | Janela deslizante de 24h por plataforma, disjuntor de erros, lease com teto de tentativas, jitter de mouse. |
| Camada de LLM | **sólido** | OpenAI, Gemini e Anthropic atrás de um contrato; autodetecção por chave, cadeia de fallback, cache em banco. |
| Documentação | **sólido** | `CLAUDE.md` registra decisões, motivos, bugs anteriores, armadilhas e dívida — não só "como rodar". |
| Testes | *desigual* | Camada unitária boa e rápida; `applicators.apply()` — o código que toca terceiros — tem cobertura zero. |
| Segurança e privacidade | *parcial* | Chaves em `.env`, fora do git. CPF e dados de diversidade ainda em texto plano no JSON de config. |
| Preparação para monetização | *costurada* | Separação vaga-global / avaliação-por-usuário desenhada; `usuario_id` ainda não existe. |
| Confiabilidade da candidatura | **não provada** | Formulários variam por empresa dentro da mesma plataforma. Nunca validado contra vários tipos de formulário real. |
| Infraestrutura de operação | **mínima** | Windows-only, sem Dockerfile da aplicação, sem supervisor. Roda enquanto o notebook estiver ligado. |

---

## Invariantes

Restrições que nasceram de falhas reais. Cada uma existe porque algo deu errado antes.

1. **Só candidata vaga aprovada.** Vagas de score intermediário aguardam revisão humana. Já foi bug: o agendador candidatava as pendentes e a fila de aprovação era decorativa.
2. **Todo caminho passa pelo guard antes de gastar recurso.** Plataforma suportada, duplicidade, limite, disjuntor, lease — nessa ordem, antes de qualquer token ou browser.
3. **Nunca afirma o que o currículo não sustenta.** Reformular e reordenar, sim; inventar experiência, certificação ou nível de idioma, não. Vale também para preenchimento de formulário: pergunta desconhecida vira pergunta manual, nunca chute.
4. **Nada de `data/` é versionado.** Contém chaves, CPF, cookies de sessão, currículos gerados e o banco.
5. **Segredo vai para `.env`.** Nunca para o JSON de configuração. A UI grava direto no `.env`.
6. **LinkedIn é opt-in e isolado.** Automatizar Easy Apply viola o User Agreement. O núcleo Greenhouse/Lever/Gupy funciona sem ele, e nenhum teste automatizado faz login.
7. **Nenhum módulo instancia SDK de LLM direto.** Sempre pela fábrica, que resolve provedor, cache, retry e fallback.
8. **Todo PDF é renderizado e verificado.** Imagem de inspeção por página, mais checagem de geometria e de legibilidade por ATS. Layout grave bloqueia o envio.
9. **Saída de LLM nunca vira artefato sem normalização.** Caso geral do bug do PDF: o JSON do modelo ia direto ao gerador.
10. **Limite de segurança é criado e consultado no mesmo commit, com teste.** Uma constante de limite diário existiu por semanas sem nenhum chamador.
11. **Segredo e PII nunca em log.** Passou a importar quando o log foi para disco.

---

## Defeitos encontrados e corrigidos

Todos achados por instrumentação nova, não por relato. Estão aqui porque a natureza deles diz mais sobre o projeto que a lista de features.

**Currículo saía com estrutura de dados impressa.** As descrições de experiência apareciam como `['bullet um', 'bullet dois']` — colchetes e aspas — num parágrafo corrido, direto para o recrutador. Causa: a saída do LLM ia ao gerador de PDF sem validação. Encontrado ao olhar a primeira imagem renderizada.

**"Enviada" saía de match de substring.** A palavra `obrigado` em qualquer lugar da página marcava sucesso. Um rodapé de agradecimento produzia falso positivo — e falso "enviada" é pior que erro, porque bloqueia aquela vaga para sempre.

**Filtro geográfico não pegava o formato mais comum.** A lista exigia vírgula ou espaço após o país, então `"Austin, USA"` e `"London, UK"` passavam batido e gastavam chamada de LLM.

**Dois thresholds contraditórios.** Um módulo usava 65 como score que autoriza candidatura; outro declarava 85 — e nunca era chamado. Duas respostas para a mesma pergunta, convivendo sem ninguém notar.

**Testes que só passavam em conjunto.** Dois testes falhavam quando rodados isolados: o carregamento do `.env` repopulava a variável que o teste tinha acabado de remover. Suíte verde que só é verde numa ordem não é garantia.

**Chave de API impressa na saída de teste.** Como os testes liam o `.env` real, o assert que falhava imprimia a chave em texto plano — para terminal, log de CI e transcript.

---

## O problema conceitual central

O sistema tratava **score alto como autorização suficiente para enviar**. Um score de LLM não é probabilidade calibrada: uma vaga com 88 não é necessariamente melhor que uma com 82, e pequenas mudanças de prompt, modelo ou descrição alteram bastante a pontuação.

Aderência técnica também não é a única variável. Faixa salarial, regime de contratação, deslocamento, interesse real na empresa, perguntas eliminatórias e qualidade da vaga entram na decisão — e nenhuma delas está no score.

Falta ainda uma dimensão que o sistema não modela: **confiança de preenchimento**. Uma vaga pode ter aderência excelente e, ainda assim, um formulário que a automação não sabe preencher com segurança. São perguntas diferentes e hoje têm uma resposta só.

Por isso o modo sombra é o padrão. O sistema prepara tudo e registra o que teria enviado; a comparação entre a decisão dele e a sua, ao longo de semanas, é o que vai calibrar o threshold — não a intuição.

---

## Dívida conhecida

| Item | Impacto | Situação |
|---|---|---|
| `applicators.apply()` sem teste de integração | **alto** | É o código que envia coisas em seu nome. A cobertura é inversamente proporcional ao risco. |
| Migrations 003 e 004 escritas, não aplicadas | **alto** | Docker fora do ar. Ordem correta: backup → `alembic upgrade head` → validar contagens. |
| CPF e diversidade em texto plano | médio | Depende da tabela de credenciais cifradas. Chave de cifra não deve ficar ao lado do banco cifrado. |
| Sem versionamento de prompt / modelo / schema | médio | Uma vaga normalizada com o prompt antigo nunca é revisitada. Impede reproduzir por que um score foi aquele. |
| Scoring sem parte determinística | médio | Requisito obrigatório, idioma e localização deveriam ser regra, não julgamento de modelo. |
| Filtro de senioridade nunca implementado | médio | O mapa existe no código, sem uso. Implementar exige decidir a política. |
| Windows-only, sem Dockerfile da aplicação | médio | Impede rodar 24/7 num servidor — que é o ponto de um bot de candidaturas. |
| Sem política de retenção de currículos e cookies | médio | Screenshots, logs e backups já têm; os dados pessoais, não. |
| Lever sem automação | baixo | Deliberado: vagas recebem status próprio e são ignoradas em vez de falhar caro. |
| CI escrito, nunca executado | baixo | Repositório sem remoto. |

---

## Decisões em aberto

Pontos onde a opinião do revisor muda o rumo.

**Qual é o posicionamento — volume ou precisão?** "Candidatar-se automaticamente a centenas de vagas" tende a produzir candidaturas ruins, bloqueio de plataforma e custo alto de manutenção. A alternativa é um copiloto: coleta, seleciona, prepara e preenche, com confirmação do usuário. Preserva quase toda a arquitetura e reduz muito o risco — mas é um produto diferente.

**Quando desligar o modo sombra, e com base em quê?** Proposta: só depois de o score demonstrar correlação com desfecho real, e apenas para formulários em que todas as respostas são conhecidas. Exige primeiro instrumentar resposta, entrevista e oferta — hoje o funil morre em "candidatada".

**Recandidatura deve ser permitida?** O banco agora tem unicidade por vaga e ciclo, o que torna a recandidatura explícita em vez de proibida. Falta definir a política: republicação da vaga conta como ciclo novo? Depois de quanto tempo?

**LinkedIn continua no escopo?** É a plataforma com maior volume e o maior passivo: viola o User Agreement e arrisca uma conta que é identidade profissional real. Removê-lo torna o projeto defensável como produto; mantê-lo o inviabiliza comercialmente.

---

## Como avaliar

**Rodar a suíte.** `pytest` — 293 testes em ~12s, sem rede nem banco. Três camadas: unitária, e2e com Playwright contra HTML de fixture, e integração marcada que pula sem PostgreSQL.

**Ler primeiro.** `CLAUDE.md` concentra invariantes, convenções, armadilhas e a direção arquitetural. `docs/initial_plan.md` é a especificação original, com a numeração de módulos que o código referencia.

**Onde olhar com ceticismo.** Os três applicators. São 1.400 linhas que dependem de HTML de terceiros, sem teste de fluxo completo, e são o único ponto onde o sistema age irreversivelmente.

**O que provaria que está pronto.** Três coisas: que não envia candidatura inadequada, que não duplica nem perde controle de execução, e que comprova o envio em formulários reais variados. Nenhuma está provada hoje.

---

*Python 3.13 · PostgreSQL 16 · Playwright · Streamlit · OpenAI / Gemini / Anthropic*
