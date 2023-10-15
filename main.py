# This is a Python script for the downloading on the FAO pages.
# example URL: https://www.fao.org/nutrition/education/food-dietary-guidelines/regions/countries/kenya/en/
#
# Created at 14 Oct 2023 by Yi
# NB. delete the temporary Pipenv Env at: /Users/mario/.local/share/virtualenvs/fao-download-NDpTkHv4

import re
import time

from tqdm import tqdm
from pathlib import Path

import pdfkit
import requests
from bs4 import BeautifulSoup as Soup

# ENV variables
CACHE_PATH = Path('cache')
CACHE_PATH.mkdir(parents=True, exist_ok=True)
SAVE_PATH = Path('save')
SAVE_PATH.mkdir(parents=True, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
}


def parse(c: str, url: str, path=None, headers={}, pause=1, stepwise=True) -> Path:
    """
    Main page parse for the page content and return a data dict

    :param: c: the country for fetching
    :param: url: the target url in string
    :param: path: the output directory, default as CACHE_PATH
    :param: headers: headers for loading, default as None
    :param: pause: pause parsing for seconds
    :param: stepwise: True=make cache, False=no cache, with version control, formatted in './country-mmddHHMMSS.json'
    :return: Dictionary-like data
    """

    # avoid duplicates
    page_file = SAVE_PATH / f'fao-description-{c}.pdf'
    if page_file.exists():
        print(f'Country duplicated: {c}')
        return page_file

    if pause:
        time.sleep(pause)

    response = requests.get(url, headers=headers)
    assert response.status_code == 200, f'invalid url: {response.url}'
    page2pdf(response.content, page_file)
    if stepwise:
        f1 = CACHE_PATH / f'{c}-url'
        f1.write_bytes(response.content)

    soup = Soup(response.content, 'lxml')
    found = soup.find_all(href=re.compile(r'.*.pdf'))
    assert len(found) > 0, 'invalid search condition'

    # NB. might have multiple pdf links
    for idx, each in enumerate(found):
        pdf_link = each.get('href')
        download = requests.get(pdf_link, headers=headers)
        assert download.status_code == 200, f'invalid pdf url: {download.url}'
        if stepwise:
            f2 = CACHE_PATH / f'{c}-pdf{idx}'
            f2.write_bytes(download.content)

        # generate PDF with correct filename
        fn = f'food-guideline-{c}{idx}.pdf'
        if path is None:
            path = SAVE_PATH

        gen_pdf(download.content, fn, path)


def gen_pdf(content: bytes, filename: str, path: Path) -> Path:
    """
    Encode page content in bytes to generate PDFs

    :param: content: page content in bytes
    :param: filename: the filename for the generated PDF, in string
    :param: path: Path-like object, the parent directory of generated PDF
    :return: Path-like object for the generated PDF
    """
    file = path / filename
    file.write_bytes(content)
    assert file.exists(), f'{file.name} failed!'
    return file


PAGE2PDF_OPTIONS = {
    'page-size': 'A4',
    'margin-top': '0.75in',
    'margin-right': '0.75in',
    'margin-bottom': '0.75in',
    'margin-left': '0.75in'
}


def page2pdf(content: bytes, cache_file: Path, options=PAGE2PDF_OPTIONS) -> Path:
    """
    Convert a web page to a PDF file

    :param: content: page content in bytes
    :param: cache_file: the file path for making cache
    :param: options: wkhtmltopdf options, see https://wkhtmltopdf.org/usage/wkhtmltopdf.txt
    :return: a Path-like object for the generated PDF
    """
    content = content.decode('utf8')  # bytes -> string
    pdfkit.from_string(content, str(cache_file), options=options)
    assert cache_file.exists(), f'{cache_file.name} failed!'
    return cache_file


def get_countries(region: str, url: str, headers={}) -> dict:
    """
    Fetch countries shown on the regional page

    :param region: a string-like region name
    :param url: the url for regional page
    :param headers: request headers, default as HEADERS
    :return: a dictionary of 'region-countries' structure
    """
    response = requests.get(url, headers=headers)
    soup = Soup(response.content, 'lxml')
    tds = soup.find_all('td')
    cs = [it.get_text() for it in tds if not it.find_all('a')]
    return {region: cs}


if __name__ == '__main__':
    import json

    # unittest: single URL
    url = 'https://www.fao.org/nutrition/education/food-dietary-guidelines/regions/countries/kenya/en/'
    f = parse('kenya', url, headers=HEADERS)

    # fetch regions
    region_file = Path('fao-regions.json')
    if region_file.exists():
        countries = json.loads(region_file.read_text('utf8'))
    else:
        base_url = 'https://www.fao.org/nutrition/education/food-dietary-guidelines/regions/{}/en/'
        regions = ['africa', 'asia-pacific', 'europe', 'latin-america-caribbean', 'near-east', 'north-america']
        countries = {}
        for r in tqdm(regions, desc='Region Fetching'):
            url = base_url.format(r)
            fetch = get_countries(r, url)
            countries.update(fetch)
            time.sleep(2)

    # fetch countries
    base_url = 'https://www.fao.org/nutrition/education/food-dietary-guidelines/regions/countries/{}/en/'
    for r, li in countries.items():
        for c in tqdm(li, desc=f'Fetching region: {r}'):
            url = base_url.format('-'.join(c.lower().split()))
            try:
                parse(c, url, pause=1.5, stepwise=True)
            except Exception as e:
                print(f'Failed on {c} with:\n{e}')

    # which countries we failed?
    with_desc = [it.name.replace('.pdf', '').split('-')[-1] for it in Path('save').glob('fao-description-*.pdf')]
    with_pdf = [it.name.replace('0.pdf', '').split('-')[-1] for it in Path('save').glob('food-*0.pdf')]
    diff = set(with_desc).difference(set(with_pdf))
    clist = '\n'.join(diff)
    print(f'Found {len(diff)} failed countries:\n{clist}')
