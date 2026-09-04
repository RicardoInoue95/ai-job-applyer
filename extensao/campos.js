// Leitura dos campos do formulário. SÓ LÊ — não decide nada.
//
// A decisão sobre o que escrever fica no Python (`jobapplier/api.py` →
// `_auto_answer`), que tem a política de resposta com teste: veto de pergunta
// sensível, recusa de pergunta composta, régua de pretensão. Reimplementar
// qualquer pedaço disso aqui criaria uma segunda fonte de verdade em
// JavaScript, e ela divergiria — é o erro que este projeto passou o dia
// consertando em outros lugares.
//
// O rótulo é a parte difícil, e varia por plataforma:
//   Gupy        <legend> do fieldset (radio), ou atributo label= (select)
//   Greenhouse  <label for=id>
//   Lever       <label> ancestral, ou aria-label
//
// O `id` NUNCA serve de âncora: na Gupy é `react-aria2452456307-25`, regerado
// a cada render. O que persiste é o `name`.

// A etapa de perguntas da empresa na Gupy — a que pede RG, nome da mãe e
// pretensão — não tem <label for>, <legend>, label= nem aria-labelledby. O
// enunciado é um <h3> irmão anterior, dentro do bloco que envolve o campo:
//
//   <div>
//     <h3>6. Pretensão Salarial *</h3>
//     <div class="form-group"><textarea name="Pretensão Salarial">
//
// Ancoro na relação estrutural, não na classe: `sc-bklklh` é hash de
// styled-components, regerado a cada build, e quebraria como o `react-aria` do
// id. Sobe até seis níveis e para no PRIMEIRO ancestral que tenha cabeçalho —
// o mais próximo é o da pergunta; ir além pegaria o título da seção.
function enunciadoAcima(campo) {
  let no = campo.parentElement;
  for (let salto = 0; no && salto < 6; no = no.parentElement, salto++) {
    for (const titulo of no.querySelectorAll("h1,h2,h3,h4,h5,h6,legend")) {
      const antes = titulo.compareDocumentPosition(campo)
        & Node.DOCUMENT_POSITION_FOLLOWING;
      const texto = titulo.textContent.trim();
      if (antes && texto) {
        // "7. Já trabalhou…?  *" → "Já trabalhou…?"
        return texto.replace(/^\d+[.)]\s*/, "").replace(/\s*\*+\s*$/, "").trim();
      }
    }
  }
  return "";
}

function rotuloDe(campo) {
  const fieldset = campo.closest("fieldset");
  const legend = fieldset && fieldset.querySelector("legend");
  if (legend && legend.textContent.trim()) return legend.textContent.trim();

  const proprio = campo.getAttribute("label") || campo.getAttribute("aria-label");
  if (proprio) return proprio.trim();

  if (campo.id) {
    const marcado = document.querySelector(`label[for="${CSS.escape(campo.id)}"]`);
    if (marcado && marcado.textContent.trim()) return marcado.textContent.trim();
  }

  // Para radio e checkbox o <label> ancestral é o texto da OPÇÃO, nunca a
  // pergunta. Foi assim que "UOL", "PagBank" e "UOL EdTech" chegaram ao aviso
  // como se fossem três perguntas — eram as opções de uma só.
  if (campo.type === "radio" || campo.type === "checkbox") {
    const acima = enunciadoAcima(campo);
    if (acima) return acima;
  } else {
    const ancestral = campo.closest("label");
    if (ancestral && ancestral.textContent.trim()) return ancestral.textContent.trim();
  }

  const rotulado = campo.getAttribute("aria-labelledby");
  if (rotulado) {
    const alvo = document.getElementById(rotulado);
    if (alvo && alvo.textContent.trim()) return alvo.textContent.trim();
  }
  return enunciadoAcima(campo);
}

// Radio agrupa por `name` igual. A Gupy numera cada checkbox do mesmo grupo —
// `checkbox-2800745-0`, `-1`, `-2` — então o `name` sozinho não agrupa nada, e
// cada opção virava uma pergunta separada.
function grupoDe(campo) {
  const nome = campo.name || "";
  const numerado = nome.match(/^(.*?)-(\d+)$/);
  return numerado ? numerado[1] : nome;
}

function tipoDe(campo) {
  const tag = campo.tagName.toLowerCase();
  if (tag === "textarea") return "textarea";
  if (tag === "select") return "multi_value_single_select";
  const t = (campo.type || "text").toLowerCase();
  if (t === "radio" || t === "checkbox") return "multi_value_single_select";
  if (t === "number") return "number";
  return "input_text";
}

function opcoesDe(campo) {
  if (campo.tagName.toLowerCase() === "select") {
    return [...campo.options].map((o) => ({ label: o.textContent.trim(), value: o.value }));
  }
  if (campo.type === "radio" || campo.type === "checkbox") {
    const grupo = grupoDe(campo);
    const irmaos = [...document.querySelectorAll(
      'input[type="radio"], input[type="checkbox"]')]
      .filter((i) => grupoDe(i) === grupo);
    // O `seletor` da opção vai junto porque o checkbox da Gupy não tem `value`:
    // todos valem "on", e casar por valor marcaria o primeiro da lista.
    return irmaos.map((r) => ({
      label: rotuloDeOpcao(r), value: r.value,
      seletor: r.name ? `[name="${r.name}"]` : "",
    }));
  }
  return [];
}

// O texto da opção de um radio fica no <label> que o envolve, não no <legend>
// — que é a pergunta. Confundir os dois faria toda opção herdar o enunciado.
function rotuloDeOpcao(radio) {
  const proprio = radio.closest("label");
  if (proprio) {
    const texto = proprio.textContent.trim();
    if (texto) return texto;
  }
  return radio.getAttribute("aria-label") || radio.value || "";
}

// Campos que a extensão não toca: já preenchidos pelo próprio site, ocultos, ou
// desabilitados. Sobrescrever o que a plataforma preencheu é como o currículo
// errado ia anexado no LinkedIn — dado velho por cima de dado certo.
function preenchivel(campo) {
  if (campo.disabled || campo.readOnly) return false;
  if (campo.type === "hidden" || campo.type === "submit" || campo.type === "button") return false;
  if (campo.type === "file") return false;
  if (campo.offsetParent === null && campo.type !== "radio") return false;
  if (campo.type === "radio" || campo.type === "checkbox") return true;
  return !String(campo.value || "").trim();
}

function lerCampos() {
  const vistos = new Set();
  const saida = [];
  for (const campo of document.querySelectorAll("input, select, textarea")) {
    if (!preenchivel(campo)) continue;
    const label = rotuloDe(campo);
    if (!label) continue;
    // Agrupa pelo grupo, não pelo `name`: senão os cinco checkboxes de uma
    // pergunta só viram cinco perguntas com o mesmo enunciado.
    const grupo = grupoDe(campo);
    const chave = `${label}|${grupo || campo.id}`;
    if (vistos.has(chave)) continue;
    vistos.add(chave);
    const agrupado = grupo !== campo.name;
    saida.push({
      label,
      tipo: tipoDe(campo),
      opcoes: opcoesDe(campo),
      seletor: agrupado ? `[name^="${grupo}-"]`
        : (campo.name ? `[name="${campo.name}"]` : `#${campo.id}`),
    });
  }
  return saida;
}

if (typeof module !== "undefined") {
  module.exports = { rotuloDe, tipoDe, opcoesDe, preenchivel, lerCampos };
}
