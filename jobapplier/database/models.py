from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from jobapplier.tempo import agora_utc


class Base(DeclarativeBase):
    pass


class Vaga(Base):
    __tablename__ = "vagas"
    __table_args__ = (
        # Unicidade pela identidade da plataforma, parcial porque vagas antigas
        # (e qualquer fonte futura sem id próprio) têm fonte_vaga_id nulo. O
        # `hash` legado continua unique e cobre esses casos.
        Index(
            "uq_vagas_plataforma_fonte_id",
            "plataforma", "fonte_vaga_id",
            unique=True,
            postgresql_where=text("fonte_vaga_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    titulo: Mapped[str] = mapped_column(String(500))
    empresa: Mapped[str] = mapped_column(String(200))
    plataforma: Mapped[str] = mapped_column(String(50))
    localizacao: Mapped[str | None] = mapped_column(Text)
    modalidade: Mapped[str | None] = mapped_column(String(50))
    senioridade: Mapped[str | None] = mapped_column(String(50))
    salario: Mapped[str | None] = mapped_column(String(100))
    descricao: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(1000))
    data_publicacao: Mapped[datetime | None] = mapped_column(DateTime)
    # ── Identidade estável ───────────────────────────────────────────────────
    # O id da vaga na própria plataforma. Sobrevive a republicação, mudança de
    # título e parâmetro extra no link — tudo que quebra o `hash` legado. As três
    # APIs devolvem isso e o projeto vinha descartando.
    fonte_vaga_id: Mapped[str | None] = mapped_column(String(120), index=True)
    fonte_empresa_id: Mapped[str | None] = mapped_column(String(120), index=True)
    #: sha256 da descrição. Não é identidade: detecta que o texto mudou e a
    #: normalização precisa ser refeita.
    content_hash: Mapped[str | None] = mapped_column(String(64))

    # ── Ciclo de vida ────────────────────────────────────────────────────────
    primeira_coleta_em: Mapped[datetime | None] = mapped_column(DateTime)
    ultima_coleta_em: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    encerrada_em: Mapped[datetime | None] = mapped_column(DateTime)

    # ── Lease de processamento ───────────────────────────────────────────────
    # Substitui a suposição de que max_instances=1 basta para saber que um
    # 'em_andamento' é órfão. Com lease, órfão é o que tem lease EXPIRADO, o que
    # continua correto se algum dia houver execução concorrente.
    bloqueado_em: Mapped[datetime | None] = mapped_column(DateTime)
    bloqueado_por: Mapped[str | None] = mapped_column(String(64))
    lease_expira_em: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    #: Tentativas de candidatura. Acima do teto, a vaga para de ser reprocessada
    #: em vez de envenenar o ciclo indefinidamente.
    tentativas: Mapped[int] = mapped_column(Integer, default=0)

    normalizado_json: Mapped[dict | None] = mapped_column(JSON)
    score: Mapped[float | None] = mapped_column(Float)
    score_breakdown_json: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(50), default="nova")
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora_utc)


class Candidatura(Base):
    __tablename__ = "candidaturas"
    __table_args__ = (
        # Idempotência garantida pelo BANCO, não por checagem em código.
        # `guard.ja_candidatado()` continua existindo para evitar trabalho
        # desnecessário, mas para uma ação irreversível como enviar candidatura a
        # garantia tem de estar aqui. `ciclo` deixa recandidatura explícita: para
        # aplicar de novo à mesma vaga, incremente o ciclo deliberadamente.
        UniqueConstraint("vaga_id", "ciclo", name="uq_candidaturas_vaga_ciclo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vaga_id: Mapped[int] = mapped_column(Integer, index=True)
    ciclo: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(50), default="pendente")
    perfil_base: Mapped[str | None] = mapped_column(String(50))
    curriculo_path: Mapped[str | None] = mapped_column(String(500))
    ats_score_original: Mapped[float | None] = mapped_column(Float)
    ats_score_otimizado: Mapped[float | None] = mapped_column(Float)
    keywords_adicionadas: Mapped[list | None] = mapped_column(JSON)
    cover_letter_path: Mapped[str | None] = mapped_column(String(500))
    screenshots_path: Mapped[str | None] = mapped_column(String(500))
    #: Resultado de `applicators.base.avaliar_preenchimento`: quais campos do
    #: formulário a automação conseguiria responder. É o que torna o modo sombra
    #: capaz de medir a taxa de formulários desconhecidos — sem isto ele só
    #: responde "eu teria me candidatado?", nunca "eu conseguiria preencher?".
    avaliacao_preenchimento_json: Mapped[dict | None] = mapped_column(JSON)
    erro: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora_utc)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, default=agora_utc, onupdate=agora_utc
    )


