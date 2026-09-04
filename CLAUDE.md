# AI Job Applier

Automação de busca e candidatura a vagas de dados no Brasil. Coleta vagas de
Greenhouse, Lever e Gupy (e LinkedIn via sessão salva), normaliza e pontua com
LLM contra o currículo do usuário, otimiza o currículo para ATS, gera cover
letter e submete a candidatura via Playwright.

**Uso pessoal (usuário único), construído para permitir monetização futura.**
Isso governa decisões de arquitetura: ver [Direção arquitetural](#direção-arquitetural).

Idioma do projeto: **português** em nomes de domínio, comentários, logs, mensagens
de commit e docstrings. Termos técnicos consagrados ficam em inglês
(`hash`, `score`, `pipeline`, `Easy Apply`, `prompt`).

---

## Finalidade

**O objetivo é que candidatar-se não seja maçante.** Essa é a régua: qualquer
coisa que adicione tédio precisa ser reconsiderada, mesmo que funcione, mesmo que
seja tecnicamente elegante.

O que isso implica, e que não é óbvio:

- **Volume não é sucesso.** 293 tentativas produziram 10 envios. Uma fila de 216
  cartões é uma lista de afazeres com 216 itens — bonita ou não. Mandar **menos
  e melhor** vale mais que automatizar o envio de muitas.
- **Decisão sem informação é carimbo.** Se a fila tem mediana 74 e mínimo 65, os
  cartões são indistinguíveis e o usuário está confirmando, não decidindo. O
  problema aí é o corte do filtro, não a interface.
- **Contabilidade que só serve ao sistema é tédio.** Se o usuário precisa voltar
  à tela para registrar algo que não lhe rende nada, procure um sinal que já
  exista no fluxo dele.
- **Configuração recorrente é tédio.** Filtro que precisa ser remontado a cada
  sessão deveria ser lembrado ou inferido.
- **O produto é o dossiê, não o envio.** Currículo sob medida por vaga já é o
  grosso do valor. O envio automático é um extra, e é onde mora toda a
  fragilidade: seletor que muda, CAPTCHA, risco de conta.
- **Honestidade sobre o limite.** Depois do link, ainda há 5–10 min de formulário
  no site que este projeto não elimina. Não finja que elimina.

### Automação por plataforma

Nem toda plataforma merece o mesmo tratamento, e a diferença é deliberada:

| Plataforma | Tratamento | Por quê |
|---|---|---|
| Greenhouse | envio automático | formulário público, sem login, sem CAPTCHA |
| Lever | baralho, envio assistido | **hCaptcha no formulário** — medido, não suposto |
| Gupy | baralho, envio manual | Cloudflare Turnstile no login |
| LinkedIn | baralho, envio manual | risco de restrição da conta (invariante 6) |
| inhire | baralho, envio assistido | reCAPTCHA no formulário — medido |

Onde o envio é manual, o trabalho é deixá-lo **rápido**: dossiê pronto, respostas
prontas, um clique para abrir. Não é aceitar o tédio — é atacá-lo onde dá.

### Política de score

- **Score nunca rejeita.** Abaixo do corte a vaga vira `pendente` — possibilidade
  acessível baixando o filtro da fila, não lixo. O score do sistema não é
  probabilidade calibrada; descartar terminalmente por ele joga fora vaga que só
  ele achou ruim.
- **Automação exige score alto.** Envio automático só acima de
  `scoring.threshold_auto` (padrão 85). Entre o corte de aprovação e o de
  automação, a vaga vai para o baralho: o sistema prepara, você decide.
- **Possibilidade não é fila.** Score baixo fica guardado e escondido por
  padrão. Mostrar tudo sempre recriaria a fila maçante.

### Banco de respostas aprendidas

O que você digita à mão uma vez, o sistema repete — `jobapplier/aprendizado.py`,
tabela `respostas_aprendidas`. Sem isso, a etapa de perguntas da empresa na Gupy
pede nome da mãe em cada uma das 230 vagas da fila.

**Não fere a invariante 3.** A invariante proíbe o *sistema* afirmar o que o
currículo não sustenta. Uma resposta aprendida é do candidato, repetida
literalmente — é a única fonte que dispensa sustentação, porque veio da pessoa.

**O que governa o reúso é a classe da pergunta** (`agents/respostas.Classe`):

| Classe | Escopo | Porquê |
|---|---|---|
| `FATO`, `PREFERENCIA`, `FERRAMENTA`, `DOMINIO`, `TEMPO`, `CONSENTIMENTO`, `SENSIVEL` | global | é sobre você, e não muda de empresa para empresa |
| `ABERTA` | por empresa | "por que a PagBank?" não responde "por que o Nubank?" |

Duas regras que já custaram bug e têm teste:

- **Casamento é exato** sobre a forma normalizada. "Python" e "Python 3" são
  perguntas diferentes; frouxidão responde uma com a outra.
- **Sigla curta casa por palavra inteira.** `"rg"` vive dentro de "ene**rg**ia",
  "u**rg**ente" e — pior — de "ó**rg**ão". Como substring, classificava pergunta
  de domínio como documento.

O nome da empresa vira `{empresa}` na chave das classes globais, então "Você
trabalha na empresa X?" tem uma resposta só para todas. Em pergunta `ABERTA` não
neutraliza: ali o nome é o assunto.

Revisão em `ui/pages/6_Respostas.py` — memória só é aceitável se for revisável.
Esvaziar uma resposta **apaga** a entrada; gravar `""` faria o banco responder
nada em todo formulário seguinte, em silêncio.

### Identificar a candidatura aberta no navegador

A URL do formulário da Gupy é `/candidates/applications/<id>/steps/<id>` e **não
carrega o `jobId`**. Medido na página real: sem `__NEXT_DATA__`, sem link para a
vaga, sem nada no DOM além do título em texto — e o título não basta, porque o
PagBank tem duas vagas "Analista de Dados Pl." (repostagem com id novo).

`api._resolver` vai da certeza para a dúvida, e **nunca deduz por título**:

1. `jobId` na própria URL — página pública, `/job/<base64>`.
2. Vínculo já gravado em `vinculos_candidatura`.
3. `referrer` — você veio da página da vaga.
4. Memória da aba — o service worker guarda por `sender.tab.id`, porque só ele
   conhece a aba. Global sobrescreveria com duas vagas abertas lado a lado.
5. Nada disso → **409 com as candidatas**, e você escolhe no aviso. 404 fica só
   para "nenhuma vaga desta empresa no acervo".

Resolvido por 3 ou 4, o vínculo é gravado e voltar por e-mail passa a funcionar
sozinho. Precedência: **inferência não sobrescreve inferência** (senão o vínculo
oscila a cada visita) e **inferência nunca sobrescreve sua escolha** (`origem =
'voce'`) — senão a próxima visita reabriria a dúvida que você já resolveu.

### Configuração de coleta

Um padrão só, para toda plataforma: `coleta.empresas_<plataforma>` (slugs) e
`coleta.keywords_<plataforma>` (busca por palavra-chave). Ler sempre via
`ConfigManager.empresas(p)` / `.keywords(p)` — não invente chave nova por
plataforma; foi assim que `gupy.search_keywords` e `linkedin.search_queries`
divergiram do resto.

## Documentação

Todo `.md` do projeto vive em **`docs/`** — exceto `CLAUDE.md` e `README.md`, que
ficam na raiz porque são o ponto de entrada. Vale para prompt de revisão, brief
de design, tutorial e qualquer coisa nova. A raiz é para código e configuração;
documento que vira arquivo solto lá some no meio de `run.py` e `pyproject.toml`.

```
docs/
  initial_plan.md          especificação original, com a numeração de módulos
  DESIGN_UI.md             régua visual: tipografia, medida, espaço
  REVISAO_BACKEND.md       prompt de revisão de engenharia
  REVISAO_FRONTEND.md      prompt de revisão de UI/UX
  REVISAO_NEGOCIO.md       prompt de revisão de produto
  TUTORIAL_LINKEDIN.md     passo a passo do perfil
  prompt_carreira.md       fatos profissionais — fonte única
  prompt_curriculos.md     regras de currículo por vaga
  prompt_candidaturas.md   protocolo de candidatura assistida (núcleo)
  comparativo_aiapply.md   o que a concorrência faz melhor, e onde discordamos
  plataformas/             camada por plataforma: linkedin, gupy, greenhouse, inhire
```

**Prompts de candidatura seguem a mesma regra dos currículos**: um núcleo, e uma
camada fina por plataforma que só **acrescenta** restrição — nunca afrouxa o
núcleo, nunca redefine pretensão ou contato. Havia um prompt completo por
plataforma e a divergência apareceu em um dia: o do LinkedIn pedia PJ igual a
CLT e piso de R$ 7.000, faixa já substituída. `tests/unit/test_prompts.py` falha
se um prompt divergir de `data/config.json` ou `data/resume.json`, se uma camada
trouxer valor próprio, ou se uma referência apontar para arquivo inexistente.

A família `prompt_*.md` é **minúscula**: era `PROMPT_CARREIRA.md` e as dez
referências a ela usavam minúsculo, então o protocolo travava na checagem de
arquivos obrigatórios.

## Método de trabalho

**Planeje antes de fazer.** Antes de qualquer mudança que toque mais de um
arquivo, mude comportamento observável ou envolva escolha entre abordagens:
escreva o plano em passos curtos e mostre-o. Só execute direto decisões muito
simples — typo, rename local, ajuste de teste que acompanha código já decidido.

Perguntas ao usuário vão no formato estruturado de opções (com recomendação
marcada), não em prosa solta no meio da resposta.

**Revisar vaga é trabalho de especialista em RH, não de leitor de score.** O
score mede sobreposição de palavra-chave; quem contrata olha outra coisa. Toda
vez que revisar uma vaga — antes de preparar, antes de enviar, ao montar
qualquer lista — leia o anúncio como recrutador leria e verifique o que o número
não vê:

- **Elegibilidade.** Vaga afirmativa é reservada a um grupo. "Affirmative Action
  for Women" apareceu com score 70 e preenchimento 85%, pronta para envio.
- **Onde o trabalho acontece de verdade.** "Remoto" no campo normalizado e
  *"office-first, we do not offer remote-only roles"* no corpo do anúncio já
  ocorreram na mesma vaga. O corpo manda; e o país define autorização de
  trabalho.
- **Cargo, não vocabulário.** Data Scientist, Software Engineer, People
  Analytics e Marketing Analytics Manager todos passaram de 85 por dividirem
  stack. Nenhum é o cargo dele.
- **Senioridade real** — Staff e Lead pedem escopo que dois anos não sustentam.
- **Domínio.** Payments Performance Analyst é analytics em pagamentos; sem
  experiência no domínio, as perguntas que decidem ficam em branco.
- **Duplicata.** Mesma vaga reposta com outro id, ou a versão regular e a
  afirmativa da mesma posição.

E diga o que a candidatura tem contra ela, não só a favor. Vaga marginal enviada
queima a empresa para a vaga certa depois — o custo de candidatar-se não é zero,
e tratá-lo como zero é o que produz 293 tentativas e 10 envios.

---

## Comandos

```powershell
# ── Setup ────────────────────────────────────────────────────────────────────
.\scripts\install.ps1                           # primeira vez
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
cp .env.example .env                            # e preencha as chaves

# ── Rodar ────────────────────────────────────────────────────────────────────
python run.py                                   # Postgres + Streamlit + orquestrador
                                                # app em http://localhost:8501

# ── Testes ───────────────────────────────────────────────────────────────────
.venv\Scripts\python.exe -m pytest tests/unit           # ~1.7s, sem rede nem banco
.venv\Scripts\python.exe -m pytest tests/e2e            # ~16s, Playwright local
.venv\Scripts\python.exe -m pytest                      # unit + e2e ('live' fica fora)
.venv\Scripts\python.exe -m pytest -m live              # toca rede — só sob demanda
.venv\Scripts\python.exe -m pytest -m db                # exige Postgres de pé
.venv\Scripts\python.exe -m pytest -k auto_answer -vv   # foco num assunto

# ── Lint ─────────────────────────────────────────────────────────────────────
.venv\Scripts\python.exe -m ruff check .          # CI roda exatamente isto
.venv\Scripts\python.exe -m ruff check . --fix
# NÃO rode 'ruff format .': reformataria ~48 arquivos, desfazendo alinhamentos
# intencionais (listas de slugs agrupadas por comentário, dicts alinhados). O
# formatter não é aplicado neste projeto e não está no CI.

# ── Banco ────────────────────────────────────────────────────────────────────
docker compose up postgres -d
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic revision -m "descrição"
.venv\Scripts\python.exe -m alembic downgrade -1

# ── Executar uma etapa isolada do pipeline ───────────────────────────────────
.venv\Scripts\python.exe -c "from jobapplier import orchestrator; orchestrator.run_collection()"
.venv\Scripts\python.exe -c "from jobapplier import orchestrator; orchestrator.run_pipeline()"
.venv\Scripts\python.exe -c "from jobapplier import orchestrator; orchestrator.run_applications()"

# ── Debug de Playwright (ver a seção Testes) ─────────────────────────────────
$env:PWDEBUG=1; .venv\Scripts\python.exe -c "from jobapplier import orchestrator; orchestrator.run_applications()"
```

---

## Fluxo

O pipeline é desenhado para **gastar LLM o mais tarde possível**. Cada etapa
descarta vagas antes da etapa mais cara. Não reordene sem entender esse custo.

```
run_collection()                                   a cada 2h · HTTP, sem IA
  collectors/{greenhouse,lever,gupy,inhire}  → CollectedJob
  applicators/linkedin.collect_jobs          (só com sessão salva)
  → vagas.status = 'nova'                    dedup por hash

varrer_encerradas()                                a cada 6h · HTTP, sem IA
  vigencia.checar por plataforma             404 · closed_at · status != published
  → 'encerrada'.  INDETERMINADA nunca encerra: rede ruim não mata vaga viva.

run_pipeline()                                     +5min · por vaga 'nova'
  4A  filters/pre_filter                     texto bruto, GRÁTIS → 'filtrada_4a'
        cargo alvo · palavra bloqueada
        vaga afirmativa de grupo não declarado
        elegibilidade geográfica · localização
  2   agents/extracao                        DETERMINÍSTICO (modo_sem_api)
        vocabulario: tecnologias, senioridade, modalidade, setor
  4B  filters/post_filter                    JSON estruturado, GRÁTIS → 'filtrada_4b'
  3   agents/extracao.pontuar                skills 40 · senioridade 20
                                             setor 15 · idioma 15 · local 10
      >= threshold_bom   → 'aprovada'        entra na esteira 3
      >= threshold_baixo → 'pendente'        possibilidade, escondida por padrão

run_applications()                                 +15min · por vaga 'aprovada'
  modo sombra ON (padrão)                    prepara tudo, NÃO envia → 'simulada'

  Guarda 1  plataforma sem automação OU score < threshold_auto (85)
              → dossiê pronto, envio seu ('pronta_envio_manual')
  Guarda 2  guard.ja_candidatado             nunca duas vezes
  Guarda 3  guard.checar_limite              24h deslizante + disjuntor
            guard.marcar_em_andamento        lease

  dossie.montar                              perfis.montar → mestre pt|en por
                                             idioma da vaga + ênfase do perfil
    12  agents/resume_optimizer              reordena; só reescreve COM LLM
        generators/pdf                       PDF + preview + checagem (inv. 8)
    6   agents/cover_letter                  idioma do currículo que vai junto

  13  applicators/{greenhouse,lever,linkedin}
      → 'enviada_confirmada' | 'revisao_manual' | 'aguardando_verificacao'
                                             | 'falha_automacao'

scripts/finalizar.py                               você, quando quiser
  vagas em 'aguardando_verificacao'          navegador VISÍVEL
  barreira == codigo   → busca no e-mail e preenche   (Greenhouse)
  barreira == captcha  → você resolve                 (Lever, inhire)
  → VOCÊ clica em enviar, no botão real
```

Agendamento em `orchestrator.main()`: coleta 2h, varredura 6h, pipeline +5min,
candidaturas +15min, relatório às 8h, backup às 3h30. APScheduler com jobstore
no Postgres, `max_instances=1` e `coalesce=True` — e **todo job registrado tem
de ser função de nível de módulo**, porque o jobstore serializa por referência
`módulo:função` (ver `tests/unit/test_orquestrador.py`).

**Onde o LLM entraria, e o que muda sem ele.** Hoje o projeto roda sem chave
nenhuma: normalização e score são determinísticos em `agents/extracao.py`, a
carta usa gabarito por idioma, e o otimizador só reordena tecnologias — ganho de
ATS medido em 120 vagas: **+0,00%**. Um LLM acrescentaria reescrever resumo e
bullets com o vocabulário da vaga, que é o que de fato move o ATS.

---

## Estrutura

Pacote único de domínio. Antes havia dez pacotes soltos na raiz — `agents`,
`config`, `filters`, `generators` e companhia —, todos importáveis do diretório
corrente. Nomes genéricos assim colidem com pacotes instalados, não deixam
fronteira entre aplicação e infraestrutura de repositório, e obrigam o pytest a
depender de `pythonpath = ["."]`.

```
run.py                 único entry point na raiz; ancora cwd e PYTHONPATH
jobapplier/            domínio — nada de UI aqui
  orchestrator.py      agendamento e as três esteiras do pipeline
  paths.py             caminhos ancorados na raiz do repositório
  tempo.py             datas: agora_utc(), hoje(), de_timestamp(), para_naive()
  perfis.py            perfil de currículo derivado do mestre (invariante 11)
  idioma.py            idioma da vaga: escolhe o mestre pt/en
  aprendizado.py       banco de respostas: o que você digitou uma vez, repete
  api.py               API local (127.0.0.1) que a extensão de navegador chama
  collectors/          Greenhouse, Lever, Gupy (APIs REST, sem browser)
  filters/             4A pré-normalização, 4B pós-normalização
  agents/              normalizer, scorer, resume_optimizer, cover_letter
  llm/                 abstração de provedor — infraestrutura, não agente
  applicators/         Greenhouse, LinkedIn, Gupy via Playwright
  safety/              Módulo 9: limites, delays, duplicidade
  resume_parser/       PDF/DOCX → JSON (extractors + parser)
  generators/          JSON → PDF
  notifications/       relatório diário por e-mail
  database/            models, repositórios, migrations Alembic
  config/              config.json e segredos
ui/                    Streamlit — descartável por design
  _bootstrap.py        põe a raiz no sys.path; importe primeiro em cada página
  app.py, pages/
tests/                 unit · e2e · integration
docs/                  especificação original
scripts/               instalação, varredura, panorama, sessão assistida
  varredura.py         tira da fila as vagas que não existem mais
  finalizar.py         sessão assistida: você resolve o desafio e clica
  panorama.py          números do funil, incluindo barreira de envio por board
```

Regras que essa estrutura impõe:

- **`jobapplier/` não importa de `ui/`.** A dependência é só num sentido. Quando
  o Streamlit for trocado por FastAPI, nada em `jobapplier/` muda.
- **`llm/` não é submódulo de `agents/`.** Abstração de provedor é
  infraestrutura. Há teste garantindo que `jobapplier.agents.llm` não exista.
- **Nunca construa caminho relativo ao cwd.** Use `jobapplier.paths`. Havia oito
  pontos com `Path("data/...")`, que só funcionavam porque todo entry point era
  executado da raiz; rodar um script de outro diretório criava um `data/` no
  lugar errado, em silêncio.
- **Data e hora só por `jobapplier.tempo`.** As colunas do banco são naive-UTC e
  essa decisão está documentada num lugar, não espalhada em chamadas
  `datetime.utcnow()` deprecadas.
- **`ui/` precisa de `import _bootstrap` como primeira linha**, em `app.py` e em
  toda página: `streamlit run ui/app.py` coloca `ui/` no sys.path, não a raiz, e
  o Streamlit pode executar uma página isolada num deep-link.

---

## Invariantes

Quebrar qualquer um destes causa dano real — conta banida, candidatura não
autorizada, currículo com informação falsa. Não relaxe nenhum sem pedir.

1. **`run_applications` só processa `status = 'aprovada'`.** Vagas `pendente`
   aguardam aprovação humana na página Vagas. Existe o escape
   `risco.auto_aplicar_pendentes = true`, que é explícito, logado como warning e
   nunca deve ser o padrão. Este bug já existiu: o agendador candidatava
   `pendente` junto e a fila de aprovação era decorativa.

2. **Todo caminho de candidatura passa por `jobapplier/safety/guard.py` antes de gastar
   qualquer recurso.** Na ordem: plataforma tem automação? já candidatou? limite
   de 24h e disjuntor liberam? Só então marca `em_andamento` e chama LLM ou abre
   browser. Nunca chame um applicator direto sem esses gates. A constante
   `MAX_DAILY_APPLICATIONS` já existiu em `jobapplier/applicators/linkedin.py` sem nunca ser
   consultada, e o resultado foi ~100 candidaturas em dois dias.

3. **O sistema nunca afirma o que o currículo não sustenta.** O otimizador pode
   reordenar tecnologias, reformular descrição com terminologia da vaga e ajustar
   ênfase; nunca criar experiência, empresa, cargo, data, certificação ou
   tecnologia inexistente (restrição no prompt de `jobapplier/agents/resume_optimizer.py`).
   O mesmo vale para `_auto_answer` nos applicators: pergunta que não sabemos
   responder retorna `None` e vira pergunta manual, **nunca um chute**. Dois bugs
   já violaram isso — responder "Sim" para inglês sem inglês no currículo, e
   escolher "São Paulo - Zona Sul" quando o currículo só diz "São Paulo".

4. **Nada de `data/` é versionado, nunca.** Contém API keys, CPF, cookies de
   sessão do LinkedIn, 101 MB de dados do Postgres e currículos gerados.

5. **Segredo novo vai para `.env` via `jobapplier/config/secrets.py`**, nunca para
   `data/config.json`. O fallback para JSON existe apenas para compatibilidade e
   emite warning. A UI grava via `secrets.gravar_env`.

6. **LinkedIn é opt-in e fica isolado.** Automatizar Easy Apply viola o User
   Agreement do LinkedIn e arrisca restrição permanente de uma conta que é a
   identidade profissional real do usuário. O núcleo Greenhouse/Lever/Gupy deve
   sempre funcionar sem ele. Nunca escreva teste automatizado que faça login no
   LinkedIn.

7. **Nenhum módulo instancia SDK de LLM direto.** Sempre `jobapplier.llm.get_client()`.

8. **Todo PDF gerado é renderizado em imagem e verificado.** `generate_pdf` chama
   `gerar_preview_e_verificar` por padrão: PNG por página ao lado do arquivo, mais
   checagem automática de geometria. Com `estrito=True` (padrão), problema grave
   levanta `LayoutInvalidoError` e a candidatura não sai — **falha fechada**.
   Nunca chame `generate_pdf(..., preview=False)` num caminho que envia currículo.
   Currículos já foram enviados quebrados porque ninguém olhava o resultado e
   nada verificava. Detalhes em [Regra dos PDFs](#regra-dos-pdfs).

9. **Saída de LLM nunca vira artefato entregável sem normalização.** Este é o caso
   geral do bug do PDF: `optimize()` devolvia o JSON do modelo direto para o
   gerador, e quando o modelo serializava uma lista como string o currículo saía
   com `['bullet um', 'bullet dois']` impresso. Todo ponto onde saída de LLM
   cruza para um arquivo, um formulário ou o banco passa por normalização
   (`_normalizar_saida`) ou validação Pydantic. Vale para cover letter,
   `normalizado_json` e qualquer campo novo.

10. **Limite, contador ou flag de segurança é criado e consultado no mesmo commit,
    com teste.** `MAX_DAILY_APPLICATIONS = 10` existiu por semanas sem nenhum
    chamador — segurança que não roda é pior que ausência de segurança, porque
    passa a sensação de proteção. Toda guarda em `safety/` tem teste que falha se
    ela for removida.

11. **Fato do currículo mora só no mestre.** `data/resume.json` (e sua tradução
    `data/resume_en.json`) são a única fonte de empresa, cargo, data, formação,
    certificação e contato. Perfil por vaga é **derivado** por
    `jobapplier/perfis.py`, que só troca resumo profissional e ordem de
    tecnologias — nunca fato. Existiam quatro `resume_base_*.json` que eram
    cópias integrais do mestre; quando o mestre foi reescrito, as quatro ficaram
    para trás afirmando FIAP "em andamento" (concluída), **sem o telefone** (o
    gerador de PDF lê `telefone`, então todo currículo saiu sem contato) e com o
    nome do cliente em duas delas. Nada apareceu no score, que lê o mestre — só o
    PDF lia as cópias. `tests/unit/test_perfis.py` falha se algum perfil ou
    idioma divergir do mestre em fato.

12. **Segredo e PII nunca entram em log.** Desde que o log passou a ser gravado em
    `data/logs/*.jsonl`, qualquer coisa logada fica em disco. Não logue
    `config.load()`, o dict de `dados_pessoais`, conteúdo de currículo nem valor
    de chave de API. Logue o nome da configuração, não o valor.

---

## Camada de LLM (`jobapplier/llm/`)

Três provedores, contrato único. Trocar de provedor é configuração, não código.

| Provedor | Modelo padrão | Variável | Pacote |
|---|---|---|---|
| `openai` | `gpt-5.6-luna` | `AIJOB_OPENAI_API_KEY` | `openai` |
| `gemini` | `gemini-2.5-flash` | `AIJOB_GEMINI_API_KEY` | `google-genai` |
| `anthropic` | `claude-sonnet-5` | `AIJOB_ANTHROPIC_API_KEY` | `anthropic` |

Padrões são o tier de custo baixo de cada família, coerente com o projeto: o
pipeline 4A/4B existe justamente para economizar chamada. Alternativas em
`MODELOS_SUGERIDOS`, e qualquer ID aceito pelo provedor serve
via `llm.modelo` / `AIJOB_LLM_MODELO`.

```python
from jobapplier.llm import get_client

client = get_client()                                  # resolve por config/ambiente
client = get_client(provedor="openai", modelo="gpt-5.6-sol")
texto = client.generate(prompt, temperature=0.2)
dados = client.generate_json(prompt, temperature=0.1)  # dict | list
```

**Resolução do provedor**, em ordem: argumento explícito → `AIJOB_LLM_PROVEDOR` →
`llm.provedor` na config → autodetecção (primeiro com chave, ordem
`openai → gemini → anthropic`).

**Arquitetura interna.** `base.py` concentra o que é comum: cache em banco
(TTL 24h), retry com backoff em rate limit, e `extrair_json` tolerante. Provedor
concreto implementa só `_gerar_texto` e, opcionalmente, `_gerar_json_nativo`.

Ao adicionar um provedor: subclasse de `LLMClient` em `jobapplier/llm/providers.py`, declare
`provedor`/`modelo_padrao`/`env_chave`/`pacote_pip`, registre em `PROVEDORES` e
`MODELOS_SUGERIDOS`, adicione a `ORDEM_PADRAO` e a `PROVEDOR_INFO` em
`ui/pages/1_Setup.py`. Há teste garantindo que todo provedor registrado declara os
metadados e que o padrão está entre os sugeridos.

**Modo JSON é nativo por provedor** — mais confiável que instruir no prompt e
limpar cerca markdown depois: `response_mime_type` no Gemini, `response_format:
json_object` na OpenAI, prefill `{` na Anthropic. `extrair_json` continua como
rede de segurança.

**SDKs são importados de forma tardia**, dentro do construtor. O projeto roda com
apenas um provedor instalado; a ausência levanta `LLMDependenciaAusente` com o
`pip install` correto.

**Cadeia de fallback.** Com `llm.fallback` ativo, cota estourada no primário cai
para o próximo em vez de derrubar todas as vagas restantes do ciclo.
`ClienteComFallback` não é subclasse de `LLMClient` de propósito — só reexpõe a
interface pública.

O shim `agents/gemini_client.py` foi removido — não havia mais nenhum importador.

---

## Módulo 9 — Controle de Risco (`jobapplier/safety/guard.py`)

Janela **deslizante de 24h**, não dia-calendário: dia-calendário permite 10
candidaturas às 23h50 e outras 10 às 00h10, exatamente a rajada que a detecção
procura.

Limites padrão: `linkedin` 10, `gupy` 15, `greenhouse` 20, `lever` 20.
LinkedIn é sempre o mais restritivo — há teste garantindo isso.

O limite principal conta só `enviada` e `perguntas_pendentes`. Erro de
pré-validação (CPF ausente, link inválido) nunca toca a plataforma, e contá-lo
queimaria a cota inteira sem enviar nada. Erros são cobertos pelo **disjuntor**:
se as tentativas totais passarem de `limite * 3`, a plataforma pausa.

`liberar_orfaos()` devolve vagas travadas em `em_andamento` para `aprovada`.
**Só é correto porque o agendador roda com `max_instances=1`** — se algum dia
houver execução concorrente, essa função precisa de uma coluna `atualizado_em`
para distinguir órfão de trabalho em andamento.

Configuração opcional em `data/config.json`:

```json
{
  "risco": {
    "limites_diarios": { "linkedin": 5, "gupy": 10 },
    "delay_min": 20,
    "delay_max": 90,
    "auto_aplicar_pendentes": false
  }
}
```

---

## Testes

Três camadas, por custo e risco crescentes.

### 1. `tests/unit/` — sem rede, sem banco, sem browser (~1.7s)

Roda sempre, inclusive em cada salvamento se quiser. Cobre a lógica que **decide**:

| Arquivo | O que protege |
|---|---|
| `test_filters.py` | 4A/4B — o que custa chamada de LLM e o que é descartado |
| `test_safety.py` | limites, delays, jitter, invariante de LinkedIn mais restritivo |
| `test_llm.py` | extração de JSON, retry, fallback, resolução de provedor |
| `test_applicators_logic.py` | `_auto_answer` — o que é escrito num formulário real |
| `test_collectors.py` | parsing de resposta de API, hash de dedup |
| `test_config.py` | precedência ambiente > JSON |
| `test_resume_parser.py` | schema do ResumeJSON, erros de parsing |
| `test_importabilidade.py` | todo módulo do pacote importa; contrato de estrutura |

`test_importabilidade.py` enumera os módulos com `pkgutil` em vez de listá-los,
então cobre arquivo novo sem ninguém atualizar o teste. Existe por causa de uma
quebra real: um import de `pathlib.Path` foi removido de `applicators/linkedin.py`
enquanto `Path` seguia em uso nas anotações, e a suíte passou verde porque nenhum
teste importava aquele módulo — o applicator só é carregado em tempo de execução.

Para LLM, use o padrão `ClienteFake` de `test_llm.py` em vez de mock de SDK:
subclasse de `LLMClient` com respostas e erros roteirizados. Testa a lógica
compartilhada de verdade, sem rede.

### 2. `tests/e2e/` — Playwright real contra HTML local (~16s)

**Esta é a camada que pega quebra de seletor**, o modo de falha mais comum dos
applicators, porque depende do HTML de terceiros. Sem rede: o HTML vem de
`tests/e2e/fixtures/`.

A fixture do Greenhouse reproduz o comportamento do **react-select** — as opções
só existem no DOM depois do clique no controle. Sem isso o teste passaria por
acidente, encontrando opções já renderizadas.

```python
pytestmark = pytest.mark.e2e

def test_algo(carregar_fixture):
    page = carregar_fixture("greenhouse_form.html")
    _pw_fill_text(page, "#first_name", "Ricardo")
    assert page.input_value("#first_name") == "Ricardo"
```

Fixtures em `tests/e2e/conftest.py`: `browser` (sessão, pula se Chromium não
estiver instalado), `page` (isolada por teste, viewport igual à de produção),
`carregar_fixture`.

**Atualizar uma fixture quando um formulário mudar** — capture o HTML real:

```python
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(); p = b.new_page()
    p.goto("https://boards.greenhouse.io/<slug>/jobs/<id>")
    open("tests/e2e/fixtures/greenhouse_form.html", "w", encoding="utf-8").write(p.content())
    b.close()
```

Revise o HTML capturado antes de commitar: páginas reais podem trazer token de
sessão ou dado pessoal.

### 3. `@pytest.mark.live` — toca rede. **Nunca roda por padrão**

`addopts = "-m 'not live'"` no `pyproject.toml` garante isso. Use só quando algo
quebrou e você precisa saber se o HTML de produção mudou: `pytest -m live`.

Restrições absolutas: **apenas Greenhouse/Lever** (boards públicos, sem login — o
hCaptcha do Lever só aparece no envio, e o teste live nunca envia) e
**nunca submeter formulário** — só navegar e verificar que os campos existem.
LinkedIn e Gupy exigem login; automatizá-los num teste queima cota de detecção e
arrisca a conta (invariante 6).

### Debugar Playwright quando um applicator quebra

```powershell
# Inspector: abre browser e pausa em cada ação
$env:PWDEBUG=1

# Ver o browser durante um teste e desacelerar
# (no código: p.chromium.launch(headless=False, slow_mo=500))

# Trace navegável — melhor ferramenta para falha intermitente
# context.tracing.start(screenshots=True, snapshots=True)
# context.tracing.stop(path="trace.zip")
.venv\Scripts\python.exe -m playwright show-trace trace.zip
```

A coluna `candidaturas.screenshots_path` existe no schema e **ninguém escreve
nela**. Capturar screenshot no `except` dos applicators e gravar o caminho ali é
o próximo passo óbvio de diagnóstico — hoje uma falha em produção deixa só a
mensagem de erro.

### Marcadores

`e2e` (Playwright local), `live` (rede, fora do padrão), `db` (exige Postgres).
`--strict-markers` está ativo: marcador não declarado no `pyproject.toml` é erro.

### O que ainda não tem cobertura

`orchestrator.run_*` (orquestração), `applicators.apply` (fluxo completo, precisa
de fixture de multi-step), `generators/pdf`, `notifications/email_sender`, as
funções de `guard` que tocam banco (`checar_limite`, `ja_candidatado`,
`liberar_orfaos` — pedem `tests/integration` com marcador `db`), e as páginas
Streamlit.

---

## Bibliotecas

Cada dependência e por que está aqui. Ver `requirements.txt`.

**Backend / dados.** `sqlalchemy>=2.0` (ORM, estilo 2.0 com
`Mapped`/`mapped_column` — não use o estilo 1.x declarativo), `alembic` (toda
mudança de schema é migration versionada, nunca `create_all` em produção),
`psycopg2-binary` (driver Postgres), `apscheduler[sqlalchemy]` (jobs periódicos
com jobstore no Postgres, então o agendamento sobrevive a restart).

**LLM.** `openai`, `google-genai`, `anthropic` — todos atrás de `jobapplier/llm`.
Note que o SDK do Gemini é `google-genai` (import `google.genai`), **não** o
legado `google-generativeai`; dois testes já ficaram silenciosamente pulados por
causa dessa confusão.

**Automação.** `playwright` — escolhido em vez de Selenium por auto-wait,
seletores mais robustos e trace viewer. Use a API **sync** (`sync_playwright`),
que é o padrão do projeto; não misture async.

**Currículo.** `pydantic>=2` (schema do `ResumeJSON` — validação de saída de LLM
é obrigatória, não opcional), `pdfplumber` (texto de PDF), `python-docx` (DOCX),
`xhtml2pdf` (HTML → PDF do currículo otimizado).

**Frontend.** `streamlit>=1.35`. Descartável por design (ver Direção
arquitetural).

**Utilitários.** `requests` (APIs de Greenhouse/Lever/Gupy — os coletores não
usam browser), `structlog` (no requirements e **ainda não adotado**; o logging é
`basicConfig`, item da Fase 1), `click`.

**Desenvolvimento.** `pytest`, `pytest-asyncio`, `ruff` (lint e format — dispensa
black + isort + flake8).

Dependências estão com `>=` e **sem pin**. Quebra de Playwright ou Streamlit
entra sem aviso; travar em `==` com um lockfile é item de infraestrutura pendente.

---

## Convenções

**Banco.** `get_session()` é context manager que commita na saída e faz rollback
na exceção. Repositórios em `database/repository.py`. Toda mudança de schema
passa por Alembic.

**Applicators** retornam sempre
`{status, application_id, mensagem, perguntas_manuais}`, com
`status ∈ enviada | perguntas_pendentes | erro`. Novo applicator deve seguir esse
contrato e ser registrado em `PLATAFORMAS_COM_AUTOMACAO` no orquestrador.

**Coletores** herdam `BaseCollector` e devolvem `CollectedJob`; o `hash` é
calculado no `__post_init__`.

**Frontend (Streamlit).** É descartável por design — não coloque regra de negócio
em `pages/`. Hoje `ui/pages/3_Vagas.py` ainda escreve `AprovacoesHistorico` direto,
dívida a pagar na Fase 1 com a camada `services/`. Padrões do projeto:
`st.set_page_config` primeiro (por isso `E402` é ignorado em `pages/`), guarda de
`config.is_setup_complete()` no topo, imports de banco dentro de `try` com
`st.error` + `st.stop()`, e chave de API sempre `type="password"`.

**Toda alteração de frontend passa por validação visual com Playwright, antes de
ser dada como pronta.** Capture a página em viewport de desktop (1600×900),
abra a imagem e avalie como especialista de UI/UX — não só "carregou".

```powershell
python run.py                                        # em outro terminal
.venv\Scripts\python.exe scripts\ui_screenshots.py   # captura em data/screenshots/ui/
```

Isto não é zelo: `HTTP 200` não prova nada porque o Streamlit devolve 200 com o
traceback dentro da página, e o teste de contrato só pega nome de coluna errado.
Nenhum dos dois enxerga layout. Duas telas foram entregues com
`layout="centered"` ocupando **736px de 1600 — 46% da tela** e três *expanders*
fechados empilhados, e isso só apareceu quando o usuário reclamou que "parece
feito para celular". O que a captura mostra e a asserção não:

- largura ocupada e espaço morto;
- densidade — quantos elementos gastam linha inteira para não mostrar nada;
- hierarquia — o que o olho encontra primeiro é o que mais importa?
- estado real com dados de produção, não com a fixture do teste.

`scripts/ui_screenshots.py` também imprime a largura do conteúdo. Abaixo de ~70%
do viewport em página de trabalho, reveja o `layout`.

A régua de tipografia, medida de linha e espaço está em `docs/DESIGN_UI.md`, e é
aplicada por `ui/_estilo.py` — não invente escala nova por página.

**Limites do Streamlit já testados, para não repetir a tentativa:**

- `st.markdown(unsafe_allow_html=True)` **remove `onclick`**. Sobrevivem apenas
  `href`, `target`, `rel` e `class` — verificado no DOM renderizado.
- `st.components.v1.html` roda em iframe cujo sandbox **não tem
  `allow-top-navigation`**. Tentar navegar o app de dentro dele dá
  `Unsafe attempt to initiate navigation … frame is sandboxed` no console.
- Consequência: **um clique não consegue abrir link externo e executar código ao
  mesmo tempo.** "Abrir a vaga e avançar o cartão" exigiria componente React
  próprio. Até lá, abrir e registrar são dois cliques — e isso está no código
  comentado, não escondido.

**Erros.** Prefira exceção específica a `except Exception` cego. Onde o cego é
proposital (jitter, cache, coleta de uma empresa entre 150), comente o porquê.

**Escrita de segredo** só via `jobapplier/config/secrets.py`.

---

## Direção arquitetural

O produto é pessoal hoje, monetizável depois. Multi-tenancy é a única coisa que
não se retroage barato, então as costuras vêm antes das features.

**Insight central**: catálogo de vagas é dado **global**; avaliação e candidatura
são **por usuário**. Uma vaga de Data Engineer no Nubank é a mesma para todos, e
`normalizado_json` também não depende de quem você é — só `score` e
`candidatura` dependem. Hoje `vagas` mistura os dois, e é isso que a Fase 1
separa:

```
vagas         GLOBAL   hash, titulo, empresa, descricao, normalizado_json,
                       status: ativa | encerrada
avaliacoes    USUÁRIO  (usuario_id, vaga_id) unique, score, breakdown_json,
                       status: nova|filtrada_4a|filtrada_4b|pendente|aprovada|
                               rejeitada|em_andamento|candidatada|erro
candidaturas  USUÁRIO  + usuario_id
cache_gemini  GLOBAL   (renomear para cache_llm, com coluna 'provedor')
```

Isso é a economia unitária: coleta e normalização são o custo variável, e nesse
desenho pagam-se uma vez por vaga, não uma vez por vaga por usuário.

**Fase 1 (pendente)**: `usuarios` + `usuario_id` com stub `usuario_atual() -> 1`;
split acima; credenciais cifradas com Fernet (tira CPF do JSON); abstração de
storage (`put`/`get`/`url`) com URI no banco em vez de caminho absoluto; camada
`services/` que UI e orquestrador compartilham; `run_*(usuario_id)`; tabela
`execucoes` com `run_id` servindo de observabilidade e futura fila; adoção do
`structlog`.

**Fase 2**: tabela `eventos` correlacionando score previsto com desfecho real
(resposta, entrevista, oferta) — o funil hoje morre em `candidatada`.

Não construir ainda: login, billing, onboarding, admin, FastAPI, fila
distribuída. Todos são aditivos **desde que as costuras acima existam**.

---

## Armadilhas conhecidas

`ruff check .` passa limpo, e é exatamente o que o CI roda. Duas regras estão em
`ignore` no `pyproject.toml` com justificativa escrita — `SIM102` e `RUF001`,
ambas avaliadas caso a caso e recusadas por mérito, não por conveniência. O
`ruff format` **não** é aplicado neste projeto: reformataria ~48 arquivos
desfazendo alinhamentos intencionais, sem ganho funcional.

- **`data_publicacao` do Greenhouse chega tz-aware** e as colunas do banco são
  naive-UTC. Comparar os dois levanta `TypeError`; use `tempo.para_naive()`.
- **`bulk_create_if_not_exists`** faz um SELECT por linha. Com ~150 slugs
  Greenhouse são milhares de round-trips por ciclo; deve virar
  `INSERT ... ON CONFLICT DO NOTHING`.
- **`run_pipeline` abre uma sessão por campo atualizado** dentro do loop, ~4 por
  vaga.
- **`data/config.json` ainda guarda CPF e dados de diversidade em texto plano.**
  Some com a tabela de credenciais cifradas na Fase 1.
- **`candidaturas` sem constraint única em `vaga_id`** — a proteção contra
  duplicata é só `guard.ja_candidatado()`, em código.
- **Vaga afirmativa passa pelo score.** 136 no acervo (119 PCD, 13 mulheres, 4
  pessoas negras); uma chegou a `aprovada` com 84. O score mede aderência
  técnica e a barreira aqui não é técnica. `elegibilidade.programa_afirmativo`
  detecta e o 4A barra — **a menos que** você declare o grupo em
  `dados_pessoais.programas_afirmativos`. O sistema não presume nenhum lado:
  presumir elegível manda candidatura indevida, presumir inelegível em silêncio
  esconderia de um candidato PCD as 119 vagas feitas para ele. Por isso o motivo
  do descarte ensina onde declarar.
- **Vaga encerrada não sai da fila sozinha.** Amostra de 40 do Greenhouse: 22%
  já não existiam, e as 8 da inhire estavam todas mortas — o usuário lê o
  dossiê, decide, e leva 404. `jobapplier/vigencia.py` checa por plataforma e
  `varrer_encerradas` roda a cada 6h. `INDETERMINADA` nunca encerra: erro de
  rede não pode matar vaga viva.
- **Windows-only**: `scripts/install.ps1`, sem Dockerfile da aplicação. Impede
  rodar 24/7 num VPS, que é o ponto de um bot de candidaturas.
- **`jobapplier/applicators/lever.py` não existe** (Módulo 14), e a decisão é
  deliberada: sondagem de 22 slugs devolveu **2 vagas aderentes**, ambas no
  Spotify. `coleta.empresas_lever` está vazio e enchê-lo renderia isso. Refaça a
  sondagem antes de implementar — a conta muda se aparecer volume.
- **inhire é MANUAL por ensaio**, não por omissão: a página traz reCAPTCHA e
  monta o formulário por JavaScript, sem campo no DOM inicial. São 8 vagas no
  acervo, mas as da Radix têm os melhores scores da fila.
- **O filtro por senioridade do Módulo 4B nunca foi implementado.** O mapa
  `SENIORIDADE_ORDEM` em `post_filter.py` segue lá sem uso, com comentário
  explicando: implementar exige decidir a política (rejeitar acima do nível do
  candidato, abaixo, ou ambos) e isso muda quais vagas passam.
- **`Empresa`** (Módulo 17) e a **aprovação adaptativa** que consome
  `AprovacoesHistorico` estão no plano e no schema, mas sem implementação.
- **`candidaturas.screenshots_path`** existe e ninguém escreve nela.
- **O CI nunca executou.** `.github/workflows/ci.yml` existe (ruff + pytest +
  checagem de que nada de `data/` foi versionado), mas o repositório ainda não
  tem remoto.

`docs/initial_plan.md` é a especificação original completa, com a numeração de módulos
que o código referencia.
