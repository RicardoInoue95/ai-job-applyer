# PROJETO: AI JOB APPLIER

## Objetivo

Desenvolver uma plataforma capaz de localizar, analisar, classificar e realizar candidaturas semi-automáticas ou automáticas em vagas de emprego no Brasil, focada em:

* LinkedIn Easy Apply
* Gupy
* Greenhouse
* Lever

O sistema é distribuído como um app Streamlit — qualquer pessoa clona o repositório, executa `streamlit run app.py` e é guiada por um wizard de configuração. Nenhum arquivo precisa ser editado manualmente.

---

# PERFIL DO CANDIDATO

Profissional com experiência em Engenharia de Dados, Analytics Engineering, Business Intelligence, Snowflake, Azure, Databricks, Azure Data Factory, Power BI, SQL, Python, Terraform, Git e Cloud Security.

O currículo é fornecido como DOCX ou PDF durante o setup. O sistema o converte para JSON canônico e usa como fonte única da verdade em todo o fluxo.

---

# ARQUITETURA GERAL

## Stack

| Camada | Tecnologia | Justificativa |
|---|---|---|
| Interface principal | Streamlit (multi-page) | Setup wizard + dashboard em um só app |
| Backend | Python 3.12+ | |
| Automação browser | Playwright (perfis persistentes) | |
| Orquestração | APScheduler com SQLAlchemyJobStore → Prefect (futuro) | Jobs persistidos no PostgreSQL — sobrevivem a restarts |
| Banco operacional | PostgreSQL (via Docker) + SQLAlchemy + Alembic | Múltiplos processos, sem locking |
| Cache IA | Tabela dedicada no PostgreSQL | |
| IA | Gemini | Análise, scoring, geração de texto |
| Logs | structlog | |
| Notificações | Email via SMTP | |
| Config/secrets | `data/config.json` (gerenciado pelo app) | Sem edição manual de arquivos |

## Dois processos separados

O sistema roda como **dois processos independentes**:

| Processo | Comando | Responsabilidade |
|---|---|---|
| `streamlit` | `streamlit run app.py` | Interface: setup wizard, dashboard, aprovações |
| `worker` | `python orchestrator.py` | Coleta, scoring, automação, relatórios |

O Streamlit tem um modelo de execução que re-processa o script a cada interação do usuário — rodar o APScheduler dentro dele causaria perda de jobs agendados. Os dois processos se comunicam exclusivamente via PostgreSQL: o worker escreve resultados, o Streamlit lê e exibe.

PostgreSQL roda em Docker. Streamlit e worker rodam localmente via `run.py`. O Docker é usado apenas para o banco — não há complexidade de display de browser em container.

```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: jobapplier
      POSTGRES_USER: jobapplier
      POSTGRES_PASSWORD: jobapplier
    ports: ["5432:5432"]
    volumes: ["./data/postgres:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U jobapplier"]
      interval: 5s
      retries: 5
```

## Princípio de configuração

**O app é a única interface de configuração.** Não existe `.env` nem `config.yaml` para editar manualmente. Tudo é configurado pelo wizard de setup e salvo em `data/config.json`. Este arquivo é local, gitignored e nunca commitado.

---

# ESTRUTURA DO APP (STREAMLIT MULTI-PAGE)

```
app.py                        # entrypoint — detecta first-run e redireciona
pages/
  1_Setup.py                  # wizard de onboarding (só aparece se não configurado)
  2_Dashboard.py              # KPIs e visão geral
  3_Vagas.py                  # fila de aprovação manual + busca
  4_Candidaturas.py           # histórico e status de cada candidatura
  5_Relatorios.py             # relatórios diários
  6_Configuracoes.py          # reconfigurar qualquer etapa do setup
```

### Lógica de first-run

`app.py` verifica se `data/config.json` existe e está completo. Se não:
→ redireciona para `1_Setup.py`

Se sim:
→ mostra `2_Dashboard.py`

---

# WIZARD DE SETUP (Módulo 0)

Executado na primeira vez. Cada etapa é uma tela no Streamlit. O progresso é salvo ao final de cada etapa — se o usuário fechar no meio, retoma de onde parou.

Todas as etapas ficam disponíveis para reconfiguração em `6_Configuracoes.py`.

---

## Etapa 1 — Gemini API Key

**O que pede:** campo de texto para a API key.

**Validação:** faz uma chamada de teste simples ao Gemini antes de salvar.

```
[ Cole sua Gemini API Key ]  [Testar e Salvar]

✓ Conectado ao Gemini (gemini-3.0-flash)
```

**O que salva em `config.json`:**
```json
{
  "gemini": {
    "api_key": "...",
    "modelo": "gemini-3.0-flash",
    "cache_ttl_horas": 24,
    "rate_limit_rpm": 60
  }
}
```

---

## Etapa 2 — Currículo

**O que pede:** upload de arquivo PDF ou DOCX.

**Fluxo:**
1. Usuário faz upload do arquivo.
2. Sistema executa o Módulo 16 (Resume Parser) em background.
3. Exibe o JSON extraído para o usuário revisar:
   - Nome, contato, resumo profissional
   - Lista de experiências com tecnologias
   - Formação, certificações, idiomas
4. Usuário confirma ou ajusta campos incorretos diretamente na tela.
5. JSON canônico salvo em `data/resume.json`.

```
Arquivo detectado: Ricardo Inoue CV.docx
Processando...

Nome:               Ricardo Inoue
Email:              ricardo@email.com
Experiências:       4 encontradas
Tecnologias:        Snowflake, Azure, Python, SQL, Power BI...
Completude:         92%

[ Confirmar e Continuar ]  [ Reprocessar ]
```

---

## Etapa 3 — Preferências de Busca

**O que pede:** configurações de filtro via formulário Streamlit.

