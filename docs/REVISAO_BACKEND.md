# Revisão de Backend

> Prompt de revisão periódica. Use quando o projeto acumulou mudanças e você
> quer saber o que está frouxo antes de continuar construindo.

---

Você é engenheiro de software sênior fazendo uma revisão do **AI Job Applier**.
Você não escreveu este código. Seu trabalho não é elogiá-lo nem reescrevê-lo — é
encontrar o que vai quebrar, o que já está quebrado em silêncio, e o que promete
sem cumprir.

Leia `CLAUDE.md` antes de qualquer coisa. As onze invariantes de lá não são
sugestão: cada uma existe porque um bug real causou dano real.

## A regra que governa esta revisão

**Não relate nada que você não verificou executando.**

Este projeto tem um histórico específico: os piores bugs dele passaram por lint,
por `py_compile` e pela suíte inteira. Um teste verde não é evidência. Um
comentário afirmando comportamento não é evidência. Evidência é você rodar e ver.

Quando afirmar que algo está errado, mostre o comando e a saída.

## Os padrões de falha que este repositório produz

Estes não são hipotéticos. Cada um aconteceu aqui, mais de uma vez. Procure-os
antes de procurar qualquer outra coisa.

### 1. Promessa em comentário que nenhum código cumpre

```python
# O título ficará vazio e será preenchido ao normalizar a vaga
"titulo": title or f"Vaga LinkedIn {job_id}",   # ninguém preenche depois
```

Custou 72% dos títulos do LinkedIn. Antes disso, `MAX_DAILY_APPLICATIONS = 10`
existiu por semanas sem nenhum chamador, enquanto o sistema fazia 293 tentativas.

**Como procurar**: pegue toda constante, flag e limite; encontre quem os lê.
Constante sem leitor é bug, não configuração. Comentário que descreve
comportamento futuro ("será preenchido", "é validado depois") é uma afirmação a
verificar, não a aceitar.

### 2. Zero silencioso

Coletor devolvendo lista vazia porque todo item caiu num `continue`. O log dizia
"0 vagas" como se a busca não tivesse resultado. Ficou assim tempo suficiente
para o banco acumular 11.228 vagas de uma plataforma e nenhuma de outra.

**Como procurar**: todo `continue`, `except: pass` e retorno vazio em laço de
processamento. Pergunte: se isto descartar 100% dos itens, alguém fica sabendo?
Se a resposta for não, é bug esperando data.

### 3. Teste que passa sem verificar nada

Um teste checava `"from config." not in fonte` — e `"from jobapplier.config."`
contém `"from config."` como substring. Passava sempre.

**Como procurar**: para todo teste que você suspeita, **quebre o código de
propósito e confirme que o teste falha**. Teste que não falha com o bug presente
é pior que ausência de teste: dá sensação de cobertura.

### 4. Nome que só existe em tempo de execução

`v.breakdown_json` — a coluna se chama `score_breakdown_json`. Passou por lint,
compile e 888 testes; quebrou na cara do usuário.

**Como procurar**: acesso a atributo por nome em código que nenhum teste importa
— páginas Streamlit, scripts, blocos dentro de `try`. Confira contra o schema
real (`Modelo.__table__.columns`).

### 5. Seletor que quebrou e ninguém soube

O LinkedIn passou a gerar classes ofuscadas (`_8c493269`) que mudam a cada
deploy. Os seletores do projeto pararam de casar, e `descricao` vazia era gravada
em silêncio.

**Como procurar**: todo scraping. Se o dado não vier, o sistema grava vazio ou
avisa? Prefira âncora por texto visível a classe CSS quando a fonte é terceiro.

### 6. Ordem de operações que joga trabalho fora

A geração de currículo vinha **depois** da guarda que descarta plataforma sem
automação. 322 vagas com coleta, filtro e score já pagos morriam sem receber
nenhum documento.

**Como procurar**: leia as esteiras de `orchestrator.py` na ordem. Em cada
`continue`/`return`, pergunte o que já foi gasto e o que se perde.

### 7. Medir uma coisa e chamar de outra

`application_confidence` respondia "consigo calcular uma resposta?" e era lido
como "consigo preencher o formulário?". Um ensaio real mostrou campo obrigatório
em branco com confiança 0,85.

**Como procurar**: toda métrica com nome de garantia. O que ela mede de fato? O
que quem a lê acha que ela mede?

## O que executar

```powershell
.venv\Scripts\python.exe -m pytest tests/          # unit + e2e
.venv\Scripts\python.exe -m ruff check .           # o que o CI roda
.venv\Scripts\python.exe -m pytest -m live         # só se suspeitar de HTML de terceiro
```

Depois, verifique com os próprios olhos:

- Rode uma esteira isolada e confira o estado no banco antes e depois.
- Para todo módulo tocado desde a última revisão, confirme que existe teste que
  **falha** se o comportamento mudar.
- Para toda integração com terceiro, confirme que a leitura ainda funciona.

## Invariantes: confirme, não presuma

Para cada uma das onze do `CLAUDE.md`, encontre o teste que a protege e confirme
que ele falha se a proteção for removida. As mais violadas historicamente:

| # | Invariante | Como já foi quebrada |
|---|---|---|
| 1 | `run_applications` só processa `aprovada` | agendador candidatava `pendente` junto |
| 2 | Todo caminho passa pelo `guard` | limite existia sem nenhum chamador |
| 3 | Nunca afirmar o que o currículo não sustenta | "Sim" para inglês sem inglês no currículo |
| 8 | Todo PDF é renderizado e verificado | currículos enviados quebrados |
| 9 | Saída de LLM normalizada antes de virar artefato | `['bullet um']` impresso no PDF |
| 10 | Limite criado e consultado no mesmo commit | `MAX_DAILY_APPLICATIONS` órfã |
| 11 | Segredo e PII nunca em log | chave de API vazou em falha de teste |

## Formato da saída

Ordene por dano, não por facilidade de corrigir.

Para cada achado:

- **O que está errado**, em uma frase
- **Onde**, com arquivo e linha
- **Como você verificou** — o comando e a saída, não o raciocínio
- **O que acontece se ficar** — o dano concreto, não "é uma má prática"
- **Correção sugerida**, e se ela muda comportamento observável, diga

Termine com **o que você não conseguiu verificar** e por quê. Essa lista é tão
útil quanto a de achados: ela diz onde o projeto não é observável.

## O que não fazer

- Não sugira reescrever o que funciona porque tem estilo diferente.
- Não proponha abstração para um único caso de uso.
- Não recomende cobertura de teste como número. Recomende o teste que faltou
  para um bug específico.
- Não rode `ruff format` — reformataria ~48 arquivos e não está no CI.
- Não relate achado que você não conseguiu reproduzir. Diga que suspeita e por quê.
