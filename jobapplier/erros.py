"""Catálogo de erros: um código estável, uma mensagem, uma ação.

Existe porque o sistema falava quatro línguas. As mesmas coisas erradas
apareciam como string solta em `JSONResponse({"erro": "vaga desconhecida"})`,
como texto no aviso da extensão, como `st.error(f"...: {exc}")` em 32 pontos das
páginas e como traceback no terminal. Nenhuma delas era identificável por
programa, então nada podia ser tratado sozinho: toda correção começava por ler
uma frase em português e adivinhar de onde tinha vindo.

O que muda com isto:

- **Código estável** (`vaga-ambigua`) atravessa API, extensão, interface e log.
  Dá para contar quantas vezes cada um acontece, e para decidir por código —
  repetir a chamada, abrir a tela certa, ou parar.
- **`acao` é obrigatória.** Erro que não diz o que fazer transfere o trabalho
  para quem está cansado. Se não houver ação possível, a entrada não deveria
  existir como erro — é estado, e estado tem outro lugar.
- **`auto` aponta a rotina que conserta.** Preenchida, a interface pode oferecer
  o botão; a extensão, o mesmo. É o que permite "ajustar automaticamente".

Mensagem é dado, não código: mudar o texto de um erro não pode exigir mexer em
quem o levanta, e é por isso que o texto mora aqui e não no `raise`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Erro:
    """Uma coisa que pode dar errado, e o que fazer a respeito."""

    #: Estável para sempre. É o que a extensão, o log e a telemetria comparam.
    #: Renomear um código é quebra de contrato — crie outro e aposente o antigo.
    codigo: str
    #: Uma linha, sem ponto final, na voz do candidato — não do sistema.
    titulo: str
    #: O que de fato aconteceu. Pode citar nome de arquivo ou de configuração,
    #: nunca o VALOR de segredo ou de dado pessoal (invariante 12).
    detalhe: str
    #: O que fazer. Imperativo, concreto, executável por quem lê.
    acao: str
    #: Identificador da rotina que resolve sozinha, quando existir uma.
    #: Consumido pela interface e pela extensão para oferecer o botão.
    auto: str | None = None
    #: Família, para agrupar na tela e no relatório.
    familia: str = "geral"

    def como_dict(self, detalhe: str = "") -> dict:
        """Forma de transporte. `detalhe` acrescenta o caso concreto.

        O do catálogo descreve a classe ("a vaga desta página não está no
        acervo"); o do parâmetro traz o caso ("id 14692"). Juntar os dois no
        catálogo obrigaria uma entrada por vaga.
        """
        return {
            "codigo": self.codigo,
            "titulo": self.titulo,
            "detalhe": f"{self.detalhe} {detalhe}".strip() if detalhe else self.detalhe,
            "acao": self.acao,
            "auto": self.auto,
            "familia": self.familia,
        }


def _e(codigo, titulo, detalhe, acao, auto=None, familia="geral") -> Erro:
    return Erro(codigo, titulo, detalhe, acao, auto, familia)


# ── Ambiente: o que precisa estar de pé antes de qualquer coisa ──────────────
# Esta família é a que mais custou tempo sem aparecer em lugar nenhum. Docker
# parado, `run.py` caído e banco fora de head falhavam cada um de um jeito, e
# nenhum se anunciava antes de a pessoa tentar usar.

BANCO_FORA = _e(
    "banco-fora",
    "O banco de dados não está no ar",
    "O PostgreSQL do projeto roda em contêiner e não respondeu.",
    "Rode `docker compose up postgres -d` e tente de novo.",
    auto="subir_banco", familia="ambiente",
)
SCHEMA_ATRASADO = _e(
    "schema-atrasado",
    "O banco está numa versão anterior à do código",
    "Há migrations do Alembic aplicadas a menos. Candidaturas ficam suspensas "
    "até isso ser resolvido: agir com schema incompatível pode falhar no meio, "
    "com a vaga já marcada como em andamento.",
    "Rode `alembic upgrade head`.",
    auto="migrar", familia="ambiente",
)
API_FORA = _e(
    "api-fora",
    "O AI Job Applier não está rodando",
    "A API local em 127.0.0.1:8787 não respondeu. É ela que a extensão consulta "
    "para saber o que preencher.",
    "Rode `python run.py` na pasta do projeto.",
    auto=None, familia="ambiente",
)
EXTENSAO_DESATUALIZADA = _e(
    "extensao-desatualizada",
    "A extensão está numa versão antiga",
    "O service worker não respondeu à página. Costuma acontecer depois que os "
    "arquivos da extensão mudam e ela não é recarregada.",
    "Abra chrome://extensions, clique em recarregar na extensão, e atualize "
    "esta aba.",
    auto=None, familia="ambiente",
)
COLETA_VELHA = _e(
    "coleta-velha",
    "A lista de vagas está desatualizada",
    "A última coleta foi há muito tempo, e vaga encerrada não sai da fila "
    "sozinha — numa amostra do Greenhouse, 22% já não existiam.",
    "Deixe o `python run.py` rodando: ele coleta a cada 2h e varre encerradas "
    "a cada 6h.",
    auto="coletar", familia="ambiente",
)

# ── Dados do candidato: o que falta para o sistema agir em seu nome ──────────

CURRICULO_AUSENTE = _e(
    "curriculo-ausente",
    "Falta o seu currículo",
    "O sistema deriva todo currículo por vaga de `data/resume.json`, e ele não "
    "foi encontrado.",
    "Envie seu PDF ou DOCX em Configurações → Currículo.",
    auto=None, familia="candidato",
)
CONFIG_INCOMPLETA = _e(
    "config-incompleta",
    "Falta preencher a configuração",
    "Dados que os formulários pedem e o sistema ainda não tem.",
    "Complete em Configurações.",
    auto=None, familia="candidato",
)
SEM_PROVEDOR_LLM = _e(
    "sem-provedor-llm",
    "Nenhum provedor de IA configurado",
    "O sistema roda inteiro sem IA: normalização e score são determinísticos, e "
    "a carta usa gabarito. O que falta sem ela é reescrever resumo e bullets "
    "com o vocabulário da vaga.",
    "Se quiser esse ganho, configure em Configurações → Provedor de IA.",
    auto=None, familia="candidato",
)

# ── Vaga: o que a extensão encontra (ou não) na página aberta ────────────────

VAGA_DESCONHECIDA = _e(
    "vaga-desconhecida",
    "Esta vaga não está no acervo",
    "Nenhuma vaga desta empresa no banco casa com o endereço desta página.",
    "Abra a vaga pela tela Revisar e aplicar, ou rode uma coleta para trazê-la.",
    auto="coletar", familia="vaga",
)
VAGA_AMBIGUA = _e(
    "vaga-ambigua",
    "Qual vaga é esta?",
    "Mais de uma vaga desta empresa poderia ser a desta página, e o endereço do "
    "formulário não carrega o identificador. Adivinhar preencheria o formulário "
    "de uma com as respostas de outra — o PagBank tem duas vagas com o mesmo "
    "título.",
    "Escolha no aviso. O vínculo fica gravado e não perguntamos de novo.",
    auto=None, familia="vaga",
)
VAGA_INEXISTENTE = _e(
    "vaga-inexistente",
    "Vaga não encontrada",
    "O identificador informado não existe no banco.",
    "Recarregue a lista de vagas.",
    auto=None, familia="vaga",
)
VAGA_ENCERRADA = _e(
    "vaga-encerrada",
    "Esta vaga saiu do ar",
    "A plataforma não lista mais esta vaga.",
    "Volte à fila e escolha outra — ela já foi retirada.",
    auto=None, familia="vaga",
)
URL_SEM_CANDIDATURA = _e(
    "url-sem-candidatura",
    "Este endereço não é de uma candidatura",
    "A página aberta não tem o identificador de candidatura que o vínculo exige.",
    "Abra o formulário da vaga e tente de novo.",
    auto=None, familia="vaga",
)

# ── Dossiê e envio ───────────────────────────────────────────────────────────

DOSSIE_AUSENTE = _e(
    "dossie-ausente",
    "O currículo desta vaga ainda não foi gerado",
    "O dossiê é montado pela esteira de candidaturas, que roda a cada 15 min.",
    "Aguarde o próximo ciclo, ou prepare a vaga agora pela tela Revisar e "
    "aplicar.",
    auto="preparar_dossie", familia="envio",
)
LIMITE_DIARIO = _e(
    "limite-diario",
    "Limite de envios desta plataforma atingido",
    "A janela é de 24 horas deslizantes, não de dia de calendário: dez envios "
    "às 23h50 e dez às 00h10 são exatamente a rajada que a detecção procura.",
    "Volte amanhã, ou ajuste `risco.limites_diarios` se souber o que está "
    "fazendo.",
    auto=None, familia="envio",
)
DISJUNTOR_ABERTO = _e(
    "disjuntor-aberto",
    "Envios pausados nesta plataforma",
    "As tentativas com erro passaram do triplo do limite. A pausa é para não "
    "insistir contra um formulário que mudou.",
    "Veja o que falhou em Candidaturas antes de liberar.",
    auto=None, familia="envio",
)
JA_CANDIDATADO = _e(
    "ja-candidatado",
    "Você já se candidatou a esta vaga",
    "Existe candidatura registrada para ela.",
    "Nada a fazer — a vaga sai da fila sozinha.",
    auto=None, familia="envio",
)
PERFIL_DE_TERCEIRO = _e(
    "perfil-de-terceiro",
    "Este não é o seu perfil",
    "A análise só lê o perfil cujo endereço está no seu currículo.",
    "Abra o seu próprio perfil do LinkedIn e clique de novo.",
    auto=None, familia="envio",
)
PERFIL_AUSENTE = _e(
    "perfil-ausente",
    "Não veio nada para analisar",
    "A leitura do perfil chegou vazia.",
    "Recarregue a página do perfil e clique em Analisar meu perfil de novo.",
    auto=None, familia="envio",
)

#: Todo erro do sistema. A busca por código é o contrato entre as camadas.
CATALOGO: dict[str, Erro] = {
    e.codigo: e for e in (
        BANCO_FORA, SCHEMA_ATRASADO, API_FORA, EXTENSAO_DESATUALIZADA, COLETA_VELHA,
        CURRICULO_AUSENTE, CONFIG_INCOMPLETA, SEM_PROVEDOR_LLM,
        VAGA_DESCONHECIDA, VAGA_AMBIGUA, VAGA_INEXISTENTE, VAGA_ENCERRADA,
        URL_SEM_CANDIDATURA,
        DOSSIE_AUSENTE, LIMITE_DIARIO, DISJUNTOR_ABERTO, JA_CANDIDATADO,
        PERFIL_DE_TERCEIRO, PERFIL_AUSENTE,
    )
}


def por_codigo(codigo: str) -> Erro | None:
    return CATALOGO.get(codigo)


def resposta(erro: Erro, status: int, detalhe: str = "", **extra):
    """`JSONResponse` no formato único da API.

    Fica aqui e não em `api.py` para que a forma do corpo seja uma decisão só.
    `extra` carrega o que o cliente precisa para agir — as candidatas de uma
    vaga ambígua, por exemplo.
    """
    from starlette.responses import JSONResponse

    return JSONResponse({"erro": erro.como_dict(detalhe), **extra}, status_code=status)
