import json, logging, re, urllib.parse
import cloudscraper
from flask import Flask, jsonify, request

app = Flask(__name__)
log = logging.getLogger(__name__)

# 1) bypass Cloudflare
scraper = cloudscraper.create_scraper(
    browser={"browser": "firefox", "platform": "windows", "desktop": True}
)

# 2) regex para cards_stock
CARDS_STOCK_RE = re.compile(r"var\s+cards_stock\s*=\s*(\[[^\]]+]);", re.DOTALL)

# 3) mapeamento de condições (inclui "1": "M")
CONDITION = {
    "1": "M",   # Mint
    "2": "NM",  # Near‑Mint
    "3": "SP",
    "4": "MP",
    "5": "HP",
    "6": "D",
}

def parse_price(txt: str | None) -> float | None:
    if not txt:
        return None
    s = txt.replace("R$", "").strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None

@app.route("/offers")
def offers():
    raw = request.args.get("card", "").strip()
    if not raw:
        return jsonify(error="card parameter required"), 400
    card = urllib.parse.unquote(raw)

    result = {
        "card": card,
        "marketplace_prices": {v: None for v in CONDITION.values()},
        "buylist_best_price": None,
    }

    # marketplace (show=1)
    html_mkt = fetch(card, show=1)
    if html_mkt:
        mp = extract_prices(html_mkt, lowest=True)
        result["marketplace_prices"].update(mp)

    # buy‑list (show=10)
    html_buy = fetch(card, show=10)
    if html_buy:
        bl = extract_prices(html_buy, lowest=False)
        # pegar apenas o maior preço de compra
        result["buylist_best_price"] = max(bl.values(), default=None)

    # menor preço do marketplace ou, se não, da buy‑list
    mp_vals = [p for p in result["marketplace_prices"].values() if p is not None]
    result["low"] = min(mp_vals) if mp_vals else result["buylist_best_price"]

    return jsonify(result)

def fetch(card_name: str, *, show: int) -> str | None:
    url = (
        "https://www.ligapokemon.com.br/?view=cards/card"
        f"&card={urllib.parse.quote(card_name)}&show={show}"
    )
    try:
        r = scraper.get(url, timeout=20)
        return r.text if r.status_code == 200 else None
    except Exception as e:
        log.warning(f"Erro ao baixar {url}: {e}")
        return None

def extract_prices(html: str, *, lowest: bool) -> dict[str, float]:
    out: dict[str, float] = {}
    m = CARDS_STOCK_RE.search(html)
    if not m:
        return out
    try:
        stock = json.loads(m.group(1))
    except json.JSONDecodeError:
        return out

    for item in stock:
        cond = CONDITION.get(str(item.get("qualid") or ""))
        if not cond:
            continue
        raw = item.get("precoFinal") or item.get("preco") or item.get("base")
        price = parse_price(raw)
        if price is None:
            continue
        prev = out.get(cond)
        if prev is None:
            out[cond] = price
        else:
            # menor para marketplace, maior para buy‑list
            out[cond] = min(prev, price) if lowest else max(prev, price)
    return out

@app.errorhandler(404)
def not_found(e): return jsonify(error="not_found"), 404
@app.errorhandler(500)
def server_error(e): return jsonify(error="internal_server_error"), 500
