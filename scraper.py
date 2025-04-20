# scraper.py  – 20 Abr 2025
import re, json, urllib.parse, logging
from flask import Flask, request, jsonify
import cloudscraper

app = Flask(__name__)
log = logging.getLogger(__name__)

scraper = cloudscraper.create_scraper(
    browser={"browser": "firefox", "platform": "windows", "desktop": True}
)

# --- util -------------------------------------------------------
def _parse_price(txt: str | None) -> float | None:
    if not txt:
        return None
    txt = txt.replace("R$", "").strip()
    if "," in txt:
        txt = txt.replace(".", "").replace(",", ".")
    try:
        return float(txt)
    except ValueError:
        return None

QUALITY = {
    "1": "M",   # Mint
    "2": "NM",  # Near‑Mint
    "3": "SP",
    "4": "MP",
    "5": "HP",
    "6": "D",
}

VAR_REGEX = re.compile(r"var\s+cards_stock\s*=\s*(\[[\s\S]*?\]);")

# ----------------------------------------------------------------
@app.route("/offers")
def offers():
    card = request.args.get("card", "").strip()
    if not card:
        return jsonify(error="card parameter required"), 400

    out = {
        "card": card,
        "marketplace": {q: None for q in QUALITY.values()},
        "buylist":     {q: None for q in QUALITY.values()},
    }

    _scrape(card, 1, out["marketplace"], lowest=True)   # marketplace
    _scrape(card,10, out["buylist"],      lowest=False) # buylist

    # agregados para facilitar a planilha
    mp_vals = [v for v in out["marketplace"].values() if v is not None]
    bl_vals = [v for v in out["buylist"].values()      if v is not None]
    out["lowest_marketplace"] = min(mp_vals) if mp_vals else None
    out["highest_buylist"]    = max(bl_vals) if bl_vals else None
    return jsonify(out)

# ----------------------------------------------------------------
def _scrape(card: str, show: int, bucket: dict, *, lowest: bool):
    url = (
        "https://www.ligapokemon.com.br/"
        f"?view=cards/card&card={urllib.parse.quote(card)}&show={show}"
    )
    r = scraper.get(url)
    if r.status_code != 200:
        log.warning("LigaPokemon devolveu %s em %s", r.status_code, url)
        return

    m = VAR_REGEX.search(r.text)
    if not m:
        return
    items = json.loads(m.group(1))

    for it in items:
        # --- marketplace (tem 'preco' ou 'precoFinal') -------------
        raw = it.get("precoFinal") or it.get("preco")
        qualid = str(it.get("qualid") or "")
        cond   = QUALITY.get(qualid)
        price  = _parse_price(raw)

        # --- buylist (não tem preco, mas tem base + q{}) -----------
        if price is None and it.get("base") and isinstance(it.get("q"), dict):
            base = _parse_price(it["base"])
            for q_id, pct in it["q"].items():
                cond2 = QUALITY.get(str(q_id))
                if cond2 and base:
                    price2 = round(base * pct / 100, 2)
                    _store(bucket, cond2, price2, lowest)
            continue

        if cond and price is not None:
            _store(bucket, cond, price, lowest)

def _store(bucket: dict, cond: str, value: float, lowest: bool):
    current = bucket[cond]
    if current is None:
        bucket[cond] = value
    else:
        bucket[cond] = min(current, value) if lowest else max(current, value)
