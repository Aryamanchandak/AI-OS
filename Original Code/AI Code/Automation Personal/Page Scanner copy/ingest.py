"""Drop-folder ingest — the front door of the pipeline.

  .venv/bin/python ingest.py            # scan every book folder on the Desktop
  .venv/bin/python ingest.py --dry-run  # resolve metadata + list, scan nothing

Layout expected in the drop folder (default: ~/Desktop/Page Scanner):

  Page Scanner/
    Atomic Habits/            ← one folder per book
      book.txt                ← optional; type the title here, else the folder
      IMG_0001.HEIC             name is used
      IMG_0002.HEIC

For each book folder it resolves bibliographic metadata (core.metadata), then
runs the existing OCR pipeline (process.process_image) over the photos, tagging
every page with the book's batch/author + full metadata JSON. Photos are NOT
moved here. New pages are handed off as mutable markdown in Raw Data/processing/
so review/correction happens before the single capture() write to bronze.
Re-running is safe: file_hash dedup skips photos already in the DB.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from core import images, metadata, settings, store

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tiff", ".tif", ".bmp"}


def _book_folders(source: Path) -> list[Path]:
    return sorted(
        p for p in source.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )


def _images_in(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS)


def scan_book(folder: Path, db: str, hsv, dry_run: bool, clean: bool = False) -> dict:
    import process as P

    meta = metadata.load_or_resolve(folder)
    photos = _images_in(folder)
    title = meta.get("title") or folder.name
    author = meta.get("author")
    conf = meta.get("confidence", "none")

    print(f"\n📖 {folder.name}")
    print(f"   → {title}" + (f" — {author}" if author else "")
          + f"   [{meta.get('meta_source', 'none')} / {conf}]")
    if conf in ("low", "none"):
        print("   ⚠  low-confidence metadata — confirm/fix .book.json in the folder")
    print(f"   {len(photos)} photo(s)")

    if dry_run or not photos:
        return {"book": folder.name, "photos": len(photos),
                "inserted": 0, "skipped": 0, "errored": 0, "gated": 0}

    args = SimpleNamespace(
        db=db, batch=title, author=author, hsv=hsv, clean=clean,
        book_meta=json.dumps(meta, ensure_ascii=False),
    )
    inserted = skipped = gated = errored = passages = 0
    for path in photos:
        try:
            n, did_insert, flagged = P.process_image(path, args)
            if did_insert:
                page = store.get_page_by_file_hash(args.db, images.file_hash(path))
                if not page:
                    raise RuntimeError(f"inserted page not found for {path}")
                processing_path = store.handoff_page_to_processing(
                    args.db,
                    page["id"],
                    settings.RAW_DATA_ROOT,
                )
                inserted += 1
                passages += n
                print(
                    f"     {'RETAKE' if flagged else 'OK':<6} {path.name:<26} "
                    f"{n} passages → {processing_path.relative_to(settings.RAW_DATA_ROOT)}"
                )
                gated += int(flagged)
            else:
                skipped += 1
                print(f"     skip   {path.name:<26} (already processed)")
        except Exception as e:                       # per-image isolation
            errored += 1
            print(f"     !!     {path.name:<26} {type(e).__name__}: {e}")
    return {"book": folder.name, "photos": len(photos), "inserted": inserted,
            "skipped": skipped, "errored": errored, "gated": gated,
            "passages": passages}


def main() -> int:
    ap = argparse.ArgumentParser(description="Page Scanner — drop-folder ingest")
    ap.add_argument("--source", default=str(settings.SOURCE_DIR))
    ap.add_argument("--db", default=str(settings.DB_PATH))
    ap.add_argument("--hsv", default=None, help='lower HSV floor "H,S,V"')
    ap.add_argument("--dry-run", action="store_true",
                    help="resolve metadata + list photos, but scan nothing")
    ap.add_argument("--clean", action="store_true",
                    help="pre-fill edited_text with an LLM OCR-cleanup pass "
                         "(needs the AI Code LLM gateway running on :8107; raw "
                         "OCR is always preserved in ocr_text)")
    args = ap.parse_args()

    hsv = tuple(int(x) for x in args.hsv.split(",")) if args.hsv else None
    source = Path(args.source).expanduser()
    if not source.exists():
        print(f"Source folder does not exist: {source}")
        return 1

    store.init_db(args.db)
    folders = _book_folders(source)
    loose = _images_in(source)
    if loose:
        print(f"⚠  {len(loose)} loose photo(s) in {source} are outside a book "
              f"folder and were skipped. Put them in a per-book subfolder.")
    if not folders:
        print(f"No book folders in {source}. Make one per book and drop photos in.")
        return 0

    results = [scan_book(f, args.db, hsv, args.dry_run, args.clean) for f in folders]

    print("\n" + "-" * 60)
    tot = {k: sum(r.get(k, 0) for r in results)
           for k in ("photos", "inserted", "skipped", "errored", "gated")}
    print(f"books: {len(results)}  photos: {tot['photos']}  inserted: {tot['inserted']}"
          f"  skipped: {tot['skipped']}  gated: {tot['gated']}  errored: {tot['errored']}")
    if not args.dry_run and tot["inserted"]:
        print("\nNext: review the Raw Data/processing handoff in the cockpit —")
        print("  .venv/bin/python -m uvicorn server:app --reload")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
