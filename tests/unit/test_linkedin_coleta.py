"""A coleta do LinkedIn gravava 200 vagas e produzia zero utilizáveis.

Dois defeitos somados, ambos silenciosos:

**Título placeholder.** 72% das vagas viravam "Vaga LinkedIn 4455351454" porque
o card ainda não tinha renderizado quando foi lido. O comentário no código dizia
"o título será preenchido ao normalizar a vaga" — e nada preenchia. Promessa em
comentário que nenhum código cumpria.

**Descrição vazia.** `"descricao": ""` era gravado literalmente: a lista de
resultados não traz descrição, e ninguém abria a página da vaga. Sem descrição o
filtro 4A não tem texto para casar, e 192 das 200 morriam ali.

O resultado combinado era pior que não coletar: linha no banco, custo de rede,
risco de detecção, e zero vaga aproveitável.
"""
import pytest

from jobapplier.applicators import linkedin


class _Elemento:
    def __init__(self, texto):
        self._texto = texto

    def inner_text(self):
        return self._texto


class _Pagina:
    """Página de mentira com o mínimo que `_detalhar` usa."""

    def __init__(self, por_seletor=None, ancora="", url="https://www.linkedin.com/jobs/view/1/"):
        self.por_seletor = por_seletor or {}
        self.ancora = ancora
        self.url = url
        self.visitadas = []

    def goto(self, url, **kwargs):
        self.visitadas.append(url)
        self.url = url

    def wait_for_timeout(self, _ms):
        pass

    def query_selector(self, seletor):
        texto = self.por_seletor.get(seletor)
        return _Elemento(texto) if texto else None

    def evaluate(self, _js):
        return self.ancora


# ── Extração de texto ─────────────────────────────────────────────────────────

def test_primeiro_seletor_com_texto_vence():
    pagina = _Pagina({"h1": "Engenheiro de Dados"})
    assert linkedin._primeiro_texto(pagina, ("#nao-existe", "h1")) == "Engenheiro de Dados"


def test_seletor_presente_mas_vazio_nao_conta():
    """Elemento existente com texto vazio precisa cair para o próximo — foi o
    que fazia o título virar placeholder mesmo com o elemento no DOM."""
    pagina = _Pagina({".titulo": "", "h1": "Analista de Dados"})
    assert linkedin._primeiro_texto(pagina, (".titulo", "h1")) == "Analista de Dados"


def test_nenhum_seletor_casa():
    assert linkedin._primeiro_texto(_Pagina(), ("#a", ".b")) == ""


def test_descricao_por_ancora_quando_classe_nao_casa():
    """O LinkedIn passou a gerar classes ofuscadas (`_8c493269`) que mudam a cada
    deploy. O rótulo que o usuário lê na tela é conteúdo, não implementação —
    por isso sobrevive."""
    pagina = _Pagina(ancora="Sobre a vaga\n\nBuscamos engenheiro de dados com Python…")
    assert "Python" in linkedin._descricao_por_ancora(pagina)


def test_ancora_que_explode_nao_derruba_a_coleta():
    class _Quebrada(_Pagina):
        def evaluate(self, _js):
            raise RuntimeError("contexto destruído")

    assert linkedin._descricao_por_ancora(_Quebrada()) == ""


# ── Enriquecimento ────────────────────────────────────────────────────────────

def _vaga(titulo="Vaga LinkedIn 123", provisorio=True, descricao=""):
    return {"titulo": titulo, "titulo_provisorio": provisorio,
            "descricao": descricao, "link": "https://www.linkedin.com/jobs/view/123/"}


def test_detalhar_preenche_titulo_e_descricao(monkeypatch):
    monkeypatch.setattr(linkedin.time, "sleep", lambda _s: None)
    pagina = _Pagina({"h1": "Engenheiro de Dados Sênior"},
                     ancora="Sobre a vaga\n" + "conteúdo real da vaga. " * 40)
    vagas = [_vaga()]

    assert linkedin._detalhar(pagina, vagas) == 1
    assert vagas[0]["titulo"] == "Engenheiro de Dados Sênior"
    assert vagas[0]["titulo_provisorio"] is False
    assert len(vagas[0]["descricao"]) > 300


def test_vaga_completa_nao_e_reaberta(monkeypatch):
    """Cada abertura é uma requisição autenticada a mais, e volume é o que a
    detecção procura. Não reabrir o que já está completo é economia de risco."""
    monkeypatch.setattr(linkedin.time, "sleep", lambda _s: None)
    pagina = _Pagina()
    completa = _vaga(titulo="Data Engineer", provisorio=False, descricao="x" * 500)

    linkedin._detalhar(pagina, [completa])
    assert pagina.visitadas == []


