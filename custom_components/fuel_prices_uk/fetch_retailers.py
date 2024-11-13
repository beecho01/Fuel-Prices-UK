import requests

from bs4 import BeautifulSoup


def fetch_fuel_data(url):
    try:
        # Send a GET request to fetch the raw HTML content
        response = requests.get(url)
        response.raise_for_status()  # Raises HTTPError for bad responses
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching the URL: {e}")
        return None


def parse_fuel_data(html_data):
    soup = BeautifulSoup(html_data, "html.parser")
    table = soup.find("table")

    if not table:
        print("Could not find the data table in the HTML.")
        return []

    rows = table.find("tbody").find_all("tr")
    retailers = []

    for row in rows:
        cells = row.find_all("td")
        if len(cells) >= 2:
            retailer = cells[0].get_text(strip=True)
            url = cells[1].get_text(strip=True)
            retailers.append({"retailer": retailer, "url": url})
        else:
            print(f"Skipping row due to insufficient cells: {row}")

    return retailers


def fetch_fuel_retailers():
    url = "https://www.gov.uk/guidance/access-fuel-price-data"
    html_data = fetch_fuel_data(url)

    if html_data:
        retailers = parse_fuel_data(html_data)
        return retailers
