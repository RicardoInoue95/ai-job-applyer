# AI Job Applier

Automação de busca e candidatura a vagas de dados no Brasil.

Coleta vagas em Greenhouse, Lever e Gupy (e LinkedIn via sessão salva), usa LLM
para normalizar e pontuar a aderência ao seu currículo, otimiza o currículo para
ATS, gera cover letter e submete a candidatura via Playwright.

Ferramenta de uso pessoal. Roda na sua máquina, com seus dados no seu disco.

> **Aviso.** Automatizar o Easy Apply do LinkedIn viola o User Agreement da
> plataforma e pode levar à restrição permanente da conta. O LinkedIn é opt-in e
> vem desligado; o núcleo Greenhouse/Lever/Gupy funciona sem ele.

---

## Como funciona

O pipeline é desenhado para gastar chamada de LLM o mais tarde possível — cada
etapa descarta vagas antes da etapa mais caraet.

```
Coleta          APIs de Greenhouse/Lever/Gupy      HTTP, sem IA
  ↓
Filtro 4A       cargo alvo, palavra bloqueada,     grátis
                localização                        
  ↓
Normalização    LLM extrai senioridade, stack,     custa
                idioma, setor, anos exigidos
  ↓
Filtro 4B       tecnologias obrigatórias,          grátis
                teto de experiência
  ↓
Scoring         LLM pontua 0–100 com pesos:        custa
                skills 40, senioridade 20,
                setor 15, idioma 15, local 10
  ↓
  ├─ score alto      → candidatura automática
  ├─ score médio     → fila de aprovação humana
  └─ score baixo     → descartada
  ↓
Candidatura     currículo otimizado para ATS +     Playwright
                cover letter + envio do formulário
```

Antes de qualquer candidatura, o controle de risco verifica limite diário por
plataforma, duplicidade e disjuntor de erros.

---

## Requisitos

- Python 3.12+
- Docker Desktop (para o PostgreSQL)
- Chave de API de **um** provedor: OpenAI, Google Gemini ou Anthropic

## Instalação

```powershell
git clone <url> && cd ai-job-applyer
.\scripts\install.ps1
```

Ou manualmente:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
copy .env.example .env
```

Preencha o `.env` com a chave do seu provedor:

```ini
AIJOB_OPENAI_API_KEY=sk-...
```

Basta uma. Deixando `AIJOB_LLM_PROVEDOR` vazio, o projeto detecta sozinho qual
provedor tem chave. Trocar de provedor depois é só preencher outra chave.

| Provedor | Modelo padrão | Variável |
|---|---|---|
| OpenAI | `gpt-5.6-luna` | `AIJOB_OPENAI_API_KEY` |
| Gemini | `gemini-2.5-flash` | `AIJOB_GEMINI_API_KEY` |
| Anthropic | `claude-sonnet-5` | `AIJOB_ANTHROPIC_API_KEY` |

## Uso

```powershell
python run.py
```

Sobe o PostgreSQL, a interface e o orquestrador. Abra http://localhost:8501 e
siga o wizard: provedor de IA → currículo → preferências de busca → LinkedIn
(opcional) → Gupy → e-mail.

Depois disso o orquestrador trabalha sozinho: coleta a cada 2h, pontua, e
candidata o que passar dos seus critérios. Vagas de score intermediário esperam
sua aprovação na aba **Vagas**.

---

## Estrutura

```
jobapplier/            domínio — nada de UI aqui
  collectors/          Greenhouse, Lever, Gupy (APIs REST)
  filters/             4A pré-normalização, 4B pós-normalização
  agents/              normalizer, scorer, resume_optimizer, cover_letter
  llm/                 abstração de provedor (OpenAI/Gemini/Anthropic)
  applicators/         Greenhouse, LinkedIn, Gupy via Playwright
  safety/              controle de risco: limites, delays, duplicidade
  resume_parser/       PDF/DOCX → JSON estruturado
  generators/          JSON → PDF do currículo
  notifications/       relatório diário por e-mail
  database/            models, repositórios, migrations Alembic
  config/              config.json e segredos
  orchestrator.py      agendamento e as três esteiras do pipeline
  paths.py             caminhos ancorados na raiz do repositório

ui/                    Streamlit (descartável por design)
tests/                 unit (rápidos) · e2e (Playwright local) · integration (banco)
docs/                  especificação original
scripts/               instalação
```

## Desenvolvimento

```powershell
.venv\Scripts\python.exe -m pytest tests/unit    # ~2s, sem rede nem banco
.venv\Scripts\python.exe -m pytest               # + e2e com Playwright local
.venv\Scripts\python.exe -m pytest -m live       # toca rede — só sob demanda
.venv\Scripts\python.exe -m ruff check . --fix
```

Convenções, invariantes e armadilhas conhecidas estão em [CLAUDE.md](CLAUDE.md).
A especificação original, com a numeração de módulos que o código referencia,
está em [docs/initial_plan.md](docs/initial_plan.md).

## Privacidade

Tudo fica na sua máquina. `data/` guarda currículos, candidaturas, cookies de
sessão e o banco — e é integralmente ignorado pelo git. Segredos vão para `.env`,
nunca para arquivo versionado.