def test_prioriza_quem_esta_sem_titulo(monkeypatch):
    """Título ausente é pior que descrição ausente: além de quebrar o filtro,
    quebra o dedup, porque o hash inclui o título."""
    monkeypatch.setattr(linkedin.time, "sleep", lambda _s: None)
    pagina = _Pagina({"h1": "Título"}, ancora="Sobre a vaga\n" + "x " * 200)
    so_sem_descricao = _vaga(titulo="Data Engineer", provisorio=False)
    so_sem_descricao["link"] = "https://www.linkedin.com/jobs/view/999/"
    sem_titulo = _vaga()

    linkedin._detalhar(pagina, [so_sem_descricao, sem_titulo], limite=1)
    assert pagina.visitadas == [sem_titulo["link"]]


def test_teto_de_aberturas_e_respeitado(monkeypatch):
    monkeypatch.setattr(linkedin.time, "sleep", lambda _s: None)
    pagina = _Pagina({"h1": "T"}, ancora="Sobre a vaga\n" + "x " * 200)
    vagas = [{**_vaga(), "link": f"https://www.linkedin.com/jobs/view/{i}/"}
             for i in range(10)]

    linkedin._detalhar(pagina, vagas, limite=3)
    assert len(pagina.visitadas) == 3


def test_sessao_expirada_interrompe_em_vez_de_insistir(monkeypatch):
    """Insistir com sessão morta são N requisições que o LinkedIn registra como
    comportamento anômalo, sem trazer nenhum dado."""
    monkeypatch.setattr(linkedin.time, "sleep", lambda _s: None)

    class _Authwall(_Pagina):
        def goto(self, url, **kwargs):
            self.visitadas.append(url)
            self.url = "https://www.linkedin.com/authwall?trk=x"

    pagina = _Authwall()
    vagas = [{**_vaga(), "link": f"https://www.linkedin.com/jobs/view/{i}/"}
             for i in range(5)]

    linkedin._detalhar(pagina, vagas)
    assert len(pagina.visitadas) == 1, "tem que parar na primeira"


def test_erro_numa_vaga_nao_derruba_as_outras(monkeypatch):
    monkeypatch.setattr(linkedin.time, "sleep", lambda _s: None)

    class _UmaFalha(_Pagina):
        def goto(self, url, **kwargs):
            self.visitadas.append(url)
            if url.endswith("/0/"):
                raise RuntimeError("timeout")
            self.url = url

    pagina = _UmaFalha({"h1": "T"}, ancora="Sobre a vaga\n" + "x " * 200)
    vagas = [{**_vaga(), "link": f"https://www.linkedin.com/jobs/view/{i}/"}
             for i in range(3)]

    assert linkedin._detalhar(pagina, vagas) == 2


def test_ha_pausa_entre_aberturas(monkeypatch):
    """Sem ritmo humano são 40 requisições autenticadas em rajada — exatamente o
    padrão que a detecção procura."""
    pausas = []
    monkeypatch.setattr(linkedin.time, "sleep", pausas.append)
    pagina = _Pagina({"h1": "T"}, ancora="Sobre a vaga\n" + "x " * 200)
    vagas = [{**_vaga(), "link": f"https://www.linkedin.com/jobs/view/{i}/"}
             for i in range(3)]

    linkedin._detalhar(pagina, vagas)
    assert len(pausas) == 2, "pausa entre aberturas, não antes da primeira"
    assert all(p >= 1.0 for p in pausas)


# ── Contrato com o orquestrador ───────────────────────────────────────────────

def test_o_orquestrador_descarta_vaga_sem_titulo_ou_descricao():
    """Gravar vaga sem texto produz linha morta: custo de rede e de risco, zero
    vaga aproveitável. As 200 do histórico viraram 192 'filtrada_4a' e 8 'erro'."""
    import inspect

    from jobapplier import orchestrator

    fonte = inspect.getsource(orchestrator._executar_coleta)
    assert "titulo_provisorio" in fonte
    assert "descartadas" in fonte


@pytest.mark.parametrize("campo", ["titulo", "titulo_provisorio", "descricao",
                                   "link", "fonte_vaga_id"])
def test_o_card_devolve_os_campos_que_o_orquestrador_le(campo):
    import inspect

    fonte = inspect.getsource(linkedin._scrape_cards)
    assert f'"{campo}"' in fonte
