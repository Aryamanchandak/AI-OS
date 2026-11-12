Read CLAUDE.md and spec.md before writing any code.

We are doing Phase 0 only: a throwaway spike script to validate the core approach before building anything real.

Build a single script: spike/spike.py

It should iterate over every image in data/inbox/ and for each one print:
1. Image filename, loaded size after EXIF correction (use ImageOps.exif_transpose). If HEIC, load via pillow-heif.
2. Full-page OCR via ocrmac: print each (text, confidence, bbox) tuple.
3. Yellow mask: convert to HSV, threshold H∈[20,35] S>80 V>120 as a starting point, write the mask as spike/masks/<filename>.png so the result can be eyeballed.
4. Laplacian variance (blur score): cv2.Laplacian(gray, cv2.CV_64F).var() — print it per image.
5. A dry-run of the word-box intersection: for each OCR word whose bbox overlaps the yellow mask, print the word and its confidence. Print total kept vs total words.
6. A dry-run of the passage grouper: print the grouped passages (words contiguous in reading order + vertically adjacent within ~1.5 line-heights go in one group).

Do not write to any database. Do not build any server. This is purely diagnostic print output + the mask images.

At the end, print a summary table: filename | blur_score | total_words | kept_words | passages_found.

Exit condition: script runs on all images in data/inbox/ without crashing, prints the summary table, and writes mask PNGs. Stop there and tell me:
- Whether EXIF correction visibly worked (did the sideways test image right itself?)
- Whether the yellow mask looks clean on the sample images
- What blur score range you're seeing across the images
- Any images that failed and why

Do not proceed to Phase 1.