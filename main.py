import asyncio
import os
import uuid
import time
from datetime import datetime
import pymongo
import requests
import schedule
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import itertools
from dotenv import load_dotenv
import json


def get_links(url):
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Failed to send HTTP request. Status code: {response.status_code}")
        return []

    link_soup = BeautifulSoup(response.text, 'html.parser')
    table = link_soup.find('table', class_='table-main')
    if table is None:
        return get_links_main_page(url)

    sections = table.find_all('td', class_='h-text-left')
    if not sections:
        a_tags = table.find_all('a', class_='in-match')
        return [{'name': a_tag.text, 'link': a_tag.get('href')} for a_tag in a_tags]

    return [{'name': section.find('a').text, 'link': section.find('a').get('href')} for section in sections]


def get_links_main_page(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        page.get_by_text("All Matches", exact=True).wait_for()
        soup = BeautifulSoup(page.content(), 'html.parser')

    main_div = soup.find('div', id='nr-ko-all')
    a_tags = main_div.find_all('a', class_='table-main__participants')
    return [{'name': a_tag.text, 'link': a_tag.get('href')} for a_tag in a_tags]


def collate_links(urls):
    all_links = []
    for url in urls:
        links = get_links(url)
        print(f"{len(links)} links found at {url}")
        all_links.extend(links)
    return all_links


def get_odds(link):
    url = f"https://www.betexplorer.com{link['link']}"
    print(url)
    try:
        with (sync_playwright() as p):
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url)
            page.get_by_text('All Odds', exact=True).wait_for()
            page.get_by_text('All Odds', exact=True).click()
            soup = BeautifulSoup(page.content(), 'html.parser')

        table = soup.find('tbody', id='best-odds-0')

        entries = []
        for tr in table.find_all('tr'):
            if tr.get('data-inactive') == "true":
                continue
            entries.append(tr)

        results = []
        for entry in entries:
            name = entry.find('td', class_='h-text-left under-s-only h-text-pl10').find('span').get('title')
            odds = [odd.find('span').text for odd in entry.find_all('td', class_='table-main__detail-odds')]
            results.append({'vendor': name, 'odds': odds})
        return results

    except Exception as e:
        print(e)
        return []


def find_arbitrage_opportunity(data):
    # Limits arbitrage to 3% or more opportunities
    opportunity = None
    resolution = 0.99
    best_prob = 1
    try:
        for item in data['odds']:
            item['odds'] = [float(od.strip()) for od in item['odds']]

        for combination in itertools.combinations(data['odds'], 3):
            odds1, odds2, odds3 = combination
            prob1 = 1 / odds1['odds'][0]
            prob2 = 1 / odds2['odds'][1]
            prob3 = 1 / odds3['odds'][2]
            total_prob = prob1 + prob2 + prob3

            if total_prob < resolution:
                if total_prob < best_prob:
                    best_prob = total_prob
                    opportunity = {
                        'vendors': [odds1['vendor'], odds2['vendor'], odds3['vendor']],
                        'odds': [odds1['odds'][0], odds2['odds'][1], odds3['odds'][2]],
                        'total_probability': total_prob
                    }
    except Exception as e:
        print(e)

    return opportunity


def generate_game_json(opportunity, result):
    return {
        "game_type": "Football",
        "match": result['match'],
        "url": result['url'],
        "timestamp": datetime.now(),
        "odds": {
            "1": {
                "sitename": opportunity['vendors'][0],
                "odds": opportunity['odds'][0]
            },
            "x": {
                "sitename": opportunity['vendors'][1],
                "odds": opportunity['odds'][1]
            },
            "2": {
                "sitename": opportunity['vendors'][2],
                "odds": opportunity['odds'][2]
            }
        }
    }


def process_links(links):
    results = [{'match': link['name'],
                 'url': f"https://www.betexplorer.com{link['link']}",
                 'odds': get_odds(link)} for link in links]

    games = []
    for result in results:
        opportunity = find_arbitrage_opportunity(result)
        if opportunity:
            print(result['match'].strip())
            games.append(generate_game_json(opportunity, result))
    
    return games
                

def job():
    urls = [
        "https://www.betexplorer.com/football/england/championship/",
        "https://www.betexplorer.com/football/england/league-one/",
        "https://www.betexplorer.com/football/england/premier-league/",
        "https://www.betexplorer.com/football/england/league-two/",
        "https://www.betexplorer.com/football/spain/laliga/",
        "https://www.betexplorer.com/football/spain/laliga2/",
        "https://www.betexplorer.com/football/italy/serie-a/",
        "https://www.betexplorer.com/football/italy/serie-b/",
        "https://www.betexplorer.com/football/france/ligue-1/",
        "https://www.betexplorer.com/football/france/ligue-2/",
        "https://www.betexplorer.com/football/netherlands/eredivisie/",
        "https://www.betexplorer.com/football/germany/bundesliga/",
        "https://www.betexplorer.com/football/germany/2-bundesliga/"
    ]
    all_links = collate_links(urls)

    games = process_links(all_links)

    load_dotenv()

    client = pymongo.MongoClient(os.getenv("mongo_connection"))
    db = client["arbie"]
    game_col = db["Games"]
    run_col = db["Runs"]

    if len(games) > 0:
        x = game_col.insert_many(games)

    run = {
        "timestamp": datetime.now(),
        "game_ids": x.inserted_ids if len(games) > 0 else []
    }

    run_col.insert_one(run)

    print(f"{len(games)} games found")

job()
