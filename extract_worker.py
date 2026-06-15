#!/usr/bin/env python3
"""
Daleel GitHub Actions Worker
Usage:
  python extract_worker.py <prefix> <skip_from> <skip_to>
  python extract_worker.py SMALL   (يعالج 051,052,057,058 بالترتيب)
"""
import requests, csv, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

import os
_BASE = os.environ.get("PROXY_URL", "https://daleel.mohaisentech.com").rstrip("/")
URL = f"{_BASE}/api/app/daleel-admin/contacts/search"
HEADERS = {
    "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "content-type": "application/json",
    "accept": "application/json",
}
PAGE_SIZE = 200
WORKERS   = 3

# ─── جلب صفحة واحدة مع retry ────────────────────────────────
def fetch(prefix, skip, attempt=0):
    try:
        r = requests.post(URL,
            json={"name": "", "phoneNumber": prefix, "skip": skip, "take": PAGE_SIZE},
            headers=HEADERS, timeout=50)
        if r.status_code == 429:
            wait = int(r.headers.get("retry-after", 30))
            print(f"  [{prefix}:{skip}] rate-limit → wait {wait}s", flush=True)
            time.sleep(wait)
            return fetch(prefix, skip, attempt)
        if r.status_code != 200:
            raise Exception(f"HTTP {r.status_code}")
        return r.json().get("items", [])
    except Exception as e:
        if attempt < 6:
            wait = min(10 * (2 ** attempt), 180)
            print(f"  [{prefix}:{skip}] retry {attempt+1} in {wait}s ({e})", flush=True)
            time.sleep(wait)
            return fetch(prefix, skip, attempt + 1)
        print(f"  [{prefix}:{skip}] FAILED — تخطي", flush=True)
        return []

# ─── معالجة prefix واحد ────────────────────────────────────
def run_prefix(prefix, skip_from, skip_to):
    out   = f"data_{prefix}_{skip_from}.csv"
    skips = list(range(skip_from, skip_to, PAGE_SIZE))
    n     = len(skips)
    print(f"\n[{prefix}] {n:,} صفحة | skip {skip_from:,} → {skip_to:,}", flush=True)

    saved = done = 0
    t0    = time.time()

    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["api_id", "phone", "name", "submitted_by", "prefix", "added_date"])

        for i in range(0, n, WORKERS * 4):
            batch = skips[i : i + WORKERS * 4]

            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                futures = {ex.submit(fetch, prefix, sk): sk for sk in batch}
                for fut in as_completed(futures):
                    items = fut.result()
                    for item in items:
                        name = (item.get("name") or "").strip()
                        if name and name != "test1":
                            w.writerow([
                                item.get("id", ""),
                                item.get("phoneNumber", ""),
                                name,
                                item.get("submittedUser", ""),
                                item.get("phonePrefix", prefix),
                                item.get("addedDate", ""),
                            ])
                            saved += 1
            done += len(batch)
            f.flush()   # حفظ دوري (لو انقطع الـ job)

            elapsed = time.time() - t0 or 0.001
            rate    = done * PAGE_SIZE / elapsed
            eta     = (n - done) * PAGE_SIZE / rate if rate else 0
            print(
                f"  [{prefix}] {done/n*100:5.1f}% | {done:,}/{n:,} صفحة | "
                f"{saved:,} محفوظ | {rate:.0f} س/ث | ETA {eta/60:.0f}د",
                flush=True
            )

    mb = os.path.getsize(out) / 1e6
    print(f"✓ [{prefix}] {saved:,} سجل → {out} ({mb:.1f} MB)", flush=True)
    return saved

# ─── main ──────────────────────────────────────────────────
if __name__ == "__main__":
    mode = sys.argv[1]

    if mode == "SMALL":
        # البوادئ الصغيرة بالترتيب
        run_prefix("051", 12000,  202000)
        run_prefix("052", 0,      159200)
        run_prefix("057", 0,      572800)
        run_prefix("058", 0,      627400)
    else:
        run_prefix(mode, int(sys.argv[2]), int(sys.argv[3]))
