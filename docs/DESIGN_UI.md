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
| Título de vaga | 1.5rem / 24px | 650 | o que o olho encontra primeiro |
| Seção | 1.05rem / 17px | 600 | cabeçalho de bloco |
| Corpo | **1rem / 16px** | 400 | tudo que se lê |
| Apoio | 0.9rem / 14.5px | 400 | legenda, metadado |
| Chip | 0.8rem / 13px | 600 | rótulo curto, nunca frase |

**Piso: 0.8rem, e só para palavra solta.** Frase nenhuma abaixo de 0.9rem.

Hierarquia se faz com **peso e cor**, não encolhendo. Entre 16px cinza e 13px
preto, escolha o primeiro.

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
