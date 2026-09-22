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

Revisão em Configurações → Respostas aprendidas (`ui/_respostas.py`; a página
`ui/pages/6_Respostas.py` só a chama) — memória só é aceitável se for revisável.
Esvaziar uma resposta **apaga** a entrada; gravar `""` faria o banco responder
nada em todo formulário seguinte, em silêncio.

### Currículo manuscrito por vaga

`data/dossies/<vaga_id>/curriculo.json` e `carta.txt` — `jobapplier/manuscrito.py`.
É o terceiro jeito de gerar o dossiê, ao lado do modelo e da reordenação
determinística: alguém lê o anúncio e escreve resumo, bullets e ordem de
tecnologias para **aquela** vaga. O usuário prefere que isso seja feito numa
sessão de assistente (créditos da assinatura), não por chave de API.

Vale nos dois geradores — `dossie.montar` (baralho) e `run_applications`
(envio) — porque a leitura mora em `optimize()` e `cover_letter.generate()`,
não em quem chama. E passa pela **mesma trava da invariante 3**:
`conferir_fatos` compara empresa, cargo, data, formação, certificação, contato
e o conjunto de tecnologias com o base; qualquer divergência levanta e o dossiê
falha fechado. Mão humana inventa tecnologia com a mesma facilidade que um
modelo. Sem a pasta, nada muda.

### Análise do perfil do LinkedIn

`jobapplier/perfil_linkedin.py`, endpoints `GET`/`POST /perfil_linkedin`, seção
em Configurações → LinkedIn (com o campo da URL, que grava no **mestre** —
contato é fato do currículo, invariante 11). O perfil chega pela extensão
(`extensao/linkedin.js`), que só carrega em `linkedin.com/in/*` — nada abre o
LinkedIn, nem com a sessão salva (invariante 6). Lê quando **você clica**, ou
**sozinha ao ver o seu perfil aberto** se a última leitura tiver mais de 7 dias
(`DIAS_PARA_RELER`): antes de ler sem clique ela pergunta à API qual é o seu slug
e compara com a página. Perfil de terceiro nunca é lido sem clique, e com clique
a API recusa (403, sem gravar).

A comparação tem três frentes, nesta ordem: **fato** contra o mestre (cargo,
empresa, data, formação — prioridade 1), **vocabulário** contra a fila (tecnologia
que as vagas `aprovada`/`pronta_envio_manual` pedem, o mestre tem e o perfil não
cita — **um** ajuste só com a lista, não um cartão por tecnologia) e a **régua do
tutorial** (`docs/TUTORIAL_LINKEDIN.md`). Tecnologia pedida pelo mercado e ausente
do mestre vira `lacuna`, nunca sugestão: o sistema não afirma o que o currículo
não sustenta (invariante 3).

Os seletores de `linkedin.js` seguem a estrutura conhecida da página (âncoras
`#about`/`#experience`/`#skills`, `span[aria-hidden]`) e a fixture de teste é
**sintética** — captura real traria dado pessoal para o repositório. O aviso da
extensão diz o que leu ("título ✓ · 2 experiências · 0 competências"); leitura
vazia é o sinal para revisar os seletores. A lista completa de competências só
existe em `/in/<slug>/details/skills/`: visitar essa página antes guarda a lista,
e o envio do perfil a usa.

### A interface mostra a jornada, não o sistema

Navegação: **Início · Vagas · Revisar · N · Candidaturas**, um traço, e
Configurações — sem grupo "Mais": com um item só, o rótulo do grupo é ruído
(`app.py` passa lista, não dict; `_ui` desenha o traço por CSS). Seis páginas de mesmo peso eram o sistema
se apresentando; o produto é *encontrar → decidir → preparar → enviar →
acompanhar*, e a barra segue essa ordem. O contador em "Revisar · 42" é
`fila.precisam_de_voce()`: excelentes (≥ `threshold_auto`) com dossiê pronto.
Não é a fila inteira (275 com dossiê) — esse número na barra é a lista de
afazeres de volta. A página Revisar abre com o **mesmo** conjunto; o filtro
deixa baixar o corte.

**Início responde "o que eu faço agora?"** e só isso: cumprimento, quantas
precisam de você com o botão, a próxima (uma, com Currículo ✓ Carta ✓), um
número de candidaturas, uma linha de automação. Saíram: fontes por plataforma,
barras, contagem de documentos, execução manual, ligar/desligar o envio (foi
para Configurações → Automação). Uma métrica só de candidaturas porque o
sistema ainda não lê respostas por e-mail — "11 enviadas · 11 aguardando" lado
a lado era o pior dos mundos; a frase diz o limite em vez de fingir funil.

