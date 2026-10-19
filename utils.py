"""
utils.py
Fungsi bantu bersama untuk scraper.py dan crawler.py.
"""

import csv
import json
import logging
import os
import re
import time
from datetime import datetime
from urllib.parse import urlparse, urldefrag
from urllib.robotparser import RobotFileParser

import requests

BOT_NAME = "MyPythonBot"
HEADERS = {
    "User-Agent": f"Mozilla/5.0 (compatible; {BOT_NAME}/1.0)",
    "Accept-Language": "id,en;q=0.9",
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "hasil")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("web")


# ---------- Input dari user ----------

def ask_url(prompt="Masukkan URL: "):
    """Minta URL dari user. Jika 'https://' tidak ditulis, otomatis ditambahkan."""
    while True:
        raw = input(prompt).strip()
        if not raw:
            print("URL tidak boleh kosong.")
            continue
        if not re.match(r"^https?://", raw, re.IGNORECASE):
            raw = "https://" + raw
        if urlparse(raw).netloc:
            return normalize_url(raw)
        print("URL tidak valid, coba lagi.")


def ask_int(prompt, default):
    """Minta angka dari user. Enter saja berarti memakai nilai default."""
    raw = input(prompt).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"Input tidak valid, memakai nilai default ({default}).")
        return default


# ---------- URL ----------

def normalize_url(url):
    """
    Samakan bentuk URL supaya halaman yang sama tidak terhitung dua kali:
    hapus #fragment, ubah '/index.html' menjadi '/', dan hapus trailing slash.
    """
    url, _ = urldefrag(url)
    url = re.sub(r"/index\.(html?|php)$", "/", url, flags=re.IGNORECASE)
    return url.rstrip("/")


def get_domain(url):
    """Nama domain tanpa 'www.', untuk perbandingan."""
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def is_same_domain(url, domain):
    return get_domain(url) == domain


# ---------- Fetch ----------

def fetch(url, timeout=10, retries=3, backoff=2.0):
    """
    Ambil HTML dari URL.
    Mengembalikan string HTML, atau None jika gagal atau bukan halaman HTML.
    """
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
        except requests.RequestException as e:
            logger.warning("Gagal koneksi (%d/%d) %s: %s", attempt, retries, url, e)
            if attempt < retries:
                time.sleep(backoff * attempt)
            continue

        code = resp.status_code

        # 429 (terlalu banyak request) dan error server (5xx) dicoba ulang
        if code == 429 or code >= 500:
            logger.warning("HTTP %d (%d/%d) %s", code, attempt, retries, url)
            if attempt < retries:
                time.sleep(backoff * attempt)
            continue

        # Error lain (404, 403, dll) tidak perlu diulang
        if code >= 400:
            logger.warning("HTTP %d, dilewati: %s", code, url)
            return None

        if "text/html" not in resp.headers.get("Content-Type", ""):
            logger.info("Bukan HTML, dilewati: %s", url)
            return None

        if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding
        return resp.text

    return None


# ---------- robots.txt ----------

def load_robots(url):
    """Baca robots.txt dari domain url dan mengembalikan RobotFileParser."""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser()
    try:
        resp = requests.get(robots_url, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            rp.parse(resp.text.splitlines())
        elif resp.status_code in (401, 403):
            rp.disallow_all = True    # server melarang akses robots.txt
        else:
            rp.allow_all = True       # robots.txt tidak ada, berarti semua boleh
    except requests.RequestException as e:
        logger.warning("Tidak bisa membaca robots.txt (%s), dianggap boleh.", e)
        rp.allow_all = True
    return rp


def is_allowed(rp, url):
    return rp.can_fetch(BOT_NAME, url)


def get_crawl_delay(rp):
    """Crawl-delay dari robots.txt dalam detik, atau None jika tidak ada."""
    value = rp.crawl_delay(BOT_NAME)
    return float(value) if value else None


# ---------- Simpan hasil ----------

def make_output_path(prefix, url, ext):
    """Nama file unik per proses: hasil/<prefix>_<domain>_<waktu>.<ext>"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    domain = re.sub(r"[^a-zA-Z0-9]+", "_", get_domain(url)).strip("_")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(OUTPUT_DIR, f"{prefix}_{domain}_{stamp}.{ext}")


def save_csv(rows, path):
    """Simpan list of dict ke CSV. Mengembalikan path, atau None jika tidak ada data."""
    if not rows:
        logger.warning("Tidak ada data untuk disimpan.")
        return None

    fieldnames = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    logger.info("Disimpan ke %s (%d baris)", path, len(rows))
    return path


def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("Disimpan ke %s", path)
    return path
