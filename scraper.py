# scraper.py — 20‑abr‑2025 (v2 hot‑fix)
import re, json, urllib.parse, logging
from flask import Flask, request, jsonify
import cloudscraper

app = Flask(__name__)
log = logging.getLogger(__name__)

scraper = cloudscraper.create_scraper(
    browser={'browser': 'firefox', 'platform': 'windows', 'desktop': True}
)

# ---------- regex que captura os 3 blocos JS --------------------
RE_QUALITY = re.compile(r"var\s+dataQuality\s*=\s*(\[[^\]]+])", re.DOTALL)
RE_STOCK   = re.compile(r"var\s+cards_stock\s*=\s*(\[[^\]]+])", re.DOTALL)

# ---------- utils ----------------------------------------------
def _parse_price(raw: str | None) -> float | None:
    if not raw:
        return None
    txt = raw.replace('R$', '').strip()
    if ',' in txt:                       # pt‑BR
        txt = txt.replace('.', '').replace(',', '.')
    try:
        return float(txt)
    except ValueError:
        return None

# ---------- rotas ----------------------------------------------
@app.route("/")
def ping():
    return {"ok": True}

@app.route("/offers")
def offers():
    card = request.args.get("card", "").strip()
    if not card:
        return jsonify(error="card parameter required"), 400

    html_mkt = _fetch(card, show=1)      # Marketplace
    html_buy = _fetch(card, show=10)     # Buy‑list

    if not html_mkt and not html_buy:
        return jsonify(error="card not found", card=card), 404

    # ----- mapa dinâmico id->sigla (M, NM, …) -------------------
    quality_map = _build_quality_map(html_mkt or html_buy)
    if not quality_map:
        return jsonify(error="quality map not found"), 500

    # cria dicionários já com todas as siglas
    bucket_mkt = {sig: None for sig in quality_map.values()}
    bucket_buy = {sig: None for sig in quality_map.values()}

    if html_mkt:
        _fill_prices(html_mkt, quality_map, bucket_mkt, lowest=True)
    if html_buy:
        _fill_prices(html_buy, quality_map, bucket_buy, lowest=False)

    res = {
        "card": card,
        "marketplace": bucket_mkt,
        "buylist":     bucket_buy,
        "lowest_marketplace":
            min(p for p in bucket_mkt.values() if p is not None)
            if any(bucket_mkt.values()) else None,
        "highest_buylist":
            max(p for p in bucket_buy.values() if p is not None)
            if any(bucket_buy.values()) else None,
    }
    return jsonify(res)

# ---------- helpers --------------------------------------------
def _fetch(card: str, *, show: int) -> str | None:
    url = (
        "https://www.ligapokemon.com.br/"
        f"?view=cards/card&card={urllib.parse.quote(card)}&show={show}"
    )
    r = scraper.get(url, timeout=25)
    return r.text if r.status_code == 200 else None

def _build_quality_map(html: str | None) -> dict[str, str]:
    if not html:
        return {}
    m = RE_QUALITY.search(html)
    if not m:
        return {}
    arr = json.loads(m.group(1))
    return {str(it["id"]): it["acron"] for it in arr}

def _fill_prices(
    html: str,
    qmap: dict[str, str],
    bucket: dict[str, float | None],
    *,
    lowest: bool,
) -> None:
    m = RE_STOCK.search(html)
    if not m:
        return
    items = json.loads(m.group(1))
    for it in items:
        cond   = qmap.get(str(it.get("qualid")))
        price  = _parse_price(it.get("precoFinal") or it.get("preco"))
        if cond and price is not None:
            prev = bucket[cond]
            bucket[cond] = (
                price if prev is None
                else min(prev, price) if lowest
                else max(prev, price)
            )