**Três níveis de informação** (`jobapplier/aderencia.py`): nível 1 é a
conclusão — `97% · Excelente`, uma frase de por quê, o ponto de atenção mais
grave —; nível 2 é evidência — barras por eixo, tecnologias cobertas, o que
falta —; nível 3 é técnico — plataforma, id, data de coleta. **Na lista de
Vagas só o título do nível 1.** No cartão de Revisar, o nível 1 inteiro. Nível
2 ao abrir; nível 3 dentro de Detalhes. Eixo ausente do breakdown é
desconhecido, não zero: score de versão antiga sem `localizacao` não pode virar
"presencial em cidade não aceita". Rótulo pelo score **arredondado**: 84,8
aparece como 85% e "85% · Boa" contradiria a faixa.

`_ui.titulo_limpo` tira o código de requisição do começo do título
(`12393045 - Engenheiro…`): é identificador do ATS, e era a primeira coisa que
o olho lia. Em Candidaturas, "aguardando alguma ação sua" conta só
`revisao_manual`; `perguntas_pendentes` é legado de agosto e punha 168 no topo.

### Funil pós-candidatura, manual por enquanto

`jobapplier/acompanhamento.py`, `POST /vaga/{id}/desfecho`, seletor por
candidatura enviada em Candidaturas. Você marca o que a empresa respondeu —
confirmação automática, resposta, entrevista, oferta, recusa — e o número que
o projeto nunca teve, *de quantas fui chamado?*, passa a existir. Grava em
`eventos` com `fonte='manual'`, a mesma tabela que a leitura de e-mail
(`desfecho.py`, ainda não implementada) vai alimentar: quando ela chegar, as
duas fontes contam juntas. Um evento por (vaga, tipo); o resumo usa o mais
forte de cada vaga; "sem resposta" apaga os manuais daquela vaga e nunca os
de e-mail. "Aguardando retorno" = enviadas − com resposta − recusas, e só
aparece no Início quando é diferente de "enviadas".

Rótulos de status são o resultado para você, não o estado do sistema:
"Envio não confirmado" em vez de "Confirmação inconclusiva", "Não conseguimos
concluir o envio" em vez de "Falha técnica", "Preparada" em vez de "Pronta
para você enviar". O código (`revisao_manual`, `falha_automacao`) não muda.

### Catálogo de erros e diagnóstico

`jobapplier/erros.py` — todo erro tem **código estável** (`vaga-ambigua`),
título, detalhe e **ação obrigatória**. A API responde sempre
`{"erro": {"codigo", "titulo", "detalhe", "acao", "auto", "familia"}}`, e
`tests/unit/test_erros.py` falha se `api.py` voltar a escrever `{"erro": "texto"}`.
A extensão e o painel renderizam do mesmo objeto; os únicos textos de erro que
nascem em JavaScript são os dois que o backend não pode informar — service
worker mudo e API fora do ar —, e o teste garante que só eles.

Por que: as mesmas falhas apareciam como string solta na API, texto no aviso da
extensão, `st.error` em 32 pontos das páginas e traceback no terminal. Nenhuma
era identificável por programa, então nada podia ser tratado sozinho.

`jobapplier/diagnostico.py` — `/saude` devolve o estado inteiro: banco, schema
em head, currículo, config, provedor de IA, idade da coleta. Cada falha carrega
um erro do catálogo. **Devolve 200 mesmo com bloqueio**: a resposta é o
diagnóstico, e um 503 faria a extensão tratar como "API fora" justamente quando
ela tem o que dizer. Toda checagem é barata e sem efeito — roda a cada abertura
de página. Aviso não derruba o estado; só bloqueio.

### Fila do dia e painel da extensão

`jobapplier/fila.py` — a regra da fila vivia dentro de `ui/pages/5_Aplicar.py`
e o painel precisava da mesma; agora é serviço, e webapp e painel renderizam.
`do_dia()` devolve **cinco** vagas, só as que já têm currículo pronto: 412
cartões não são escolha, e oferecer vaga sem dossiê é oferecer trabalho.
`decidir()` só aceita o mapa `DECISOES` — POST com status arbitrário poderia
gravar `enviada_confirmada` sem prova e `guard.ja_candidatado` bloquearia a vaga
para sempre.

