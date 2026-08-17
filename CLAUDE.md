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

## Comandos

```powershell
# ── Setup ────────────────────────────────────────────────────────────────────
.\install.ps1                                   # primeira vez
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
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff check . --fix
.venv\Scripts\python.exe -m ruff format .

# ── Banco ────────────────────────────────────────────────────────────────────
docker compose up postgres -d
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic revision -m "descrição"
.venv\Scripts\python.exe -m alembic downgrade -1

# ── Executar uma etapa isolada do pipeline ───────────────────────────────────
.venv\Scripts\python.exe -c "import orchestrator; orchestrator.run_collection()"
.venv\Scripts\python.exe -c "import orchestrator; orchestrator.run_pipeline()"
.venv\Scripts\python.exe -c "import orchestrator; orchestrator.run_applications()"

# ── Debug de Playwright (ver a seção Testes) ─────────────────────────────────
$env:PWDEBUG=1; .venv\Scripts\python.exe -c "import orchestrator; orchestrator.run_applications()"
```

---

## Fluxo

O pipeline é desenhado para **gastar LLM o mais tarde possível**. Cada etapa
descarta vagas antes da etapa mais cara. Não reordene sem entender esse custo.

```
run_collection()                      HTTP, sem IA
  collectors/{greenhouse,lever,gupy}  → CollectedJob (hash = sha256(titulo+empresa+link))
  → vagas.status = 'nova'             dedup por hash

run_pipeline()                        por vaga com status 'nova'
  4A  filters/pre_filter              texto bruto, GRÁTIS      → 'filtrada_4a'
  2   agents/normalizer               LLM → normalizado_json
  4B  filters/post_filter             JSON estruturado, GRÁTIS → 'filtrada_4b'
  3   agents/scorer                   LLM → score 0-100
      score >= threshold_excelente    → 'aprovada'   (candidata automaticamente)
      score >= threshold_bom          → 'pendente'   (aguarda humano em pages/3_Vagas.py)
      abaixo                          → 'rejeitada'

run_applications()                    por vaga com status 'aprovada'
  Módulo 9  safety/guard              limites e duplicidade ANTES de gastar nada
  12  agents/resume_optimizer         LLM → perfil otimizado + delta ATS
      generators/pdf                  → PDF
  6   agents/cover_letter             LLM → texto
  13  applicators/{greenhouse,linkedin,gupy}   Playwright
  → candidaturas + vagas.status = 'candidatada' | 'aguardando_resposta' | 'erro'
```

Agendamento em `orchestrator.main()`: coleta a cada 2h, pipeline em +5min,
candidaturas em +15min, relatório por e-mail às 8h. APScheduler com jobstore no
Postgres, `max_instances=1` e `coalesce=True`.

---

## Invariantes

Quebrar qualquer um destes causa dano real — conta banida, candidatura não
autorizada, currículo com informação falsa. Não relaxe nenhum sem pedir.

1. **`run_applications` só processa `status = 'aprovada'`.** Vagas `pendente`
   aguardam aprovação humana na página Vagas. Existe o escape
   `risco.auto_aplicar_pendentes = true`, que é explícito, logado como warning e
   nunca deve ser o padrão. Este bug já existiu: o agendador candidatava
   `pendente` junto e a fila de aprovação era decorativa.

2. **Todo caminho de candidatura passa por `safety/guard.py` antes de gastar
   qualquer recurso.** Na ordem: plataforma tem automação? já candidatou? limite
   de 24h e disjuntor liberam? Só então marca `em_andamento` e chama LLM ou abre
   browser. Nunca chame um applicator direto sem esses gates. A constante
   `MAX_DAILY_APPLICATIONS` já existiu em `applicators/linkedin.py` sem nunca ser
   consultada, e o resultado foi ~100 candidaturas em dois dias.

3. **O sistema nunca afirma o que o currículo não sustenta.** O otimizador pode
   reordenar tecnologias, reformular descrição com terminologia da vaga e ajustar
   ênfase; nunca criar experiência, empresa, cargo, data, certificação ou
   tecnologia inexistente (restrição no prompt de `agents/resume_optimizer.py`).
   O mesmo vale para `_auto_answer` nos applicators: pergunta que não sabemos
   responder retorna `None` e vira pergunta manual, **nunca um chute**. Dois bugs
   já violaram isso — responder "Sim" para inglês sem inglês no currículo, e
   escolher "São Paulo - Zona Sul" quando o currículo só diz "São Paulo".

4. **Nada de `data/` é versionado, nunca.** Contém API keys, CPF, cookies de
   sessão do LinkedIn, 101 MB de dados do Postgres e currículos gerados.

5. **Segredo novo vai para `.env` via `config/secrets.py`**, nunca para
   `data/config.json`. O fallback para JSON existe apenas para compatibilidade e
   emite warning. A UI grava via `secrets.gravar_env`.

