import re, json, logging, urllib.parse
import cloudscraper
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

scraper = cloudscraper.create_scraper(
    browser={'browser': 'firefox', 'platform': 'windows', 'desktop': True}
)

# --- mapas & regex -----------------------------------------------------------
CONDITION_CODES = {
    "1": "M",   # Mint               (Nova)
    "2": "NM",  # Near‑Mint          (Praticamente Nova)
    "3": "SP",  # Slightly‑Played    (Usada Leve)
    "4": "MP",  # Moderately‑Played  (Usada Moderada)
    "5": "HP",  # Heavily‑Played     (Muito Usada)
    "6": "D"    # Damaged            (Danificada)
}

CARDS_STOCK_RX = re.compile(r"var cards_stock\s*=\s*(\[.*?]);", re.DOTALL)
BUYLIST_RX     = re.compile(r"var cards_stock\s*=\s*(\[.*?]);", re.DOTALL)

# --- utilidades --------------------------------------------------------------
def _str_price_to_float(raw: str) -> float:
    """
    Converte '1.199,99'   → 1199.99
            '1199,99'     → 1199.99
    """
    clean = raw.replace('.', '').replace(',', '.').replace('R$', '').strip()
    return float(clean)

def _extract_cards_stock(html: str):
    m = CARDS_STOCK_RX.search(html)
    return json.loads(m.group(1)) if m else []

# --- rotas -------------------------------------------------------------------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/offers')
def offers():
    card = request.args.get('card', '')
    if not card:
        return jsonify(error="card parameter required"), 400

    decoded = urllib.parse.unquote(card)

    result = {
        "card": decoded,
        "marketplace_prices": {k: None for k in CONDITION_CODES.values()},
        "buylist_prices":     {k: None for k in CONDITION_CODES.values()},
        "low": None
    }

    # ---------------- marketplace (show=1) ----------------
    html_market = _get_page(decoded, show=1)
    _fill_prices(html_market, result["marketplace_prices"])

    # ---------------- buy‑list   (show=10) ---------------
    html_buy = _get_page(decoded, show=10)
    _fill_prices(html_buy, result["buylist_prices"])

    # menor preço geral (entre marketplace + buylist)
    all_prices = [p for p in
                  list(result["marketplace_prices"].values()) +
                  list(result["buylist_prices"].values())
                  if p is not None]
    result["low"] = min(all_prices) if all_prices else None

    return jsonify(result)

# --- helpers -----------------------------------------------------------------
def _get_page(card_name: str, show: int) -> str | None:
    url = (f"https://www.ligapokemon.com.br/"
           f"?view=cards/card&card={urllib.parse.quote(card_name)}&show={show}")
    r = scraper.get(url)
    return r.text if r.status_code == 200 else None

def _fill_prices(html: str|None, bucket: dict):
    if not html:
        return
    listings = _extract_cards_stock(html)
    for item in listings:
        # marketplace:  'precoFinal'  | buylist: 'precoFinal' ou 'preco'
        price_raw = item.get("precoFinal") or item.get("preco")
        qualid    = str(item.get("qualid") or item.get("quality") or "")
        if price_raw and qualid in CONDITION_CODES:
            try:
                price = _str_price_to_float(price_raw)
                cond  = CONDITION_CODES[qualid]
                if bucket[cond] is None or price < bucket[cond]:
                    bucket[cond] = price
            except ValueError:
                logging.warning("Falha ao converter preço %s", price_raw)

# -----------------------------------------------------------------------------            
if __name__ == '__main__':
    # importante para produção no Render:
    # bind na porta indicada em $PORT (Render ajusta a variável)
    import os
    from waitress import serve
    serve(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
