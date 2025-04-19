from flask import Flask, request, jsonify
import cloudscraper, urllib.parse
from bs4 import BeautifulSoup

app = Flask(__name__)
scraper = cloudscraper.create_scraper(
  browser={'browser':'firefox','platform':'windows','desktop':True}
)

@app.route('/offers')
def offers():
  carta = request.args.get('card', '')
  url = ("https://www.ligapokemon.com.br/"
         "?view=cards/card&card=" + urllib.parse.quote(carta))
  html = scraper.get(url).text
  soup = BeautifulSoup(html, 'html.parser')

  vendas = []
  for tr in soup.select('.marketplace-table tbody tr'):
      loja = tr.select_one('.marketplace-loja').get_text(strip=True)
      cond = tr.select_one('.marketplace-condicao').get_text(strip=True)
      preco= tr.select_one('.marketplace-preco').get_text(strip=True)
      val  = float(preco.replace('R$','').replace('.','').replace(',','.'))
      vendas.append({'store': loja, 'condition': cond, 'price': val})

  buys = []
  for tr in soup.select('.buylist-table tbody tr'):
      loja = tr.select_one('.buylist-loja').get_text(strip=True)
      preco= tr.select_one('.buylist-preco').get_text(strip=True)
      val  = float(preco.replace('R$','').replace('.','').replace(',','.'))
      buys.append({'store': loja, 'price': val})

  vendas.sort(key=lambda x: x['price'])
  buys.sort(key=lambda x: x['price'], reverse=True)
  return jsonify({'marketplace': vendas, 'buylist': buys})

if __name__ == '__main__':
  app.run(host='0.0.0.0', port=5000)