```
Cargos de interesse (multiselect):
  ☑ Data Engineer  ☑ Analytics Engineer  ☑ BI Analyst
  ☑ Data Analyst   ☐ Data Architect      ☑ Cloud Data Engineer

Localização (multiselect):
  ☑ Remoto  ☑ Híbrido  ☐ Presencial
  Cidades específicas: São Paulo, Rio de Janeiro

Score mínimo para autoaprovação: [85] (slider 70–100)
Score mínimo para revisão manual: [70] (slider 50–84)

Palavras bloqueadas (tags):
  SAP  COBOL  Mainframe  TOTVS  [+ adicionar]

Palavras obrigatórias:
  Modo: ( ) Qualquer uma  (•) Todas
  Termos: SQL  Python  [+ adicionar]

Limite diário de candidaturas por plataforma:
  LinkedIn: [10]   Gupy: [30]   Greenhouse: [50]   Lever: [50]

Pretensão salarial:
  Valor: [ R$ 15.000 ]   Moeda: (•) BRL  ( ) USD
  (usado para preencher campos de formulário — não afeta o scoring)
```

**O que salva:**
```json
{
  "filtros": {
    "cargos": ["Data Engineer", "Analytics Engineer", "BI Analyst", "Data Analyst", "Cloud Data Engineer"],
    "localizacao": ["Remoto", "Híbrido"],
    "cidades": ["São Paulo", "Rio de Janeiro"],
    "palavras_bloqueadas": ["SAP", "COBOL", "Mainframe", "TOTVS"],
    "palavras_obrigatorias": { "modo": "todas", "termos": ["SQL", "Python"] }
  },
  "scoring": {
    "threshold_excelente": 85,
    "threshold_bom": 70
  },
  "candidatura": {
    "pretensao_salarial": 15000,
    "moeda": "BRL"
  },
  "automacao": {
    "limites_diarios": { "linkedin": 10, "gupy": 30, "greenhouse": 50, "lever": 50 },
    "delay_min_segundos": 5,
    "delay_max_segundos": 15,
    "retry_max": 3,
    "screenshot_audit": true
  }
}
```

---

## Etapa 4 — LinkedIn

**O que pede:** autenticação via browser.

**Fluxo:**
1. Usuário clica em "Conectar LinkedIn".
2. Sistema abre o Playwright em modo visível (browser real na tela do usuário).
3. Usuário faz login normalmente, incluindo 2FA se necessário.
4. Após login bem-sucedido, usuário clica em "Sessão Salva" no app.
5. Sistema salva o estado do browser em `data/sessions/linkedin_state.json`.
6. Exibe confirmação com o nome da conta detectada.

```
[ Conectar LinkedIn ]

→ Browser aberto. Faça login no LinkedIn normalmente.
  Quando terminar, clique no botão abaixo.

[ ✓ Já fiz login — Salvar Sessão ]

✓ Sessão salva — conta: Ricardo Inoue
```

**Notas:**
- Senha nunca é solicitada nem armazenada pelo app.
- Se sessão expirar, app detecta e pede nova autenticação via mesma tela.
- Etapa opcional — usuário pode pular e configurar depois.

---

## Etapa 5 — Gupy

Mesmo fluxo da Etapa 4.

```
[ Conectar Gupy ]
→ Browser aberto. Faça login na Gupy normalmente.
[ ✓ Já fiz login — Salvar Sessão ]
✓ Sessão salva
```

Sessão salva em `data/sessions/gupy_state.json`.

---

## Etapa 6 — Notificações por Email

**O que pede:** endereço de email de destino + credenciais SMTP (ou Gmail app password).

```
Email de destino:  [ ricardo@email.com        ]

Configuração SMTP:
  Host:     [ smtp.gmail.com ]
  Porta:    [ 587            ]
  Usuário:  [ meu@gmail.com  ]
  Senha:    [ ************** ]  ← app password do Gmail

[ Enviar Email de Teste ]  → ✓ Email recebido com sucesso
```

Etapa opcional. Se pulada, notificações ficam desabilitadas.

---

## Etapa 7 — Conclusão

```
✓ Gemini API configurada
✓ Currículo processado (92% de completude)
✓ Preferências de busca salvas
✓ LinkedIn conectado
✓ Gupy conectado
✓ Notificações configuradas

Tudo pronto!

[ Ir para o Dashboard ]
```

---

# ARMAZENAMENTO DE DADOS

Toda a persistência fica em `data/` — diretório local, gitignored.

```
data/
  config.json         # configurações do app (settings + secrets)
  resume.json         # JSON canônico do currículo
  app.db              # SQLite (vagas, candidaturas, cache)
  sessions/
    linkedin_state.json
    gupy_state.json
  resumes/            # PDFs gerados pelo Módulo 12
  screenshots/        # auditoria das candidaturas
  reports/            # relatórios diários
  logs/
```

`data/config.json` é a fonte única de configuração. O app lê e escreve nele — nunca o usuário diretamente.

---

# FLUXO PRINCIPAL

```
[First-run]
    → Wizard de setup (Módulo 0)
    → Currículo convertido para JSON (Módulo 16)
    → Sessões de browser salvas

[Ciclo diário — APScheduler]
    → Coleta de vagas (Módulo 1)
    → Deduplicação (Módulo 1A)
    → Filtros pré-IA sobre texto bruto (Módulo 4A)
    → Normalização via Gemini (Módulo 2)
    → Filtros pós-normalização (Módulo 4B)
    → Match IA — score 0–100 (Módulo 3)
        score >= 85 → autoaprovação
        score 70–84 → fila de revisão humana
        score < 70  → descartada
    → Para cada vaga aprovada:
        → Pesquisa da empresa (Módulo 17)
        → Otimização de currículo a partir do perfil base (Módulo 12)
        → Geração de cover letter personalizada (Módulo 6)
        → Geração de respostas de formulário (Módulo 5)
        → Automação de candidatura por prioridade:
            1. Greenhouse API  2. Lever API  3. Gupy  4. LinkedIn (best effort)
        → Registro: perfil usado, ATS score antes/depois, screenshots, status
    → Relatório diário (Módulo 11)
    → Notificação por email
```