6. **LinkedIn é opt-in e fica isolado.** Automatizar Easy Apply viola o User
   Agreement do LinkedIn e arrisca restrição permanente de uma conta que é a
   identidade profissional real do usuário. O núcleo Greenhouse/Lever/Gupy deve
   sempre funcionar sem ele. Nunca escreva teste automatizado que faça login no
   LinkedIn.

7. **Nenhum módulo instancia SDK de LLM direto.** Sempre `agents.llm.get_client()`.

---

## Camada de LLM (`agents/llm/`)

Três provedores, contrato único. Trocar de provedor é configuração, não código.

| Provedor | Modelo padrão | Variável | Pacote |
|---|---|---|---|
| `openai` | `gpt-5.6-luna` | `AIJOB_OPENAI_API_KEY` | `openai` |
| `gemini` | `gemini-2.5-flash` | `AIJOB_GEMINI_API_KEY` | `google-genai` |
| `anthropic` | `claude-sonnet-5` | `AIJOB_ANTHROPIC_API_KEY` | `anthropic` |

Padrões são o tier de custo baixo de cada família, coerente com o projeto: o
pipeline 4A/4B existe justamente para economizar chamada. Alternativas em
`MODELOS_SUGERIDOS` (`providers.py`), e qualquer ID aceito pelo provedor serve
via `llm.modelo` / `AIJOB_LLM_MODELO`.

```python
from agents.llm import get_client

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

Ao adicionar um provedor: subclasse de `LLMClient` em `providers.py`, declare
`provedor`/`modelo_padrao`/`env_chave`/`pacote_pip`, registre em `PROVEDORES` e
`MODELOS_SUGERIDOS`, adicione a `ORDEM_PADRAO` e a `PROVEDOR_INFO` em
`pages/1_Setup.py`. Há teste garantindo que todo provedor registrado declara os
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

`agents/gemini_client.py` é fachada depreciada. Não use em código novo.

---

## Módulo 9 — Controle de Risco (`safety/guard.py`)

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

Restrições absolutas: **apenas Greenhouse/Lever** (boards públicos, sem login) e
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

**LLM.** `openai`, `google-genai`, `anthropic` — todos atrás de `agents/llm`.
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
em `pages/`. Hoje `pages/3_Vagas.py` ainda escreve `AprovacoesHistorico` direto,
dívida a pagar na Fase 1 com a camada `services/`. Padrões do projeto:
`st.set_page_config` primeiro (por isso `E402` é ignorado em `pages/`), guarda de
`config.is_setup_complete()` no topo, imports de banco dentro de `try` com
`st.error` + `st.stop()`, e chave de API sempre `type="password"`.

**Erros.** Prefira exceção específica a `except Exception` cego. Onde o cego é
proposital (jitter, cache, coleta de uma empresa entre 150), comente o porquê.

**Escrita de segredo** só via `config/secrets.py`.

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

`ruff check .` aponta ~61 achados que são dívida consciente, majoritariamente os
dois primeiros itens abaixo.

- **`datetime.utcnow()`** está deprecado (Python 3.13) e aparece em ~10 pontos
  (`DTZ003`). As colunas do banco são naive-UTC. Em código novo use
  `datetime.now(timezone.utc).replace(tzinfo=None)` — há helpers `agora_utc()` em
  `agents/llm/base.py` e `_agora()` em `safety/guard.py`. `data_publicacao` do
  Greenhouse vem tz-aware; cuidado ao comparar.
- **`except Exception` cego** em ~7 pontos (`SIM105`) e `raise` sem `from`
  (`B904`).
- **`bulk_create_if_not_exists`** faz um SELECT por linha. Com ~150 slugs
  Greenhouse são milhares de round-trips por ciclo; deve virar
  `INSERT ... ON CONFLICT DO NOTHING`.
- **`run_pipeline` abre uma sessão por campo atualizado** dentro do loop, ~4 por
  vaga.
- **`data/config.json` ainda guarda CPF e dados de diversidade em texto plano.**
  Some com a tabela de credenciais cifradas na Fase 1.
- **`candidaturas` sem constraint única em `vaga_id`** — a proteção contra
  duplicata é só `guard.ja_candidatado()`, em código.
- **Windows-only**: `install.ps1`, sem Dockerfile da aplicação. Impede rodar 24/7
  num VPS, que é o ponto de um bot de candidaturas.
- **`applicators/lever.py` não existe** (Módulo 14). Vagas Lever recebem status
  `sem_automacao` e são ignoradas.
- **`Empresa`** (Módulo 17) e a **aprovação adaptativa** que consome
  `AprovacoesHistorico` estão no plano e no schema, mas sem implementação.
- **`candidaturas.screenshots_path`** existe e ninguém escreve nela.
- **Sem CI.** Nenhum GitHub Actions; testes e lint rodam só localmente.

`initial_plan.md` é a especificação original completa, com a numeração de módulos
que o código referencia.
