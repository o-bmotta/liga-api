# scraper.py  –  API mínima para LigaPokemon
#
# • /offers?card=<nome exato da carta>
#     →  JSON com marketplace (menor→maior)   e   buylist (maior→menor)
#
# O script:
#   1. Baixa o HTML da página pública da carta.
#   2. Extrai o código interno g_iCard (ex.: 5380_014).
#   3. Consulta os endpoints JSON nativos:
#        _json/mp.php?card=...   (vendas)
#        _json/buy.php?card=...  (compras)
#   4. Ordena e devolve.

from flask import Flask, request, jsonify
import urllib.parse, re, cloudscraper, json

app = Flask(__name__)
scraper = cloudscraper.create_scraper(
    browser={'browser': 'firefox', 'platform': 'windows', 'desktop': True}
)

BASE_SITE = "https://www.ligapokemon.com.br/"
HEADERS   = {"User-Agent": "Mozilla/5.0"}

# ---------- funções utilitárias ---------- #

def pegar_html(url: str) -> str | None:
    """Baixa a página e devolve HTML ou None se falhar."""
    try:
        r = scraper.get(url, headers=HEADERS, timeout=15)
        return r.text if r.status_code == 200 else None
    except Exception:
        return None

def extrair_gicard(html: str) -> str | None:
    """Procura var g_iCard = 123_456 no HTML."""
    m = re.search(r"var\s+g_iCard\s*=\s*([0-9_]+)", html)
    return m.group(1) if m else None

def pegar_json(url: str) -> list:
    try:
        r = scraper.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []

# ---------- rota da API ---------- #

@app.route("/offers")
def offers():
    nome = request.args.get("card", "").strip()
    if not nome:
        return jsonify({"error": "parâmetro ?card= obrigatório"})

    quoted = urllib.parse.quote(nome)

    # 1ª tentativa – link da busca comum
    urls_tentativa = [
        f"{BASE_SITE}?view=cards/card&tipo=1&card={quoted}",
        # 2ª – link que aparece na aba BUYLIST
        f"{BASE_SITE}?view=cards/card&card={quoted}&show=10",
        # 3ª – link quando volta ao marketplace
        f"{BASE_SITE}?view=cards/card&card={quoted}&show=1",
    ]

    gicard = None
    for u in urls_tentativa:
        html = pegar_html(u)
        if html:
            gicard = extrair_gicard(html)
            if gicard:
                break

    if not gicard:
        return jsonify({
            "error": "card not found",
            "searched": nome,
            "marketplace": [],
            "buylist": []
        })

    # Endpoints JSON internos
    mp_url  = f"{BASE_SITE}_json/mp.php?card={gicard}"
    buy_url = f"{BASE_SITE}_json/buy.php?card={gicard}"

    marketplace = pegar_json(mp_url)
    buylist     = pegar_json(buy_url)

    marketplace.sort(key=lambda x: x["price"])                 # menor → maior
    buylist.sort(key=lambda x: x["price"], reverse=True)        # maior → menor

    return jsonify({"marketplace": marketplace, "buylist": buylist})

# ---------- executar localmente ---------- #
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