`painel/` — React + Vite + TypeScript. `npm run build` gera `extensao/painel/`,
que o `manifest.json` carrega como **side panel** do Chrome (`sidePanel`, abre
no clique do ícone). O painel é página da extensão, não da vaga: as
`host_permissions` dispensam CORS e ele fala com `127.0.0.1:8787` direto — ao
contrário de `conteudo.js`, que precisa do service worker por causa do CSP do
site. Tokens de cor copiados de `ui/_ui.py`: é o mesmo produto.

Rotas que o painel consome: `/saude`, `/fila` (`tudo=1` para o acervo),
`/vaga/{id}/dossie`, `/vaga/{id}/curriculo`, `/vaga/{id}/decisao`.

**A inbox é a tela padrão do painel** (`painel/src/Inbox.tsx`): uma vaga por
vez, `← 3 / 42 →`, nível 1 da aderência no cartão, checklist do dossiê, a
evidência atrás de "por que combina" (uma chamada por vaga, só quando aberta).
Ações: **Abrir candidatura** (primária — abre o link numa aba E grava
`aberta`; a vaga NÃO sai da fila, porque abrir o link não é enviar), e
"Já me candidatei" / "Depois" / "Não é para mim". Atalhos: ← → navegam, Enter
abre, A candidatei, S depois, E não é para mim — ignorados quando o foco está
num campo de texto. `/fila` sem parâmetro devolve `precisam_de_voce()`, o mesmo
conjunto do contador "Revisar · N" do webapp: as duas telas contam a mesma
coisa. `titulo_exibicao` (em `fila.py`, não na UI) tira o código de requisição
do título nos dois lugares.

`tests/e2e/test_painel.py` carrega o painel como página da extensão contra a
API real e prova contador, navegação por teclado e evidência sob demanda. Não
decide nada: decisão grava no banco real, sobre vaga sua.

Lição do primeiro build: a API em execução era anterior às rotas novas e
respondeu 404 sem corpo do catálogo; o cliente chamou isso de "API fora" ao lado
de um ponto verde que acabara de falar com ela. Resposta sem `erro.codigo` agora
é `contrato-desconhecido` — versão diferente —, não "não está rodando".

`ui/_documentos.py` + `jobapplier/documentos.py` — todo currículo e
carta em disco (593 e 566), com busca. **Tabela, não cartões**: a primeira
versão punha três documentos por tela. A fonte é o disco, porque só 351 dos 593
têm linha em `candidaturas` — o dossiê é gerado para o baralho sem candidatura.
Medido na tela: no `st.dataframe`, clicar no texto seleciona a *célula*; quem
seleciona a linha é a caixa da primeira coluna, e a legenda diz isso.
É acervo, não decisão: saiu da barra lateral ("Mais" tem só Configurações) e
vive como seção de Configurações, junto com Respostas aprendidas. O corpo das
duas mora em `ui/_documentos.py` / `ui/_respostas.py` com `render(com_cabecalho)`;
as páginas em `pages/` são de três linhas e continuam roteáveis por URL —
`st.navigation` não tem página escondida, então `_ui` oculta o item por CSS.

### Preencher tudo: a extensão mostra antes, escreve no clique

`extensao/conteudo.js` tem duas etapas. `preparar()` lê o formulário, pergunta
à API e mostra no aviso o que vai acontecer — "12 perguntas neste passo · 10 o
sistema sabe responder · 2 ficam para você" — com o botão **Preencher tudo**.
`aplicar()` escreve, e só roda no clique. A versão anterior preenchia sozinha
1,2 s depois do load: quem estava lendo o anúncio via o formulário mudar sem
ter pedido, sem saber o que foi escrito nem por quê.

A assinatura do formulário (rótulos + tipos) evita perguntar de novo a cada
re-render do React; passo novo do SPA muda a assinatura e reconsulta. O que
você digita nas que ficaram vai para o banco de respostas, como antes.

`tests/unit/test_extensao.py` roda `node --check` nos quatro scripts: erro de
sintaxe em content script não aparece em lugar nenhum — nem no console da
página, nem no aviso — e custou uma rodada inteira de depuração.

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

**`coleta.localizacoes_alvo` são as cidades onde você aceita presencial ou
híbrido**, e é lida por `agents/extracao.locais_alvo()`. Até 21/09/2026 era
chave morta: a tela de Configurações gravava e ninguém lia.

