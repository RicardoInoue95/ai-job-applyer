"""Testes da camada multi-provedor de LLM.

Usa um provedor falso em vez de chamada de rede: o objetivo é cobrir a lógica
compartilhada (extração de JSON, retry, fallback, resolução de provedor), não os
SDKs de terceiros.
"""
import json

import pytest

from jobapplier import llm
from jobapplier.llm import base
from jobapplier.llm.base import (
    LLMClient,
    LLMError,
    LLMRespostaVazia,
    LLMSemChave,
    extrair_json,
)

# ── Provedor falso ────────────────────────────────────────────────────────────

class ClienteFake(LLMClient):
    provedor = "fake"
    modelo_padrao = "fake-1"
    env_chave = "FAKE_API_KEY"

    def __init__(self, respostas=None, erros=None, **kwargs):
        kwargs.setdefault("api_key", "chave-fake")
        kwargs.setdefault("use_cache", False)
        super().__init__(**kwargs)
        self.respostas = list(respostas or ["ok"])
        self.erros = list(erros or [])
        self.chamadas = 0

    def _gerar_texto(self, prompt, temperature):
        self.chamadas += 1
        if self.erros:
            raise self.erros.pop(0)
        return self.respostas[min(self.chamadas - 1, len(self.respostas) - 1)]


@pytest.fixture
def sem_sono(monkeypatch):
    monkeypatch.setattr(base.time, "sleep", lambda s: None)


# ── extrair_json ──────────────────────────────────────────────────────────────

def test_json_puro():
    assert extrair_json('{"a": 1}') == {"a": 1}


def test_json_em_cerca_markdown():
    assert extrair_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_json_em_cerca_sem_linguagem():
    assert extrair_json('```\n{"a": 1}\n```') == {"a": 1}


def test_json_array():
    assert extrair_json('[1, 2, 3]') == [1, 2, 3]


def test_json_com_prosa_antes_e_depois():
    bruto = 'Claro! Aqui está o resultado:\n{"score": 80}\nEspero que ajude.'
    assert extrair_json(bruto) == {"score": 80}


def test_json_com_espacos_e_quebras():
    assert extrair_json('\n\n  {"a": 1}  \n\n') == {"a": 1}


def test_json_aninhado_recorta_ate_ultima_chave():
    bruto = 'resposta: {"a": {"b": [1, 2]}} fim'
    assert extrair_json(bruto) == {"a": {"b": [1, 2]}}


def test_none_levanta_resposta_vazia():
    # Regressão do bug real: response.text vinha None em bloqueio de safety e
    # o código antigo estourava AttributeError, engolido por except genérico.
    with pytest.raises(LLMRespostaVazia):
        extrair_json(None)


def test_string_vazia_levanta_resposta_vazia():
    with pytest.raises(LLMRespostaVazia):
        extrair_json("   ")


def test_texto_sem_json_levanta_decode_error():
    with pytest.raises(json.JSONDecodeError):
        extrair_json("desculpe, não posso responder isso")


# ── Identidade e cache key ────────────────────────────────────────────────────

def test_modelo_completo_inclui_provedor():
    assert ClienteFake().modelo_completo == "fake:fake-1"


def test_chave_de_cache_separa_provedores():
    a, b = ClienteFake(), ClienteFake()
    b.provedor = "outro"
    assert a._chave_cache("p", "texto") != b._chave_cache("p", "texto")


def test_chave_de_cache_separa_modos():
    c = ClienteFake()
    assert c._chave_cache("p", "texto") != c._chave_cache("p", "json")


def test_chave_de_cache_separa_modelos():
    a = ClienteFake(modelo="m1")
    b = ClienteFake(modelo="m2")
    assert a._chave_cache("p", "texto") != b._chave_cache("p", "texto")


def test_chave_de_cache_e_estavel():
    c = ClienteFake()
    assert c._chave_cache("mesmo prompt", "texto") == c._chave_cache("mesmo prompt", "texto")


def test_construtor_sem_chave_levanta():
    with pytest.raises(LLMSemChave):
        ClienteFake(api_key="")


# ── Retry ─────────────────────────────────────────────────────────────────────

def test_retry_em_rate_limit_e_depois_sucesso(sem_sono):
    c = ClienteFake(respostas=["depois do 429"], erros=[RuntimeError("429 quota exceeded")])
    assert c.generate("p") == "depois do 429"
    assert c.chamadas == 2


@pytest.mark.parametrize("mensagem", [
    "429 Too Many Requests", "RESOURCE_EXHAUSTED", "rate limit reached",
    "529 overloaded", "insufficient quota", "at capacity",
])
def test_variacoes_de_rate_limit_sao_reconhecidas(mensagem, sem_sono):
    c = ClienteFake(respostas=["ok"], erros=[RuntimeError(mensagem)])
    assert c.generate("p") == "ok"


def test_erro_nao_transitorio_nao_faz_retry(sem_sono):
    c = ClienteFake(erros=[ValueError("prompt inválido")])
    with pytest.raises(ValueError):
        c.generate("p")
    assert c.chamadas == 1


