# scraper.py  – 20‑abr‑2025
import re, json, urllib.parse, logging, os
from flask import Flask, request, jsonify
import cloudscraper

app = Flask(__name__)
log = logging.getLogger(__name__)

scraper = cloudscraper.create_scraper(
    browser={'browser': 'firefox', 'platform': 'windows', 'desktop': True}
)

# ---------- util -------------------------------------------------
def _parse_price(raw: str | None) -> float | None:
    """Converte '1.099,99' -> 1099.99   /   '999,95' -> 999.95"""
    if not raw:
        return None
    txt = raw.replace('R$', '').strip()
    if ',' in txt:                       # há separador decimal brasileiro
        txt = txt.replace('.', '').replace(',', '.')
    return float(txt)

# ---------- mapeamento de condições -----------------------------
QUALITY = {           # id  ->  rótulo
    "1": "M",
    "2": "NM",
    "3": "SP",
    "4": "MP",
    "5": "HP",
    "6": "D",
}

# ---------- rotas -----------------------------------------------
@app.route("/")
def ping():
    return {"ok": True}

@app.route("/offers")
def offers():
    card = request.args.get("card", "").strip()
    if not card:
        return jsonify(error="card parameter required"), 400

    result = {
        "card": card,
        "marketplace": {q: None for q in QUALITY.values()},
        "buylist":     {q: None for q in QUALITY.values()},
    }

    # marketplace  (show=1) – menor preço por condição
    html = _fetch(card, show=1)
    if html:
        _fill_marketplace(html, result["marketplace"])

    # buy‑list (show=10) – maior preço por condição
    html = _fetch(card, show=10)
    if html:
        _fill_buylist(html, result["buylist"])

    # agregados que sua planilha usa
    mp_vals = [p for p in result["marketplace"].values() if p]
    bl_vals = [p for p in result["buylist"].values() if p]

    result["lowest_marketplace"] = min(mp_vals) if mp_vals else None
    result["highest_buylist"]   = max(bl_vals) if bl_vals else None

    return jsonify(result)

# ---------- helpers ---------------------------------------------
def _fetch(card: str, *, show: int) -> str | None:
    url = (
        "https://www.ligapokemon.com.br/"
        f"?view=cards/card&card={urllib.parse.quote(card)}&show={show}"
    )
    r = scraper.get(url, timeout=25)
    return r.text if r.status_code == 200 else None

RE_STOCK = re.compile(r"var\s+cards_stock\s*=\s*(\[[^\]]+\]);", re.DOTALL)

def _fill_marketplace(html: str, bucket: dict[str, float | None]) -> None:
    m = RE_STOCK.search(html)
    if not m:
        return
    items = json.loads(m.group(1))
    for it in items:
        cond = QUALITY.get(str(it.get("qualid")))
        price = _parse_price(it.get("precoFinal") or it.get("preco"))
        if cond and price is not None:
            bucket[cond] = price if bucket[cond] is None else min(bucket[cond], price)

def _fill_buylist(html: str, bucket: dict[str, float | None]) -> None:
    m = RE_STOCK.search(html)
    if not m:
        return
    items = json.loads(m.group(1))
    for it in items:
        base = _parse_price(it.get("base"))
        qmap = it.get("q", {})
        if base is None or not isinstance(qmap, dict):
            continue
        for qid, perc in qmap.items():
            cond = QUALITY.get(str(qid))
            if not cond:
                continue
            buy_price = round(base * perc / 100, 2)
            prev = bucket[cond]
            bucket[cond] = buy_price if prev is None else max(prev, buy_price)
