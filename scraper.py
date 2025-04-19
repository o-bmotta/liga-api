# scraper.py – API simples para preços da LigaPokemon
#
#  /offers?card=<nome exato>
#     devolve:
#       { "marketplace":[…],  "buylist":[…] }
#
# marketplace = vendas (menor→maior)
# buylist     = compras (maior→menor)

from flask import Flask, request, jsonify
import urllib.parse, re, cloudscraper

app = Flask(__name__)
scraper = cloudscraper.create_scraper(
    browser={'browser':'firefox','platform':'windows','desktop':True}
)

BASE = "https://www.ligapokemon.com.br/"
HEAD = {"User-Agent":"Mozilla/5.0"}

# ---------- util ---------- #
def html(url:str) -> str|None:
    try:
        r = scraper.get(url, headers=HEAD, timeout=15)
        return r.text if r.status_code == 200 else None
    except Exception:
        return None

def gicard(text:str) -> str|None:
    m = re.search(r"var\s+g_iCard\s*=\s*([0-9_]+)", text)
    return m.group(1) if m else None

def j(url:str) -> list:
    try:
        r = scraper.get(url, headers=HEAD, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []

# ---------- rota ---------- #
@app.route("/offers")
def offers():
    raw = request.args.get("card","").strip()
    if not raw:
        return jsonify({"error":"parâmetro ?card= obrigatório"})

    # dois formatos de encoding
    quoted      = urllib.parse.quote(raw)
    quoted_plus = urllib.parse.quote_plus(raw.lower())

    urls = [
        # como sai da busca
        f"{BASE}?view=cards/card&tipo=1&card={quoted}",
        f"{BASE}?view=cards/card&tipo=1&card={quoted_plus}",

        # já dentro da página da carta
        f"{BASE}?view=cards/card&card={quoted}",
        f"{BASE}?view=cards/card&card={quoted_plus}",

        # abas internas
        f"{BASE}?view=cards/card&card={quoted}&show=10",
        f"{BASE}?view=cards/card&card={quoted_plus}&show=10",
        f"{BASE}?view=cards/card&card={quoted}&show=1",
        f"{BASE}?view=cards/card&card={quoted_plus}&show=1",
    ]

    code = None
    for u in urls:
        h = html(u)
        if h:
            code = gicard(h)
            if code:
                break

    if not code:
        return jsonify({"error":"card not found",
                        "searched": raw,
                        "marketplace":[], "buylist":[]})

    mp  = j(f"{BASE}_json/mp.php?card={code}")
    buy = j(f"{BASE}_json/buy.php?card={code}")

    mp.sort(key=lambda x: x["price"])
    buy.sort(key=lambda x: x["price"], reverse=True)
    return jsonify({"marketplace": mp, "buylist": buy})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