Quem decidia era `_pontuar_localizacao`, procurando a cidade do candidato em
qualquer posição da localização da vaga — e como ele mora em "São Paulo", que é
também o nome do **estado**, toda vaga presencial do interior casava. Franca
(400 km) pontuava 10 de 10, igual à capital. Parecia preferência configurada e
era coincidência de substring; um dia alguém "corrigiria" o casamento e as vagas
do interior sumiriam da fila sem ninguém entender por quê.

Agora a comparação é pela **cidade** — primeiro campo de `Cidade, Estado, País`
— contra a lista declarada mais a cidade do currículo. Presencial em cidade não
declarada zera; híbrido leva 40%. Remoto ignora a lista. `Remoto`, `Remote` e
`Brasil` continuam na lista por causa da UI, e `locais_alvo()` os descarta:
modalidade é tratada antes e não é cidade.

**Texto livre usa a string inteira**, não o primeiro campo: `Brazil (São Paulo -
Hybrid)` e `Sao Paulo` não têm campo de estado para confundir, e são 100 das 410
vagas da fila. Exigir o formato de três campos as esconderia todas.

**A lista tem de incluir a região metropolitana**, não só o interior. A primeira
versão dela respondia "é interior?" em vez de "ele consegue ir?", e 18 vagas da
fila iriam a zero — Barueri/Alphaville, Guarulhos, São Bernardo, Taboão,
Santana de Parnaíba —, todas mais perto da casa dele que Campinas. Uma delas
estava no lote já preparado para envio.

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
  DESIGN_QA.md             auditoria de UI medida com Playwright, e o antes/depois
  DESIGN_AUDIT.md          auditoria profunda (colisão, clipping, teclado, tokens) + rodada 1
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

# ── Painel da extensão (React) ───────────────────────────────────────────────
cd painel; npm install; npm run build          # gera extensao/painel/
                                                # depois: recarregar em chrome://extensions

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
  erros.py             catálogo: código estável, mensagem e ação, para toda tela
  diagnostico.py       /saude — banco, schema, currículo, config, coleta
  fila.py              a fila do dia e a decisão sobre uma vaga (webapp e painel)
  aderencia.py         o score em três níveis: conclusão, evidência, técnico
  documentos.py        todo currículo e carta em disco, ligados à vaga pelo nome
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
painel/                React + Vite: painel lateral do Chrome; build em extensao/painel/
extensao/              content scripts, service worker e o painel construído
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

**Auditoria medida, não só olhada**: `scripts/auditoria_ui.py` percorre as seis
páginas em seis viewports (1440/1600/1920, 1024, 390/360) e grava em
`data/screenshots/qa/medidas.json` tipografia, ritmo vertical, botões, inputs,
cartões, truncamentos, contraste, alvos < 24px, raios, azuis e a ordem de foco.
Rode antes e depois de mexer na interface e compare. O relatório da primeira
rodada está em `docs/DESIGN_QA.md`, com o antes/depois do que foi corrigido.
Duas lições que só a medição pegou: o `stMarkdownContainer` do Streamlit tem
`margin-bottom: -1rem` (supõe um `<p>` no fim) e, num contêiner com gap
reduzido, o bloco seguinte invade o HTML anterior — a correção é local, nunca
global (a global abriu 16px em toda página); e a barra lateral fixa de 300px
deixa 724px a 1024 — abaixo de 1280px o workspace de Revisar empilha por CSS
(`.st-key-workspace`) e os filtros de Vagas quebram em duas linhas.

A régua de tipografia, medida de linha e espaço está em `docs/DESIGN_UI.md`, e é
aplicada por `ui/_estilo.py` — não invente escala nova por página.

O contrato de interface (dez regras, três níveis de informação, três níveis de
superfície, escala de espaço `--e1..--e7`) está na seção "O contrato" do mesmo
arquivo. As decisões que ele fixa e que já custaram retrabalho:

- **Cartão só para o protagonista.** Início tem um cartão: o próximo passo.
  Revisar tem um: a vaga em decisão. Lista de vagas tem borda por item, mas o
  "Detalhes" de cada um é link, não segunda caixa dentro da caixa.
- **Índigo só para ação.** Barras de aderência, métricas e progresso são cinza;
  o único índigo da tela é o botão que faz alguma coisa.
- **Status não vai na lista de vagas.** Em "aguardando você" é sempre o mesmo, e
  nos outros filtros você acabou de escolhê-lo. Fica só "● Preparada" quando há
  dossiê, porque isso muda o que fazer com a vaga.
- **Filtro é dropdown, não slider.** "80%+" se lê e se lembra; slider de 5 em 5
  pede ajuste fino que ninguém quer fazer em lista.
