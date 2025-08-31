import re, unicodedata
import string

_STOPWORDS = {"port","pelabuhan","pel","harbour","harbor","terminal","marine","maritime","of","the","pt","portos"}
_PUNCT = set(string.punctuation)

def _strip_accents(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))

def canon_name(s: str) -> str:
    if not s: return ""
    s = _strip_accents(s).lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = "".join((" " if ch in _PUNCT else ch) for ch in s)
    tokens = [t for t in s.split() if t and t not in _STOPWORDS]
    return " ".join(tokens)

# Optional: rapidfuzz helpers with graceful fallback
def has_rapidfuzz():
    try:
        import rapidfuzz  # noqa
        return True
    except Exception:
        return False

def rf_match(query_key: str, choices):
    from rapidfuzz import process as rf_process, fuzz as rf_fuzz
    match = rf_process.extractOne(query_key, choices, scorer=rf_fuzz.token_sort_ratio)
    if not match:
        return None, 0
    return match[0], match[1]