---

# MÓDULO 1 – COLETOR DE VAGAS

## Estratégia por plataforma

| Plataforma | Método | Observação |
|---|---|---|
| LinkedIn | Playwright | API privada |
| Gupy | Playwright | Layouts variam por empresa |
| Greenhouse | API REST pública | `boards.greenhouse.io/v1/boards/{company}/jobs` |
| Lever | API REST pública | `api.lever.co/v0/postings/{company}` |

## Dados coletados

* Título, empresa, plataforma de origem
* Localização, modalidade, senioridade
* Faixa salarial (quando disponível)
* Descrição completa, link canônico, data de publicação
* `SHA256(título + empresa + link)` — hash para deduplicação

---

# MÓDULO 1A – DEDUPLICAÇÃO

1. Calcular hash. Se já existe no banco → ignorar.
2. Mesma vaga em múltiplas plataformas → registrar todos os links, candidatar pela preferencial: LinkedIn Easy Apply > Greenhouse API > Lever API > Gupy.

---

# MÓDULO 2 – NORMALIZAÇÃO

Executado após filtros pré-IA. Verifica cache antes de chamar Gemini.

**Output:**
```json
{
  "cargo": "",
  "senioridade": "",
  "tecnologias": [],
  "anos_experiencia_minimo": 0,
  "localizacao": "",
  "modalidade": "",
  "salario": "",
  "soft_skills": []
}
```

---

# MÓDULO 3 – IA DE MATCH

Avalia aderência entre currículo JSON e vaga normalizada com pesos explícitos por critério.

## Pesos de scoring

| Critério | Peso | Descrição |
|---|---|---|
| Skills técnicas | 40% | Sobreposição entre tecnologias do currículo e da vaga |
| Senioridade | 20% | Alinhamento entre nível exigido e experiência do candidato |
| Setor da empresa | 15% | Experiência prévia no mesmo setor (financeiro, varejo, saúde, etc.) |
| Idioma | 15% | Idioma exigido vs idiomas do currículo |
| Localização / modalidade | 10% | Compatibilidade com preferências configuradas |

Os pesos são configuráveis em `data/config.json` para ajuste fino.

## Output

```json
{
  "score": 0,
  "breakdown": {
    "skills_tecnicas": 0,
    "senioridade": 0,
    "setor": 0,
    "idioma": 0,
    "localizacao": 0
  },
  "motivos_positivos": [],
  "gaps": [],
  "resumo": ""
}
```

`breakdown` permite ao usuário entender exatamente por que uma vaga recebeu determinado score.

Verifica cache antes de chamar Gemini.

---

# MÓDULO 4 – FILTROS

## Módulo 4A — Pré-normalização (texto bruto, sem IA)

* Palavras bloqueadas no texto → descartar.
* Título não contém nenhum cargo da lista → descartar.
* Localização incompatível → descartar.

Custo: zero. Reduz volume antes de qualquer chamada Gemini.

## Módulo 4B — Pós-normalização (JSON normalizado)

* Senioridade fora do configurado → descartar.
* Anos de experiência exigidos acima do aceitável → descartar.
* Palavras obrigatórias ausentes (modo AND ou OR configurável) → descartar.

---

# MÓDULO 5 – GERAÇÃO DE RESPOSTAS

Gemini responde perguntas de formulários usando apenas o currículo JSON.

| Tipo de campo | Estratégia |
|---|---|
| Texto livre / textarea | Gemini gera resposta baseada no currículo |
| Dropdown | Gemini seleciona a opção mais aderente |
| Radio / checkbox | Gemini seleciona com base nos dados do currículo |
| Número (anos de exp.) | Calculado diretamente do JSON do currículo |
| Upload de arquivo | PDF do currículo otimizado (Módulo 12) |

Restrições: nunca inventar, usar apenas o currículo JSON, respostas em português.

Cache por `SHA256(pergunta + vaga_id)`.

---

# MÓDULO 6 – CARTA DE APRESENTAÇÃO

Gemini gera cover letter personalizada.

* Máximo 300 palavras, em português.
* Referenciar tecnologias específicas da vaga.
* Destacar experiências relevantes do currículo.

Cache por `vaga_id`.

---

# MÓDULO 7 – AUTOMAÇÃO LINKEDIN

## Classificação: best effort

LinkedIn detecta automação ativamente — analisa fingerprint do browser, padrões comportamentais ao longo do tempo e volume de ações por sessão. Contas podem receber restrição silenciosa (candidaturas "enviadas" que nunca chegam ao recrutador) ou bloqueio explícito após semanas ou meses de uso.

**O sistema funciona sem LinkedIn.** Greenhouse, Lever e Gupy são as plataformas confiáveis. LinkedIn é um bônus que agrega volume enquanto está ativo. O usuário deve estar ciente que a conta pode precisar de atenção periódica.

Limite: **10 candidaturas/dia** via Easy Apply — conservador o suficiente para reduzir risco de detecção.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Detecção de bot | Perfil persistente, delays aleatórios, user-agent fixo, limite de 10/dia |
| Captcha | Pausar, registrar `aguardando_captcha`, alertar por email |
| Sessão expirada | Detectar redirecionamento, registrar `sessao_expirada`, alertar |
| Restrição silenciosa | Logar confirmação de envio; alertar se taxa de resposta cair a zero |
| Vaga fechada | Verificar antes de iniciar; registrar `vaga_encerrada` |

## Fluxo

1. Carregar `data/sessions/linkedin_state.json`
2. Verificar validade (acesso ao feed sem redirecionamento)
3. Para cada vaga aprovada:
   - Abrir página, confirmar que está aberta
   - Iniciar Easy Apply
   - Iterar pelos steps do formulário usando Módulo 5
   - Upload do PDF otimizado (Módulo 12)
   - Screenshot de cada etapa
   - Submeter e registrar resultado