- **Lista curta é chip** (`st.multiselect(accept_new_options=True)`), não
  textarea "um por linha": cargos, cidades, palavras bloqueadas. Slugs do
  Greenhouse (150) seguem em textarea, atrás de um expander.
- **Configurações navega por lista vertical** (`st.radio` estilizado via
  `.st-key-nav-config`), não por segmented control: nove rótulos numa linha não
  cabem. Cada etapa do assistente já se intitula; só Documentos e Respostas
  ganham título da navegação.
- **Localização na tela é a cidade** (`fila.local_exibicao`, que `_ui.local_curto`
  delega e o painel recebe pronto): "São Paulo, São Paulo, Brasil" vira "São
  Paulo". Texto livre fica como está.
- **"Abrir candidatura", não "Abrir e candidatar".** O botão abre o site e
  registra `aberta`; quem envia é você. O nome não promete o que o sistema não
  faz — vale no webapp e no painel.
- **Evidência é palavra + número, não barra.** "Tecnologias · Forte · 89%",
  tecnologias cobertas em chips e "⚠ Não cita: PySpark". Cinco barras quase
  cheias lado a lado pareciam painel de métricas e não ajudavam a decidir
  (`_ui.evidencia`, `painel/src/Inbox.tsx`, mesma régua de palavras).
- **Lista de vagas tem uma linha de inteligência por cartão** — o `porque` do
  nível 1 —, e só ela: o ponto de atenção em cem cartões vira ruído e fica em
  Detalhes e em Revisar. Cartão com padding 12/16 e "Detalhes" colado.
- **Lista longa em Configurações é resumo + "Editar (N)"**: "São Paulo, Remoto,
  Barueri e mais 98", e os chips só dentro do editor. Cem chips na tela era um
  gerenciador de etiquetas.
- **"Aguardando retorno" não existe.** O sistema sabe que enviou e que ninguém
  marcou resposta; a frase é "Nenhuma resposta identificada ainda". Cada
  candidatura enviada mostra a data (`max(candidaturas.criado_em)` por vaga —
  não `vagas.atualizado_em`, que a varredura de encerradas também toca).
- **As etapas do assistente checam `_no_assistente()`** e não desenham
  Voltar/Avançar/Pular no modo ajuste: "Avançar" índigo ao lado de "Salvar" era
  uma segunda primária, e a legenda que pedia para ignorá-los era a interface
  se desculpando.
- **Motivo em frase não é tecnologia** (`aderencia._e_frase`): o scorer antigo
  escrevia "Forte alinhamento tecnológico com…" em `motivos_positivos`, e isso
  virava chip de 869px e "Forte aderência em Forte alinhamento…". Frase vira o
  `porque`, resumida.
- **Breakpoints vêm do conteúdo, não de número redondo.** O workspace de
  Revisar empilha abaixo de 1160px (330 + 520 + gap = 880 de conteúdo, mais
  300 de barra e 160 de padding); a linha de 5 filtros de Vagas quebra em duas
  no mesmo corte — e **só entre 768 e 1159**: abaixo de 768 o Streamlit já
  empilha, e forçar 30% truncava os filtros no celular (regressão medida).
- **Tokens que o Streamlit também obedece**: `theme.borderColor = #D0D5DD` e
  `theme.baseRadius = 8px` no `config.toml` — sem isso container, input,
  select e expander nativos trazem um terceiro e um quarto cinza de borda e
  um raio de 10px que ninguém escolheu. `--txt` é 14px (corpo do contrato);
  a barra lateral tem 15,2px por regra própria porque o rótulo do item de
  navegação é um `<p>` de markdown e cairia junto.
- **`initial_sidebar_state="auto"`**: com `"expanded"`, toda carga nova no
  celular abria a barra (300px) por cima da página.
- **Chips de multiselect são valor, não ação**: cinza. Havia duas regras para
  `[data-baseweb=tag]` em `_ui.py` e a mais antiga (índigo) vencia a nova —
  "meio corrigido" na auditoria. Ao mexer em chip, procure as duas.
- **`docs/DESIGN_AUDIT.md`** tem a auditoria profunda (colisões, clipping,
  teclado, hover, tokens derivados) e o "Implementation Round 1" com o
  antes/depois; `data/screenshots/design-audit_antes/` é a linha de base.
- **`kind="primaryFormSubmit"`** é o botão de formulário: a regra de botão
  primário precisa listá-lo, senão "Salvar preferências" sai com texto cinza
  sobre índigo. Medido na captura.

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
