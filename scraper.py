# scraper.py  – 20‑abr‑2025  versão estável
import re, json, urllib.parse, logging
from flask import Flask, request, jsonify
import cloudscraper

app = Flask(__name__)
log = logging.getLogger(__name__)

scraper = cloudscraper.create_scraper(
    browser={"browser": "firefox", "platform": "windows", "desktop": True}
)

# ---------- util ----------------------------------------------------------
def _parse_price(raw: str | None) -> float | None:
    """Converte '1.099,99' ou '1099.99' em 1099.99   (None se falhar)"""
    if not raw:
        return None
    txt = raw.replace("R$", "").strip()
    # se existir vírgula, significa que ela é separador decimal
    if "," in txt:
        txt = txt.replace(".", "").replace(",", ".")
    try:
        return float(txt)
    except ValueError:
        return None


# ---------- rotas ---------------------------------------------------------
@app.route("/")
def health():
    return "Liga‑API OK"

@app.route("/offers")
def offers():
    card = request.args.get("card", "").strip()
    if not card:
        return jsonify(error="card parameter required"), 400

    # estrutura‑resultado
    bucket_mkt = {}   # loja vendendo → menor preço por condição
    bucket_buy = {}   # buylist        → maior preço por condição

    html_mkt = _fetch(card, show=1)
    if html_mkt:
        _fill_prices(html_mkt, bucket_mkt, lowest=True)

    html_buy = _fetch(card, show=10)
    if html_buy:
        _fill_prices(html_buy, bucket_buy, lowest=False)

    # monta resposta final
    all_conds = sorted({"M", "NM", "SP", "MP", "HP", "D"})
    resp = {
        "card": card,
        "marketplace": {c: bucket_mkt.get(c) for c in all_conds},
        "buylist":     {c: bucket_buy.get(c) for c in all_conds},
        "lowest_marketplace":
            min(bucket_mkt.values()) if bucket_mkt else None,
        "highest_buylist":
            max(bucket_buy.values()) if bucket_buy else None,
    }
    return jsonify(resp)


# ---------- helpers -------------------------------------------------------
def _fetch(name: str, show: int) -> str | None:
    url = (
        "https://www.ligapokemon.com.br/"
        f"?view=cards/card&card={urllib.parse.quote(name)}&show={show}"
    )
    r = scraper.get(url, timeout=20)
    return r.text if r.status_code == 200 else None

VAR_STOCK = re.compile(r"var\s+cards_stock\s*=\s*(\[[^\]]+]);", re.DOTALL)
VAR_QUAL  = re.compile(r"var\s+dataQuality\s*=\s*(\[[^\]]+]);", re.DOTALL)

def _get_quality_map(html: str) -> dict[str, str]:
    """
    Constrói dinamicamente o mapa id→acron ('1'→'M', '2'→'NM' …)
    para evitar disparidades entre marketplace e buy‑list.
    """
    m = VAR_QUAL.search(html)
    if not m:
        return {}
    arr = json.loads(m.group(1))
    out = {}
    for q in arr:
        # alguns sites escrevem "M / NM" – tratamos como 'M' **e** 'NM'
        acr = q.get("acron", "").replace(" ", "").split("/")
        for a in acr:
            if a:                       # 'M', 'NM' …
                out[str(q["id"])] = a
    return out

def _fill_prices(html: str, bucket: dict, *, lowest: bool):
    qual_map = _get_quality_map(html)
    m = VAR_STOCK.search(html)
    if not m:
        return
    data = json.loads(m.group(1))

    for item in data:
        raw = item.get("precoFinal") or item.get("preco") or item.get("base")
        price = _parse_price(raw)
        # 'qualid' no marketplace, 'q' na buylist
        qid   = str(item.get("qualid") or item.get("q") or "")
        cond  = qual_map.get(qid)
        if price is None or cond is None:
            continue

        # agrupa menor (loja) ou maior (buy‑list)
        if cond not in bucket:
            bucket[cond] = price
        else:
            bucket[cond] = min(bucket[cond], price) if lowest else max(bucket[cond], price)
