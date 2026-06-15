#!/usr/bin/env python3
"""
دمج نتائج GitHub Actions في قاعدة البيانات المحلية
الاستخدام:
  1. حمّل كل الـ artifacts من GitHub (زر Download artifacts)
  2. افك ضغط كل ملف ZIP في مجلد: ./artifacts/
  3. شغّل: python merge_results.py
"""
import sqlite3, csv, glob, os, time

DB_FILE      = "/home/mesha/daleel_full.db"
ARTIFACTS_DIR = "./artifacts"

def find_csv_files():
    # يبحث في كل المجلدات الفرعية
    files = glob.glob(f"{ARTIFACTS_DIR}/**/*.csv", recursive=True)
    files += glob.glob(f"{ARTIFACTS_DIR}/*.csv")
    return sorted(set(files))

def merge():
    csv_files = find_csv_files()
    if not csv_files:
        print(f"⚠️  لا توجد ملفات CSV في {ARTIFACTS_DIR}/")
        print("    ضع ملفات data_*.csv داخل مجلد artifacts/")
        return

    print(f"✓ وجدت {len(csv_files)} ملف CSV")

    db = sqlite3.connect(DB_FILE, timeout=60)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")

    total_inserted = 0
    total_skipped  = 0
    t0 = time.time()

    for i, csv_path in enumerate(csv_files, 1):
        fname = os.path.basename(csv_path)
        print(f"\n[{i}/{len(csv_files)}] {fname}", end=" ... ", flush=True)

        rows = []
        try:
            with open(csv_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = (row.get("name") or "").strip()
                    if not name or name == "test1":
                        continue
                    rows.append((
                        row.get("api_id") or None,
                        row.get("phone", ""),
                        name,
                        row.get("submitted_by", ""),
                        row.get("prefix", ""),
                        row.get("added_date", ""),
                    ))
        except Exception as e:
            print(f"خطأ في القراءة: {e}")
            continue

        if not rows:
            print("فارغ")
            continue

        before = db.execute("SELECT COUNT(*) FROM raw_contacts").fetchone()[0]
        db.executemany(
            "INSERT OR IGNORE INTO raw_contacts(api_id,phone,name,submitted_by,prefix,added_date,fetched_at) "
            "VALUES(?,?,?,?,?,?,unixepoch())",
            rows
        )
        db.commit()
        after = db.execute("SELECT COUNT(*) FROM raw_contacts").fetchone()[0]

        inserted = after - before
        skipped  = len(rows) - inserted
        total_inserted += inserted
        total_skipped  += skipped
        print(f"{inserted:,} جديد | {skipped:,} مكرر | مجموع الملف: {len(rows):,}")

    # تحديث جدول phones
    print(f"\n{'─'*50}")
    print(f"✓ أُضيف {total_inserted:,} سجل جديد | تخطي {total_skipped:,} مكرر")
    print(f"  الوقت: {time.time()-t0:.0f} ثانية")

    total = db.execute("SELECT COUNT(*) FROM raw_contacts").fetchone()[0]
    unique = db.execute("SELECT COUNT(DISTINCT phone) FROM raw_contacts").fetchone()[0]
    print(f"\n  قاعدة البيانات الآن:")
    print(f"  سجلات خام  : {total:,}")
    print(f"  أرقام فريدة: {unique:,}")

    db.close()

if __name__ == "__main__":
    merge()
