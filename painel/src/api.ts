// Tudo que o painel pede ao backend, num arquivo só.
//
// O painel é uma página da extensão (`chrome-extension://`), e não a página da
// vaga: o CSP que bloqueia o `fetch` do content script não vale aqui, então
// este arquivo fala com a API direto — diferente de `extensao/conteudo.js`, que
// precisa passar pelo service worker.

const API = "http://127.0.0.1:8787";

/** Erro do catálogo do Python (`jobapplier/erros.py`). Forma única em todas as rotas. */
export type ErroApi = {
  codigo: string;
  titulo: string;
  detalhe: string;
  acao: string;
  auto: string | null;
  familia: string;
};

export type Checagem = {
  nome: string;
  ok: boolean;
  aviso: boolean;
  erro?: ErroApi;
  detalhe?: string;
};

export type Saude = { ok: boolean; versao: number; checagens: Checagem[] };

/** Nível 1 da aderência: a conclusão, sem a evidência. */
export type Nivel1 = { titulo: string; rotulo: string; porque: string; atencao: string };

/** Nível 2: o que sustenta a conclusão. */
export type Eixo = { nome: string; nota: number; maximo: number; fracao: number };
export type Aderencia = Nivel1 & {
  score: number;
  eixos: Eixo[];
  cobertas: string[];
  faltam: string[];
  eliminatorios: string[];
};

export type Vaga = {
  id: number;
  titulo: string;
  empresa: string;
  empresa_exibicao: string;
  plataforma: string;
  link: string;
  score: number;
  localizacao: string;
  modalidade: string;
  status: string;
  tem_curriculo: boolean;
  tem_carta: boolean;
  aderencia: Nivel1 | null;
};

export type Pergunta = {
  pergunta: string;
  resposta: string;
  respondida: boolean;
  obrigatoria: boolean;
  eliminatoria: boolean;
  origem: string;
};

export type Dossie = {
  vaga: Vaga;
  aderencia: Aderencia;
  carta: string;
  perguntas: Pergunta[];
  manuscrito: boolean;
  situacao_ficha: string;
};

/** Erro com o objeto do catálogo junto, para a tela renderizar título e ação. */
export type Decisao = "enviada" | "descartar" | "adiar" | "abrir";

export class FalhaApi extends Error {
  constructor(readonly erro: ErroApi, readonly status: number) {
    super(erro.titulo);
  }
}

// Quando a API não responde não há catálogo para consultar — ela é que o serve.
// Mesma forma dos outros de propósito, para quem renderiza não precisar saber.
const API_FORA: ErroApi = {
  codigo: "api-fora",
  titulo: "O AI Job Applier não está rodando",
  detalhe: "O serviço local não respondeu.",
  acao: "Rode `python run.py` na pasta do projeto.",
  auto: null,
  familia: "ambiente",
};

// A API respondeu, mas sem erro do catálogo: rota que ela não conhece, ou corpo
// que este painel não entende. Quase sempre é versão — o `python run.py` de
// antes de uma atualização. Chamar isso de "não está rodando" contradiz o ponto
// verde ao lado, que acabou de falar com a mesma API.
const CONTRATO_DESCONHECIDO: ErroApi = {
  codigo: "contrato-desconhecido",
  titulo: "O painel e o serviço estão em versões diferentes",
  detalhe: "A API respondeu, mas não do jeito que esta versão do painel espera.",
  acao: "Reinicie o `python run.py` e recarregue a extensão em chrome://extensions.",
  auto: null,
  familia: "ambiente",
};

async function chamar<T>(caminho: string, opcoes?: RequestInit): Promise<T> {
  let resposta: Response;
  try {
    resposta = await fetch(API + caminho, opcoes);
  } catch {
    throw new FalhaApi(API_FORA, 0);
  }
  const corpo = await resposta.json().catch(() => ({}));
  if (!resposta.ok) {
    throw new FalhaApi(corpo.erro ?? CONTRATO_DESCONHECIDO, resposta.status);
  }
  return corpo as T;
}

export const api = {
  saude: () => chamar<Saude>("/saude"),
  fila: () => chamar<{ vagas: Vaga[]; corte: number }>("/fila"),
  acervo: (scoreMin = 0) =>
    chamar<{ vagas: Vaga[] }>(`/fila?tudo=1&limite=100&score_min=${scoreMin}`),
  dossie: (vagaId: number) => chamar<Dossie>(`/vaga/${vagaId}/dossie`),
  decidir: (vagaId: number, decisao: Decisao) =>
    chamar<{ ok: boolean }>(`/vaga/${vagaId}/decisao`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decisao }),
    }),
  curriculoUrl: (vagaId: number) => `${API}/vaga/${vagaId}/curriculo`,
};