---

# MÓDULO 8 – AUTOMAÇÃO GUPY

Mesmo padrão do LinkedIn. Sessão em `data/sessions/gupy_state.json`.

Se campo desconhecido encontrado → registrar `formulario_desconhecido`, pausar, alertar.

Arquitetura extensível com handlers por tipo de formulário (cada layout de empresa pode ter um handler).

---

# MÓDULO 9 – CONTROLE DE RISCO

* Delays aleatórios entre `delay_min` e `delay_max` (configurados no setup)
* Movimentos de mouse e scroll simulados antes de cliques
* Verificar banco antes de aplicar — nunca duplicar candidatura
* Respeitar limite diário por plataforma
* Retry com backoff exponencial para erros transitórios
* Logging estruturado de todos os erros com contexto completo

---

# MÓDULO 10 – DASHBOARD (página 2_Dashboard.py)

## KPIs

* Vagas encontradas / filtradas / descartadas hoje
* Score médio das aprovadas
* Candidaturas realizadas / com erro
* Sessões de plataformas: ativa / expirada

## Status completo de candidatura

| Status | Descrição |
|---|---|
| `pendente` | Score 70–84, aguardando revisão humana |
| `aprovada` | Aprovada, aguardando execução |
| `rejeitada` | Rejeitada pelo usuário ou score < 70 |
| `em_andamento` | Automação executando agora |
| `candidatada` | Concluída com sucesso |
| `aguardando_captcha` | Captcha detectado, pausa até intervenção |
| `formulario_desconhecido` | Campo não mapeado (Gupy), requer revisão |
| `vaga_encerrada` | Vaga fechou antes da candidatura |
| `sessao_expirada` | Sessão da plataforma inválida |
| `erro` | Falha técnica, ver logs |

## Aprovação adaptativa

O sistema aprende o comportamento do usuário ao longo do tempo e ajusta o threshold efetivo de autoaprovação.

**Lógica:**
- A cada aprovação manual, registrar o score da vaga aprovada.
- Após 10+ aprovações manuais, calcular o score mínimo histórico aprovado.
- Se o usuário consistentemente aprova vagas com score >= X, sugerir elevar o threshold de revisão manual para X.
- O usuário confirma ou ignora a sugestão no dashboard.

```
Histórico: aprovadas com scores [69, 71, 72, 74, 73, 70, 72, 75, 71, 73]
Score mínimo aprovado: 69
Sugestão: "Você aprova consistentemente vagas com score ≥ 69. Deseja ajustar o threshold para 69?"
```

O threshold nunca é ajustado automaticamente sem confirmação do usuário.

## Página 3_Vagas.py — Fila de Aprovação

Para cada vaga com score entre threshold_bom e threshold_excelente:

* Título, empresa, score, breakdown por critério, motivos positivos, gaps
* Resumo da pesquisa da empresa (Módulo 17)
* Link para a vaga original
* Botões: **Aprovar** / **Rejeitar**

## Página 4_Candidaturas.py

Histórico completo com filtros por plataforma, data, status. Link para screenshots de auditoria.

## Página 6_Configuracoes.py

Permite reconfigurar qualquer etapa do wizard sem precisar reiniciar o setup completo:

* Trocar API key do Gemini
* Atualizar currículo
* Ajustar preferências de busca
* Renovar sessão do LinkedIn ou Gupy
* Alterar email de notificações

---

# MÓDULO 11 – RELATÓRIOS

Gerado ao final de cada ciclo diário.

* Total de vagas encontradas / filtradas / descartadas
* Top vagas por score
* Candidaturas realizadas e falhas do dia
* Alertas ativos (sessão expirada, captcha, etc.)

Formato: PDF e HTML (xhtml2pdf). Enviado por email e disponível em `5_Relatorios.py`.

---

# MÓDULO 12 – RESUME OPTIMIZATION ENGINE

## Princípio

JSON canônico (`data/resume.json`) é a fonte única da verdade. PDF e DOCX são sempre gerados a partir dele.

## Restrições absolutas

Nunca inventar: experiências, certificações, cargos, empresas, tecnologias, datas.

Pode apenas: reorganizar, reordenar competências, reescrever descrições com terminologia da vaga, ajustar resumo e palavras-chave ATS.

## Processo

1. Rankear skills da vaga por importância
2. Calcular ATS match score (matched vs missing keywords)
3. Reescrever priorizando: Resumo → Experiência atual → Anteriores → Competências → Certificações
4. **Auditoria em duas camadas** antes de salvar:

   **Camada literal** — campos estruturados (diff exato):
   - Empresas, cargos, datas, certificações, nomes de tecnologias
   - Qualquer valor no JSON otimizado que não exista literalmente no original → rejeitar e alertar

   **Camada semântica** — texto livre (via Gemini):
   - Descrições de experiências podem ser reescritas com terminologia diferente ("desenvolvi pipelines ETL" → "construção de pipelines de ingestão")
   - Gemini verifica se cada descrição otimizada é semanticamente equivalente à original — sem novas afirmações de fatos, só reformulação
   - Resultado: `aprovado` ou `rejeitado` com explicação do que foi inventado

## Perfis pré-gerados (resume_master.json → perfis base)

O `resume_master.json` é o currículo completo. A partir dele, o sistema gera **4 versões base** no onboarding — uma por perfil. Cada versão já destaca as competências relevantes para aquele cargo.

Quando uma vaga é aprovada, o sistema parte da versão base do perfil mais próximo e faz a otimização final para aquela vaga específica — não começa do zero.

```
resume_master.json
    ├── resume_base_data_engineer.json
    ├── resume_base_analytics_engineer.json
    ├── resume_base_bi_analyst.json
    └── resume_base_cloud_data_engineer.json
              ↓ (otimização por vaga)
    resume_data_engineer_{vaga_id}.pdf
```

