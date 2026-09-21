# Brief de Design — AI Job Applier

> Prompt para mim mesmo antes de tocar em qualquer tela. Não é revisão (isso é
> `REVISAO_FRONTEND.md`) — é a régua de como construir.

---

Você é designer de produto com dez anos em ferramentas internas densas —
painéis de operação, sistemas de triagem, telas que alguém usa duzentas vezes
por dia. Você já viu o que acontece quando uma ferramenta de trabalho é
desenhada com a estética de uma landing page: fica bonita na captura e cansativa
na décima vaga.

Este produto tem **um usuário**, num monitor, decidindo sobre 216 vagas. Não há
onboarding a otimizar, não há conversão a subir. A tela é boa quando ele decide
rápido e não cansa.

## O contrato

Dez regras, e uma tela que quebra uma delas volta. Existem porque a segunda
rodada de revisão de UX (21/09/2026) achou o mesmo padrão em todas as páginas:
nível 1, 2 e 3 de informação na mesma camada, índigo em tudo, cartão como
contêiner de qualquer coisa, e texto que fala do sistema em vez do resultado.

1. **Uma ação primária por tela.** Índigo é só ela.
2. **A IA explica suas decisões.** Score vem com por quê e ponto de atenção.
3. **Informação técnica fica escondida até ser pedida.** Plataforma, id, data
   de coleta, pesos: nível 3, dentro de Detalhes.
4. **Preparação acontece sozinha.** Nenhuma tela pede que o usuário "gere".
5. **O usuário decide; não configura o processo.** Configuração é rara e fica
   em Configurações.
6. **Índigo = ação.** Botão primário, item selecionado, link acionável, foco.
   Nunca em barra, score, indicador ou decoração.
7. **Verde = pronto ou confirmado.**
8. **Âmbar = merece atenção.**
9. **Vermelho = falhou.**
10. **Toda tela responde "o que eu faço agora?"** Se um elemento não ajuda
    nessa resposta, fica escondido, secundário, ou sai.

### Três níveis de informação

| Nível | O quê | Onde |
|---|---|---|
| 1 — decisão | empresa, cargo, local, aderência (`97% · Excelente`), status, próxima ação | lista e cartão |
| 2 — contexto | por quê, ponto de atenção, tecnologias, eixos, requisitos | ao abrir |
| 3 — técnico | plataforma, id, data de coleta, pesos, logs | só se pedido |

### Três níveis de superfície

| Nível | Aparência | Uso |
|---|---|---|
| Superfície | sem borda | o padrão — texto sobre o fundo |
| Seção | divisor ou fundo sutil | agrupar |
| Cartão | borda + raio | só o que é **protagonista**: a vaga em decisão, o próximo passo |

Quase tudo era cartão. Cartão em tudo é cartão em nada.

### Escala de espaço

`4 · 8 · 12 · 16 · 24 · 32 · 48` px — micro, relacionado, campo, grupo, seção
pequena, seção, separação grande. Sem valores fora da escala.

### Texto fala do resultado, não do sistema

| Evitar | Usar |
|---|---|
| 590 documentos gerados | Seu currículo está pronto. |
| 325 vagas aguardando revisão | 42 vagas precisam da sua decisão. |
| Documentos prontos, não enviados | 14 candidaturas prontas para você enviar. |
| Confirmação inconclusiva | Envio não confirmado |
| Falha técnica | Não conseguimos concluir o envio |

### Estados, e só estes

`✓ Preparado` · `● Revisar` · `● Ativa` · `⚠ Atenção` · `× Falha` · `✓ Enviado`.
Cor pelo significado (7–9), não uma por estado.

## Os dois erros que já cometi aqui

**Fonte pequena.** O padrão do Streamlit é ~14px, e eu piorei com `.72rem`,
`.78rem`, `.85rem` em legenda e chip. Num monitor a 60cm, 14px é pequeno; 11px
é hostil. Reduzir tamanho não é como se cria hierarquia — peso, cor e espaço
fazem isso sem custo de legibilidade.

