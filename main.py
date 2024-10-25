import asyncio
import os

import time
import requests
import schedule
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import itertools
from dotenv import load_dotenv
from telegram import Bot

load_dotenv()
API_TOKEN = os.getenv("API_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

bot = Bot(token=API_TOKEN)


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


def find_arbitrage_opportunities(data):
    opportunities = []
    # Limits arbitrage to 3% or more opportunities
    resolution = 0.97
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
                opportunities.append({
                    'vendors': [odds1['vendor'], odds2['vendor'], odds3['vendor']],
                    'odds': [odds1['odds'][0], odds2['odds'][1], odds3['odds'][2]],
                    'total_probability': total_prob
                })
    except Exception as e:
        print(e)

    return opportunities


def collate_links(urls):
    all_links = []
    for url in urls:
        links = get_links(url)
        print(f"{len(links)} links found at {url}")
        all_links.extend(links)
    return all_links


def process_links(links):
    bet_amount = 100
    results = [{'match': link['name'], 'odds': get_odds(link)} for link in links]

    bets = []
    for result in results:
        opportunities = find_arbitrage_opportunities(result)
        if opportunities:
            print(result['match'].strip())
            for opp in opportunities:
                odds = opp['odds']
                inverse_odds_sum = sum(1 / odd for odd in odds)
                bet_amounts = [(bet_amount / odd) / inverse_odds_sum for odd in odds]
                potential_profit = bet_amount / inverse_odds_sum - sum(bet_amounts)
                bets.append({
                    'match': result['match'],
                    'vendors': opp['vendors'],
                    'odds': odds,
                    'bet_amounts': bet_amounts,
                    'potential_profits': potential_profit
                })

    asyncio.run(send_bets(bets))


async def send_bets(bets):
    if not bets:
        print("No bets")
    for bet in bets:
        message = f"Match: {bet['match']}\nBetting Scenario: {bet['vendors']}\n"
        for i, vendor in enumerate(bet['vendors']):
            message += f"Bet: {bet['bet_amounts'][i]:.2f} at odds {bet['odds'][i]}\n"
        message += f"Potential Profit: {bet['potential_profits']:.2f}\n"
        await bot.send_message(chat_id=CHAT_ID, text=message)


def job():
    urls = [
        "https://www.betexplorer.com/football/england/championship/",
        # "https://www.betexplorer.com/football/england/league-one/",
        # "https://www.betexplorer.com/football/england/premier-league/",
        # "https://www.betexplorer.com/football/england/league-two/",
    ]
    all_links = collate_links(urls)
    process_links(all_links)


job()
# if __name__ == "__main__":
#     schedule.every().hour.do(job)  # Schedules the job to run every hour
#
#     while True:
#         schedule.run_pending()
#         time.sleep(1)
