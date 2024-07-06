import requests
from bs4 import BeautifulSoup
import re
from playwright.sync_api import sync_playwright


def get_links(url_retrieval):
    response = requests.get(url_retrieval)

    if response.status_code == 200:
        print("HTTP request successful.")
    else:
        print("Failed to send HTTP request. Status code: ", response.status_code)

    link_soup = BeautifulSoup(response.text, 'html.parser')
    table = link_soup.find('table', attrs={'class': 'table-main'})

    if table is None:
        return get_links_main_page(url_retrieval)

    sections = table.find_all('td', attrs={'class': 'h-text-left'})

    links = []
    if len(sections) == 0:
        a_tags = table.find_all('a', attrs={'class': 'in-match'})
        for a_tag in a_tags:
            link = a_tag.get('href')
            name = a_tag.text
            links.append({'name': name, 'link': link})
        return links

    for section in sections:
        link = section.find('a').attrs['href']
        name = section.find('a').text
        links.append({'name': name, 'link': link})

    return links


def get_links_main_page(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        text = page.get_by_text("All Matches", exact=True)
        text.wait_for()
        html = page.content()
        soup = BeautifulSoup(html, 'html.parser')

    main_div = soup.find('div', attrs={'id': 'nr-ko-all'})
    a_tags = main_div.find_all('a', attrs={'class': 'table-main__participants'})

    links = []
    for a_tag in a_tags:
        link = a_tag.attrs['href']
        name = a_tag.text
        links.append({'name': name, 'link': link})

    return links


def get_odds(link):
    results = []
    url = "https://www.betexplorer.com" + link['link']
    print(url)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url)
            all_odds = page.get_by_text('All Odds', exact=True)
            all_odds.wait_for()
            all_odds.click()
            html = page.content()
            soup = BeautifulSoup(html, 'html.parser')

        table = soup.find('tbody', attrs={'id': 'best-odds-0'})
        entries = table.find_all('tr')

        for entry in entries:
            found_odds = []
            name = \
            entry.find('td', attrs={'class': 'h-text-left under-s-only h-text-pl10'}).find('a').find('span').attrs[
                'title']
            odds = entry.find_all('td', attrs={'class': 'table-main__detail-odds'})
            for odd in odds:
                found_odds.append(odd.find('span').text)
            results.append({'vendor': name, 'odds': found_odds})
    except Exception as e:
        print(e)

    return results


def find_arbitrage_opportunities(data):
    import itertools

    opportunities = []
    try:
        # Convert odds to float and strip spaces
        for item in data['odds']:
            item['odds'] = [float(od.strip()) for od in item['odds']]

        # Generate all combinations of different vendors
        for combination in itertools.combinations(data['odds'], 3):
            odds1, odds2, odds3 = combination

            # Calculate implied probabilities for each outcome
            prob1 = 1 / odds1['odds'][0]
            prob2 = 1 / odds2['odds'][1]
            prob3 = 1 / odds3['odds'][2]

            total_prob = prob1 + prob2 + prob3

            # Check if the total implied probability is less than 1
            if total_prob < 1:
                opportunities.append({
                    'vendors': [odds1['vendor'], odds2['vendor'], odds3['vendor']],
                    'odds': [odds1['odds'][0], odds2['odds'][1], odds3['odds'][2]],
                    'total_probability': total_prob
                })
    except Exception as e:
        print(e)

    return opportunities


'''
urls = ["https://www.betexplorer.com/football/england/championship/",
        "https://www.betexplorer.com/football/england/league-one/",
        "https://www.betexplorer.com/football/england/premier-league/",
        "https://www.betexplorer.com/football/england/league-two/",
        "https://www.betexplorer.com/football/",
        "https://www.betexplorer.com/",]
'''
urls = ["https://www.betexplorer.com/football/england/premier-league/",
        "https://www.betexplorer.com/football/england/league-two/",
        "https://www.betexplorer.com/football/",
        "https://www.betexplorer.com/", ]
for url in urls:
    links = get_links(url)
    results = []
    print(len(links), "links found")
    i = 0
    for link in links:
        i += 1
        print(i, "link")
        odds_results = get_odds(link)
        results.append({'match': link['name'], 'odds': odds_results})

    bet_amount = 100
    bets = []
    for result in results:
        output = find_arbitrage_opportunities(result)
        if len(output) > 0:
            print(result['match'].strip())
            for vendor in output:
                odds = vendor['odds']
                inverse_odds_sum = sum([1 / odd for odd in odds])
                bet_amounts = [(bet_amount / odd) / inverse_odds_sum for odd in odds]

                # Calculate potential profit
                potential_profits = [bet_amount / inverse_odds_sum - sum(bet_amounts)] * len(odds)
                bets.append({
                    'vendors': vendor,
                    'odds': odds,
                    'bet_amounts': bet_amounts,
                    'potential_profits': potential_profits
                })

    for bet in bets:
        print(f"Betting Scenario: {bet['vendors']}")
        for i, vendor in enumerate(bet['vendors']):
            print(f"Bet: {bet['bet_amounts'][i]:.2f} at odds {bet['odds'][i]}")
        print(f"Potential Profit: {bet['potential_profits'][0]:.2f}\n")

    with open('bets.txt', 'a') as file:
        for bet in bets:
            file.write(f"Betting Scenario: {bet['vendors']}\n")
            for i, vendor in enumerate(bet['vendors']):
                file.write(f"Bet: {bet['bet_amounts'][i]:.2f} at odds {bet['odds'][i]}\n")
            file.write(f"Potential Profit: {bet['potential_profits'][0]:.2f}\n")
