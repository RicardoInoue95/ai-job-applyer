# AIApply e a categoria — o que eles fazem melhor, e onde discordamos

Pesquisa feita em 24/08/2026. Fontes ao final.

**Aviso sobre as fontes.** Boa parte do que se publica sobre "melhor ferramenta de
auto-apply" é blog de concorrente comparando a si mesmo. Separei o que é
marketing do que é relato primário, e sinalizo qual é qual — os números que
importam aqui vêm de relato de uso, não de página de produto.

---

## 1. O que o AIApply é

Plataforma comercial de candidatura assistida por IA. Começou como extensão de
navegador e virou produto web depois de uma demo viral.

O que oferece:

- **Auto-Apply** — encontra vagas e submete em seu nome
- **Currículo por vaga** reescrito contra a descrição, com verificador de ATS
- **Carta de apresentação** gerada por vaga
- **Importação do LinkedIn** — perfil vira currículo em um passo
- **Interview Buddy** — sugere respostas em tempo real durante entrevista ao vivo
- **Simulado de entrevista** e tradução de currículo para 50+ idiomas

Preço: **US$ 50/mês por 100 candidaturas**, mais add-ons. LazyApply, do mesmo
segmento, cobra de US$ 99 a US$ 999 por ano.

A submissão automática funciona **no LinkedIn e num conjunto estreito de ATSes**.
Fora disso é autofill: preenche e você envia.

---

## 2. Onde eles são melhores, sem rodeio

**A extensão de navegador.** É a peça que nos falta e a que resolve o problema
mais duro. Ela roda dentro da sessão que você já autenticou, então:

- não precisa da senha da Gupy nem enfrentar o Turnstile do login
- não precisa de `storage_state` do LinkedIn nem gastar cota de detecção
- o CAPTCHA aparece na sua tela, e você resolve como resolveria de qualquer jeito

Nós construímos a **sessão assistida** (`scripts/finalizar.py`) que chega perto:
navegador visível, formulário preenchido, você conclui. Mas ela abre um Chrome
novo, sem suas sessões, e por isso só serve para board público. Uma extensão
serviria para tudo.

**Preparação de entrevista.** Não temos nada. O funil do projeto termina no
envio, e depois do envio o candidato está sozinho.

**Volume, quando volume é o que se quer.** Eles submetem 100/mês por US$ 50. Nós
enviamos uma candidatura confirmada até hoje.

---

## 3. O que os números dizem sobre o modelo deles

O relato primário mais completo que achei — alguém que deixou uma IA candidatar
por meses:

```
819 candidaturas
 71 respostas          8,6%
  5 entrevistas        0,6%
                       ~1 entrevista a cada 200 candidaturas
```

Duas dessas cinco foram recusadas pelo próprio candidato por não querer a
empresa. Sobraram **duas oportunidades viáveis de 819 candidaturas**.

O autor foi honesto sobre o que ganhou: não foi taxa de conversão, foi **banda
mental** — não sentir cada rejeição pessoalmente, e liberar tempo para
relacionamento e exploração. Isso é um ganho real, e não é o que o marketing
vende.

Para comparar: **75% de todas as candidaturas não recebem resposta nenhuma, e em
tecnologia esse número chega a 95%.** Então 8,6% de resposta não é ruim — mas
0,6% de entrevista quer dizer que a resposta era quase sempre recusa automática.

### O que os usuários reclamam

De fóruns (Reddit, Blind) e avaliações, não de blog de produto:

- **conta do LinkedIn banida**
- **experiência alucinada no currículo** — a IA inventou o que o candidato não tem
- **blacklist de recrutador** — "o mesmo perfil aparece em dezenas de vagas da
  mesma empresa"
- **carta genérica** e falha em responder pergunta aberta de triagem
- **"o painel disse que aplicou e nada aconteceu"** — a reclamação mais comum

---

## 4. Onde discordamos, e por quê

Três coisas que essa categoria trata como recurso e este projeto recusa. Não é
postura: cada uma tem um custo documentado acima.

### Simular comportamento humano para não ser detectado

O texto de uma delas descreve como qualidade: *"boas ferramentas adicionam
atrasos entre ações, rolam a página naturalmente, e não aplicam em velocidade
sobre-humana"*.

Isso é evasão de detecção com outro nome. Recusamos três vezes nesta base — o
Turnstile da Gupy, o `navigator.webdriver`, o hCaptcha do Lever — e há teste
falhando se aparecer. O custo de fazer é **a conta banida**, que aparece na lista
de reclamações acima.

### Volume sem avaliação

Elas aplicam a tudo que casa vagamente com uma palavra-chave. Nós medimos o que
isso produz no seu próprio acervo, e o número é pior que o do relato de 819:

```
293 tentativas  ->  10 envios
```

E hoje, ao varrer a fila, achamos por que o volume engana: **21% das vagas já
estavam encerradas**, e as mortas eram justamente as de maior score — vaga boa
fecha rápido. A fila parecia grande e era em parte cemitério.

### Inventar o que o currículo não sustenta

"Hallucinated experience on resumes" é reclamação recorrente. É exatamente a
invariante 3 daqui, e é o que separa "ênfase" de "mentira": ênfase se sustenta
numa entrevista técnica, invenção não.

Nossa linha de **equivalência** é a resposta a isso — `equivalente: AWS, GCP` ao
lado de Azure é verdadeiro e preciso; escrever `AWS` na lista seria invenção. E
metade da fila cai nesse caso.

---

## 5. O que eu levaria deles

Em ordem de valor:

1. **Extensão de navegador.** Resolve Gupy, LinkedIn e CAPTCHA de uma vez, sem
   contornar nada — porque é você navegando. É a maior lacuna nossa.
2. **Preparação de entrevista.** O funil daqui morre no envio. Se o gargalo real
   é converter entrevista em oferta, nada aqui ajuda.
3. **Interface de autofill genérico.** Nosso `ficha.py` prepara respostas, mas
   você ainda copia e cola.

## O que eu não levaria

Auto-apply desatendido, simulação de comportamento humano, e geração de currículo
sem revisão.

---

## 6. A diferença que resume tudo

Eles otimizam **candidaturas enviadas por hora**. Este projeto otimiza **que a
candidatura certa exista e seja boa**.

Os dois são defensáveis, e o deles tem mérito psicológico que o autor das 819
descreveu bem. Mas com 1 entrevista a cada 200 envios, "mais envios" é uma
alavanca fraca — e cara, em risco de conta e de reputação com a empresa.

O dado que ainda falta para saber quem está certo **no seu caso** é o mesmo que
falta desde sempre: quantas das suas candidaturas viram resposta. A tabela
`eventos` existe agora para medir isso.

---

## Fontes

- [AIApply — página do produto](https://aiapply.co/)
- [I Let AI Apply to 819 Jobs for Me](https://jobsearchwithai.substack.com/p/i-let-ai-apply-to-819-jobs-for-me) — relato primário, a melhor fonte deste documento
- [Auto-Apply AI Tools Are Making Your Job Search Worse](https://www.tryzipply.com/blog/auto-apply-tools-are-hurting-your-job-search) — blog de concorrente; usei só os dados de fórum que ele agrega
- [We Tested 7 Auto-Apply Extensions](https://www.autoapplymax.com/blog/auto-apply-jobs-chrome-extension) — blog de concorrente; usei só a descrição técnica
- [Blind: anyone used applyall.com / lazy apply](https://www.teamblind.com/post/anyone-used-applyallcomlazy-applyother-autoappy-tools-17qnogy3)
- [AIApply no ToolDirectory](https://tooldirectory.ai/tools/aiapply)
