# AI Job Applier

Automação de busca e candidatura a vagas de dados no Brasil. Coleta vagas de
Greenhouse, Lever e Gupy (e LinkedIn via sessão salva), normaliza e pontua com
Gemini contra o currículo do usuário, otimiza o currículo para ATS, gera cover
letter e submete a candidatura via Playwright.

**Uso pessoal (usuário único), construído para permitir monetização futura.**
Isso governa decisões de arquitetura: ver [Direção arquitetural](#direção-arquitetural).

Idioma do projeto: **português** em nomes de domínio, comentários, logs, mensagens
de commit e docstrings. Termos técnicos consagrados ficam em inglês
(`hash`, `score`, `pipeline`, `Easy Apply`).

## Comandos

```powershell
# Setup inicial (uma vez)
.\install.ps1

# Rodar tudo: Postgres + Streamlit + orquestrador
python run.py                      # app em http://localhost:8501

# Testes
.venv\Scripts\python.exe -m pytest tests/unit -q          # rápidos, sem banco
.venv\Scripts\python.exe -m pytest tests -q               # inclui integração (exige Postgres)

# Banco
docker compose up postgres -d
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic revision -m "descrição"

# Executar uma etapa do pipeline isoladamente
.venv\Scripts\python.exe -c "import orchestrator; orchestrator.run_collection()"
.venv\Scripts\python.exe -c "import orchestrator; orchestrator.run_pipeline()"
.venv\Scripts\python.exe -c "import orchestrator; orchestrator.run_applications()"
```

## Fluxo

O pipeline é desenhado para **gastar Gemini o mais tarde possível**. Cada etapa
descarta vagas antes da etapa mais cara. Não reordene sem entender esse custo.

```
run_collection()                      HTTP, sem IA
  collectors/{greenhouse,lever,gupy}  → CollectedJob (hash = sha256(titulo+empresa+link))
  → vagas.status = 'nova'             dedup por hash

run_pipeline()                        por vaga com status 'nova'
  4A  filters/pre_filter              texto bruto, GRÁTIS      → 'filtrada_4a'
  2   agents/normalizer               Gemini → normalizado_json
  4B  filters/post_filter             JSON estruturado, GRÁTIS → 'filtrada_4b'
  3   agents/scorer                   Gemini → score 0-100
      score >= threshold_excelente    → 'aprovada'   (candidata automaticamente)
      score >= threshold_bom          → 'pendente'   (aguarda humano em pages/3_Vagas.py)
      abaixo                          → 'rejeitada'

run_applications()                    por vaga com status 'aprovada'
  Módulo 9  safety/guard              limites e duplicidade ANTES de gastar nada
  12  agents/resume_optimizer         Gemini → perfil otimizado + delta ATS
      generators/pdf                  → PDF
  6   agents/cover_letter             Gemini → texto
  13  applicators/{greenhouse,linkedin,gupy}   Playwright
  → candidaturas + vagas.status = 'candidatada' | 'aguardando_resposta' | 'erro'
```

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
   de 24h e disjuntor liberam? Só então marca `em_andamento` e chama Gemini ou
   abre browser. Nunca chame um applicator direto sem esses gates. A constante
   `MAX_DAILY_APPLICATIONS` já existiu em `applicators/linkedin.py` sem nunca ser
   consultada, e o resultado foi ~100 candidaturas em dois dias.

3. **O otimizador de currículo nunca inventa fato.** Reordenar tecnologias,
   reformular descrição com terminologia da vaga e ajustar ênfase: sim. Criar
   experiência, empresa, cargo, data, certificação ou tecnologia que não existe
   no currículo base: nunca. A restrição está no prompt em
   `agents/resume_optimizer.py` e não deve ser afrouxada.

4. **Nada de `data/` é versionado, nunca.** Contém API key, CPF, cookies de
   sessão do LinkedIn, 101 MB de dados do Postgres e currículos gerados.

5. **Segredo novo vai para `.env` via `config/secrets.py`**, nunca para
   `data/config.json`. O fallback para JSON existe apenas para compatibilidade e
   emite warning.

6. **LinkedIn é opt-in e fica isolado.** Automatizar Easy Apply viola o User
   Agreement do LinkedIn e arrisca restrição permanente de uma conta que é a
   identidade profissional real do usuário. O núcleo Greenhouse/Lever/Gupy deve
   sempre funcionar sem ele.

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
houver execução concorrente, essa função precisa de uma coluna
`atualizado_em` para distinguir órfão de trabalho em andamento.

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

## Convenções

- **Banco**: SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Alembic para migration.
  `get_session()` é context manager que commita na saída e rollback na exceção.
- **Gemini**: sempre via `agents/gemini_client.py`, nunca `genai` direto — ele
  concentra cache em banco (TTL 24h), retry com backoff em 429 e limpeza de
  cerca markdown no `generate_json`.
- **Applicators** retornam sempre
  `{status, application_id, mensagem, perguntas_manuais}`.
  `status` ∈ `enviada | perguntas_pendentes | erro`.
- **Coletores** herdam `BaseCollector` e devolvem `CollectedJob`; o `hash` é
  calculado no `__post_init__`.
- **Streamlit** é descartável por design. Não coloque regra de negócio em
  `pages/` — hoje `pages/3_Vagas.py` ainda escreve `AprovacoesHistorico` direto,
  o que é dívida a pagar na Fase 1.
- **Testes**: `tests/unit` não toca banco nem rede e roda em ~1s; mantenha
  assim. `tests/integration` exige Postgres.

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
cache_gemini  GLOBAL   (fica como está)
```

Isso é a economia unitária: coleta e normalização são o custo variável, e nesse
desenho pagam-se uma vez por vaga, não uma vez por vaga por usuário.

Fase 1 (pendente): `usuarios` + `usuario_id` com stub `usuario_atual() -> 1`;
split acima; credenciais cifradas com Fernet; abstração de storage
(`put`/`get`/`url`) com URI no banco em vez de caminho absoluto; camada
`services/` que UI e orquestrador compartilham; `run_*(usuario_id)`; tabela
`execucoes` com `run_id` servindo de observabilidade e futura fila.

Fase 2: tabela `eventos` correlacionando score previsto com desfecho real
(resposta, entrevista, oferta) — o funil hoje morre em `candidatada`.

Não construir ainda: login, billing, onboarding, admin, FastAPI, fila
distribuída. Todos são aditivos **desde que as costuras acima existam**.

## Armadilhas conhecidas

- **`datetime.utcnow()`** está deprecado (Python 3.13) e aparece em ~15 pontos.
  As colunas do banco são naive-UTC. Em código novo use
  `datetime.now(timezone.utc).replace(tzinfo=None)` para manter compatibilidade.
  `data_publicacao` do Greenhouse vem tz-aware — cuidado ao comparar.
- **`bulk_create_if_not_exists`** faz um SELECT por linha. Com ~150 slugs
  Greenhouse são milhares de round-trips por ciclo; deve virar
  `INSERT ... ON CONFLICT DO NOTHING`.
- **`run_pipeline` abre uma sessão por campo atualizado** dentro do loop, ~4 por
  vaga.
- **`response.text` do Gemini pode ser `None`** (bloqueio de safety,
  MAX_TOKENS), o que faz `generate_json` estourar `AttributeError` engolido por
  `except Exception` genérico — a vaga é pulada em silêncio.
- **`data/config.json` ainda guarda CPF e dados de diversidade em texto plano.**
  Some com a tabela de credenciais cifradas na Fase 1.
- **Dependências sem pin** (`>=`): quebra de Playwright ou Streamlit entra sem
  aviso.
- **Windows-only**: `install.ps1`, sem Dockerfile da aplicação.
- **`applicators/lever.py` não existe** (Módulo 14). Vagas Lever recebem status
  `sem_automacao` e são ignoradas — antes caíam no applicator do Greenhouse e
  falhavam depois de já ter gasto Gemini.
- **`Empresa`** (Módulo 17) e a **aprovação adaptativa** que consome
  `AprovacoesHistorico` estão no plano e no schema, mas sem implementação.

`initial_plan.md` é a especificação original completa, com numeração de módulos
que o código referencia.
