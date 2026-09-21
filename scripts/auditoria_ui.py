"""Auditoria de UI/UX: captura + medições de DOM em todas as páginas e viewports.

    python run.py                                        # em outro terminal
    .venv\\Scripts\\python.exe scripts\\auditoria_ui.py [1600 390 ...]

Saída: data/screenshots/qa/<largura>/<pagina>.png (viewport e _full) e
data/screenshots/qa/medidas.json com, por página e viewport: tipografia
(tamanho/peso/contraste), ritmo vertical dos blocos, botões, inputs, cartões,
badges, expanders, elementos fora da tela, textos truncados, contraste < 4,5,
alvos < 24px, raios, azuis em uso e a sequência de foco por Tab.

Serve para o antes/depois de qualquer mudança de interface: rode, mude, rode
de novo e compare os JSONs. Foi assim que as duas sobreposições (Início e
Vagas > Detalhes) e a coluna de 195px do tablet foram encontradas.
"""
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "data" / "screenshots" / "qa"
VIEWPORTS = [(1440, 900), (1600, 900), (1920, 1080), (1024, 768), (390, 844), (360, 800)]
PAGINAS = ["", "vagas", "revisar", "candidaturas", "configuracoes", "documentos"]
so = sys.argv[1:]  # opcional: larguras a rodar

