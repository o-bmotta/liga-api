import re
import urllib.parse
import logging
import json
import cloudscraper
from flask import Flask, request, jsonify

app = Flask(__name__)

# 1) Cria o cloudscraper para driblar Cloudflare
scraper = cloudscraper.create_scraper(
    browser={'browser': 'firefox', 'platform': 'windows', 'desktop': True}
)

# 2) Códigos de condição
CONDITION_CODES = {
    "1": "NM",  # Near Mint
    "2": "SP",  # Slightly Played
    "3": "MP",  # Moderately Played
    "4": "HP",  # Heavily Played
    "5": "D"    # Damaged
}

# 3) Regex atualizadas para capturar **exatamente** o JSON injetado pelo site
#    – marketplace: JSON puro enviado como resposta a show=1
MARKETPLACE_JSON_REGEX = re.compile(r'<script[^>]*>window\.dataMS\s*=\s*([^<]+);?</script>', re.DOTALL)
#    – buylist: JSON puro enviado como resposta a show=10
BUYLIST_JSON_REGEX     = re.compile(r'<script[^>]*>window\.dataBL\s*=\s*([^<]+);?</script>', re.DOTALL)

# Logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@app.route('/offers')
def preco():
    carta = request.args.get('card', '').strip()
    if not carta:
        return jsonify(error="card_name_required"), 400

    nome = urllib.parse.unquote(carta)
    logger.info(f"Buscando preços para: {nome}")

    # Estrutura de retorno
    result = {
        "card": nome,
        "marketplace_prices": {c: None for c in CONDITION_CODES.values()},
        "buylist_best_price": None
    }

    # 1) Marketplace (show=1) → menor preço em cada condição
    html_mp = get_html_content(nome, show_param=1)
    if html_mp:
        mkt = extract_marketplace_prices(html_mp)
        for cond, price in mkt.items():
            result["marketplace_prices"][cond] = price

    # 2) Buylist (show=10) → maior preço possível
    html_bl = get_html_content(nome, show_param=10)
    if html_bl:
        bl = extract_buylist_price(html_bl)
        if bl is not None:
            result["buylist_best_price"] = bl

    # 3) Campo “low” para compatibilidade (menor de marketplace ou buylist se vazio)
    lowest = min([p for p in result["marketplace_prices"].values() if p is not None] + \
                 ([result["buylist_best_price"]] if result["buylist_best_price"] else []),
                 default=None)
    if lowest is not None:
        result["low"] = lowest

    # Se não encontrou preço nenhum, retorna 404
    if lowest is None:
        return jsonify(error="price_not_found", card=nome), 404

    return jsonify(result)


def get_html_content(card_name, show_param):
    """
    Busca diretamente a página com ?show=1 (venda) ou =10 (buylist).
    Escapa parênteses manualmente para garantir consistência.
    """
    # Escapa espaços e parênteses corretamente
    encoded = urllib.parse.quote(card_name, safe='')
    url = f"https://www.ligapokemon.com.br/?view=cards/card&card={encoded}&show={show_param}"
    logger.debug(f"GET {url}")
    resp = scraper.get(url)
    if resp.status_code != 200:
        logger.error(f"Status {resp.status_code} na página {url}")
        return None
    return resp.text


def extract_marketplace_prices(html):
    """
    Procura o <script>…window.dataMS = [ … ]… e parseia o JSON.
    Retorna um dict { 'NM': menor, 'SP':…, … }
    """
    match = MARKETPLACE_JSON_REGEX.search(html)
    if not match:
        logger.warning("dataMS não encontrado no HTML")
        return {}
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        logger.error(f"JSON inválido em marketplace: {e}")
        return {}

    prices = {}
    for item in data:
        cond_code = str(item.get("condition", "")).strip()
        price_str = str(item.get("price", "")).replace(".", "").replace(",", ".").strip()
        if cond_code in CONDITION_CODES and price_str:
            try:
                p = float(price_str)
                cond = CONDITION_CODES[cond_code]
                # mantém o menor preço por condição
                if cond not in prices or p < prices[cond]:
                    prices[cond] = p
            except ValueError:
                logger.warning(f"Preço inválido: {price_str}")
    return prices


def extract_buylist_price(html):
    """
    Procura o <script>…window.dataBL = [ … ]… e parseia o JSON.
    Retorna o maior preço da buylist.
    """
    match = BUYLIST_JSON_REGEX.search(html)
    if not match:
        logger.warning("dataBL não encontrado no HTML")
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        logger.error(f"JSON inválido em buylist: {e}")
        return None

    best = None
    for item in data:
        price_str = str(item.get("price", "")).replace(".", "").replace(",", ".").strip()
        if price_str:
            try:
                p = float(price_str)
                if best is None or p > best:
                    best = p
            except ValueError:
                logger.warning(f"Preço buylist inválido: {price_str}")
    return best


@app.errorhandler(404)
def not_found(e):
    return jsonify(error="not_found"), 404


@app.errorhandler(500)
def internal_error(e):
    return jsonify(error="internal_server_error"), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

