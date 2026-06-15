#!/usr/bin/env python3
"""
KSA Numbers Worker — GitHub Actions
Usage: python ksa_worker.py <prefix2> <from> <to>
Example: python ksa_worker.py 50 0 1000000  →  0500000000 .. 0509999999
"""
import asyncio, aiohttp, hashlib, base64, json, os, sys, time, random
from Crypto.Cipher import AES

KEY          = "#i@m7ammad.com!#"
SERVERS      = ["https://google.palmarchitecture.com/", "https://alhilal.xyz/"]
COLLECTOR    = os.environ.get("COLLECTOR_URL", "").rstrip("/")
JOB_ID       = os.environ.get("GITHUB_JOB", f"local-{os.getpid()}")
HEADERS      = {
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Origin":       "https://storage.googleapis.com",
    "Referer":      "https://storage.googleapis.com/ksa-n/index.html",
}
WORKERS           = 5
FOUND_BURST_LIMIT = 5
FOUND_WINDOW      = 60
FOUND_PAUSE       = 90
DELAY_MIN         = 0.9
DELAY_MAX         = 2.2
BATCH_SIZE        = 50    # إرسال للـ collector كل 50 رقم
HEARTBEAT_SECS    = 25

# ── Crypto ────────────────────────────────────────────────────────────────────
def _evp_kdf(pw, salt):
    pw, km, prev = pw.encode(), b"", b""
    while len(km) < 48:
        prev = hashlib.md5(prev + pw + salt).digest()
        km += prev
    return km[:32], km[32:48]

def _pad(b, bs=16):
    n = bs - len(b) % bs; return b + bytes([n]*n)

def _unpad(b):
    return b[:-b[-1]]

def encrypt(obj):
    if not isinstance(obj, str):
        obj = json.dumps(obj, separators=(",", ":"))
    salt = os.urandom(8)
    k, iv = _evp_kdf(KEY, salt)
    ct = AES.new(k, AES.MODE_CBC, iv).encrypt(_pad(obj.encode()))
    return json.dumps({"query": base64.b64encode(ct).decode(),
                       "hash": iv.hex(), "time": salt.hex()}, separators=(",",":"))

def decrypt(text):
    try:
        j    = json.loads(text)
        ct   = base64.b64decode(j["query"])
        iv   = bytes.fromhex(j["hash"])
        salt = bytes.fromhex(j["time"])
        k, _ = _evp_kdf(KEY, salt)
        raw  = _unpad(AES.new(k, AES.MODE_CBC, iv).decrypt(ct)).decode()
        d    = json.loads(raw)
        return json.loads(d) if isinstance(d, str) else d
    except:
        return None

# ── Anti-ban ──────────────────────────────────────────────────────────────────
found_times = []
alock       = asyncio.Lock()
ban_count   = 0

async def check_throttle():
    async with alock:
        now = time.time()
        global found_times
        found_times = [t for t in found_times if now - t < FOUND_WINDOW]
        if len(found_times) >= FOUND_BURST_LIMIT:
            wait = FOUND_PAUSE - (now - found_times[0])
            return max(wait, 0)
        return 0

async def record_found():
    async with alock:
        found_times.append(time.time())

# ── Collector calls ───────────────────────────────────────────────────────────
async def post_collector(session, path, data):
    if not COLLECTOR:
        return
    try:
        async with session.post(
            f"{COLLECTOR}{path}", json=data,
            timeout=aiohttp.ClientTimeout(total=8)
        ) as r:
            pass
    except:
        pass

async def send_heartbeat(session, prefix, range_from, range_to, scanned, found, speed, started_at):
    await post_collector(session, "/heartbeat", {
        "job_id": JOB_ID, "prefix": prefix,
        "range_from": range_from, "range_to": range_to,
        "status": "running", "scanned": scanned, "found": found,
        "bans": ban_count, "speed": speed, "started_at": started_at,
    })

async def send_ban(session, note):
    global ban_count
    ban_count += 1
    await post_collector(session, "/ban", {"job_id": JOB_ID, "note": note})
    print(f"  [BAN] {note}", flush=True)

async def send_results(session, results, empty):
    if not results and not empty:
        return
    await post_collector(session, "/results", {
        "job_id": JOB_ID,
        "results": results,
        "empty":   empty,
    })