MEDIR = r"""
() => {
  const q = (s, r=document) => r.querySelector(s);
  const qa = (s, r=document) => [...r.querySelectorAll(s)];
  const cs = (e) => getComputedStyle(e);
  const rect = (e) => { const r = e.getBoundingClientRect(); return {x: Math.round(r.x), y: Math.round(r.y + window.scrollY), w: Math.round(r.width), h: Math.round(r.height)}; };
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && cs(e).visibility !== 'hidden'; };
  const lum = (rgb) => { const m = rgb.match(/[\d.]+/g); if (!m) return null; const [r,g,b] = m.slice(0,3).map(Number).map(v => { v/=255; return v<=0.03928? v/12.92 : Math.pow((v+0.055)/1.055,2.4); }); return 0.2126*r+0.7152*g+0.0722*b; };
  const bgOf = (e) => { let n = e; while (n && n !== document.body) { const c = cs(n).backgroundColor; if (c && !c.startsWith('rgba(0, 0, 0, 0)') && c !== 'transparent') return c; n = n.parentElement; } return cs(document.body).backgroundColor; };
  const contrast = (e) => { const l1 = lum(cs(e).color), l2 = lum(bgOf(e)); if (l1==null||l2==null) return null; const [a,b] = l1>l2?[l1,l2]:[l2,l1]; return Math.round(((a+0.05)/(b+0.05))*100)/100; };

  const out = {};
  out.scroll = {docW: document.documentElement.scrollWidth, clientW: document.documentElement.clientWidth,
                docH: document.documentElement.scrollHeight, clientH: document.documentElement.clientHeight};
  const main = q('[data-testid=stMainBlockContainer]');
  out.main = main ? Object.assign(rect(main), {padding: cs(main).padding, maxWidth: cs(main).maxWidth}) : null;
  const sb = q('[data-testid=stSidebar]');
  out.sidebar = sb ? Object.assign(rect(sb), {ariaExpanded: sb.getAttribute('aria-expanded')}) : null;

  const tipo = {};
  for (const [nome, sel] of [['h1','.pg-titulo'],['desc','.pg-desc'],['sec','.sec'],['vagaTitulo','.vaga-titulo'],['vagaEmpresa','.vaga-empresa'],['meta','.vaga-meta'],['metaLinha','.meta-linha'],['destaque','.destaque-titulo'],['lede','.lede'],['caption','[data-testid=stCaptionContainer] p'],['body','[data-testid=stMarkdownContainer] p'],['h4','h4'],['h3','h3'],['h2','h2']]) {
    const e = qa(sel).find(vis)
    if (!e) continue;
    const c = cs(e);
    tipo[nome] = {size: c.fontSize, weight: c.fontWeight, lh: c.lineHeight, color: c.color, contrast: contrast(e), n: qa(sel).filter(vis).length, texto: (e.textContent||'').trim().slice(0,50)};
  }
  out.tipo = tipo;
  out.headingsSemanticos = qa('h1,h2,h3,h4,h5,h6').filter(vis).map(h => h.tagName + ': ' + (h.textContent||'').trim().slice(0,40));

  const raiz = main && q('[data-testid=stVerticalBlock]', main);
  const blocos = [];
  if (raiz) for (const ch of raiz.children) {
    if (!vis(ch)) continue;
    const r = rect(ch);
    const primeiro = ch.querySelector('[data-testid]');
    const cls = ch.querySelector('.pg-titulo') ? 'pg' : ch.querySelector('.sec') ? 'sec:' + ch.querySelector('.sec').textContent.trim().slice(0,22) : (primeiro ? primeiro.getAttribute('data-testid') : ch.className.slice(0,20));
    blocos.push({y: r.y, h: r.h, tipo: cls, texto: (ch.textContent||'').trim().slice(0,40).replace(/\s+/g,' ')});
  }
  out.blocos = blocos.map((b,i) => Object.assign(b, {gapAntes: i ? b.y - (blocos[i-1].y + blocos[i-1].h) : null}));

  out.botoes = qa('button, a[data-testid^=stBaseLinkButton]').filter(vis).filter(b => (b.textContent||'').trim()).slice(0,60).map(b => { const c = cs(b); const r = rect(b); return {texto: (b.textContent||'').trim().slice(0,28), kind: b.getAttribute('kind') || b.getAttribute('data-testid') || '', h: r.h, w: r.w, pad: c.padding, radius: c.borderRadius, weight: c.fontWeight, size: c.fontSize, color: c.color, bg: c.backgroundColor, contrast: contrast(b), border: c.borderColor, min: Math.min(r.w, r.h)}; });
  out.botoesSemNome = qa('button').filter(vis).filter(b => !(b.textContent||'').trim() && !b.getAttribute('aria-label') && !b.getAttribute('title')).length;

  out.inputs = qa('input, textarea, [data-baseweb=select], [data-testid=stNumberInputContainer]').filter(vis).slice(0,30).map(i => { const r = rect(i); const c = cs(i); return {tag: i.tagName, type: i.getAttribute('type')||'', h: r.h, w: r.w, radius: c.borderRadius, border: c.borderColor, placeholder: i.getAttribute('placeholder')||'', ariaLabel: i.getAttribute('aria-label')||''}; });
  out.labelsColapsadas = qa('[data-testid=stWidgetLabel]').filter(l => cs(l).display === 'none' || cs(l).visibility === 'hidden' || cs(l).height === '0px').length;

  const cards = qa('[data-testid=stVerticalBlock]').filter(vis).filter(e => cs(e).borderTopWidth !== '0px' && cs(e).borderTopStyle !== 'none');
  out.cards = cards.slice(0,40).map(e => { const r = rect(e); const c = cs(e); return {h: r.h, w: r.w, pad: c.padding, radius: c.borderRadius, border: c.borderColor, shadow: c.boxShadow !== 'none', gap: c.gap, nested: cards.some(o => o !== e && o.contains(e))}; });
  out.cartaoHtml = qa('.cartao').filter(vis).map(e => { const r = rect(e); const c = cs(e); return {h: r.h, pad: c.padding, radius: c.borderRadius, border: c.borderColor}; });

  out.badges = qa('.bdg').filter(vis).slice(0,12).map(e => { const c = cs(e); return {texto: e.textContent.trim().slice(0,18), size: c.fontSize, weight: c.fontWeight, radius: c.borderRadius, color: c.color, bg: c.backgroundColor, contrast: contrast(e), h: rect(e).h}; });

  out.expanders = qa('[data-testid=stExpander]').filter(vis).slice(0,12).map(e => { const d = e.querySelector('details'); const s = e.querySelector('summary'); return {rotulo: s ? s.textContent.trim().slice(0,32) : '', open: d ? d.open : null, border: d ? cs(d).borderTopWidth : '', h: rect(e).h}; });

  const W = window.innerWidth;
  out.foraDaTela = qa('body *').filter(vis).filter(e => { const r = e.getBoundingClientRect(); return r.right > W + 1 && r.width < 3000; }).slice(0,8).map(e => (e.getAttribute('data-testid')||e.tagName) + ':' + (e.textContent||'').trim().slice(0,30));
  out.truncados = qa('body *').filter(vis).filter(e => { const c = cs(e); return c.overflow !== 'visible' && e.scrollWidth > e.clientWidth + 2 && e.children.length === 0 && (e.textContent||'').trim(); }).slice(0,10).map(e => ({t: (e.textContent||'').trim().slice(0,40), sw: e.scrollWidth, cw: e.clientWidth, ellipsis: cs(e).textOverflow}));
  out.contrasteBaixo = qa('p, span, div, a, label, caption, small').filter(vis).filter(e => e.children.length === 0 && (e.textContent||'').trim().length > 2).map(e => ({t: (e.textContent||'').trim().slice(0,36), c: contrast(e), size: cs(e).fontSize, color: cs(e).color})).filter(x => x.c !== null && x.c < 4.5).filter((x,i,arr) => arr.findIndex(y => y.color === x.color && y.size === x.size) === i).slice(0,10);
  out.alvosPequenos = qa('button, a, input[type=checkbox], [role=checkbox], summary').filter(vis).filter(e => { const r = e.getBoundingClientRect(); return Math.min(r.width, r.height) < 24; }).slice(0,8).map(e => ({t: (e.textContent||e.getAttribute('aria-label')||e.tagName).trim().slice(0,24), h: Math.round(e.getBoundingClientRect().height), w: Math.round(e.getBoundingClientRect().width)}));
  const icones = qa('[data-testid=stIconMaterial]').filter(vis).map(e => cs(e).fontSize);
  out.icones = [...new Set(icones)];
  const radii = {};
  qa('button, input, [data-baseweb=select], [data-testid=stVerticalBlock], details, .bdg, .cartao, a[data-testid^=stBaseLinkButton]').filter(vis).forEach(e => { const c = cs(e); if (c.borderTopWidth !== '0px' || c.backgroundColor !== 'rgba(0, 0, 0, 0)') { const r = c.borderRadius; radii[r] = (radii[r]||0)+1; } });
  out.radii = radii;
  const cores = {};
  qa('body *').filter(vis).forEach(e => { const c = cs(e); for (const v of [c.color, c.backgroundColor, c.borderTopColor]) { const m = v.match(/rgb\((\d+), (\d+), (\d+)/); if (m) { const r=+m[1], g=+m[2], b=+m[3]; if (b > r && b > g && (b - r) > 60) cores[v] = (cores[v]||0)+1; } } });
  out.azuis = cores;
  out.vazios = qa('.vazio').filter(vis).length;
  out.excecoes = qa('[data-testid=stException]').length;
  return out;
}
"""

