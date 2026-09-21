import { useEffect, useState } from "react";
import { api, type Checagem, type ErroApi, type Saude } from "./api";

/** Alerta do catálogo: título, o que houve, e o que fazer.
 *
 * A ação é a metade que importa para quem está cansado — um erro que só diz o
 * que aconteceu transfere o trabalho de volta. Por isso `acao` é obrigatória no
 * catálogo do Python e aparece sempre aqui. */
export function Alerta({ erro, tom = "erro" }: { erro: ErroApi; tom?: "erro" | "aviso" }) {
  return (
    <div className={`alerta ${tom}`}>
      <div className="titulo">{erro.titulo}</div>
      <div>{erro.detalhe}</div>
      <div className="acao">{erro.acao}</div>
    </div>
  );
}

/** Um ponto e uma frase. O detalhe abre no clique.
 *
 * Antes cada parte fora do ar falhava no seu canto — o banco virava traceback
 * na página, a API virava "não respondeu" no aviso da extensão, o schema
 * atrasado só aparecia no log. Aqui há um lugar para olhar. */
export function Estado({ aoMudar }: { aoMudar?: (s: Saude | null) => void }) {
  const [saude, setSaude] = useState<Saude | null>(null);
  const [falhou, setFalhou] = useState(false);
  const [aberto, setAberto] = useState(false);

  useEffect(() => {
    let vivo = true;
    const ler = () =>
      api
        .saude()
        .then((s) => {
          if (!vivo) return;
          setSaude(s);
          setFalhou(false);
          aoMudar?.(s);
        })
        .catch(() => {
          if (!vivo) return;
          setFalhou(true);
          aoMudar?.(null);
        });
    ler();
    // A cada 20s: o painel fica aberto ao lado do formulário por muito tempo, e
    // um estado congelado de dez minutos atrás engana mais do que ajuda.
    const t = setInterval(ler, 20000);
    return () => {
      vivo = false;
      clearInterval(t);
    };
  }, [aoMudar]);

  if (falhou) {
    return (
      <Alerta
        erro={{
          codigo: "api-fora",
          titulo: "O AI Job Applier não está rodando",
          detalhe: "O serviço local não respondeu.",
          acao: "Rode `python run.py` na pasta do projeto.",
          auto: null,
          familia: "ambiente",
        }}
      />
    );
  }
  if (!saude) return <div className="estado"><span className="ponto" />Verificando…</div>;

  const bloqueios = saude.checagens.filter((c) => !c.ok && !c.aviso);
  const avisos = saude.checagens.filter((c) => !c.ok && c.aviso);
  const tom = bloqueios.length ? "erro" : avisos.length ? "aviso" : "ok";
  const frase = bloqueios.length
    ? `${bloqueios.length} coisa(s) impedem de trabalhar`
    : avisos.length
      ? `${avisos.length} aviso(s)`
      : "Tudo pronto";

  return (
    <>
      <div className="estado" onClick={() => setAberto(!aberto)}>
        <span className={`ponto ${tom}`} />
        {frase}
        <span style={{ marginLeft: "auto" }}>{aberto ? "▲" : "▼"}</span>
      </div>
      {bloqueios.map((c) => c.erro && <Alerta key={c.nome} erro={c.erro} />)}
      {aberto &&
        avisos.map((c) => c.erro && <Alerta key={c.nome} erro={c.erro} tom="aviso" />)}
      {aberto && <Checagens itens={saude.checagens} />}
    </>
  );
}

function Checagens({ itens }: { itens: Checagem[] }) {
  return (
    <div className="cartao">
      {itens.map((c) => (
        <div key={c.nome} className="meta" style={{ marginTop: 4 }}>
          <span className={`ponto ${c.ok ? "ok" : c.aviso ? "aviso" : "erro"}`}
                style={{ display: "inline-block", marginRight: 6 }} />
          {c.nome}
          {c.detalhe ? ` — ${c.detalhe}` : ""}
        </div>
      ))}
    </div>
  );
}
