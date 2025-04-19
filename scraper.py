from flask import Flask, request, jsonify
import re, json, urllib.parse
import cloudscraper, requests

app = Flask(__name__)
scraper = cloudscraper.create_scraper(
    browser={'browser':'firefox','platform':'windows','desktop':True}
)

def codigo_interno(html):
    m = re.search(r"var\s+g_iCard\s*=\s*([0-9_]+)", html)
    return m.group(1) if m else None

def fetch_json(url):
    r = scraper.get(url, timeout=15)
    return r.json() if r.status_code == 200 else []

@app.route("/offers")
def offers():
    nome = request.args.get("card", "")
    base = "https://www.ligapokemon.com.br/"
    page = (base + "?view=cards/card&card=" +
            urllib.parse.quote(nome))
    html = scraper.get(page, timeout=15).text
    cod = codigo_interno(html)
    if not cod:
        return jsonify({"error": "card not found", "marketplace": [], "buylist": []})

    mp_url  = f"{base}_json/mp.php?card={cod}"
    buy_url = f"{base}_json/buy.php?card={cod}"
    market  = fetch_json(mp_url)
    buylist = fetch_json(buy_url)

    # cada item já vem com price; só ordenar
    market.sort(key=lambda x: x["price"])
    buylist.sort(key=lambda x: x["price"], reverse=True)
    return jsonify({"marketplace": market, "buylist": buylist})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

