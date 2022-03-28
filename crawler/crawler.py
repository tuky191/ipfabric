import pathlib
from urllib.parse import urlparse
from queue import Queue
import os
import sys
from pprint import pprint
import asyncio
import aiohttp
import backoff
from bs4 import BeautifulSoup
import logging
from urllib.parse import urljoin
import magic
from yaspin import yaspin
from yaspin.spinners import Spinners
import time

logging.basicConfig(level=logging.CRITICAL)
if os.name == 'nt':
    os.system('cls')
elif os.name == 'posix':
    os.system('clear')


def no_retry_code(e):
    # dont retry request if 404 received
    if isinstance(e, aiohttp.ClientResponseError):
        return e.status == 404


class urlExplorer():
    download_q = Queue()
    queued_urls = []
    root_url = ''
    root_url_parsed = ''

    def __init__(self, url):
        self.root_url = url
        self.root_url_parsed = urlparse(url)

    async def soupSave(self, tag, pagefolder, url, inner='src'):
        logging.debug("Downloading: %s", tag.get(inner))
        try:
            filename = os.path.basename(tag[inner])
            fileurl = urljoin(url, tag.get(inner))
            filepath = os.path.join(pagefolder, filename)
            tag[inner] = os.path.join(os.path.basename(pagefolder), filename)
            if not os.path.isfile(filepath):  # was not downloaded
                with open(filepath, 'wb') as file:
                    filebin = await self.request_with_retries(url=fileurl,
                                                              method='get')
                    file.write(filebin)
        except Exception as exc:
            logging.warning("soupSave: %s", exc)

    async def process_url(self, url, sp):

        tasks = []
        logging.info("processing: %s", url)
        url_parsed = urlparse(url)
        pagefolder = url_parsed.netloc if url_parsed.path == '/' else url_parsed.netloc + url_parsed.path
        response = await self.request_with_retries(url=url, method='GET')
        if response is None:
            return True
        response_type = magic.from_buffer(response)
        logging.debug("Found url is %s:", response_type)
        sp.text = f'{url}'
        #In case explored url is not a html page, but a file, save file
        if 'HTML' not in response_type:

            filename = pagefolder
            folder_list = pagefolder.split('/')
            folder_list.pop()
            pathlib.Path('/'.join(folder_list)).mkdir(parents=True,
                                                      exist_ok=True)
            with open(filename, 'wb') as file:
                file.write(response)
            return True

        self.extract(response)
        soup = BeautifulSoup(response, "html.parser")
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
        with open(os.path.join(pagefolder, 'index.html'), 'w') as file:
            file.write(soup.prettify())

    async def download(self):
        tasks = []

        with yaspin(Spinners.dots8Bit, text="Exploring!") as sp:
            await self.process_url(self.download_q.get(), sp)
            while not self.download_q.empty():
                logging.info('pending %s items', self.download_q.qsize())

                for _ in range(10):
                    if self.download_q.empty():
                        logging.info('processing q is empty, finishing up...')
                        break
                    url = self.download_q.get()
                    tasks.append(self.process_url(url, sp))
                await asyncio.gather(*tasks)
                tasks = []

    def extract(self, response):
        if not response:
            return True
        soup = BeautifulSoup(response, "html.parser")
        for link in soup.find_all('a'):
            href = link.get('href')
            if not href:
                continue
            found_parsed_url = urlparse(href)
            # We want only explore from the root url onwards
            if self.root_url not in href:
                continue
            # Already crawled that url
            if href in self.queued_urls:
                continue
            if self.root_url_parsed.netloc == found_parsed_url.netloc and self.root_url_parsed.path != found_parsed_url.path:
                self.queued_urls.append(href)
                logging.info("adding %s to the q", href)
                self.download_q.put(href)

    def run(self):
        start = time.time()
        self.download_q.put(self.root_url)
        asyncio.run(self.download())
        end = time.time()
        print(
            f'Explored #{len(self.queued_urls)} paths in {int(end - start)} seconds'
        )

    @backoff.on_exception(backoff.expo,
                          (aiohttp.ClientError, asyncio.TimeoutError),
                          max_tries=3,
                          max_time=20,
                          giveup=no_retry_code)
    async def request_with_retries(self, **kwargs):
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.request(timeout=timeout,
                                       raise_for_status=True,
                                       **kwargs) as response:
                if response is not None:
                    return await response.read()

        except Exception as e:
            logging.warning("request_with_retries: %s", e)


if __name__ == '__main__':
    explorer = urlExplorer(url='https://ipfabric.io/')
    explorer.run()
