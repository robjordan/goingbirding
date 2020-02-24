#!/usr/bin/env python
import requests
from bs4 import BeautifulSoup
from flask import Flask
from flask import render_template
from flask import request
import time
from datetime import date, datetime, timedelta, timezone
from birdlist import birdlist
import google.cloud.logging
import logging
from google.cloud import datastore
import pickle

# globals
cache_ttl = 7200 # seconds


def fetch_day(d, ds_client):  # day is a datetime date
    d = d.strftime("%Y-%m-%d")
    url = "https://www.goingbirding.co.uk/hants/birdnews.asp?date_search=8&date={}&sort=2&status_id=8".format(d)

    key = ds_client.key('DaySightings', d)
    cache_entry = ds_client.get(key)

    if cache_entry == None or cache_entry['expires'] < datetime.now(timezone.utc):
        # not cached or expired, create/update cache entry for this date
        app.logger.info(url)
        page=requests.get(url)
        if page.status_code != 200:
            app.logger.error('fetch error, http response: %d', page.status_code)
            return None
        expires = datetime.now(timezone.utc) + timedelta(seconds=cache_ttl)
        sightings = parse_html(page.content)

        cache_entry = datastore.Entity(key=key, exclude_from_indexes=('sightings', 'expires'))
        cache_entry.update({
            'sightings': sightings,
            'expires': expires
        })
        ds_client.put(cache_entry)

    else: 
        # use from cache   
        app.logger.info('%s from cache', d)
        sightings = cache_entry['sightings']


    return sightings


def parse_html(html): # takes page.content from http fetch, returns an array of sightings
    sightings = []

    soup = BeautifulSoup(html, 'html.parser')
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
            if (i%2) == 1: # odd numbered row
                # it's a main row, with bird details
                d = short_date(data[0].get_text()) # sighting date
                species = data[1].get_text().strip()
                if species not in birdlist:
                    app.logger.info('adding unknown bird %s to birdlist', species)
                    birdlist.insert(0,species)
                # print(species, birdlist[species.upper()])
                site = data[2].get_text()
                count = data[3].get_text()
                observer = data[4].get_text()
            else: # even numbered row
                t = data[0].get_text() # sighting time
                notes = data[1].get_text()
                sightings.append({
                    "site": site,
                    "species": species,
                    "date": d,
                    "time": t,
                    "count": count,
                    "observer": observer,
                    "notes": notes})
    return sightings


def short_date(d):  # takes a date in form "dd/mm/yy" and returns d/m e.g. "1/12" for 1st December
    dt = datetime.strptime(d, "%d/%m/%y")
    return "{}/{}".format(dt.day, dt.month)

def add_day(sightings, records): # sightings is an array of dictionaries, one item per sighting

    for s in sightings:
        # app.logger.info('adding: %s for: %s', species, d)
        if records.get(s['species']) == None:
            records[s['species']]={}
        if records[s['species']].get(s['site']) == None:
            records[s['species']][s['site']] = []
        records[s['species']][s['site']].append(
            {"date": s['date'],
            "time": s['time'],
            "count": s['count'],
            "observer": s['observer'],
            "notes": s['notes']})

            

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
    logging_client = google.cloud.logging.Client()
    # Connects the logger to the root logging handler; by default this captures
    # all logs at INFO level and higher
    logging_client.setup_logging()

    # set up and test access to Google Datastore
    ds_client = datastore.Client()

    records = {}
    fromdate_str = request.args.get('fromdate')
    todate_str = request.args.get('todate')
    fromdate = datetime.strptime(fromdate_str, "%Y-%m-%d")
    todate = datetime.strptime(todate_str, "%Y-%m-%d")
    d = fromdate
    while d <= todate:
        add_day(fetch_day(d, ds_client), records)
        d = d + timedelta(days=1)
    
    app.logger.info('Number of species recorded: %d', len(records))

    # order the records in taxonomic order
    taxonomic = []
    for species in birdlist:
        if species in records:  # This species has been sighted, add it to our taxonomic list
            taxonomic.append((species, records[species]))

    app.logger.info('Number of species in taxonomic list: %d', len(taxonomic))

    return render_template(
        'results.html', 
        records=taxonomic, 
        num_species=len(records),
        fromdate=fromdate_str, 
        todate=todate_str)


if __name__ == '__main__':  
    app.run(debug=True)