def test_desiste_apos_max_tentativas(sem_sono):
    erros = [RuntimeError("429")] * base.MAX_TENTATIVAS
    c = ClienteFake(erros=erros)
    with pytest.raises(RuntimeError):
        c.generate("p")
    assert c.chamadas == base.MAX_TENTATIVAS


# ── generate / generate_json ──────────────────────────────────────────────────

def test_resposta_vazia_levanta():
    c = ClienteFake(respostas=[""])
    with pytest.raises(LLMRespostaVazia):
        c.generate("p")


def test_generate_json_usa_caminho_generico_quando_sem_modo_nativo():
    c = ClienteFake(respostas=['{"ok": true}'])
    assert c.generate_json("p") == {"ok": True}


def test_generate_json_adiciona_instrucao_no_prompt():
    """Modo JSON da OpenAI exige a palavra JSON no prompt."""
    capturado = {}

    class Espia(ClienteFake):
        def _gerar_texto(self, prompt, temperature):
            capturado["prompt"] = prompt
            return "{}"

    Espia().generate_json("pontue esta vaga")
    assert "JSON" in capturado["prompt"]
    assert "pontue esta vaga" in capturado["prompt"]


def test_modo_json_nativo_tem_precedencia():
    class ComNativo(ClienteFake):
        def _gerar_json_nativo(self, prompt, temperature):
            return '{"via": "nativo"}'

    assert ComNativo().generate_json("p") == {"via": "nativo"}


def test_cai_no_generico_se_nativo_devolve_none():
    class NativoIndisponivel(ClienteFake):
        def _gerar_json_nativo(self, prompt, temperature):
            return None

    c = NativoIndisponivel(respostas=['{"via": "generico"}'])
    assert c.generate_json("p") == {"via": "generico"}


# ── Fallback ──────────────────────────────────────────────────────────────────

def test_fallback_usa_primeiro_que_funciona():
    a = ClienteFake(erros=[LLMError("cota estourada")])
    b = ClienteFake(respostas=["resposta do reserva"])
    cadeia = llm.ClienteComFallback([a, b])
    assert cadeia.generate("p") == "resposta do reserva"


def test_fallback_nao_chama_reserva_se_primario_funciona():
    a = ClienteFake(respostas=["primario"])
    b = ClienteFake(respostas=["reserva"])
    assert llm.ClienteComFallback([a, b]).generate("p") == "primario"
    assert b.chamadas == 0


def test_fallback_agrega_erros_quando_todos_falham():
    a = ClienteFake(erros=[LLMError("erro A")])
    b = ClienteFake(erros=[LLMError("erro B")])
    with pytest.raises(LLMError) as info:
        llm.ClienteComFallback([a, b]).generate("p")
    assert "erro A" in str(info.value)
    assert "erro B" in str(info.value)


def test_fallback_tambem_vale_para_json():
    a = ClienteFake(erros=[LLMError("falhou")])
    b = ClienteFake(respostas=['{"ok": 1}'])
    assert llm.ClienteComFallback([a, b]).generate_json("p") == {"ok": 1}


def test_fallback_vazio_levanta():
    with pytest.raises(LLMSemChave):
        llm.ClienteComFallback([])


def test_fallback_expoe_cadeia_no_repr():
    cadeia = llm.ClienteComFallback([ClienteFake(), ClienteFake()])
    assert "fake:fake-1" in cadeia.modelo_completo


# ── Catálogo e resolução ──────────────────────────────────────────────────────

def test_provedores_registrados():
    assert set(llm.PROVEDORES) == {"gemini", "openai", "anthropic", "ollama"}


def test_todo_provedor_declara_metadados():
    for nome, classe in llm.PROVEDORES.items():
        assert classe.provedor == nome
        assert classe.modelo_padrao, f"{nome} sem modelo_padrao"
        assert classe.env_chave.endswith("_API_KEY"), f"{nome} com env_chave estranha"
        assert classe.pacote_pip, f"{nome} sem pacote_pip"


def test_modelo_padrao_esta_entre_os_sugeridos():
    for nome, classe in llm.PROVEDORES.items():
        ids = [m for m, _ in llm.MODELOS_SUGERIDOS[nome]]
        assert classe.modelo_padrao in ids, f"padrão de {nome} fora de MODELOS_SUGERIDOS"


def test_ordem_padrao_e_subconjunto_dos_provedores():
    assert set(llm.ORDEM_PADRAO) <= set(llm.PROVEDORES)


def test_ollama_fica_fora_da_autodeteccao():
    """Saber se o Ollama está no ar exige rede.

    Autodetectá-lo trocaria a mensagem clara de "nenhum provedor configurado"
    por um connection refused tardio, na primeira geração.
    """
    assert "ollama" in llm.PROVEDORES
    assert "ollama" not in llm.ORDEM_PADRAO
    assert "ollama" in llm.SEM_CHAVE