| Perfil | Destaque principal |
|---|---|
| **Data Engineer** | ETL/ELT, Snowflake, Databricks, ADF, Python, SQL |
| **Analytics Engineer** | Modelagem, Bronze/Silver/Gold, Métricas, Power BI, SQL |
| **BI Analyst** | Dashboards, KPIs, Power BI, Análise de negócio |
| **Cloud Data Engineer** | Azure, Terraform, Segurança, Infraestrutura |

## Output de auditoria ATS (por candidatura)

```json
{
  "vaga_id": "abc123",
  "perfil_base": "data_engineer",
  "ats_original": 72,
  "ats_otimizado": 91,
  "keywords_adicionadas": ["Data Modeling", "Snowflake", "Azure Data Factory"],
  "auditoria": "aprovado",
  "todas_keywords_existem_no_master": true
}
```

Salvo junto com a candidatura para rastrear quais perfis geram mais entrevistas.

## Exportação

`xhtml2pdf` (PDF) + `python-docx` (DOCX). Templates em `templates/resume/`.

`xhtml2pdf` é instalável via pip puro em Windows/Mac/Linux sem dependências de sistema — substitui WeasyPrint que exige GTK3 e quebra no Windows.

Arquivos salvos em `data/resumes/resume_{perfil}_{vaga_id}.pdf`.

---

# MÓDULO 13 – AUTOMAÇÃO GREENHOUSE

API pública: `POST /boards/{company}/jobs/{id}/applications`

Fallback para Playwright se necessário.

---

# MÓDULO 14 – AUTOMAÇÃO LEVER

API pública: `POST /v0/postings/{company}/{id}/apply`

Fallback para Playwright se necessário.

---

# MÓDULO 15 – CACHE E CONTROLE DE CUSTOS GEMINI

* Cache em tabela `cache_gemini` no PostgreSQL
* Chave: `SHA256(modelo + prompt)`
* TTL configurável por tipo (padrão 24h)
* Rate limiting interno: fila respeita `rate_limit_rpm`
* Retry com backoff em `429`
* Estimativa de tokens consumidos logada por ciclo e exibida no dashboard

---

# MÓDULO 16 – RESUME PARSER (DOCX/PDF → JSON)

Executado no setup (Etapa 2) e disponível para reprocessamento em Configurações.

## Fluxo interno

```
Upload (DOCX/PDF)
    → Extrator por formato
    → Texto bruto + metadados
    → GeminiResumeParser → JSON
    → Validação Pydantic
    → Score de completude (0–100)
    → Exibição para confirmação do usuário
    → Salvo em data/resume.json
```

## Arquitetura

| Camada | Componente |
|---|---|
| Extratores | `PDFExtractor` (pdfplumber), `DOCXExtractor` (python-docx) |
| Factory | Seleciona extrator pelo sufixo — extensível sem tocar no restante |
| Parser IA | `GeminiResumeParser` — JSON mode, retry até 3x |
| Validação | Pydantic + score de completude |

PDF escaneado (< 100 chars/página) → `ScannedPDFError` com mensagem clara.

## Dependências

`pdfplumber`, `python-docx`, `google-generativeai`, `pydantic`, `xhtml2pdf`

---

# MÓDULO 17 – AGENTE DE PESQUISA DE EMPRESA

## Objetivo

Antes de cada candidatura, coletar informações públicas sobre a empresa para enriquecer cover letters, respostas de formulário e o contexto do match.

## Quando executa

Após aprovação da vaga (manual ou automática), antes do Módulo 12 e 6.

## Fontes

| Fonte | Método | Dados coletados |
|---|---|---|
| Site institucional | Playwright (scrape da homepage + /about) | Missão, produtos, segmento, tecnologias citadas |
| LinkedIn da empresa | Playwright (página pública) | Tamanho, setor, localização, descrição |
| Google News | Requests + parsing | Notícias recentes (últimos 90 dias) |

Glassdoor **não** incluído — ToS restritivo para scraping.

## Output

```json
{
  "empresa": "Nubank",
  "segmento": "Fintech",
  "tamanho": "10.000+ funcionários",
  "tecnologias_mencionadas": ["Clojure", "Python", "Kafka", "Spark"],
  "sobre": "Empresa brasileira de serviços financeiros digitais...",
  "noticias_recentes": [
    "Nubank anuncia expansão para novos mercados (Jun 2025)"
  ],
  "resumo_para_candidatura": "Nubank é uma fintech líder na América Latina..."
}
```

## Uso pelos outros módulos

* **Módulo 6 (Cover Letter)**: usa `resumo_para_candidatura` para personalizar a carta.
* **Módulo 5 (Respostas)**: usa `sobre` e `noticias_recentes` para responder "por que quer trabalhar aqui?".
* **Módulo 3 (Match)**: usa `segmento` para calcular o critério de setor (peso 15%).

Cache por `empresa` com TTL de 7 dias — a mesma empresa pode aparecer em múltiplas vagas.

---

# INSTALAÇÃO E EXECUÇÃO

## Pré-requisitos

Apenas dois programas precisam ser instalados manualmente. O `install.ps1` resolve todo o restante.

---

### Pré-requisito 1 — Python 3.12+

1. Acesse **python.org/downloads**
2. Clique em "Download Python 3.12.x" (ou versão mais recente 3.12+)
3. Execute o instalador
4. **Importante:** na primeira tela do instalador, marque a opção **"Add Python to PATH"** antes de clicar em Install
5. Após a instalação, abra o PowerShell e confirme:
   ```
   python --version
   → Python 3.12.x
   ```

---

### Pré-requisito 2 — Docker Desktop

Docker é usado para rodar o banco de dados PostgreSQL. Você não precisa entender Docker para usá-lo — o `install.ps1` e o `run.py` gerenciam tudo automaticamente.

**Passo 1 — Verificar se WSL2 está habilitado**

Docker no Windows requer o WSL2 (subsistema Linux). Abra o PowerShell como Administrador e execute:

```powershell
wsl --install
```