FOCO = r"""
() => { const e = document.activeElement; if (!e || e === document.body) return null; const c = getComputedStyle(e);
  return {tag: e.tagName, testid: e.getAttribute('data-testid')||'', texto: (e.textContent||e.getAttribute('aria-label')||'').trim().slice(0,30), outline: c.outlineStyle + ' ' + c.outlineWidth + ' ' + c.outlineColor, shadow: c.boxShadow.slice(0,60)}
  }
"""


def esperar(p):
    p.wait_for_load_state("networkidle")
    for _ in range(20):
        p.wait_for_timeout(500)
        if not p.query_selector("[data-testid=stStatusWidget]") and p.query_selector("[data-testid=stMainBlockContainer]"):
            break
    p.wait_for_timeout(1500)
    p.evaluate("() => document.fonts && document.fonts.ready")


def abrir(p, pagina):
    for _ in range(30):
        try:
            p.goto(f"http://localhost:8501/{pagina}", wait_until="domcontentloaded", timeout=60000)
            break
        except Exception:
            time.sleep(2)
    esperar(p)


def teclado(p, n=8):
    seq = []
    for _ in range(n):
        p.keyboard.press("Tab")
        p.wait_for_timeout(120)
        seq.append(p.evaluate(FOCO))
    return seq


medidas = {}
with sync_playwright() as pw:
    b = pw.chromium.launch()
    for (w, h) in VIEWPORTS:
        if so and str(w) not in so:
            continue
        ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
        p = ctx.new_page()
        pasta = SAIDA / str(w)
        pasta.mkdir(parents=True, exist_ok=True)
        for pagina in PAGINAS:
            nome = pagina or "inicio"
            abrir(p, pagina)
            p.screenshot(path=str(pasta / f"{nome}.png"))
            p.screenshot(path=str(pasta / f"{nome}_full.png"), full_page=True)
            m = p.evaluate(MEDIR)
            if w >= 1440:
                m["foco"] = teclado(p, 8)
            medidas[f"{w}/{nome}"] = m
            print(w, nome, "docW", m["scroll"]["docW"], "clientW", m["scroll"]["clientW"], "docH", m["scroll"]["docH"], "exc", m["excecoes"], "main", m["main"] and m["main"]["w"], flush=True)

        if w in (1600, 390):
            inter = {}
            abrir(p, "vagas")
            try:
                p.click("text=Mais filtros")
                p.wait_for_timeout(800)
                p.screenshot(path=str(pasta / "vagas_mais_filtros.png"))
                p.click("[data-testid=stExpander] summary:has-text('Detalhes')", timeout=5000)
                p.wait_for_timeout(1500)
                p.screenshot(path=str(pasta / "vagas_detalhes.png"))
                inter["vagas_detalhes"] = p.evaluate(MEDIR)["expanders"][:3]
                sel = p.query_selector_all("[data-baseweb=select]")
                if len(sel) > 1:
                    sel[1].click()
                    p.wait_for_timeout(500)
                    p.click("li:has-text('80%+')", timeout=5000)
                    esperar(p)
                    p.screenshot(path=str(pasta / "vagas_filtro_ativo.png"))
            except Exception as exc:
                inter["vagas_erro"] = str(exc)[:200]
            abrir(p, "revisar")
            try:
                p.click("[data-testid=stExpander] summary:has-text('Filtros')", timeout=5000)
                p.wait_for_timeout(800)
                p.screenshot(path=str(pasta / "revisar_filtros.png"))
                carta = p.query_selector("[data-testid=stExpander] summary:has-text('carta')")
                if carta:
                    carta.click()
                    p.wait_for_timeout(800)
                    p.screenshot(path=str(pasta / "revisar_carta.png"), full_page=True)
                p.mouse.wheel(0, 900)
                p.wait_for_timeout(600)
                p.screenshot(path=str(pasta / "revisar_baixo.png"))
            except Exception as exc:
                inter["revisar_erro"] = str(exc)[:200]
            abrir(p, "candidaturas")
            try:
                sel = p.query_selector("[data-baseweb=select]")
                if sel:
                    sel.click()
                    p.wait_for_timeout(500)
                    p.screenshot(path=str(pasta / "candidaturas_select.png"))
                    p.keyboard.press("Escape")
                p.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                p.wait_for_timeout(800)
                p.screenshot(path=str(pasta / "candidaturas_historico.png"))
                p.evaluate("() => window.scrollTo(0, 0)")
            except Exception as exc:
                inter["cand_erro"] = str(exc)[:200]
            abrir(p, "configuracoes")
            try:
                for rot in ["Automação", "Plataformas", "LinkedIn", "Currículo", "Provedor de IA", "Notificações", "Documentos"]:
                    lab = p.query_selector(f".st-key-nav-config label:has-text('{rot}')")
                    if not lab:
                        continue
                    lab.click()
                    esperar(p)
                    p.screenshot(path=str(pasta / f"config_{rot.split()[0].lower()}.png"))
                    inter[f"config_{rot}"] = {"docH": p.evaluate("() => document.documentElement.scrollHeight"), "blocos": len(p.evaluate(MEDIR)["blocos"])}
                lab = p.query_selector(".st-key-nav-config label:has-text('Preferências')")
                if lab:
                    lab.click()
                    esperar(p)
                p.click("[data-testid=stExpander] summary:has-text('Editar (')", timeout=5000)
                p.wait_for_timeout(800)
                p.screenshot(path=str(pasta / "config_editar.png"))
                p.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                p.wait_for_timeout(600)
                p.screenshot(path=str(pasta / "config_rodape.png"))
            except Exception as exc:
                inter["config_erro"] = str(exc)[:200]
            abrir(p, "documentos")
            try:
                cb = p.query_selector("[data-testid=stDataFrame] canvas")
                if cb:
                    box = cb.bounding_box()
                    p.mouse.click(box["x"] + 18, box["y"] + 52)
                    p.wait_for_timeout(1500)
                    p.screenshot(path=str(pasta / "documentos_selecionado.png"), full_page=True)
            except Exception as exc:
                inter["doc_erro"] = str(exc)[:200]
            medidas[f"{w}/interacoes"] = inter
        ctx.close()
    b.close()

(SAIDA / "medidas.json").write_text(json.dumps(medidas, ensure_ascii=False, indent=1), encoding="utf-8")
print("ok", SAIDA / "medidas.json")
