"""
scraper.py  –  Liga Pokémon ⇄ Google Sheets
Rodando em Flask + Cloudflare Bypass (cloudscraper)
"""

import json, logging, re, urllib.parse
import cloudscraper
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# 1) ─────────── Cloudflare bypass
scraper = cloudscraper.create_scraper(
    browser={"browser": "firefox", "platform": "windows", "desktop": True}
)

# 2) ─────────── Expressões regulares
CARDS_STOCK_REGEX = re.compile(r"var\s+cards_stock\s*=\s*(\[.*?]);", re.DOTALL)

# Nos dadosQuality da página:
#  id 2 = NM / 3 = SP / 4 = MP / 5 = HP / 6 = D
CONDITION_CODES = {
    "2": "NM",
    "3": "SP",
    "4": "MP",
    "5": "HP",
    "6": "D",
}

# 3) ─────────── Rota raiz (formulário simples opcional)
@app.route("/")
def index():
    return render_template("index.html")  # coloque um HTML ou remova a chamada

# 4) ─────────── API
@app.route("/offers")
def preco():
    """
    /offers?card=Mew+Star+(14/29)

    Resposta:
    {
      "card": "Mew Star (14/29)",
      "marketplace_prices": { "NM": 1259.10, "SP": null, … },
      "buylist_best_price": 3500.0,
      "low": 1259.10
    }
    """
    carta_raw = request.args.get("card", "")
    if not carta_raw:
        return jsonify(error="card_name_required"), 400

    nome_carta = urllib.parse.unquote(carta_raw)

    result = {
        "card": nome_carta,
        "marketplace_prices": {c: None for c in ["NM", "SP", "MP", "HP", "D"]},
        "buylist_best_price": None,
    }

    # ── 4.1 marketplace (lojas vendendo)  ─────────────────────────────
    html_market = get_html(nome_carta, show=1)
    if html_market:
        mp_prices = extract_marketplace_prices(html_market)
        result["marketplace_prices"].update(mp_prices)

    # ── 4.2 buylist (lojas comprando)  ────────────────────────────────
    html_buy = get_html(nome_carta, show=10)
    if html_buy:
        result["buylist_best_price"] = extract_buylist_price(html_buy)

    # menor preço geral – útil para Sheets ordenar
    lowest = min(
        (p for p in result["marketplace_prices"].values() if p is not None),
        default=None,
    )
    result["low"] = lowest if lowest is not None else result["buylist_best_price"]

    if result["low"] is None:
        return jsonify(error="price_not_found", card=nome_carta), 404

    return jsonify(result)


# 5) ─────────── Helpers ───────────────────────────────────────────────
def get_html(card_name: str, show: int) -> str | None:
    url = (
        "https://www.ligapokemon.com.br/?view=cards/card"
        f"&card={urllib.parse.quote(card_name)}&show={show}"
    )
    try:
        r = scraper.get(url, timeout=20)
        return r.text if r.status_code == 200 else None
    except Exception as e:
        logging.warning(f"Erro ao baixar página ({url}): {e}")
        return None


def extract_marketplace_prices(html: str) -> dict[str, float]:
    """
    Lê cards_stock na aba show=1 e devolve o MENOR preço por condição.
    """
    prices = {}
    m = CARDS_STOCK_REGEX.search(html)
    if not m:
        return prices

    try:
        stock = json.loads(m.group(1))
    except json.JSONDecodeError:
        return prices

    for item in stock:
        cond_code = str(item.get("qualid", ""))
        cond = CONDITION_CODES.get(cond_code)
        if not cond:
            continue

        # campo de preço pode ser 'precoFinal' ou 'preco'
        price_str = (
            item.get("precoFinal")
            or item.get("preco")
            or item.get("base")  # fallback
        )
        if not price_str:
            continue

        try:
            price = float(price_str.replace(".", "").replace(",", "."))
        except ValueError:
            continue

        # guarda o menor preço por condição
        if cond not in prices or price < prices[cond]:
            prices[cond] = price

    return prices


def extract_buylist_price(html: str) -> float | None:
    """
    Lê cards_stock na aba show=10 e devolve o MAIOR preço de compra.
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
        price_str = item.get("precoFinal") or item.get("base")
        if not price_str:
            continue
        try:
            price = float(price_str.replace(".", "").replace(",", "."))
        except ValueError:
            continue
        if highest is None or price > highest:
            highest = price
    return highest


# 6) ─────────── Tratamento de erros HTTP  ────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return jsonify(error="not_found"), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify(error="internal_server_error"), 500 
