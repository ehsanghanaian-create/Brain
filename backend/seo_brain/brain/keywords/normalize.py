"""Persian-aware keyword normalization and tokenization (shared by import, clustering and the GSC join)."""
from __future__ import annotations

import re
import unicodedata

_ARABIC_TO_PERSIAN = str.maketrans({"ي": "ی", "ك": "ک", "ة": "ه", "ؤ": "و", "إ": "ا", "أ": "ا", "آ": "ا", "ئ": "ی"})
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_ZW = re.compile(r"[‌‍‎‏‪-‮﻿]")      # ZWNJ/ZWJ/bidi marks → space (ZWNJ) / removed
_DIACRITICS = re.compile(r"[ً-ٰٟ]")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")

STOPWORDS = {
    # fa
    "و", "در", "به", "از", "با", "برای", "که", "این", "آن", "را", "تا", "یا", "هم", "بر", "است", "هست", "شود", "می", "های", "ها",
    "یک", "چه", "چی", "کجا", "چگونه", "بهترین", "ترین", "خود", "روی", "بی", "بدون", "درباره", "کنید", "کردن",
    # en
    "the", "a", "an", "of", "for", "in", "on", "to", "and", "or", "with", "by", "at", "is", "are", "how", "what", "best", "near", "me",
}


def normalize_keyword(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    s = s.translate(_ARABIC_TO_PERSIAN).translate(_DIGITS)
    s = _ZW.sub(" ", s)
    s = _DIACRITICS.sub("", s)
    s = s.lower()
    s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    return s


def tokenize(s: str, drop_stopwords: bool = True) -> list[str]:
    toks = normalize_keyword(s).split(" ") if s else []
    toks = [t for t in toks if t]
    if drop_stopwords:
        toks = [t for t in toks if t not in STOPWORDS and len(t) > 1]
    return toks
