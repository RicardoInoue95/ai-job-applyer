"""Ter a resposta certa não é o mesmo que conseguir escrevê-la no formulário.

Um ensaio no formulário real da Adyen mostrou o applicator calculando resposta
para todo campo obrigatório (`perguntas_manuais` vazio) e mesmo assim deixando
três em branco na tela: a carta de apresentação, o consentimento obrigatório e o
nível de inglês. Nenhum teste pegava isso porque todos verificavam a camada de
decisão — `_auto_answer` — e nenhum verificava a camada de escrita.

`application_confidence` media disponibilidade de resposta e era lido como
prontidão para enviar. Estes testes cobrem a diferença.
"""
import pytest

from jobapplier.applicators import greenhouse as gh

# ── Consentimento obrigatório ─────────────────────────────────────────────────

class _Caixa:
    """Checkbox de mentira, com o mínimo que `_pw_marcar_checkbox` usa."""

    def __init__(self, marcado=False, aceita=True):
        self._marcado = marcado
        self._aceita = aceita

    def is_checked(self):
        return self._marcado

    def check(self, timeout=None):
        if self._aceita:
            self._marcado = True


class _Pagina:
    def __init__(self, por_seletor):
        self.por_seletor = por_seletor
        self.consultas = []

    def query_selector(self, sel):
        self.consultas.append(sel)
        achado = self.por_seletor.get(sel)
        return achado[0] if isinstance(achado, list) and achado else achado

    def query_selector_all(self, sel):
        self.consultas.append(sel)
        achado = self.por_seletor.get(sel, [])
        return achado if isinstance(achado, list) else [achado]


def test_marca_pelo_id_exato_quando_a_resposta_e_o_value():
    caixa = _Caixa()
    pagina = _Pagina({'input[type=checkbox][id="q[]_731111200"]': caixa})

    assert gh._pw_marcar_checkbox(pagina, "q[]", "731111200") is True
    assert caixa.is_checked()


def test_resposta_yes_marca_a_caixa_unica_do_campo():
    """`_auto_answer` devolve 'yes' para consentimento, não o value numérico.

    Era exatamente aqui que o Point of Data Transfer da Adyen ficava em branco:
    o id `question_67923270[]_yes` não existe, e o código desistia.
    """
    caixa = _Caixa()
    pagina = _Pagina({'input[type=checkbox][id^="q[]_"]': [caixa]})

    assert gh._pw_marcar_checkbox(pagina, "q[]", "yes") is True
    assert caixa.is_checked()


@pytest.mark.parametrize("afirmativo", ["yes", "Sim", "TRUE", "1", "y", "s"])
def test_formas_afirmativas_aceitas(afirmativo):
    caixa = _Caixa()
    pagina = _Pagina({'input[type=checkbox][id^="q[]_"]': [caixa]})
    assert gh._pw_marcar_checkbox(pagina, "q[]", afirmativo) is True


def test_varias_caixas_com_resposta_generica_nao_marca_nada():
    """'yes' não diz QUAL caixa. Marcar a primeira seria inventar uma resposta."""
    caixas = [_Caixa(), _Caixa()]
    pagina = _Pagina({'input[type=checkbox][id^="q[]_"]': caixas})

    assert gh._pw_marcar_checkbox(pagina, "q[]", "yes") is False
    assert not any(c.is_checked() for c in caixas)


def test_campo_que_nao_e_checkbox_devolve_false():
    """False significa 'tente o react-select', não 'falhou'."""
    assert gh._pw_marcar_checkbox(_Pagina({}), "q", "algum") is False


def test_caixa_que_nao_aceita_marcacao_nao_e_reportada_como_sucesso():
    """O input real fica sob um SVG; clique interceptado não levanta exceção.

    Confiar no `check()` sem reconferir devolveria True com a caixa vazia — o
    pior desfecho possível, porque some do log e reaparece como rejeição.
    """
    caixa = _Caixa(aceita=False)
    pagina = _Pagina({'input[type=checkbox][id^="q[]_"]': [caixa]})

    assert gh._pw_marcar_checkbox(pagina, "q[]", "yes") is False


def test_caixa_ja_marcada_permanece_marcada():
    caixa = _Caixa(marcado=True)
    pagina = _Pagina({'input[type=checkbox][id="q[]_1"]': caixa})
    assert gh._pw_marcar_checkbox(pagina, "q[]", "1") is True


# ── Idioma: currículo em português, formulário em inglês ──────────────────────

@pytest.mark.parametrize("resposta,esperado", [
    ("Avançado", "advanced"),
    ("avancado", "advanced"),   # sem acento
    ("AVANÇADO", "advanced"),   # caixa alta
    ("Fluente", "fluent"),
    ("Nativo", "native"),
    ("Intermediário", "intermediate"),
    ("Básico", "beginner"),
])
def test_nivel_em_portugues_encontra_a_opcao_em_ingles(resposta, esperado):
    """O currículo diz 'Avançado'; a Adyen oferece 'C. Advanced'. Sem equivalência
    o campo fica vazio com a resposta certa já calculada."""
    assert esperado in gh._equivalentes(resposta)


def test_termo_desconhecido_nao_inventa_equivalencia():
    """Sem correspondência é melhor não preencher do que preencher errado."""
    assert gh._equivalentes("Klingon") == ()
    assert gh._equivalentes("") == ()


def test_o_termo_exato_tem_prioridade_sobre_o_equivalente():
    """'Fluente' aceita 'native' como alternativa, mas se existir opção 'fluent'
    é ela que deve ganhar — a equivalência é rede de segurança, não preferência."""
    equivalentes = gh._equivalentes("Fluente")
    assert equivalentes.index("fluent") < equivalentes.index("native")


# ── Carta de apresentação ─────────────────────────────────────────────────────

def test_o_applicator_clica_em_enter_manually_antes_de_desistir_da_carta():
    """Nos formulários novos o textarea não existe até clicar em 'Enter manually':
    o campo nasce como quatro botões. Sem o clique a carta não entrava, e nada
    acusava — textarea ausente era lido como 'esta vaga não pede carta'."""
    import inspect

    fonte = inspect.getsource(gh.apply)
    assert "Enter manually" in fonte, "o applicator precisa abrir o campo manual"
    # E a busca pelo textarea tem que vir DEPOIS do clique, não antes.
    assert fonte.index("Enter manually") < fonte.rindex("cover_letter_body")
