"""A política de resposta decide o que é escrito num formulário real, em nome do
usuário, para um empregador real. É a camada de maior consequência do projeto.

Dois erros custam coisas diferentes, e os testes refletem isso:

- responder de menos custa a vaga (campo em branco vale "não" numa triagem);
- responder além do sustentável custa o contato com a empresa, porque a entrevista
  comprada é perdida nos primeiros minutos.
"""
import pytest

from jobapplier.agents import respostas as r


def _contexto(titulo="", senioridade="", centrais=()):
    return r.Contexto(titulo=titulo, senioridade=senioridade,
                      termos_centrais=set(centrais))


# ── Classificação ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pergunta,esperada", [
    ("What is your gender identity?", r.Classe.SENSIVEL),
    ("Você se identifica como parte da comunidade LGBTQI+?", r.Classe.SENSIVEL),
    ("Você tem alguma deficiência?", r.Classe.SENSIVEL),
    ("Point of Data Transfer — Acknowledge/Confirm", r.Classe.CONSENTIMENTO),
    ("Concordo com o tratamento de dados conforme a LGPD", r.Classe.CONSENTIMENTO),
    ("What is your current employer?", r.Classe.FATO),
    ("Qual sua formação acadêmica?", r.Classe.FATO),
    ("Do you require visa sponsorship?", r.Classe.FATO),
    ("How many years of experience do you have with Python?", r.Classe.TEMPO),
    ("What is your salary expectation?", r.Classe.PREFERENCIA),
    ("Are you able to work from São Paulo in a hybrid model?", r.Classe.PREFERENCIA),
    ("Do you have experience with Airflow?", r.Classe.FERRAMENTA),
    ("Do you have experience with payments?", r.Classe.DOMINIO),
])
def test_classificacao(pergunta, esperada):
    assert r.classificar(pergunta) is esperada


def test_consentimento_sobre_dado_sensivel_cai_em_sensivel():
    """A ordem dos padrões importa: 'autorizo o uso dos meus dados de deficiência'
    tem palavra de consentimento E de dado sensível. Tem que valer o sensível,
    senão o sistema consente por ele num campo que só ele pode responder."""
    p = "Autorizo o uso dos meus dados sobre deficiência para fins estatísticos"
    assert r.classificar(p) is r.Classe.SENSIVEL


# ── Política: onde a esticada é permitida ─────────────────────────────────────

def test_fato_verificavel_nunca_passa_de_documentada():
    """Inventar empregador ou formação não custa a entrevista — custa a oferta.
    Falsidade em processo seletivo é causa de rescisão."""
    assert r.politica_para(r.Classe.FATO, _contexto()) is r.Sustentacao.DOCUMENTADA


def test_sensivel_nunca_e_inferido():
    assert r.politica_para(r.Classe.SENSIVEL, _contexto()) is r.Sustentacao.DOCUMENTADA


def test_dominio_periferico_aceita_esticada():
    """Vaga de Data Engineer que cita pagamentos de passagem: afirmar domínio é
    barato e provavelmente nem é assunto da entrevista."""
    ctx = _contexto(titulo="Data Engineer", centrais={"python", "spark"})
    assert r.politica_para(r.Classe.DOMINIO, ctx, "pagamentos") is r.Sustentacao.ESTENDIDA


def test_dominio_central_da_vaga_nao_aceita_esticada():
    """Este é o caso da Adyen. 'Payments' está no TÍTULO: dizer que tem
    experiência não leva à entrevista, leva à tela técnica sobre pagamentos."""
    ctx = _contexto(titulo="Payments Performance Analyst (Data & Analytics)")
    assert r.politica_para(r.Classe.DOMINIO, ctx, "payments") is r.Sustentacao.DERIVADA


def test_centralidade_tambem_olha_os_requisitos_nao_so_o_titulo():
    ctx = _contexto(titulo="Data Analyst", centrais={"risco de crédito", "fraude"})
    assert r.politica_para(r.Classe.DOMINIO, ctx, "fraude") is r.Sustentacao.DERIVADA


def test_tempo_composto_aceita_leitura_favoravel():
    """'Anos com Risco, Payment Performance E Dados' bundla três áreas: 2,2 anos
    em dados torna '2-4 years' verdadeiro para um dos termos, e não existe leitura
    única correta."""
    p = "How many years of experience do you have with Risk, Payment Performance, and Data?"
    assert r.politica_para(r.Classe.TEMPO, _contexto(), pergunta=p) is r.Sustentacao.ESTENDIDA


def test_tempo_de_termo_unico_nao_aceita_esticada():
    """'How many years with Python?' tem resposta exata, e as datas estão no
    LinkedIn dele. Esticar aqui é barato de conferir e caro quando conferem —
    esta é a metade do teto de TEMPO que fazia o dano."""
    p = "How many years of experience do you have with Python?"
    assert r.politica_para(r.Classe.TEMPO, _contexto(), pergunta=p) is r.Sustentacao.DERIVADA


