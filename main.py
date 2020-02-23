#!/usr/bin/env python
import requests
from bs4 import BeautifulSoup
from flask import Flask
from flask import render_template
from flask import request
import time
from datetime import date, datetime, timedelta
from birdlist import birdlist
import google.cloud.logging
import logging

# globals
records = {}
cache = {}
cache_ttl = 3600 # seconds


def fetch_day(d):  # day is a datetime date
    d = d.strftime("%Y-%m-%d")
    url = "https://www.goingbirding.co.uk/hants/birdnews.asp?date_search=8&date={}&sort=2&status_id=8".format(d)
    if cache.get(d) == None or cache[d]["expires"] < datetime.now():
        #logger.log_text("INFO: " + url)
        app.logger.info(url)
        page=requests.get(url)
        if page.status_code != 200:
            #logger.log_text("ERROR: fetch error, http response: {}".format(page.status_code))
            app.logger.error('fetch error, http response: %d', page.status_code)
            return None
        soup = BeautifulSoup(page.content, 'html.parser')
        cache[d] = {}
        cache[d]["rows"] = soup.select('tr')
        cache[d]["expires"] = datetime.now() + timedelta(seconds=cache_ttl)
    else:    
        #logger.log_text("INFO: " + d + "from cache")
        app.logger.info('%s from cache', d)
    return cache[d]["rows"]
    

def short_date(d):  # takes a date in form "dd/mm/yy" and returns d/m e.g. "1/12" for 1st December
    dt = datetime.strptime(d, "%d/%m/%y")
    return "{}/{}".format(dt.day, dt.month)

def add_day(rows): # 'rows' contains the <tr> tags from the table
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
            if (i%2) == 1: # odd numbered row
                # it's a main row, with bird details
                d = short_date(data[0].get_text()) # sighting date
                species = data[1].get_text().strip()
                if species not in birdlist:
                    # logger.log_text("INFO: adding unknown bird %s to birdlist: " + species) 
                    app.logger.info('adding unknown bird %s to birdlist', species)
                    birdlist.insert(0,species)
                # print(species, birdlist[species.upper()])
                site = data[2].get_text()
                count = data[3].get_text()
                observer = data[4].get_text()
            else: # even numbered row
                t = data[0].get_text() # sighting time
                notes = data[1].get_text()

                # after processing even row, add a record with all the data from this pair of rows
                # app.logger.info('adding: %s for: %s', species, d)
                if records.get(species) == None:
                    records[species]={}
                if records[species].get(site) == None:
                    records[species][site] = []
                records[species][site].append(
                    {"date": d,
                    "time": t,
                    "count": count,
                    "observer": observer,
                    "notes": notes})

            

app = Flask(__name__)
@app.route('/')
def index():
    fom = date.today().replace(day=1) # first of the month
    lopm = fom - timedelta(days=1)
    fopm = lopm.replace(day=1)
    return render_template('index.html', fromdate=fopm, todate=lopm)


@app.route('/search', methods=['GET', 'POST'])
def results():
    # set up logging to Google cloud Stackdriver
    client = google.cloud.logging.Client()
    # Connects the logger to the root logging handler; by default this captures
    # all logs at INFO level and higher
    client.setup_logging()
    logging.warn('logging enabled')

    records.clear()
    fromdate_str = request.args.get('fromdate')
    todate_str = request.args.get('todate')
    fromdate = datetime.strptime(fromdate_str, "%Y-%m-%d")
    todate = datetime.strptime(todate_str, "%Y-%m-%d")
    d = fromdate
    while d <= todate:
        add_day(fetch_day(d))
        d = d + timedelta(days=1)
    # logger.log_text("INFO: Number of species recorded: {}".format(len(records)))
    app.logger.info('Number of species recorded: %d', len(records))

    # order the records in taxonomic order
    taxonomic = []
    for species in birdlist:
        if species in records:  # This species has been sighted, add it to our taxonomic list
            taxonomic.append((species, records[species]))

    # logger.log_text("INFO: Number of species recorded: {}".format(len(taxonomic)))
    app.logger.info('Number of species in taxonomic list: %d', len(taxonomic))

    # present results
    # for sp in records:
    #     print(sp) # species
    #     for site in records[sp]:
    #         print("  ", site)
    #         for sighting in records[sp][site]:
    #             print("    ",
    #                     sighting["date"],
    #                     sighting["time"],
    #                     sighting["count"])
    return render_template(
        'results.html', 
        records=taxonomic, 
        num_species=len(records),
        fromdate=fromdate_str, 
        todate=todate_str)


if __name__ == '__main__':  
    app.run(debug=True)