**Caixa larga com pouco texto.** "Sem perguntas extras. Currículo e envio, só."
esticado por 640px. Um bloco de texto herda a largura do container porque
ninguém o impediu, e aí a linha passa de 90 caracteres. O olho perde o começo da
linha seguinte e a leitura fica cansativa mesmo com fonte grande.

Ambos vêm da mesma omissão: aceitar o padrão do framework em vez de decidir.

## A régua

### Tipografia

| Papel | Tamanho | Peso | Uso |
|---|---|---|---|
| H1 — cumprimento, título de página | 1.75–1.9rem / 28–30px | 700 | uma por tela |
| H2 — cargo em destaque | 1.3rem / 21px | 650 | o que o olho encontra primeiro num cartão |
| H3 — bloco | 1rem / 16px | 600 | cabeçalho de seção |
| Corpo | 0.95rem / 15px | 400 | tudo que se lê |
| Meta | 0.8rem / 13px | 400–500 | local, plataforma, data |
| Número importante | 1.75–2.25rem / 28–36px | 650 | "42", "11 enviadas" |
| Rótulo de seção | 0.78rem / 12.5px | 650, caixa alta | "PRÓXIMO PASSO" |

Hierarquia vem de **tamanho e peso**, não só de cor. Hoje quase tudo tem a
mesma voz e parece texto de tabela.

### Medida de linha

Texto corrido: **máximo 68 caracteres** (`max-width: 62ch`). Vale para
parágrafo, carta de apresentação, descrição de vaga, aviso.

Não vale para tabela, lista de chips e código — esses querem a largura.

Caixa colorida (sucesso, aviso, erro) **abraça o conteúdo**, não estica: uma
frase de seis palavras não ocupa 640px.

### Espaço

Vertical é rolagem, e rolagem tira o cartão de vista. Seja generoso na
horizontal e econômico na vertical.

- Entre blocos: 1.5rem. Dentro de um bloco: 0.5rem.
- Um respiro grande vale mais que cinco pequenos — agrupa.
- Espaço morto no fim da página é sinal de conteúdo mal distribuído, não de
  elegância.

### Cor

Semântica, nunca decorativa:

| Significado | Onde |
|---|---|
| Eliminatória | vermelho de borda, nunca de preenchimento |
| Requer sua ação | âmbar |
| Pronto / confirmado | verde discreto |
| Neutro | cinza com leve viés do fundo |

Cinza puro parece não escolhido. Puxe levemente para o azul do fundo.

Funciona nos dois temas do Streamlit. Cor fixa quebra num dos dois — use
`rgba()` sobre o fundo, ou variável do tema.

### Números

`font-variant-numeric: tabular-nums` sempre que houver coluna de números ou
valor que muda entre estados. Sem isso os dígitos dançam a cada rerun.

## Como decidir uma tela

Antes de escrever CSS, responda:

1. **Qual a ação principal?** Ela está acima da dobra, sem rolagem?
2. **O que o olho encontra primeiro?** É o que mais importa?
3. **O que gasta linha inteira sem informar?** Expander fechado, box vazio,
   divisor decorativo — some com isso.
4. **Quanto do viewport é usado?** Abaixo de 70% numa página de trabalho, o
   `layout` está errado.

## Obrigatório antes de dar por pronto

```powershell
.venv\Scripts\python.exe scripts\ui_screenshots.py
```

Abra cada imagem. Não confie no código nem no HTTP 200 — o Streamlit devolve 200
com traceback dentro da página, e nem lint nem teste enxergam layout.

Olhando a captura, pergunte:

- Consigo ler tudo sem apertar os olhos?
- Alguma linha passa de ~70 caracteres?
- Alguma caixa está muito maior que seu conteúdo?
- Há espaço morto grande no fim?
- A ação principal salta aos olhos?

Se a resposta a qualquer uma incomodar, ainda não está pronto.

## O que não fazer

- Não use `st.expander` para esconder o que a decisão precisa. Expander é para
  o que raramente se olha.
- Não crie escala de fonte nova por página. A régua acima vale para todas.
- Não use emoji como marcador de seção. Use como ícone semântico ou não use.
- Não centralize texto longo.
- Não adicione animação. Isto é ferramenta de trabalho.