@pytest.mark.parametrize("pergunta,composta", [
    ("How many years of experience with Risk, Payments and Data?", True),
    ("Quantos anos de experiência com Python e SQL?", True),
    ("Experiência com ETL/ELT?", True),
    ("How many years of experience do you have with Python?", False),
    ("Quantos anos de experiência com Spark?", False),
    # A vírgula está ANTES do sujeito: a pergunta segue sendo de um termo só.
    ("In your career, how many years of experience do you have with Airflow?", False),
])
def test_deteccao_de_pergunta_composta(pergunta, composta):
    assert r._e_composta(pergunta) is composta


def test_esticada_em_tempo_de_termo_unico_e_recusada_ponta_a_ponta():
    assert r.validar(
        {"valor": "5-7 years", "sustentacao": "estendida", "evidencia": ""},
        "How many years of experience do you have with Python?",
        [{"label": "2-4 years"}, {"label": "5-7 years"}], _contexto(),
    ) is None


# ── Validação da saída do modelo ──────────────────────────────────────────────

OPCOES = [
    {"label": "A. Beginner", "value": "1"},
    {"label": "C. Advanced", "value": "3"},
]


def test_aceita_resposta_documentada_com_evidencia():
    resp = r.validar(
        {"valor": "C. Advanced", "sustentacao": "documentada",
         "evidencia": "Idiomas: Inglês — Avançado"},
        "What is your level of proficiency in English?", OPCOES, _contexto(),
    )
    assert resp is not None
    assert resp.valor == "C. Advanced"
    assert resp.sustentacao is r.Sustentacao.DOCUMENTADA


def test_rotulo_que_nao_existe_e_recusado():
    """Modelo alucinando opção é a forma mais fácil de submeter campo vazio sem
    ninguém perceber: o applicator tenta selecionar, não acha, e segue."""
    assert r.validar(
        {"valor": "F. Perfect", "sustentacao": "documentada", "evidencia": "x"},
        "English?", OPCOES, _contexto(),
    ) is None


def test_casamento_parcial_resolve_para_o_rotulo_exato():
    resp = r.validar(
        {"valor": "Advanced", "sustentacao": "documentada", "evidencia": "Avançado"},
        "English?", OPCOES, _contexto(),
    )
    assert resp.valor == "C. Advanced", "tem que virar o rótulo exato do formulário"


def test_documentada_sem_evidencia_e_rebaixada():
    """Autoclassificação do modelo não é confiável sozinha. Sem trecho citado,
    'documentada' é só uma afirmação sobre si mesma."""
    resp = r.validar(
        {"valor": "C. Advanced", "sustentacao": "documentada", "evidencia": ""},
        "English?", OPCOES, _contexto(),
    )
    assert resp.sustentacao is r.Sustentacao.DERIVADA


def test_sustentacao_invalida_vira_o_pior_caso():
    """Se não dá para saber quão esticada é, trate como a mais esticada — e deixe
    a política decidir. O contrário deixaria passar por omissão: bastaria o modelo
    devolver um rótulo que ninguém reconhece para escapar de todo teto.

    Aqui o efeito é recusa, porque pergunta aberta tem teto `derivada`."""
    assert r.validar(
        {"valor": "C. Advanced", "sustentacao": "inventada", "evidencia": ""},
        "English?", OPCOES, _contexto(),
    ) is None

    # Onde o teto é `estendida`, a mesma saída passa — o pior caso é o teto, não
    # uma recusa automática.
    ctx = _contexto(titulo="Data Engineer")
    assert r.validar(
        {"valor": "Yes", "sustentacao": "inventada", "evidencia": ""},
        "Do you have experience with retail?", [{"label": "Yes"}], ctx,
    ) is not None


def test_estendida_em_fato_verificavel_e_recusada():
    assert r.validar(
        {"valor": "Nubank", "sustentacao": "estendida", "evidencia": ""},
        "What is your current employer?", None, _contexto(),
    ) is None


def test_estendida_em_dominio_central_e_recusada():
    """O caso Adyen, ponta a ponta."""
    ctx = _contexto(titulo="Payments Performance Analyst")
    assert r.validar(
        {"valor": "Yes", "sustentacao": "estendida", "evidencia": ""},
        "Do you have experience with payments?",
        [{"label": "Yes"}, {"label": "No"}], ctx,
    ) is None


def test_estendida_em_dominio_periferico_passa():
    ctx = _contexto(titulo="Data Engineer", centrais={"spark"})
    resp = r.validar(
        {"valor": "Yes", "sustentacao": "estendida", "evidencia": "",
         "preparar": "citar análise de transações no projeto X"},
        "Do you have experience with retail?",
        [{"label": "Yes"}, {"label": "No"}], ctx,
    )
    assert resp is not None and resp.valor == "Yes"


def test_valor_nulo_nao_vira_resposta():
    for vazio in (None, "", "null"):
        assert r.validar({"valor": vazio}, "Qualquer?", None, _contexto()) is None


def test_saida_que_nao_e_dict_nao_derruba():
    for lixo in (None, [], "texto", 42):
        assert r.validar(lixo, "P?", None, _contexto()) is None


