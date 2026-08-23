---
name: pdf-extract
description: >
  Extracts text and tables from PDFs, fills forms, and merges documents.
  Use when the user mentions PDFs, form filling, or document extraction.
  Do not use for scanned image-only PDFs without OCR.
license: MIT
metadata:
  author: skill-lint
  version: "1.2"
---

# PDF extract

1. Confirm the file path and the desired output (text, tables, filled form, merge).
2. Prefer `scripts/extract.py` over ad-hoc one-liners.
3. For form field maps see [FORMS.md](references/FORMS.md).
4. Return the artifact path and a one-line summary of pages processed.

Do not load every page into context. Stream through the script and keep only the rows you need.

```python
python scripts/extract.py input.pdf --tables
```

## Safety

Never upload the PDF to a third-party API. Confirm page count before writing.