Se já estiver instalado, o comando vai informar. Reinicie o computador se solicitado.

**Passo 2 — Baixar e instalar o Docker Desktop**

1. Acesse **docker.com/products/docker-desktop**
2. Clique em "Download for Windows"
3. Execute o instalador `Docker Desktop Installer.exe`
4. Na tela de configuração, mantenha marcado **"Use WSL 2 instead of Hyper-V"**
5. Clique em Ok e aguarde a instalação
6. Reinicie o computador quando solicitado

**Passo 3 — Iniciar o Docker Desktop**

1. Abra o Docker Desktop pelo menu Iniciar
2. Aguarde o ícone da baleia 🐳 aparecer na barra de tarefas (pode levar 1-2 minutos na primeira vez)
3. Quando o ícone parar de animar, o Docker está pronto

**Passo 4 — Confirmar a instalação**

Abra o PowerShell e execute:

```powershell
docker --version
→ Docker version 26.x.x

docker compose version
→ Docker Compose version v2.x.x
```

Se ambos os comandos retornarem versões, o Docker está instalado corretamente.

> **Nota:** O Docker Desktop precisa estar aberto (rodando em background) sempre que você usar o app. Ele inicia automaticamente com o Windows por padrão — você pode confirmar isso nas configurações do Docker Desktop em Settings → General → "Start Docker Desktop when you sign in to your computer".

---

## Primeira vez (`install.ps1`)

O script faz tudo: verifica dependências, instala pacotes Python, baixa o browser para automação, sobe o container do banco, aguarda ele estar pronto e cria a estrutura de tabelas.

```powershell
# install.ps1
$ErrorActionPreference = "Stop"

Write-Host "=== AI Job Applier — Instalação ===" -ForegroundColor Cyan

# ── 1. Python 3.12+ ──────────────────────────────────────────────────────────
Write-Host "`n[1/7] Verificando Python..."
$version = python --version 2>&1
if ($version -notmatch "3\.(1[2-9]|[2-9]\d)") {
    Write-Host "ERRO: Python 3.12+ necessário." -ForegroundColor Red
    Write-Host "      Baixe em: https://python.org/downloads"
    Write-Host "      Marque 'Add Python to PATH' durante a instalação."
    exit 1
}
Write-Host "  OK: $version" -ForegroundColor Green

# ── 2. Docker instalado ───────────────────────────────────────────────────────
Write-Host "`n[2/7] Verificando Docker..."
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "ERRO: Docker Desktop não encontrado." -ForegroundColor Red
    Write-Host "      Baixe em: https://docker.com/products/docker-desktop"
    Write-Host "      Siga o passo a passo na seção 'Instalação do Docker' deste guia."
    exit 1
}

# Docker instalado mas não está rodando?
$dockerRunning = docker info 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: Docker está instalado mas não está rodando." -ForegroundColor Red
    Write-Host "      Abra o Docker Desktop e aguarde o ícone 🐳 aparecer na barra de tarefas."
    exit 1
}
Write-Host "  OK: Docker rodando" -ForegroundColor Green

# ── 3. Virtual environment ────────────────────────────────────────────────────
Write-Host "`n[3/7] Criando ambiente virtual Python..."
python -m venv .venv
.\.venv\Scripts\Activate.ps1
Write-Host "  OK" -ForegroundColor Green

# ── 4. Dependências Python ────────────────────────────────────────────────────
Write-Host "`n[4/7] Instalando dependências Python..."
pip install -r requirements.txt --quiet
Write-Host "  OK" -ForegroundColor Green

# ── 5. Browser para automação ─────────────────────────────────────────────────
Write-Host "`n[5/7] Baixando browser para automação (Chromium)..."
playwright install chromium
Write-Host "  OK" -ForegroundColor Green

# ── 6. PostgreSQL via Docker ──────────────────────────────────────────────────
Write-Host "`n[6/7] Iniciando banco de dados PostgreSQL..."
docker compose up postgres -d

# Espera ativa: tenta conectar até o banco responder (máx. 60 segundos)
$db_url = "postgresql://jobapplier:jobapplier@localhost:5432/jobapplier"
$connected = $false
for ($i = 1; $i -le 12; $i++) {
    Start-Sleep -Seconds 5
    $check = python -c "
import sqlalchemy, sys
try:
    e = sqlalchemy.create_engine('$db_url')
    e.connect().close()
    print('ok')
except: print('fail')
" 2>&1
    if ($check -eq "ok") { $connected = $true; break }
    Write-Host "  Aguardando PostgreSQL... ($($i * 5)s)"
}

if (-not $connected) {
    Write-Host "ERRO: PostgreSQL não respondeu em 60 segundos." -ForegroundColor Red
    Write-Host "      Verifique: docker compose logs postgres"
    exit 1
}
Write-Host "  OK: banco de dados pronto" -ForegroundColor Green

# ── 7. Estrutura de pastas e migrations ───────────────────────────────────────
Write-Host "`n[7/7] Criando estrutura de dados e tabelas..."
$dirs = @("data", "data/postgres", "data/sessions", "data/resumes",
          "data/screenshots", "data/reports", "data/logs")
foreach ($dir in $dirs) { New-Item -ItemType Directory -Force $dir | Out-Null }

$env:DATABASE_URL = $db_url
alembic upgrade head
Write-Host "  OK" -ForegroundColor Green

# ── Conclusão ─────────────────────────────────────────────────────────────────
Write-Host "`n===================================" -ForegroundColor Cyan
Write-Host "  Instalação concluída com sucesso!" -ForegroundColor Green
Write-Host "===================================" -ForegroundColor Cyan
Write-Host "`nPara iniciar o app:"
Write-Host "  python run.py" -ForegroundColor Yellow
Write-Host "`nO browser abrirá em http://localhost:8501"
Write-Host "O wizard de setup guiará a configuração inicial.`n"
```

## Execução diária (`run.py`)

Sobe o banco (se não estiver rodando) e inicia os dois processos:

```python
# run.py
import subprocess
import sys
import time