class Empresa(Base):
    __tablename__ = "empresas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    segmento: Mapped[str | None] = mapped_column(String(100))
    tamanho: Mapped[str | None] = mapped_column(String(50))
    tecnologias: Mapped[list | None] = mapped_column(JSON)
    sobre: Mapped[str | None] = mapped_column(Text)
    noticias: Mapped[list | None] = mapped_column(JSON)
    resumo: Mapped[str | None] = mapped_column(Text)
    pesquisado_em: Mapped[datetime | None] = mapped_column(DateTime)


class AprovacoesHistorico(Base):
    __tablename__ = "aprovacoes_historico"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vaga_id: Mapped[int] = mapped_column(Integer, index=True)
    score: Mapped[float] = mapped_column(Float)
    aprovado: Mapped[bool] = mapped_column(Boolean)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora_utc)


class AppMetadata(Base):
    """Identidade explícita da aplicação dona deste banco.

    Terceiro sinal da confirmação, ao lado do nome do banco e da revisão do
    Alembic — e o único que a aplicação escreve deliberadamente. Nome de banco
    pode coincidir e tabela pode ser renomeada; um marcador gravado por nós, não.
    """

    __tablename__ = "app_metadata"

    chave: Mapped[str] = mapped_column(String(64), primary_key=True)
    valor: Mapped[str] = mapped_column(Text)
    atualizado_em: Mapped[datetime | None] = mapped_column(DateTime)


class Execucao(Base):
    """Uma execução de esteira do pipeline: coleta, pipeline ou candidaturas.

    Serve a dois propósitos de propósito. Hoje é observabilidade durável — a
    única forma de responder "o que rodou ontem e o que falhou" depois que o
    terminal fechou. Amanhã, no desenho multi-usuário, é a linha de fila: ganha
    `usuario_id` e um worker consome as pendentes.
    """

    __tablename__ = "execucoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(32), index=True)
    tipo: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(30), default="em_andamento", index=True)
    iniciado_em: Mapped[datetime] = mapped_column(DateTime, default=agora_utc, index=True)
    terminado_em: Mapped[datetime | None] = mapped_column(DateTime)
    metricas_json: Mapped[dict | None] = mapped_column(JSON)
    erro: Mapped[str | None] = mapped_column(Text)


class CacheGemini(Base):
    __tablename__ = "cache_gemini"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chave_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    modelo: Mapped[str] = mapped_column(String(100))
    resposta: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora_utc)
    expira_em: Mapped[datetime] = mapped_column(DateTime, index=True)


