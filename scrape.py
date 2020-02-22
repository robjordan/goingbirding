#!/usr/bin/env python
import requests
from bs4 import BeautifulSoup
from flask import Flask
from flask import render_template

url = "https://www.goingbirding.co.uk/hants/birdnews.asp?date_search=8&date=2020-02-20&sort=7&status_id=8"

page=requests.get(url)
page.status_code # should be 200
soup = BeautifulSoup(page.content, 'html.parser')
rows = soup.select('tr')
# row 0 is headers
#
# rows 1,3,5,7,9...
# td[0]: date
# td[1]: species
# td[2]: site (gridref in href)
# td[3]: count
# td[4]: observer
#
# rows 2,4,6,8,10...
# td[0]: time
# td[1]: notes
for i,row in enumerate(rows, start=0):
    data = row.select('td')
    if len(data) > 1:  # ignore the header row, that doesn't have <td>
        if (i%2)==1:
            # it's a main row, with bird details
            date = data[0].get_text()
            species = data[1].get_text()
            site = data[2].get_text()
            count = data[3].get_text()
            observer = data[4].get_text()
        else:
            time = data[0].get_text()
            notes = data[1].get_text()
            print('{}: {} {} s:{} c:{} o:{} n:{}'.format(
                species,
                date,
                time,
                site,
                count,
                observer,
                notes)) 

# app = Flask(__name__)
# @app.route('/')
# def index():
#    return render_template('index.html')
# app.run(debug=True)