# ── Briefing ──────────────────────────────────────────────────────────────────

def test_briefing_lista_o_que_precisa_ser_defendido():
    """Contrapartida de permitir esticar: uma afirmação que ele não lembra de ter
    feito é uma armadilha com o nome dele."""
    dados = {
        "Inglês?": r.Resposta("C. Advanced", r.Classe.FERRAMENTA,
                              r.Sustentacao.DOCUMENTADA, evidencia="Avançado"),
        "Varejo?": r.Resposta("Yes", r.Classe.DOMINIO, r.Sustentacao.ESTENDIDA,
                              preparar="ligar a dashboards de vendas"),
        "ETL?": r.Resposta("Yes", r.Classe.FERRAMENTA, r.Sustentacao.DERIVADA,
                           evidencia="Azure Data Factory, Airbyte"),
    }
    b = r.briefing(dados)
    perguntas = [i["pergunta"] for i in b]

    assert "Inglês?" not in perguntas, "documentada não precisa de preparo"
    assert set(perguntas) == {"Varejo?", "ETL?"}
    assert b[0]["pergunta"] == "Varejo?", "estendida primeiro: é o maior risco"


def test_briefing_vazio_quando_tudo_e_documentado():
    dados = {"X?": r.Resposta("Sim", r.Classe.FERRAMENTA,
                              r.Sustentacao.DOCUMENTADA, evidencia="y")}
    assert r.briefing(dados) == []


# ── Prompt ────────────────────────────────────────────────────────────────────

def test_prompt_carrega_o_teto_resolvido_pela_politica():
    """O modelo não decide a própria licença: o teto entra pronto no prompt."""
    ctx = _contexto(titulo="Payments Performance Analyst")
    p = r.montar_prompt("Do you have experience with payments?", "select",
                        [{"label": "Yes"}, {"label": "No"}], {"nome": "R"}, ctx)
    assert "**derivada**" in p
    assert "estendida" in p, "os níveis precisam estar explicados"


def test_prompt_proibe_inventar_fato_e_responder_sensivel():
    p = r.montar_prompt("Qualquer coisa?", "text", None, {}, _contexto())
    baixo = p.lower()
    assert "nunca invente empregador" in baixo
    assert "sensível" in baixo or "sensivel" in baixo


def test_prompt_ensina_equivalencia_antes_de_esticar():
    """O maior ganho não é mentir melhor, é parar de deixar em branco o que já é
    verdade. `_auto_answer` devolvia None para 'Which BI tools?' com Power BI
    escrito no currículo."""
    p = r.montar_prompt("Which BI tools?", "text", None, {}, _contexto())
    assert "esgote a VERDADE" in p
    assert "Power BI" in p


def test_prompt_exige_rotulo_exato_quando_ha_opcoes():
    p = r.montar_prompt("Nível?", "select",
                        [{"label": "A. Beginner"}, {"label": "C. Advanced"}],
                        {}, _contexto())
    assert "A. Beginner, C. Advanced" in p
    assert "EXATAMENTE" in p


# ── Termo e centralidade ──────────────────────────────────────────────────────

@pytest.mark.parametrize("pergunta,termo", [
    ("Do you have experience with payments?", "payments"),
    ("Experiência com risco de crédito?", "risco"),
    ("Do you have experience with Snowflake?", "Snowflake"),
    ("Do you like coffee?", ""),
])
def test_termo_da_pergunta(pergunta, termo):
    assert r._termo_da_pergunta(pergunta) == termo


def test_centralidade_ignora_acento_e_caixa():
    ctx = _contexto(titulo="Analista de LOGÍSTICA")
    assert ctx.e_central("logistica")


# ── Documentos: o que decide se o banco de respostas serve para algo ──────────

@pytest.mark.parametrize("pergunta", [
    "RG",
    "Órgão e Estado de emissão do RG",
    "Nome da mãe",
    "Nome do pai",
    "Naturalidade (cidade e estado de nascimento)",
    "Data de nascimento",
    "Você trabalha na empresa PagBank?",
    "Alguém que trabalha nesta empresa indicou você para esta vaga?",
])
def test_documento_e_filiacao_sao_fato(pergunta):
    """Fato tem escopo global no banco de respostas; ABERTA tem escopo por
    empresa. `cpf` estava sozinho nesta lista, e os irmãos dele caíam em ABERTA:
    o banco guardaria "nome da mãe" uma vez POR EMPRESA e ele redigitaria em
    quase todas as 230 vagas da Gupy — o tédio que o banco existe para matar."""
    assert r.classificar(pergunta) is r.Classe.FATO


@pytest.mark.parametrize("pergunta", [
    "Qual sua experiência com energia renovável?",
    "Descreva um argumento técnico que você defendeu",
    "Isso é urgente?",
])
def test_sigla_curta_nao_contamina_por_substring(pergunta):
    """"rg" vive dentro de "energia", "urgente" e "orgao". Como substring,
    classificaria pergunta de domínio como documento — e o banco passaria a
    devolver um RG onde se pedia experiência."""
    assert r.classificar(pergunta) is not r.Classe.FATO