class Evento(Base):
    """O que aconteceu com uma candidatura depois de enviada.

    A tabela que faltava para o funil não morrer em `candidatada`. Sem ela, o
    corte de score nunca foi validado contra realidade: tudo o que se ajustou no
    projeto foi medido contra métrica interna — preenchimento, ATS, tamanho da
    fila —, nunca contra "ele foi chamado?".

    Um registro por (vaga, tipo): a empresa manda várias vezes o mesmo aviso, e
    contar duplicata inflaria justamente o número que a tabela existe para tornar
    confiável. Reagendamento de entrevista atualiza a linha, não cria outra.
    """

    __tablename__ = "eventos"
    __table_args__ = (
        UniqueConstraint("vaga_id", "tipo", name="uq_eventos_vaga_tipo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vaga_id: Mapped[int] = mapped_column(Integer, index=True)
    #: `desfecho.Desfecho`: recebida | resposta | entrevista | oferta | recusa.
    tipo: Mapped[str] = mapped_column(String(30), index=True)
    #: Como o sistema soube: 'email' (lido da caixa) ou 'manual' (você marcou).
    fonte: Mapped[str] = mapped_column(String(20), default="email")
    #: Assunto do e-mail que gerou o registro. Sem corpo e sem remetente: é o
    #: mínimo para você reconhecer o evento, e o resto é PII que não precisa
    #: viver no banco (invariante 11).
    referencia: Mapped[str | None] = mapped_column(String(300))
    #: Quando o evento aconteceu, não quando foi lido — a diferença importa para
    #: medir tempo de resposta por plataforma.
    ocorrido_em: Mapped[datetime | None] = mapped_column(DateTime)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora_utc)


class RespostaAprendida(Base):
    """O que você respondeu uma vez e o sistema repete.

    Sem isto, a etapa de perguntas da empresa na Gupy pede nome da mãe em cada
    uma das 230 vagas da fila. A regra de escopo e a de neutralização de empresa
    vivem em `jobapplier/aprendizado.py`, com teste; aqui é só o armazenamento.

    A unicidade é (chave, escopo, empresa) e não só `chave`: a mesma pergunta
    aberta tem uma resposta por empresa, e sem a empresa na constraint a segunda
    empresa sobrescreveria a primeira.
    """

    __tablename__ = "respostas_aprendidas"
    __table_args__ = (
        UniqueConstraint("chave", "escopo", "empresa",
                         name="uq_respostas_chave_escopo_empresa"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    #: Pergunta normalizada — ver `aprendizado.normalizar`. Casamento é exato
    #: sobre esta forma; aproximado responderia uma pergunta com outra.
    chave: Mapped[str] = mapped_column(String(400), index=True)
    #: 'global' (resposta é sobre você) ou 'empresa' (pergunta aberta).
    escopo: Mapped[str] = mapped_column(String(10), default="global")
    #: Vazio quando o escopo é global.
    empresa: Mapped[str] = mapped_column(String(200), default="")
    #: O enunciado como apareceu, para você reconhecer na tela de revisão.
    pergunta: Mapped[str] = mapped_column(Text)
    resposta: Mapped[str] = mapped_column(Text)
    #: `respostas.Classe` — governa o escopo e aparece na revisão.
    classe: Mapped[str] = mapped_column(String(20), default="aberta")
    vezes_usada: Mapped[int] = mapped_column(Integer, default=0)
    usada_em: Mapped[datetime | None] = mapped_column(DateTime)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora_utc)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=agora_utc)


class VinculoCandidatura(Base):
    """Qual vaga é a candidatura que está aberta no navegador.

    A URL do formulário da Gupy é `/candidates/applications/<id>/steps/<id>` e
    não carrega o `jobId` em lugar nenhum — nem no DOM, nem em `__NEXT_DATA__`,
    nem num link. Medido na página real. Sem esta tabela, voltar ao formulário
    por um link de e-mail deixa o sistema sem saber de que vaga se trata, e a
    extensão não tem o que preencher.

    O vínculo é gravado uma vez, no primeiro encontro — quando ainda há
    `referrer` ou memória da aba — e vale para sempre depois.

    Não deduzir por título: o PagBank tem DUAS vagas "Analista de Dados Pl.",
    repostagens com ids diferentes. Deduzir escolheria uma no cara ou coroa e
    preencheria o formulário de uma com as respostas da outra.
    """

    __tablename__ = "vinculos_candidatura"
    __table_args__ = (
        UniqueConstraint("plataforma", "referencia",
                         name="uq_vinculos_plataforma_referencia"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plataforma: Mapped[str] = mapped_column(String(30), index=True)
    #: Id da candidatura no site — `749637585` na Gupy.
    referencia: Mapped[str] = mapped_column(String(100), index=True)
    vaga_id: Mapped[int] = mapped_column(Integer, index=True)
    #: 'referrer' | 'aba' | 'voce' — de onde veio a certeza. Um vínculo que veio
    #: de você é o único que nunca deve ser sobrescrito por inferência.
    origem: Mapped[str] = mapped_column(String(20), default="referrer")
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora_utc)