def wait_for_postgres():
    """Aguarda o PostgreSQL aceitar conexões."""
    import sqlalchemy
    from sqlalchemy import text
    engine = sqlalchemy.create_engine("postgresql://jobapplier:jobapplier@localhost:5432/jobapplier")
    for _ in range(10):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            time.sleep(2)
    return False

def main():
    # Garante que o PostgreSQL está rodando
    subprocess.run(["docker", "compose", "up", "postgres", "-d"], check=True)
    print("Aguardando banco de dados...")
    if not wait_for_postgres():
        print("Erro: PostgreSQL não respondeu. Verifique o Docker.")
        sys.exit(1)

    processes = [
        subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py"]),
        subprocess.Popen([sys.executable, "orchestrator.py"]),
    ]
    print("App rodando em http://localhost:8501")
    print("Pressione Ctrl+C para encerrar.")
    try:
        for p in processes:
            p.wait()
    except KeyboardInterrupt:
        print("\nEncerrando...")
        for p in processes:
            p.terminate()

if __name__ == "__main__":
    main()
```

## Fluxo completo do zero

```
# Pré-requisitos instalados: Python 3.12+ e Docker Desktop

git clone https://github.com/usuario/ai-job-applier
cd ai-job-applier

powershell ./install.ps1    ← uma única vez
python run.py               ← toda vez que quiser usar

→ Browser abre em http://localhost:8501
→ Wizard de setup guia a configuração inicial
```

## requirements.txt

```
streamlit>=1.35
sqlalchemy>=2.0
alembic>=1.13
psycopg2-binary>=2.9
playwright>=1.44
apscheduler[sqlalchemy]>=3.10
google-generativeai>=0.8
pydantic>=2.0
pdfplumber>=0.11
python-docx>=1.1
xhtml2pdf>=0.2
structlog>=24.0
click>=8.0
```

---

# BANCO DE DADOS

PostgreSQL desde o início. SQLAlchemy + Alembic para migrations. Roda via Docker Compose.

`DATABASE_URL=postgresql://jobapplier:jobapplier@localhost:5432/jobapplier`

## Tabelas principais

**vagas:** `id, hash, titulo, empresa, plataforma, localizacao, modalidade, senioridade, salario, descricao, link, data_publicacao, normalizado_json, score, score_breakdown_json, status, criado_em`

**candidaturas:** `id, vaga_id, status, perfil_base, curriculo_path, ats_score_original, ats_score_otimizado, keywords_adicionadas, cover_letter_path, screenshots_path, erro, criado_em, atualizado_em`

**empresas:** `id, nome, segmento, tamanho, tecnologias, sobre, noticias, resumo, pesquisado_em`

**aprovacoes_historico:** `id, vaga_id, score, aprovado, criado_em` ← alimenta a aprovação adaptativa

**cache_gemini:** `chave_hash, modelo, resposta, criado_em, expira_em`

---

# ESTRUTURA DE PASTAS

```
/
  app.py                      # entrypoint Streamlit
  orchestrator.py             # APScheduler

  pages/
    1_Setup.py
    2_Dashboard.py
    3_Vagas.py
    4_Candidaturas.py
    5_Relatorios.py
    6_Configuracoes.py

  resume_parser/
    __init__.py, models.py, exceptions.py, pipeline.py
    extractors/  (base, pdf, docx, factory)
    parsers/     (base, gemini)

  agents/
    job_matcher.py, answer_generator.py
    cover_letter.py, resume_optimizer.py

  collectors/
    base.py, linkedin.py, gupy.py
    greenhouse.py, lever.py

  automation/
    base.py, linkedin.py, gupy.py
    greenhouse.py, lever.py

  filters/
    pre_normalization.py
    post_normalization.py

  database/
    models.py, repository.py
    migrations/              # Alembic

  notifications/
    email.py

  templates/
    resume/   (templates HTML por perfil)
    reports/  (template relatório diário)

  tests/
    unit/
    integration/

  docker/
    Dockerfile
    docker-compose.yml        # dois serviços: streamlit + worker

  data/                       # gitignored — criado automaticamente
    config.json
    resume.json
    app.db
    sessions/
    resumes/
    screenshots/
    reports/
    logs/

  install.ps1                 # instalação com um comando
  run.py                      # inicia Streamlit + worker juntos
  requirements.txt
  .gitignore                  # inclui data/
  README.md                   # instruções: git clone → install.ps1 → run.py
```

---

# QUALIDADE DE CÓDIGO

* SOLID, Clean Architecture, Repository Pattern
* Dependency Injection, Type Hints, Pydantic
* Pytest — cobertura mínima 80%
* Playwright: mocks para unit tests, testes de integração headless separados

---

# ENTREGÁVEIS

Cada fase só é considerada concluída quando **todos** os critérios de validação passarem. Não avançar para a próxima fase enquanto houver critério pendente.

---

## Fase 1 — Fundação do App

**O que será construído:**
- `install.ps1` + `run.py`
- PostgreSQL via Docker Compose + SQLAlchemy + Alembic
- `data/config.json` como sistema de configuração
- Módulo 16: Resume Parser (DOCX/PDF → JSON + 4 perfis base)
- Wizard de setup completo (Etapas 1–7)
- Integração Gemini com cache
- Coletores Greenhouse e Lever via API

**Critérios de validação:**

- [ ] `powershell ./install.ps1` roda do início ao fim sem erros em uma máquina limpa
- [ ] `python run.py` sobe os dois processos e o browser abre em `localhost:8501`
- [ ] O wizard de setup aparece na primeira execução (sem `data/config.json`)
- [ ] API key do Gemini é testada no wizard e retorna "Conectado" ou mensagem de erro clara
- [ ] Upload de um DOCX ou PDF real retorna JSON com nome, experiências e tecnologias preenchidos
- [ ] Os 4 perfis base são gerados e salvos em `data/resumes/`
- [ ] Coletor Greenhouse retorna pelo menos 5 vagas reais de uma empresa conhecida
- [ ] Coletor Lever retorna pelo menos 5 vagas reais de uma empresa conhecida
- [ ] As vagas coletadas aparecem na tabela `vagas` do PostgreSQL
- [ ] Executar o coletor duas vezes não duplica vagas (deduplicação funcionando)