def test_ollama_funciona_quando_pedido_explicitamente(tmp_path):
    from jobapplier.config.manager import ConfigManager

    cliente = llm.get_client(
        config=ConfigManager(path=tmp_path / "v.json"),
        provedor="ollama", com_fallback=False,
    )
    assert cliente.provedor == "ollama"
    assert "11434" in cliente.base_url


def test_provedor_desconhecido_no_teste_de_conexao():
    ok, msg = llm.testar_conexao("cohere")
    assert not ok
    assert "desconhecido" in msg


def test_sem_nenhuma_chave_levanta_com_instrucao(monkeypatch, tmp_path):
    from jobapplier.config.manager import ConfigManager

    for classe in llm.PROVEDORES.values():
        monkeypatch.delenv(f"AIJOB_{classe.env_chave}", raising=False)
    monkeypatch.delenv("AIJOB_LLM_PROVEDOR", raising=False)

    with pytest.raises(LLMSemChave) as info:
        llm.get_client(config=ConfigManager(path=tmp_path / "vazio.json"))
    assert "AIJOB_OPENAI_API_KEY" in str(info.value)


def test_autodeteccao_escolhe_por_ordem_de_preferencia(monkeypatch, tmp_path):
    from jobapplier.config.manager import ConfigManager

    for classe in llm.PROVEDORES.values():
        monkeypatch.delenv(f"AIJOB_{classe.env_chave}", raising=False)
    monkeypatch.delenv("AIJOB_LLM_PROVEDOR", raising=False)
    # Só Gemini tem chave — deve ser o escolhido mesmo não sendo o primeiro
    # da ORDEM_PADRAO.
    monkeypatch.setenv("AIJOB_GEMINI_API_KEY", "chave-g")

    cfg = ConfigManager(path=tmp_path / "vazio.json")
    assert llm.provedores_configurados(config=cfg) == ["gemini"]
    cliente = llm.get_client(config=cfg)
    assert cliente.provedor == "gemini"


def test_openai_ganha_de_gemini_quando_ambos_tem_chave(monkeypatch, tmp_path):
    from jobapplier.config.manager import ConfigManager

    monkeypatch.delenv("AIJOB_LLM_PROVEDOR", raising=False)
    monkeypatch.delenv("AIJOB_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("AIJOB_GEMINI_API_KEY", "chave-g")
    monkeypatch.setenv("AIJOB_OPENAI_API_KEY", "chave-o")

    cfg = ConfigManager(path=tmp_path / "vazio.json")
    assert llm.provedores_configurados(config=cfg)[0] == "openai"


def test_provedor_explicito_vence_autodeteccao(monkeypatch, tmp_path):
    from jobapplier.config.manager import ConfigManager

    monkeypatch.setenv("AIJOB_GEMINI_API_KEY", "chave-g")
    monkeypatch.setenv("AIJOB_OPENAI_API_KEY", "chave-o")

    cfg = ConfigManager(path=tmp_path / "vazio.json")
    cliente = llm.get_client(config=cfg, provedor="gemini", com_fallback=False)
    assert cliente.provedor == "gemini"


def test_provedor_selecionado_sem_chave_da_erro_claro(monkeypatch, tmp_path):
    from jobapplier.config.manager import ConfigManager

    monkeypatch.delenv("AIJOB_ANTHROPIC_API_KEY", raising=False)
    cfg = ConfigManager(path=tmp_path / "vazio.json")
    with pytest.raises(LLMSemChave) as info:
        llm.get_client(config=cfg, provedor="anthropic")
    assert "AIJOB_ANTHROPIC_API_KEY" in str(info.value)


def test_chave_do_provedor_cai_no_config_json(monkeypatch, tmp_path):
    from jobapplier.config.manager import ConfigManager

    monkeypatch.delenv("AIJOB_OPENAI_API_KEY", raising=False)
    cfg = ConfigManager(path=tmp_path / "c.json")
    cfg.save({"llm": {"openai": {"api_key": "do-json"}}})
    assert llm.chave_do_provedor("openai", config=cfg) == "do-json"


def test_gemini_mantem_caminho_legado_no_config(monkeypatch, tmp_path):
    from jobapplier.config.manager import ConfigManager

    monkeypatch.delenv("AIJOB_GEMINI_API_KEY", raising=False)
    cfg = ConfigManager(path=tmp_path / "c.json")
    cfg.save({"gemini": {"api_key": "legado"}})
    assert llm.chave_do_provedor("gemini", config=cfg) == "legado"


# ── SDK ausente ───────────────────────────────────────────────────────────────

def test_sdk_ausente_da_mensagem_com_pip_install(monkeypatch):
    from jobapplier.llm import providers

    def falha(pacote, pip):
        raise llm.LLMDependenciaAusente(f"SDK '{pacote}' não instalado. Rode: pip install {pip}")

    monkeypatch.setattr(providers, "_exigir", falha)
    with pytest.raises(llm.LLMDependenciaAusente) as info:
        providers.OpenAIClient(api_key="x")
    assert "pip install openai" in str(info.value)
