"""
scraper.py – Liga Pokémon ⇒ JSON p/ Google Sheets
versão 2 ( Mint + parse_price robusto )
"""

import json, logging, re, urllib.parse
import cloudscraper
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# ───────────────── Cloudflare bypass
scraper = cloudscraper.create_scraper(
    browser={"browser": "firefox", "platform": "windows", "desktop": True}
)

# ───────────────── Regex
CARDS_STOCK_REGEX = re.compile(r"var\s+cards_stock\s*=\s*(\[.*?]);", re.DOTALL)

# id → acrônimo da condição (veja dataQuality da página)
CONDITION_CODES = {
    "1": "M",   # Mint / Nova
    "2": "NM",  # Near‑Mint
    "3": "SP",  # Slightly‑Played
    "4": "MP",  # Moderately‑Played
    "5": "HP",  # Heavily‑Played
    "6": "D",   # Damaged
}


# ───────────────── Página inicial (opcional)
@app.route("/")
def index():
    return render_template("index.html")


# ───────────────── API principal
@app.route("/offers")
def offers():
    card_raw = request.args.get("card", "")
    if not card_raw:
        return jsonify(error="card_name_required"), 400

    card_name = urllib.parse.unquote(card_raw)

    result = {
        "card": card_name,
        "marketplace_prices": {c: None for c in CONDITION_CODES.values()},
        "buylist_best_price": None,
    }

    # marketplace – aba show=1
    html_market = fetch_html(card_name, show=1)
    if html_market:
        mp_prices = extract_marketplace(html_market)
        result["marketplace_prices"].update(mp_prices)

    # buylist – aba show=10
    html_buy = fetch_html(card_name, show=10)
    if html_buy:
        result["buylist_best_price"] = extract_buylist(html_buy)

    # preço mais baixo para referência rápida
    lowest = min(
        (p for p in result["marketplace_prices"].values() if p is not None),
        default=None,
    )
    result["low"] = lowest if lowest is not None else result["buylist_best_price"]

    if result["low"] is None:
        return jsonify(error="price_not_found", card=card_name), 404

    return jsonify(result)


# ───────────────── Helpers
def fetch_html(card: str, show: int) -> str | None:
    url = (
        "https://www.ligapokemon.com.br/?view=cards/card"
        f"&card={urllib.parse.quote(card)}&show={show}"
    )
    try:
        r = scraper.get(url, timeout=20)
        return r.text if r.status_code == 200 else None
    except Exception as e:
        logging.warning(f"Falha ao baixar {url}: {e}")
        return None


def parse_price(s: str) -> float | None:
    """
    Converte string preço brasileira/americana em float.
    - '1.259,10'  -> 1259.10
    - '1259,10'   -> 1259.10
    - '1259.10'   -> 1259.10
    """
    s = s.strip().replace("R$", "").replace(" ", "")
    if not s:
        return None

    # formato '1.259,10'
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    # formato '1259,10'
    elif "," in s:
        s = s.replace(",", ".")
    # formato '1.259.10' (duas bolinhas)
    elif s.count(".") > 1:
        parts = s.split(".")
        s = "".join(parts[:-1]) + "." + parts[-1]

    try:
        return float(s)
    except ValueError:
        return None


def extract_marketplace(html: str) -> dict[str, float]:
    """
    Menor preço por condição (inclui M).
    """
    prices: dict[str, float] = {}
    m = CARDS_STOCK_REGEX.search(html)
    if not m:
        return prices

    try:
        stock = json.loads(m.group(1))
    except json.JSONDecodeError:
        return prices

    for item in stock:
        cond = CONDITION_CODES.get(str(item.get("qualid", "")))
        if not cond:
            continue

        price = parse_price(
            item.get("precoFinal") or item.get("preco") or item.get("base", "")
        )
        if price is None:
            continue

        if cond not in prices or price < prices[cond]:
            prices[cond] = price

    return prices


def extract_buylist(html: str) -> float | None:
    """
    Maior preço pago (qualquer condição).
    """
    m = CARDS_STOCK_REGEX.search(html)
    if not m:
        return None

    try:
        stock = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None

    highest = None
    for item in stock:
        price = parse_price(item.get("precoFinal") or item.get("base", ""))
        if price is None:
            continue
        if highest is None or price > highest:
            highest = price
    return highest


# ───────────────── Tratamento de erros HTTP
@app.errorhandler(404)
def not_found(e):
    return jsonify(error="not_found"), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify(error="internal_server_error"), 500