---

## Fase 2 — Inteligência

**O que será construído:**
- Filtros 4A (texto bruto) e 4B (pós-normalização)
- Normalização via Gemini (Módulo 2)
- Match IA com pesos por critério (Módulo 3)
- Resume Optimization Engine com auditoria ATS (Módulo 12)
- Agente de pesquisa de empresa (Módulo 17)
- Geração de cover letter e respostas (Módulos 5 e 6)

**Critérios de validação:**

- [ ] Vagas com palavras bloqueadas são descartadas antes de qualquer chamada Gemini
- [ ] Uma vaga sem cargo relevante no título é descartada no filtro 4A
- [ ] O JSON normalizado de uma vaga contém `cargo`, `senioridade`, `tecnologias` e `modalidade` preenchidos
- [ ] O score de uma vaga claramente compatível (ex: Data Engineer com Snowflake) retorna >= 80
- [ ] O score de uma vaga claramente incompatível (ex: Desenvolvedor Java) retorna < 50
- [ ] O `breakdown` do score mostra valores por critério (skills, senioridade, setor, idioma, localização)
- [ ] O currículo otimizado para uma vaga específica tem ATS score maior que o original
- [ ] A auditoria do Módulo 12 rejeita uma versão otimizada que contenha uma empresa inexistente no currículo original
- [ ] A pesquisa de empresa retorna `segmento`, `sobre` e pelo menos uma tecnologia mencionada
- [ ] A cover letter gerada menciona o nome da empresa e ao menos uma tecnologia da vaga
- [ ] Executar normalização na mesma vaga duas vezes usa o cache (zero chamadas Gemini na segunda vez)

---

## Fase 3 — Dashboard e Relatórios

**O que será construído:**
- Páginas 2–6 do Streamlit (Dashboard, Vagas, Candidaturas, Relatórios, Configurações)
- Aprovação adaptativa
- Relatórios PDF/HTML
- Notificações por email
- Orquestrador APScheduler com job store no PostgreSQL

**Critérios de validação:**

- [ ] Dashboard exibe KPIs reais do banco (vagas encontradas, score médio, candidaturas)
- [ ] Vagas com score 70–84 aparecem na fila de aprovação com score, motivos e gaps visíveis
- [ ] Clicar em "Aprovar" muda o status da vaga para `aprovada` e ela sai da fila
- [ ] Clicar em "Rejeitar" muda o status para `rejeitada` e ela sai da fila
- [ ] Página de Candidaturas exibe o histórico com filtro por status funcionando
- [ ] Relatório PDF é gerado com dados reais e pode ser aberto normalmente
- [ ] Email de teste chega na caixa de entrada configurada
- [ ] APScheduler executa o ciclo de coleta no horário configurado sem intervenção manual
- [ ] Reiniciar o `orchestrator.py` não perde os jobs agendados (job store no PostgreSQL)
- [ ] Página de Configurações permite trocar a API key e o efeito é imediato no próximo ciclo

---

## Fase 4 — Automação LinkedIn

**O que será construído:**
- Login e gestão de sessão persistente
- Easy Apply automático com navegação por múltiplos steps
- Controle de risco (delays, limite diário, detecção de captcha)

**Critérios de validação:**

- [ ] Setup do LinkedIn abre o browser, usuário faz login manualmente e a sessão é salva
- [ ] Segunda execução carrega a sessão salva sem abrir tela de login
- [ ] O sistema encontra vagas Easy Apply com os filtros configurados
- [ ] Uma candidatura completa é enviada a uma vaga real de teste (pode ser uma vaga própria ou de teste)
- [ ] Screenshot de cada etapa do formulário é salvo em `data/screenshots/`
- [ ] A candidatura aparece no banco com status `candidatada`
- [ ] Ao atingir o limite diário (10), o sistema para e registra o motivo no log
- [ ] Se captcha for detectado, status muda para `aguardando_captcha` e email de alerta é enviado
- [ ] Executar o coletor do LinkedIn retorna vagas e as salva no banco

---

## Fase 5 — Automação Gupy

**O que será construído:**
- Login e sessão persistente na Gupy
- Candidatura automática com handlers por tipo de formulário
- Fallback para `formulario_desconhecido`

**Critérios de validação:**

- [ ] Setup da Gupy salva a sessão após login manual
- [ ] Uma candidatura completa é enviada a uma vaga real na Gupy
- [ ] Screenshot de cada etapa é salvo
- [ ] A candidatura aparece no banco com status `candidatada`
- [ ] Um campo de formulário desconhecido muda o status para `formulario_desconhecido` e envia alerta — sem travar nem crashar
- [ ] Executar o processo duas vezes na mesma vaga não gera candidatura duplicada

---

## Fase 6 — Greenhouse e Lever

**O que será construído:**
- Candidaturas via API REST oficial
- Fallback para Playwright quando a empresa exige formulário web

**Critérios de validação:**

- [ ] Candidatura via API Greenhouse é enviada a uma vaga real e retorna status 2xx
- [ ] Candidatura via API Lever é enviada a uma vaga real e retorna status 2xx
- [ ] A candidatura aparece no banco com status `candidatada` e `plataforma = greenhouse` ou `lever`
- [ ] Quando a API retorna erro de formulário obrigatório, o fallback Playwright é acionado automaticamente
- [ ] O currículo otimizado em PDF é anexado corretamente via API

---

**Padrão de entrega por fase:** código completo + testes (unit + integração) + `requirements.txt` atualizado + passo a passo de execução dos critérios de validação.
