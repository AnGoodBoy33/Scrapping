"""
scraper.py
SCRAPING: ambil data dari halaman yang di masukkan.

Jalankan:  python scraper.py
"""

import json
import time
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from utils import (
    ask_int, ask_url, fetch, get_domain, is_same_domain,
    make_output_path, normalize_url, save_csv, save_json, logger,
)

DELAY = 1.0  # jeda (detik) antar halaman

# Selector siap pakai untuk situs latihan. Kunci = nama domain.
PRESETS = {
    "books.toscrape.com": {
        "item": "article.product_pod",
        "fields": {
            "judul": ("h3 a", "title"),
            "harga": ("p.price_color", None),
        },
    },
    "quotes.toscrape.com": {
        "item": "div.quote",
        "fields": {
            "teks": ("span.text", None),
            "penulis": ("small.author", None),
        },
    },
}


def get_value(el, attr=None):
    """Ambil atribut (mis. title, href) jika attr diisi, kalau tidak ambil teksnya."""
    if el is None:
        return ""
    if attr:
        return el.get(attr, "")
    return el.get_text(strip=True)


def find_next_page(soup, current_url):
    """Cari link halaman berikutnya (tombol next). None jika tidak ada."""
    a = soup.select_one("li.next a, a[rel='next']")
    if a and a.get("href"):
        return normalize_url(urljoin(current_url, a["href"]))
    return None


def parse_fields(text):
    """
    Ubah teks dari user menjadi dict field.
    Format: nama=selector;nama=selector@atribut
    Contoh: judul=h3 a@title;harga=p.price_color
    """
    fields = {}
    for part in text.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        name, rest = part.split("=", 1)
        attr = None
        if "@" in rest:
            rest, attr = rest.rsplit("@", 1)
            attr = attr.strip()
        fields[name.strip()] = (rest.strip(), attr)
    return fields


# ---------- Mode 1: info halaman ----------

def scrape_page_info(soup, url):
    title = soup.title.get_text(strip=True) if soup.title else ""
    desc_tag = soup.find("meta", attrs={"name": "description"})
    h1 = soup.find("h1")
    return {
        "url": url,
        "title": title,
        "description": desc_tag.get("content", "").strip() if desc_tag else "",
        "h1": h1.get_text(strip=True) if h1 else "",
        "jumlah_h2": len(soup.find_all("h2")),
        "jumlah_link": len(soup.find_all("a", href=True)),
        "jumlah_gambar": len(soup.find_all("img")),
    }


# ---------- Mode 2: semua link ----------

def scrape_links(soup, url):
    domain = get_domain(url)
    rows, seen = [], set()
    for a in soup.find_all("a", href=True):
        full = normalize_url(urljoin(url, a["href"]))
        if urlparse(full).scheme not in ("http", "https") or full in seen:
            continue
        seen.add(full)
        rows.append({
            "teks": a.get_text(strip=True) or a.get("title", ""),
            "url": full,
            "tipe": "internal" if is_same_domain(full, domain) else "eksternal",
        })
    return rows


# ---------- Mode 3: daftar item (dengan pagination) ----------

def scrape_items(start_url, item_selector, fields, max_pages):
    rows, visited = [], set()
    url = start_url

    for page_no in range(1, max_pages + 1):
        if not url or url in visited:
            break
        visited.add(url)

        html = fetch(url)
        if html is None:
            break

        soup = BeautifulSoup(html, "lxml")
        items = soup.select(item_selector)
        logger.info("Halaman %d: %d item di %s", page_no, len(items), url)

        for item in items:
            row = {"sumber": url}
            for name, (sel, attr) in fields.items():
                row[name] = get_value(item.select_one(sel), attr)
            rows.append(row)

        url = find_next_page(soup, url)
        if url:
            time.sleep(DELAY)

    return rows


def print_preview(rows, n=5):
    for row in rows[:n]:
        print(json.dumps(row, ensure_ascii=False))
    if len(rows) > n:
        print(f"... dan {len(rows) - n} baris lainnya")


def main():
    print("=== SCRAPER ===")
    url = ask_url("Masukkan URL: ")
    print(
        "\nPilih mode:\n"
        "  1 = Info halaman (judul, deskripsi, jumlah link)\n"
        "  2 = Semua link di halaman\n"
        "  3 = Daftar item (otomatis untuk books/quotes; situs lain isi selector sendiri)"
    )
    mode = input("Mode (1/2/3): ").strip()

    if mode == "1":
        html = fetch(url)
        if html is None:
            print("Gagal mengambil halaman. Cek URL atau koneksi.")
            return
        info = scrape_page_info(BeautifulSoup(html, "lxml"), url)
        print(json.dumps(info, ensure_ascii=False, indent=2))
        path = save_json(info, make_output_path("info", url, "json"))

    elif mode == "2":
        html = fetch(url)
        if html is None:
            print("Gagal mengambil halaman. Cek URL atau koneksi.")
            return
        rows = scrape_links(BeautifulSoup(html, "lxml"), url)
        print(f"{len(rows)} link ditemukan.")
        print_preview(rows)
        path = save_csv(rows, make_output_path("links", url, "csv"))

    elif mode == "3":
        domain = get_domain(url)
        if domain in PRESETS:
            item_selector = PRESETS[domain]["item"]
            fields = PRESETS[domain]["fields"]
            print(f"Memakai selector bawaan untuk {domain}.")
        else:
            item_selector = input("Selector item (mis. div.product): ").strip()
            fields = parse_fields(input("Field (format nama=selector;nama=selector@atribut): "))
            if not item_selector or not fields:
                print("Selector item atau field kosong.")
                return

        max_pages = ask_int("Jumlah halaman yang diambil (default 3): ", 3)
        rows = scrape_items(url, item_selector, fields, max_pages)
        if not rows:
            print("Tidak ada item ditemukan. Cek URL atau selector.")
            return
        print(f"{len(rows)} item ditemukan.")
        print_preview(rows)
        path = save_csv(rows, make_output_path("items", url, "csv"))

    else:
        print("Mode tidak dikenal.")
        return

    if path:
        print(f"Hasil disimpan ke: {path}")


if __name__ == "__main__":
    main()
