"""
scraper.py  –  Liga Pokémon ⇄ Google Sheets
Rodando em Flask + Cloudflare Bypass (cloudscraper)
"""

import json, logging, re, urllib.parse
import cloudscraper
from flask import Flask, jsonify, request

app = Flask(__name__)
log = logging.getLogger(__name__)

# ─────────── Cloudflare bypass ───────────
scraper = cloudscraper.create_scraper(
    browser={"browser": "firefox", "platform": "windows", "desktop": True}
)

# ─────────── Regex para capturar cards_stock ───────────
CARDS_STOCK_REGEX = re.compile(r"var\s+cards_stock\s*=\s*(\[[\s\S]*?\]);", re.DOTALL)

# ─────────── Mapeamento de qualid → condição ───────────
CONDITION_CODES = {
    "1": "M",   # Mint
    "2": "NM",  # Near Mint
    "3": "SP",  # Slightly Played
    "4": "MP",  # Moderately Played
    "5": "HP",  # Heavily Played
    "6": "D",   # Damaged
}

def parse_price(raw: str | None) -> float | None:
    """
    Converte strings de preço de forma inteligente:
    - Se houver vírgula, remove pontos (milhar) e troca vírgula por ponto.
    - Se só houver ponto, assume que é decimal e não remove nada.
    Ex.: '1.259,10' → 1259.10
         '399.95'   → 399.95
    """
    if not raw:
        return None
    s = raw.replace("R$", "").strip()
    if "," in s:
        # ponto = separador de milhar, vírgula = decimal
        s = s.replace(".", "").replace(",", ".")
    # else: mantém o ponto como decimal
    try:
        return float(s)
    except ValueError:
        return None

@app.route("/offers")
def offers():
    carta_raw = request.args.get("card", "").strip()
    if not carta_raw:
        return jsonify(error="card parameter required"), 400

    card = urllib.parse.unquote(carta_raw)
    # inicializa buckets com todas as condições
    mp = {c: None for c in ["M","NM","SP","MP","HP","D"]}
    bl = {c: None for c in ["M","NM","SP","MP","HP","D"]}

    # ── marketplace (show=1): menor por condição
    html1 = _fetch(card, show=1)
    if html1:
        _fill(html1, mp, lowest=True)

    # ── buylist (show=10): maior de todas
    html2 = _fetch(card, show=10)
    if html2:
        _fill(html2, bl, lowest=False)

    # agrega
    best_bl = max((p for p in bl.values() if p is not None), default=None)
    lows = [p for p in mp.values() if p is not None]
    low = min(lows) if lows else best_bl

    return jsonify({
        "card": card,
        "marketplace_prices": mp,
        "buylist_best_price": best_bl,
        "low": low
    })

def _fetch(card: str, show: int) -> str | None:
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

def _fill(html: str, bucket: dict, *, lowest: bool):
    """
    Preenche o bucket a partir de var cards_stock.
    - lowest=True  → guarda o menor preço (marketplace)
    - lowest=False → guarda o maior preço (buylist)
    """
    m = CARDS_STOCK_REGEX.search(html)
    if not m:
        return
    try:
        stock = json.loads(m.group(1))
    except json.JSONDecodeError:
        return

    for itm in stock:
        qual = str(itm.get("qualid", ""))
        cond = CONDITION_CODES.get(qual)
        if not cond:
            continue
        raw = itm.get("precoFinal") or itm.get("preco") or itm.get("base")
        price = parse_price(raw)
        if price is None:
            continue
        prev = bucket.get(cond)
        if prev is None:
            bucket[cond] = price
        else:
            bucket[cond] = min(prev, price) if lowest else max(prev, price)

@app.errorhandler(404)
def not_found(e):    return jsonify(error="not_found"), 404
@app.errorhandler(500)
def server_error(e): return jsonify(error="internal_server_error"), 500

if __name__ == "__main__":
    app.run()