# ── Lookup ────────────────────────────────────────────────────────────────────
async def lookup(session, number):
    payload = encrypt({
        "n": number, "fp": 0, "type": 1, "s": "0.00",
        "ab": 0, "r": "0,0",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        "nuc": 0, "nac": 0, "hash2": "0", "ali": "0", "git": "0",
        "top": "https://storage.googleapis.com/ksa-n/index.html",
        "v": "9.0.0",
    })
    for server in SERVERS:
        try:
            async with session.post(
                server, data=payload, headers=HEADERS,
                timeout=aiohttp.ClientTimeout(total=12)
            ) as r:
                if r.status == 429:
                    await send_ban(session, f"429 from {server}")
                    await asyncio.sleep(120)
                    return None
                if r.status != 200:
                    continue
                data = decrypt(await r.text())
                if not data or not isinstance(data, dict):
                    continue
                if data.get("type") == 3:   # banned
                    await send_ban(session, f"type=3 ban from {server}")
                    await asyncio.sleep(300)
                    return None
                rows = data.get("results", [])
                if rows:
                    def sort_key(r):
                        try: return (-int(r[2]), -int(r[3]))
                        except: return (0, 0)
                    rows.sort(key=sort_key)
                    return [{"name": r[0], "confidence": int(r[2]) if r[2] else 0,
                             "source_id": int(r[3]) if r[3] else 0}
                            for r in rows if r[0] and str(r[0]).strip()]
                return []
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            continue
    return []

# ── Main ──────────────────────────────────────────────────────────────────────
async def main(prefix2, start, end):
    total      = end - start
    scanned    = 0
    found      = 0
    t0         = time.time()
    last_beat  = t0
    last_print = t0

    buf_results = []
    buf_empty   = []

    numbers = [f"0{prefix2}{i:07d}" for i in range(start, end)]
    queue   = asyncio.Queue()
    for n in numbers:
        queue.put_nowait(n)

    print(f"[{prefix2}] {total:,} رقم | {start:,}→{end:,} | job={JOB_ID}", flush=True)
    if COLLECTOR:
        print(f"[{prefix2}] Collector: {COLLECTOR}", flush=True)

    # إرسال heartbeat أولي
    async with aiohttp.ClientSession() as sess:
        await send_heartbeat(sess, prefix2, start, end, 0, 0, 0, t0)

    async def worker_task(sess):
        nonlocal scanned, found, buf_results, buf_empty, last_beat, last_print

        while True:
            try:
                number = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            wait = await check_throttle()
            if wait > 0:
                print(f"  [{prefix2}] throttle {wait:.0f}s", flush=True)
                await asyncio.sleep(wait)

            names = await lookup(sess, number)

            if names is None:  # ban
                queue.put_nowait(number)  # أعد الرقم للقائمة
                await asyncio.sleep(30)
                continue

            if names:
                await record_found()
                found += 1
                buf_results.append({"phone": number, "names": names})
            else:
                buf_empty.append(number)

            scanned += 1

            # إرسال batch للـ collector
            if len(buf_results) + len(buf_empty) >= BATCH_SIZE:
                await send_results(sess, buf_results, buf_empty)
                buf_results = []
                buf_empty   = []

            # heartbeat
            now = time.time()
            if now - last_beat >= HEARTBEAT_SECS:
                speed = scanned / (now - t0) * 60
                await send_heartbeat(sess, prefix2, start, end, scanned, found, speed, t0)
                last_beat = now

            # طباعة محلية
            if now - last_print >= 30:
                pct   = scanned / total * 100
                speed = scanned / (now - t0) * 60
                eta   = (total - scanned) / (speed / 60) if speed > 0 else 0
                print(f"  [{prefix2}] {pct:.1f}% | {scanned:,}/{total:,} | وجد:{found:,} | {speed:.0f}/د | ETA:{eta/60:.0f}د | bans:{ban_count}", flush=True)
                last_print = now

            await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    async with aiohttp.ClientSession() as sess:
        tasks = [asyncio.create_task(worker_task(sess)) for _ in range(WORKERS)]
        await asyncio.gather(*tasks)

        # إرسال ما تبقى
        await send_results(sess, buf_results, buf_empty)

        # heartbeat نهائي
        speed = scanned / (time.time() - t0) * 60 if time.time() > t0 else 0
        await post_collector(sess, "/heartbeat", {
            "job_id": JOB_ID, "prefix": prefix2,
            "range_from": start, "range_to": end,
            "status": "done", "scanned": scanned, "found": found,
            "bans": ban_count, "speed": speed, "started_at": t0,
        })

    print(f"✓ [{prefix2}] انتهى | {scanned:,} مسح | {found:,} وجد | {ban_count} ban", flush=True)

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python ksa_worker.py <prefix2> <from> <to>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3])))
