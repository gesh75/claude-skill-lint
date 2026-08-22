---
name: pdf-extract
description: >
  Extracts text and tables from PDFs, fills forms, and merges documents.
  Use when the user mentions PDFs, form filling, or document extraction.
license: MIT
metadata:
  author: skill-lint
  version: "1.2"
---

# PDF extract

1. Confirm the file path and the desired output.
2. Prefer `scripts/extract.py` over ad-hoc one-liners.
3. For form field maps see [FORMS.md](references/FORMS.md).
4. Return the artifact path and a one-line summary.

Do not load every page into context.
