import json
import pathlib
from urllib.parse import urlparse
from queue import Queue
import os
import sys
from pprint import pprint
import asyncio
import requests
import aiohttp
import backoff
from bs4 import BeautifulSoup
import logging
from urllib.parse import urljoin
logging.basicConfig(level=logging.INFO)


def no_retry_code(e):
    # dont retry request if 404 received
    if isinstance(e, aiohttp.ClientResponseError):
        return e.status == 404


class urlExplorer():

    downloaded_urls = []
    paths_taken = []
    root_url = ''
    root_url_parsed = ''

    def __init__(self, url):
        self.root_url = url
        self.root_url_parsed = urlparse(url)

    async def soupSave(self, tag, pagefolder, url, inner='src'):
        logging.debug("Downloading: %s", tag.get(inner))
        try:
            filename = os.path.basename(
                tag[inner])
            fileurl = urljoin(url, tag.get(inner))
            filepath = os.path.join(pagefolder, filename)
            tag[inner] = os.path.join(
                os.path.basename(pagefolder), filename)
            if not os.path.isfile(filepath):  # was not downloaded
                with open(filepath, 'wb') as file:
                    filebin = await self.request_with_retries(
                        url=fileurl, method='get')
                    file.write(filebin)
        except Exception as exc:
            print(exc, file=sys.stderr)

    async def download(self, response, pagefilename='index'):
        url = response.url
        url_parsed = urlparse(url)
        tasks = []
        soup = BeautifulSoup(response.text, "html.parser")
        pagefolder = url_parsed.netloc if url_parsed.path == '/' else url_parsed.netloc + url_parsed.path
        if pagefolder in self.paths_taken:
            logging.info("%s is already downloaded", pagefolder)
            return True
        else:
            self.paths_taken.append(pagefolder)

        # create folder if not exists
        pathlib.Path(pagefolder).mkdir(parents=True, exist_ok=True)
        for tag in soup.findAll(['script', 'img', 'style']):
            inner = 'data-breeze' if tag.get('data-breeze') else 'src'
            try:
                element = tag.get('data-breeze')
                if not tag.get(inner).startswith('http'):
                    logging.debug("Not a downloadable element: %s", element)
                    continue
            except AttributeError:
                logging.debug("Not a downloadable empty element:")
                continue
            tasks.append(self.soupSave(tag, pagefolder, url, inner))

        await asyncio.gather(*tasks)
        # save the main page
        with open(os.path.join(pagefolder, pagefilename+'.html'), 'w') as file:
            file.write(soup.prettify())

    def extract(self, response):
        hrefs = []
        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.find_all('a'):
            href = link.get('href')
            if not href:
                continue
            found_parsed_url = urlparse(href)
            # We want only explore from the root url onwards
            if self.root_url not in href:
                continue
            # Already crawled that url
            if href in self.downloaded_urls:
                continue
            if self.root_url_parsed.netloc == found_parsed_url.netloc and self.root_url_parsed.path != found_parsed_url.path and href not in hrefs:
                hrefs.append(link.get('href'))
        return hrefs

    def run(self, url=None):
        if not url:
            url = self.root_url
        if url in self.downloaded_urls:
            logging.info("%s is already downloaded", url)
            return True
        else:
            self.downloaded_urls.append(url)
        logging.info("processing: %s", url)
        page_content = self.request_with_retries_sync(
            url=url, method='GET')
        if not page_content:
            return True
        asyncio.run(
            self.download(response=page_content))
        urls = self.extract(page_content)
        for url in urls:
            self.run(url=url)
        return True

    @backoff.on_exception(
        backoff.expo, (requests.exceptions.Timeout,
                       requests.exceptions.ConnectionError,
                       requests.exceptions.RequestException,
                       ), max_tries=3, max_time=20, giveup=no_retry_code)
    def request_with_retries_sync(self, **kwargs):
        try:
            r = requests.request(**kwargs, timeout=30)
            r.raise_for_status()
            return r
        except Exception as e:
            logging.error("request_with_retries_sync: %s", json.dumps(e))

    @backoff.on_exception(backoff.expo, (aiohttp.ClientError, asyncio.TimeoutError), max_tries=3, max_time=20, giveup=no_retry_code)
    async def request_with_retries(self, **kwargs):
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.request(timeout=timeout, raise_for_status=True, **kwargs) as response:
                return await response.read()
        except Exception as e:
            logging.error("request_with_retries: %s", json.dumps(e))


if __name__ == '__main__':
    explorer = urlExplorer(
        url='https://ipfabric.io/')
    explorer.run()
