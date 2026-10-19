"""
crawler.py
CRAWLING: menelusuri link dalam satu domain (BFS) dan mengambil info tiap halaman.

Jalankan:  python crawler.py
"""

import time
from collections import deque
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from utils import (
    ask_int, ask_url, fetch, get_crawl_delay, get_domain, is_allowed,
    is_same_domain, load_robots, make_output_path, normalize_url, save_csv, logger,
)

# Ekstensi file yang bukan halaman HTML, tidak perlu dikunjungi
SKIP_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".pdf", ".zip", ".rar", ".mp3", ".mp4", ".css", ".js", ".xml",
)


class Crawler:
    def __init__(self, start_url, max_pages=20, max_depth=2, delay=1.0, respect_robots=True):
        self.start_url = normalize_url(start_url)
        self.domain = get_domain(self.start_url)
        self.max_pages = max_pages   # batas jumlah halaman yang disimpan
        self.max_depth = max_depth   # batas kedalaman dari halaman awal
        self.delay = delay           # jeda (detik) antar request

        self.robots = load_robots(self.start_url) if respect_robots else None
        if self.robots is not None:
            crawl_delay = get_crawl_delay(self.robots)
            if crawl_delay:
                self.delay = max(self.delay, crawl_delay)

        self.visited = set()
        self.results = []

    def extract_links(self, soup, base_url):
        """Ambil link internal (satu domain) dari halaman."""
        links = set()
        for a in soup.find_all("a", href=True):
            link = normalize_url(urljoin(base_url, a["href"]))
            if urlparse(link).scheme not in ("http", "https"):
                continue
            if not is_same_domain(link, self.domain):
                continue
            if link.lower().endswith(SKIP_EXTENSIONS):
                continue
            links.add(link)
        return links

    def parse_page(self, soup, url, depth):
        """Data yang diambil dari tiap halaman. Tambah field di sini jika perlu."""
        title = soup.title.get_text(strip=True) if soup.title else ""
        desc_tag = soup.find("meta", attrs={"name": "description"})
        h1 = soup.find("h1")
        return {
            "url": url,
            "depth": depth,
            "title": title,
            "description": desc_tag.get("content", "").strip() if desc_tag else "",
            "h1": h1.get_text(strip=True) if h1 else "",
        }

    def crawl(self):
        queue = deque([(self.start_url, 0)])
        self.visited.add(self.start_url)

        try:
            while queue and len(self.results) < self.max_pages:
                url, depth = queue.popleft()

                if self.robots is not None and not is_allowed(self.robots, url):
                    logger.info("Dilarang robots.txt, dilewati: %s", url)
                    continue

                html = fetch(url)
                time.sleep(self.delay)
                if html is None:
                    continue

                soup = BeautifulSoup(html, "lxml")
                self.results.append(self.parse_page(soup, url, depth))
                logger.info("[%d/%d] kedalaman %d: %s",
                            len(self.results), self.max_pages, depth, url)

                if depth >= self.max_depth:
                    continue

                for link in self.extract_links(soup, url):
                    if link not in self.visited:
                        self.visited.add(link)
                        queue.append((link, depth + 1))

        except KeyboardInterrupt:
            logger.warning("Dihentikan manual. Data yang sudah terkumpul tetap disimpan.")

        logger.info("Selesai. Total halaman: %d", len(self.results))
        return self.results


def main():
    print("=== CRAWLER ===")
    url = ask_url("Masukkan URL awal: ")
    max_pages = ask_int("Maksimal halaman (default 20): ", 20)
    max_depth = ask_int("Kedalaman maksimal (default 2): ", 2)
    delay = ask_int("Jeda antar request dalam detik (default 1): ", 1)

    crawler = Crawler(url, max_pages=max_pages, max_depth=max_depth, delay=delay)
    print(f"Mulai crawling {url} (jeda {crawler.delay} detik)...")
    results = crawler.crawl()

    path = save_csv(results, make_output_path("crawl", url, "csv"))
    if path:
        print(f"Selesai. {len(results)} halaman disimpan ke: {path}")
    else:
        print("Tidak ada halaman yang berhasil diambil. Cek URL atau koneksi.")


if __name__ == "__main__":
    main()
