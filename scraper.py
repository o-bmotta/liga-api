# scraper.py  – versão 2025‑04‑20
import re, json, urllib.parse, logging
from flask import Flask, request, jsonify, render_template
import cloudscraper

app = Flask(__name__)
log = logging.getLogger(__name__)

scraper = cloudscraper.create_scraper(
    browser={'browser': 'firefox', 'platform': 'windows', 'desktop': True}
)

# --- util -------------------------------------------------------
def _parse_price(raw: str) -> float | None:
    """
    Converte '1.099,99'  →  1099.99   e  '999,95' → 999.95
    """
    if not raw:
        return None
    txt = raw.replace('R$', '').strip()
    if ',' in txt:
        txt = txt.replace('.', '').replace(',', '.')
    return float(txt)

# --- mapeamento de condição ------------------------------------
QUALITY = {     # id -> rótulo apresentado
    "1": "M",   # Mint / Nova
    "2": "NM",  # Near‑Mint
    "3": "SP",
    "4": "MP",
    "5": "HP",
    "6": "D",
}

# --- rotas ------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/offers")
def offers():
    card = request.args.get("card", "").strip()
    if not card:
        return jsonify(error="card parameter required"), 400

    result = {
        "card": card,
        "marketplace": {q: None for q in QUALITY.values()},
        "buylist":      {q: None for q in QUALITY.values()},
    }

    # Marketplace  (show=1)
    html_mkt = _fetch(card, show=1)
    if html_mkt:
        _fill_prices(html_mkt, result["marketplace"], lowest=True)

    # Buy‑list     (show=10)
    html_buy = _fetch(card, show=10)
    if html_buy:
        _fill_prices(html_buy, result["buylist"], lowest=False)

    # campos agregados que sua planilha usa
    result["lowest_marketplace"] = min(
        p for p in result["marketplace"].values() if p is not None
    ) if any(result["marketplace"].values()) else None

    result["highest_buylist"] = max(
        p for p in result["buylist"].values() if p is not None
    ) if any(result["buylist"].values()) else None

    return jsonify(result)

# --- helpers ----------------------------------------------------
def _fetch(card_name: str, show: int) -> str | None:
    url = (
        "https://www.ligapokemon.com.br/"
        f"?view=cards/card&card={urllib.parse.quote(card_name)}&show={show}"
    )
    r = scraper.get(url)
    return r.text if r.status_code == 200 else None

VAR_CARDS_REGEX = re.compile(r"var\s+cards_stock\s*=\s*(\[[^\]]+\]);", re.DOTALL)

def _fill_prices(html: str, bucket: dict, *, lowest: bool):
    """
    Atualiza o dict bucket → condição:preço
    lowest=True   → armazena o menor preço para cada condição.
    lowest=False  → armazena o MAIOR  preço (buy‑list).
    """
    m = VAR_CARDS_REGEX.search(html)
    if not m:
        return
    data = json.loads(m.group(1))

    for item in data:
        # precoFinal preferencial, senão preco
        raw = item.get("precoFinal") or item.get("preco")
        price = _parse_price(raw)
        qualid = str(item.get("qualid") or item.get("q") or "")
        cond = QUALITY.get(qualid)
        if price is None or cond is None:
            continue

        existing = bucket[cond]
        if existing is None:
            bucket[cond] = price
        else:
            bucket[cond] = min(existing, price) if lowest else max(existing, price)
