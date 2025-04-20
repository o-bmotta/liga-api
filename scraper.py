import json, logging, re, urllib.parse
import cloudscraper
from flask import Flask, jsonify, request

app = Flask(__name__)
log = logging.getLogger(__name__)
scraper = cloudscraper.create_scraper(
    browser={"browser": "firefox", "platform": "windows", "desktop": True}
)

# regex para cards_stock e cards_editions
CARDS_STOCK_RE    = re.compile(r"var\s+cards_stock\s*=\s*(\[[^\]]+\]);", re.DOTALL)
CARDS_EDITIONS_RE = re.compile(r"var\s+cards_editions\s*=\s*(\[[^\]]+\]);", re.DOTALL)

# qualid → condições
CONDITION_MAP = {
    "1": ["M", "NM"],  # Mint preenche M e NM
    "2": ["NM"],
    "3": ["SP"],
    "4": ["MP"],
    "5": ["HP"],
    "6": ["D"],
}

def parse_price(txt: str | None) -> float | None:
    """Converte '1.099,99'→1099.99 e '3500.00'→3500.0"""
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

    # buckets iniciais
    mp = {c: None for c in ["M","NM","SP","MP","HP","D"]}
    bl = {c: None for c in ["M","NM","SP","MP","HP","D"]}

    # marketplace (show=1) → menor por condição
    html = fetch(card, show=1)
    if html:
        fill(html, mp, lowest=True)
        # fallback editions se mp ainda vazio (ex: Metagross)
        if all(v is None for v in mp.values()):
            fallback_editions(html, mp)

    # buylist (show=10) → maior por condição
    html = fetch(card, show=10)
    if html:
        fill(html, bl, lowest=False)

    # build result
    best_bl = max((p for p in bl.values() if p is not None), default=None)
    lows = [p for p in mp.values() if p is not None]
    low = min(lows) if lows else best_bl

    return jsonify({
        "card": card,
        "marketplace_prices": mp,
        "buylist_best_price": best_bl,
        "low": low
    })

def fetch(card: str, *, show: int) -> str | None:
    url = (
        "https://www.ligapokemon.com.br/?view=cards/card"
        f"&card={urllib.parse.quote(card)}&show={show}"
    )
    try:
        r = scraper.get(url, timeout=20)
        return r.text if r.status_code == 200 else None
    except Exception as e:
        log.warning(f"Erro ao baixar {url}: {e}")
        return None

def fill(html: str, bucket: dict, *, lowest: bool):
    """Preenche bucket usando var cards_stock."""
    m = CARDS_STOCK_RE.search(html)
    if not m:
        return
    try:
        stock = json.loads(m.group(1))
    except json.JSONDecodeError:
        return

    for itm in stock:
        qual = str(itm.get("qualid", ""))
        conds = CONDITION_MAP.get(qual)
        if not conds:
            continue
        raw = itm.get("precoFinal") or itm.get("preco") or itm.get("base")
        price = parse_price(raw)
        if price is None:
            continue
        for c in conds:
            prev = bucket.get(c)
            bucket[c] = price if prev is None else (min(prev,price) if lowest else max(prev,price))

def fallback_editions(html: str, bucket: dict):
    """Se não achou em cards_stock, pega price[0].p de cards_editions."""
    m = CARDS_EDITIONS_RE.search(html)
    if not m:
        return
    try:
        eds = json.loads(m.group(1))
    except json.JSONDecodeError:
        return
    if not eds or "price" not in eds[0]:
        return
    # price é um dict com key "0": {"p": "..."}
    p0 = eds[0]["price"].get("0", {}).get("p")
    price = parse_price(p0)
    if price is None:
        return
    # assume Mint+NM
    for c in ["M","NM"]:
        bucket[c] = price

@app.errorhandler(404)
def not_found(e):    return jsonify(error="not_found"), 404
@app.errorhandler(500)
def server_error(e): return jsonify(error="internal_server_error"), 500

if __name__ == "__main__":
    app.run()
