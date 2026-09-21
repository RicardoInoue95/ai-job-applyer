import { useCallback, useEffect, useState } from "react";
import { api, FalhaApi, type Decisao, type Dossie, type Vaga } from "./api";
import { Alerta } from "./Estado";

/** A inbox de revisão: uma vaga por vez, e a decisão é um toque.
 *
 * É a tela que o Streamlit não consegue fazer: ← → percorrem a fila sem
 * recarregar, um clique abre a vaga E registra que foi aberta, e o teclado
 * decide sem tirar a mão dele. Quem revisa 40 vagas sente a diferença entre
 * três cliques por vaga e um.
 *
 * O que ela mostra é o nível 1 da aderência — conclusão, por quê, ponto de
 * atenção — e o estado do dossiê. A evidência (barras, tecnologias) fica atrás
 * de "por que combina", porque em toda vaga voltaria o excesso de informação. */

const ATALHOS: Record<string, Decisao | "anterior" | "proxima" | "abrir"> = {
  ArrowLeft: "anterior",
  ArrowRight: "proxima",
  Enter: "abrir",
  a: "enviada",
  e: "descartar",
  s: "adiar",
};

export function Inbox({ vagas, aoDecidir }: {
  vagas: Vaga[];
  aoDecidir: (vagaId: number, decisao: Decisao) => Promise<void>;
}) {
  const [pos, setPos] = useState(0);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<FalhaApi | null>(null);
  const [aberta, setAberta] = useState<Set<number>>(new Set());

  const total = vagas.length;
  const vaga = vagas[Math.min(pos, total - 1)];

  const anterior = useCallback(() => setPos((p) => Math.max(0, p - 1)), []);
  const proxima = useCallback(() => setPos((p) => Math.min(total - 1, p + 1)), [total]);

  // "Abrir e candidatar": abre o link numa aba nova E registra `aberta`. A
  // vaga não sai da fila — o que se sabe é que o link foi aberto. Sair só
  // com "enviei" ou "não é para mim".
  const abrir = useCallback(async () => {
    if (!vaga) return;
    window.open(vaga.link, "_blank");
    setAberta((s) => new Set(s).add(vaga.id));
    try {
      await api.decidir(vaga.id, "abrir");
    } catch (e) {
      setErro(e as FalhaApi);
    }
  }, [vaga]);

  const decidir = useCallback(async (decisao: Decisao) => {
    if (!vaga || ocupado) return;
    setOcupado(true);
    setErro(null);
    try {
      await aoDecidir(vaga.id, decisao);
      // A lista encolheu por baixo: a mesma posição já é a próxima vaga.
      setPos((p) => Math.min(p, Math.max(0, total - 2)));
    } catch (e) {
      setErro(e as FalhaApi);
    } finally {
      setOcupado(false);
    }
  }, [vaga, ocupado, aoDecidir, total]);

  // Atalhos: só quando o foco não está num campo de texto — senão "a" e "e"
  // dentro de uma busca decidiriam vagas.
  useEffect(() => {
    const h = (ev: KeyboardEvent) => {
      const alvo = ev.target as HTMLElement | null;
      if (alvo && ["INPUT", "TEXTAREA", "SELECT"].includes(alvo.tagName)) return;
      const acao = ATALHOS[ev.key];
      if (!acao) return;
      ev.preventDefault();
      if (acao === "anterior") anterior();
      else if (acao === "proxima") proxima();
      else if (acao === "abrir") abrir();
      else decidir(acao);
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [anterior, proxima, abrir, decidir]);

  if (!vaga) {
    return (
      <div className="vazio">
        Nada precisa de você agora.
        <br />
        O coletor segue rodando; volte mais tarde.
      </div>
    );
  }

  const a = vaga.aderencia;
  const foiAberta = aberta.has(vaga.id) || vaga.status === "aberta";

  return (
    <>
      <div className="nav">
        <button onClick={anterior} disabled={pos === 0} title="← anterior">←</button>
        <span className="contador">{pos + 1} / {total}</span>
        <button onClick={proxima} disabled={pos >= total - 1} title="→ próxima">→</button>
      </div>

      {erro && <Alerta erro={erro.erro} />}

      <div className="cartao inbox">
        <div className="empresa">{vaga.empresa_exibicao}</div>
        <div className="titulo-vaga">{vaga.titulo}</div>
        <div className="meta">
          {[vaga.modalidade, vaga.localizacao].filter(Boolean).join(" · ") || vaga.plataforma}
        </div>

        {a && (
          <div className="concl">
            <div className={`ader ${vaga.score >= 85 ? "otima" : ""}`}>{a.titulo}</div>
            <div className="porque">{a.porque}</div>
            {a.atencao && <div className="atencao">⚠ {a.atencao}</div>}
          </div>
        )}

        <div className="checklist">
          <span className={vaga.tem_curriculo ? "ok" : ""}>
            Currículo {vaga.tem_curriculo ? "✓" : "—"}
          </span>
          <span className={vaga.tem_carta ? "ok" : ""}>Carta {vaga.tem_carta ? "✓" : "—"}</span>
          {foiAberta && <span className="selo neutro">aberta por você</span>}
        </div>

        <Evidencia vagaId={vaga.id} />
      </div>

      <div className="acoes">
        <button className="primario grande" onClick={abrir} disabled={ocupado}>
          Abrir e candidatar
        </button>
        <div className="linha">
          <button onClick={() => decidir("enviada")} disabled={ocupado}>Já me candidatei</button>
          <button onClick={() => decidir("adiar")} disabled={ocupado}>Depois</button>
          <button onClick={() => decidir("descartar")} disabled={ocupado}>Não é para mim</button>
        </div>
        <div className="atalhos">
          ← → navegar · Enter abrir · A candidatei · S depois · E não é para mim
        </div>
      </div>
    </>
  );
}

/** Nível 2, atrás de um clique: barras por eixo e tecnologias. Carrega só
 * quando aberto — é uma chamada por vaga, e ninguém abre em todas. */
function Evidencia({ vagaId }: { vagaId: number }) {
  const [aberto, setAberto] = useState(false);
  const [dossie, setDossie] = useState<Dossie | null>(null);

  useEffect(() => {
    setAberto(false);
    setDossie(null);
  }, [vagaId]);

  useEffect(() => {
    if (aberto && !dossie) api.dossie(vagaId).then(setDossie).catch(() => null);
  }, [aberto, dossie, vagaId]);

  return (
    <div className="evidencia">
      <a className="voltar" onClick={() => setAberto(!aberto)}>
        {aberto ? "▲ menos" : "▼ por que combina"}
      </a>
      {aberto && !dossie && <div className="meta">Carregando…</div>}
      {aberto && dossie && (
        <>
          {dossie.aderencia.eixos.map((e) => (
            <div className="eixo" key={e.nome}>
              <span>{e.nome}</span>
              <div className="barra"><i style={{ width: `${Math.round(e.fracao * 100)}%` }} /></div>
              <span className="num">{Math.round(e.fracao * 100)}%</span>
            </div>
          ))}
          <div className="chips">
            {dossie.aderencia.cobertas.slice(0, 10).map((t) => (
              <span className="selo neutro" key={t}>✓ {t.replace(" (equivalente)", "")}</span>
            ))}
          </div>
          {dossie.aderencia.faltam.length > 0 && (
            <div className="meta">Não cita: {dossie.aderencia.faltam.join(", ")}</div>
          )}
          {dossie.perguntas.length > 0 && (
            <div className="meta" style={{ marginTop: 6 }}>
              {dossie.perguntas.filter((p) => p.respondida).length} de {dossie.perguntas.length}{" "}
              perguntas do formulário o sistema responde.
            </div>
          )}
        </>
      )}
    </div>
  );
}
