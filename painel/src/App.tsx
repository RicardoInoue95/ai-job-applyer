import { useCallback, useEffect, useState } from "react";
import { api, FalhaApi, type Decisao, type Dossie, type Vaga } from "./api";
import { Alerta, Estado } from "./Estado";
import { Inbox } from "./Inbox";

/** O painel tem dois estados: a fila do dia, e uma vaga aberta.
 *
 * Não há navegação além disso de propósito. O painel vive ao lado do formulário
 * e é usado com a atenção dividida — cada nível a mais é um lugar onde se perde
 * o fio de onde estava. */
export default function App() {
  const [vagas, setVagas] = useState<Vaga[] | null>(null);
  const [aberta, setAberta] = useState<number | null>(null);
  const [erro, setErro] = useState<FalhaApi | null>(null);
  const [tudo, setTudo] = useState(false);

  const carregar = useCallback(() => {
    setErro(null);
    const pedido = tudo ? api.acervo() : api.fila();
    pedido
      .then((r) => setVagas(r.vagas))
      .catch((e: FalhaApi) => {
        setVagas([]);
        setErro(e);
      });
  }, [tudo]);

  useEffect(carregar, [carregar]);

  if (aberta !== null) {
    return (
      <Detalhe
        vagaId={aberta}
        aoVoltar={() => {
          setAberta(null);
          carregar();
        }}
      />
    );
  }

  // Decidir tira a vaga da lista local na hora: esperar o backend e recarregar
  // faria a inbox piscar a cada decisão, e a próxima vaga demoraria a aparecer.
  const decidir = useCallback(async (vagaId: number, decisao: Decisao) => {
    await api.decidir(vagaId, decisao);
    setVagas((atual) => (atual ?? []).filter((v) => v.id !== vagaId));
  }, []);

  return (
    <>
      <div className="topo">
        <h1>AI Job Applier</h1>
        <button className="discreto" onClick={() => setTudo(!tudo)}>
          {tudo ? "Só o que precisa de você" : "Ver a fila inteira"}
        </button>
      </div>
      <p className="sub">
        {tudo
          ? "Toda a fila, da melhor para a pior."
          : vagas && vagas.length
            ? `${vagas.length} precisam de você. A IA já preparou tudo.`
            : "A IA encontrou e preparou. Falta a sua decisão."}
      </p>
      <Estado />
      {erro && <Alerta erro={erro.erro} />}

      {vagas === null && <div className="vazio">Carregando…</div>}

      {vagas && !tudo && <Inbox vagas={vagas} aoDecidir={decidir} />}

      {vagas && tudo && vagas.length === 0 && !erro && (
        <div className="vazio">Nada na fila.</div>
      )}
      {vagas && tudo && vagas.map((v) => (
        <div key={v.id} className="cartao" onClick={() => setAberta(v.id)}
             style={{ cursor: "pointer" }}>
          <div className="empresa">{v.empresa_exibicao}</div>
          <div className="vaga">{v.titulo}</div>
          <div className="meta">
            <span className="selo">{v.aderencia?.titulo ?? `${v.score.toFixed(0)}%`}</span>{" "}
            {v.plataforma} · {v.modalidade || "modalidade não informada"}
            {v.localizacao ? ` · ${v.localizacao}` : ""}
            {!v.tem_curriculo && <> · <span className="selo neutro">sem dossiê</span></>}
          </div>
        </div>
      ))}
    </>
  );
}

function Detalhe({ vagaId, aoVoltar }: { vagaId: number; aoVoltar: () => void }) {
  const [dossie, setDossie] = useState<Dossie | null>(null);
  const [erro, setErro] = useState<FalhaApi | null>(null);
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    api.dossie(vagaId).then(setDossie).catch((e: FalhaApi) => setErro(e));
  }, [vagaId]);

  const decidir = (decisao: "enviada" | "descartar" | "adiar") => {
    setOcupado(true);
    api
      .decidir(vagaId, decisao)
      .then(aoVoltar)
      .catch((e: FalhaApi) => {
        setErro(e);
        setOcupado(false);
      });
  };

  if (erro) {
    return (
      <>
        <a className="voltar" onClick={aoVoltar}>← voltar</a>
        <Alerta erro={erro.erro} />
      </>
    );
  }
  if (!dossie) return <div className="vazio">Carregando…</div>;

  const { vaga, perguntas } = dossie;
  const pendentes = perguntas.filter((p) => !p.respondida);

  return (
    <>
      <a className="voltar" onClick={aoVoltar}>← voltar para a fila</a>
      <h1 style={{ marginTop: 10 }}>{vaga.empresa_exibicao}</h1>
      <p className="sub">{vaga.titulo}</p>
      <div className="meta" style={{ marginBottom: 12 }}>
        <span className="selo">{vaga.score.toFixed(0)}% de aderência</span>{" "}
        {vaga.plataforma} · {vaga.modalidade || "modalidade não informada"}
        {dossie.manuscrito && <> · <span className="selo">escrito à mão</span></>}
      </div>

      <div className="linha">
        <button className="primario" onClick={() => window.open(vaga.link, "_blank")}>
          Abrir a vaga
        </button>
        {vaga.tem_curriculo && (
          <button onClick={() => window.open(api.curriculoUrl(vaga.id), "_blank")}>
            Currículo
          </button>
        )}
      </div>

      <h2>Perguntas do formulário</h2>
      {perguntas.length === 0 ? (
        <div className="cartao meta">
          {dossie.situacao_ficha === "ok"
            ? "Sem perguntas extras. Currículo e envio, só."
            : "Não deu para ler o formulário desta vaga daqui — abra e confira."}
        </div>
      ) : (
        <div className="cartao">
          <div className="meta" style={{ marginBottom: 6 }}>
            {perguntas.length - pendentes.length} de {perguntas.length} o sistema
            responde. {pendentes.length > 0 && `${pendentes.length} ficam para você.`}
          </div>
          {perguntas.map((p, i) => (
            <div className="pergunta" key={i}>
              <div className="txt">
                {p.eliminatoria && <span className="selo">eliminatória</span>}{" "}
                {p.pergunta}
              </div>
              <div className="resp">
                {p.respondida ? p.resposta : "— você responde, e o sistema guarda"}
              </div>
            </div>
          ))}
        </div>
      )}

      {dossie.carta && (
        <>
          <h2>Carta</h2>
          <pre className="carta">{dossie.carta}</pre>
          <button
            style={{ width: "100%", marginTop: 6 }}
            onClick={() => navigator.clipboard.writeText(dossie.carta)}
          >
            Copiar carta
          </button>
        </>
      )}

      <h2>Quando terminar</h2>
      {/* "Enviei" não marca como confirmada: quem afirma é ele, e o sistema não
          viu a página de confirmação. Falso "enviada" bloqueia a vaga para
          sempre em `guard.ja_candidatado`. */}
      <div className="linha">
        <button className="primario" disabled={ocupado} onClick={() => decidir("enviada")}>
          Enviei
        </button>
        <button disabled={ocupado} onClick={() => decidir("adiar")}>Depois</button>
        <button disabled={ocupado} onClick={() => decidir("descartar")}>
          Não é para mim
        </button>
      </div>
    </>
  );
}
