"""Deterministic Persian inverse text normalization (ITN) for ASR output.

Converts *spoken-form* Persian numbers and units into their *written* form:

* digit words:      «پانصد» → «۵۰۰»، «دویست و پنجاه» → «۲۵۰»
* compound numbers: «سه هزار و دویست» → «۳۲۰۰»
* decimals:         «هفت ممیز دو» → «۷٫۲»، «هفت ممیز بیست و پنج» → «۷٫۲۵»
* fractions:        «هفت دهم» → «۰٫۷»، «پنج صدم» → «۰٫۰۵»
* halves:           «دو و نیم» → «۲٫۵»، «نیم ساعت» → «۰٫۵ ساعت»
* percent:          «پنج درصد» → «۵٪»
* ordinals:         «روز سوم» → «روز ۳» (only next to time/step units)

Design rules:

* **Value-preserving.** The module is table-driven and deterministic; the
  property tests in ``server/tests/test_itn.py`` assert that parsing the
  spoken form and parsing the emitted digits back yields the same canonical
  number for hundreds of generated cases. When a sequence cannot be parsed
  unambiguously it is left untouched.
* **Conservative.** Ambiguous bare words are not converted: «نه» also means
  "no" and «یک» doubles as an indefinite article, so single digit words and
  ordinals are only converted next to a unit (قرص/روز/درصد/...) or inside an
  unambiguous multi-word number. Latin text («HbA1c 7.2%») is never touched.
* **Rollback-safe.** ``PHLOX_ITN=auto`` (default) applies ITN only to the
  Shenava output path (its model card documents spoken-form numbers);
  ``on`` applies it to every engine; ``off`` restores the exact previous
  output. The transcription result carries ``itn_applied: bool``.

Digits are emitted in the Persian script (۰-۹) with U+066B (٫) as the
decimal separator — the same canonical form ``server.nlp_tools.verification``
normalizes to before comparing values.
"""

from __future__ import annotations

import os
import re
from typing import Any

# ---------------------------------------------------------------------------
# Tables (digits built programmatically — never hand-typed)
# ---------------------------------------------------------------------------

_PERSIAN_DIGIT_MAP = str.maketrans("0123456789", "".join(chr(0x06F0 + i) for i in range(10)))
_TO_ASCII = str.maketrans(
    "".join(chr(0x06F0 + i) for i in range(10)) + "٠١٢٣٤٥٦٧٨٩",
    "0123456789" * 2,
)

_ONES = {
    "صفر": 0,
    "یک": 1,
    "دو": 2,
    "سه": 3,
    "چهار": 4,
    "پنج": 5,
    "شش": 6,
    "هفت": 7,
    "هشت": 8,
    "نه": 9,
}
_TEENS = {
    "ده": 10,
    "یازده": 11,
    "دوازده": 12,
    "سیزده": 13,
    "چهارده": 14,
    "پانزده": 15,
    "شانزده": 16,
    "هفده": 17,
    "هجده": 18,
    "نوزده": 19,
}
_TENS = {
    "بیست": 20,
    "سی": 30,
    "چهل": 40,
    "پنجاه": 50,
    "شصت": 60,
    "هفتاد": 70,
    "هشتاد": 80,
    "نود": 90,
}
_HUNDREDS = {
    "صد": 100,
    "یکصد": 100,
    "دویست": 200,
    "سیصد": 300,
    "چهارصد": 400,
    "پانصد": 500,
    "ششصد": 600,
    "هفتصد": 700,
    "هشتصد": 800,
    "نهصد": 900,
}
_SCALES = {"هزار": 1000, "میلیون": 1000000}

# Ordinal forms: cardinal root + «م» (سی‌ام keeps a ZWNJ spelling variant).
_ORDINALS: dict[str, int] = {
    word + "م": value
    for word, value in {**_ONES, **_TEENS, **_TENS, **_HUNDREDS}.items()
    if word != "صفر"
}
# «سه» forms the irregular ordinal «سوم»; the regular «سم» would collide with
# the unrelated word for hoof/poison and must never be treated as a number.
_ORDINALS.pop("سم", None)
_ORDINALS.update({"سوم": 3, "سی ام": 30, "سی‌ام": 30, "هزارم": 1000})

# Fraction denominator words: «هفت دهم» = 7/10. Next to a time/step unit the
# same words are ordinals instead («روز دهم» = day 10).
_FRACTION_DENOMS = {"دهم": 10, "صدم": 100}
_ORDINAL_CONTEXT = frozenset({"روز", "ساعت", "هفته", "ماه", "سال", "مرحله", "نوبت", "طبقه", "شب"})

# Units that licence bare digit words/ordinals and are kept verbatim after
# conversion. Matched on the ZWNJ-stripped, casefolded token core.
_UNIT_WORDS = frozenset(
    {
        "میلیگرم",
        "میلیلیتر",
        "میلیلتر",
        "لیتر",
        "گرم",
        "کیلوگرم",
        "کیلو",
        "میکروگرم",
        "واحد",
        "قطره",
        "قرص",
        "کپسول",
        "امپول",
        "پوکه",
        "عدد",
        "بار",
        "مرتبه",
        "دفعه",
        "روز",
        "ساعت",
        "دقیقه",
        "هفته",
        "ماه",
        "سال",
        "درصد",
        "سیسی",
        "میلیمتر",
        "سانتیمتر",
        "متر",
        "درجه",
        "نفر",
    }
)

# «درصد» becomes the percent sign after a converted number.
_PERCENT_WORD = "درصد"
_PERCENT_SIGN = "\u066a"
_DECIMAL_WORD = "ممیز"
_HALF_WORD = "نیم"
_CONNECTOR = "و"

# Punctuation peeled off token cores so «پانصد،» still converts.
_PUNCT_CHARS = " \t.,;:!?،؛؟٪()«»[]{}\"'’‘–—…•*-"

_MAX_PHRASE_TOKENS = 40


def _core(token: str) -> tuple[str, str, str]:
    """Split a token into (leading punctuation, core, trailing punctuation)."""
    left = 0
    while left < len(token) and token[left] in _PUNCT_CHARS:
        left += 1
    right = len(token)
    while right > left and token[right - 1] in _PUNCT_CHARS:
        right -= 1
    return token[:left], token[left:right], token[right:]


def _norm_word(word: str) -> str:
    """ZWNJ-stripped, casefolded lookup key for a token core."""
    return word.replace("\u200c", "").casefold()


def _word_norm(token: str) -> str:
    return _norm_word(_core(token)[1])


# ---------------------------------------------------------------------------
# Number formatting / canonical parsing
# ---------------------------------------------------------------------------


def format_persian_number(value: float) -> str:
    """Render a canonical number in Persian digits (۷٫۲ style, ٫ = U+066B)."""
    value = float(value)
    if value.is_integer():
        return str(int(value)).translate(_PERSIAN_DIGIT_MAP)
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    integer, _, fraction = text.partition(".")
    return f"{int(integer)}\u066b{fraction}".translate(_PERSIAN_DIGIT_MAP)


def parse_written_number(text: str) -> float | None:
    """Parse a written number (Persian/Arabic-Indic/ASCII digits) canonically.

    «۵۰۰» → 500.0, «۷٫۲» → 7.2. Returns None when the text is not a number.
    """
    cleaned = (text or "").strip().translate(_TO_ASCII).replace("\u066b", ".")
    cleaned = re.sub(r"(?<=\d)،(?=\d)", ".", cleaned)
    if not re.fullmatch(r"\d+(?:\.\d+)?", cleaned):
        return None
    return float(cleaned)


# ---------------------------------------------------------------------------
# Spoken-form grammar
# ---------------------------------------------------------------------------


class _Slot:
    """Accumulator for one number phrase, enforcing Persian number grammar."""

    __slots__ = ("total", "cur", "ones", "teen", "tens", "hundreds")

    def __init__(self) -> None:
        self.total = 0
        self.cur = 0
        self.ones = False
        self.teen = False
        self.tens = False
        self.hundreds = False

    def add(self, kind: str, value: int) -> bool:
        if kind == "ones":
            if value == 0:
                # «صفر» only ever stands alone (e.g. before «ممیز»).
                return self.cur == 0 and self.total == 0 and not self.ones
            if self.ones or self.teen:
                return False
            self.ones = True
        elif kind == "teens":
            # Teens combine with hundreds («پانصد و هفده» = 517) but not
            # with ones or tens («بیست و دوازده» is not a number).
            if self.ones or self.tens or self.teen:
                return False
            self.teen = True
        elif kind == "tens":
            if self.tens or self.teen:
                return False
            self.tens = True
        elif kind == "hundreds":
            if self.hundreds or self.teen:
                return False
            self.hundreds = True
        else:  # scale words multiply what was accumulated so far
            multiplier = self.cur if self.cur else 1
            self.total += multiplier * value
            self.cur = 0
            self.ones = self.teen = self.tens = self.hundreds = False
            return True
        self.cur += value
        return True

    @property
    def value(self) -> int:
        return self.total + self.cur


def _classify(core: str) -> tuple[str, int] | None:
    """Classify one ZWNJ-normalized token core as a number-phrase component."""
    if not core:
        return None
    if core in _ORDINALS:
        return "ordinal", _ORDINALS[core]
    norm = _norm_word(core)
    if norm in _ONES:
        return "ones", _ONES[norm]
    if norm in _TEENS:
        return "teens", _TEENS[norm]
    if norm in _TENS:
        return "tens", _TENS[norm]
    if norm in _HUNDREDS:
        return "hundreds", _HUNDREDS[norm]
    if norm in _SCALES:
        return "scale", _SCALES[norm]
    return None


def _is_family(token: str) -> bool:
    core = _core(token)[1]
    norm = _norm_word(core)
    return (
        norm in {_CONNECTOR, _DECIMAL_WORD, _HALF_WORD, *_FRACTION_DENOMS}
        or _classify(core) is not None
    )


def parse_number_words(phrase: str) -> float | None:
    """Canonical value of a spoken Persian number phrase, or None.

    Accepts the same grammar the rewriter uses: cardinals with «و»
    connectors, scale words, «ممیز» decimals, «X دهم/صدم» fractions,
    «(X و) نیم» halves and ordinals. «روز دهم»-style ordinal context is a
    *rewriter* concern and is not modelled here.
    """
    tokens = [t for t in (phrase or "").split() if t]
    value, consumed = _parse_window(tokens, ordinal_context=False)
    if value is None or consumed != len(tokens):
        return None
    return value


def _parse_fraction(tokens: list[str], norms: list[str]) -> tuple[float | None, int]:
    """«X دهم/صدم» as a fraction starting at tokens[0]; (value, consumed)."""
    if len(tokens) < 2 or norms[1] not in _FRACTION_DENOMS:
        return None, 0
    denom = _FRACTION_DENOMS[norms[1]]
    cls = _classify(_core(tokens[0])[1])
    if cls is None or cls[0] not in {"ones", "teens", "tens"}:
        return None, 0
    numerator = cls[1]
    limit = denom - 1 if denom == 10 else 99
    if not 1 <= numerator <= limit:
        return None, 0
    return numerator / denom, 2


def _parse_decimal(tokens: list[str], norms: list[str]) -> tuple[float | None, int]:
    """«INT ممیز FRAC» starting at tokens[0]; FRAC is digit words read one by
    one («دو پنج» → .25) or a small cardinal («بیست و پنج» → .25). The
    interpretation consuming more tokens wins, so both spoken styles work."""
    if _DECIMAL_WORD not in norms[:_MAX_PHRASE_TOKENS]:
        return None, 0
    pivot = norms.index(_DECIMAL_WORD)
    if pivot == 0 or pivot >= len(tokens) - 1:
        return None, 0
    if norms[pivot - 1] == _CONNECTOR or norms[pivot + 1] == _CONNECTOR:
        return None, 0
    int_value, consumed = _parse_cardinal_window(tokens[:pivot])
    if int_value is None or consumed != pivot or not int_value.is_integer():
        return None, 0
    frac_tokens = tokens[pivot + 1 :]

    # Style A: digit words read one by one (longest leading run of ones).
    run = 0
    while run < len(frac_tokens) and _word_norm(frac_tokens[run]) in _ONES:
        run += 1
    digits_value, digits_consumed = None, 0
    if run:
        digits = "".join(str(_ONES[_word_norm(w)]) for w in frac_tokens[:run])
        digits_value = float(f"{int(int_value)}.{digits}")
        digits_consumed = pivot + 1 + run

    # Style B: a cardinal number («بیست و پنج» = 25).
    cardinal_value, cardinal_consumed = None, 0
    frac_value, frac_consumed = _parse_cardinal_window(frac_tokens)
    if (
        frac_value is not None
        and frac_consumed > 0
        and frac_value.is_integer()
        and frac_value < 1000
    ):
        cardinal_value = float(f"{int(int_value)}.{int(frac_value)}")
        cardinal_consumed = pivot + 1 + frac_consumed

    if digits_value is None and cardinal_value is None:
        return None, 0
    if digits_consumed >= cardinal_consumed:
        return digits_value, digits_consumed
    return cardinal_value, cardinal_consumed


def _parse_cardinal_window(tokens: list[str]) -> tuple[float | None, int]:
    """Longest valid cardinal/ordinal run from the start of ``tokens``."""
    slot = _Slot()
    consumed = 0
    pending_and = False
    saw_component = False
    for index, token in enumerate(tokens[:_MAX_PHRASE_TOKENS]):
        norm = _word_norm(token)
        if norm == _CONNECTOR:
            if not saw_component or pending_and:
                break
            pending_and = True
            continue
        core = _core(token)[1]
        cls = _classify(core)
        if cls is None:
            break
        if cls[0] == "ordinal":
            # Ordinals stand alone («سوم») — «بیست و پنجم» stays spoken.
            if saw_component or slot.value != 0:
                break
            slot.cur = cls[1]
            saw_component = True
            consumed = index + 1
            break
        if cls[0] == "ones" and cls[1] == 0 and saw_component:
            break
        if not slot.add(cls[0], cls[1]):
            break
        saw_component = True
        pending_and = False
        consumed = index + 1
    if not saw_component:
        return None, 0
    return float(slot.value), consumed


def _parse_window(
    tokens: list[str],
    *,
    ordinal_context: bool,
) -> tuple[float | None, int]:
    """Parse the longest valid number phrase starting at ``tokens[0]``.

    Returns ``(value, consumed_token_count)``; ``(None, 0)`` when the first
    token does not start a convertible phrase.
    """
    if not tokens:
        return None, 0
    norms = [_word_norm(t) for t in tokens]
    first = norms[0]

    # A bare «دهم»/«صدم» is a fraction denominator only with a preceding
    # number; next to a time/step unit it is the ordinal 10th/100th.
    if first in _FRACTION_DENOMS:
        if ordinal_context:
            return float(_FRACTION_DENOMS[first]), 1
        return None, 0

    # Fraction («هفت دهم») and decimal («هفت ممیز دو») phrases first — they
    # are the only shapes where trailing words change the value.
    if ordinal_context:
        # «روز هفت دهم»: the denominator word acts as an ordinal marker.
        for end in (2, 3, 4):
            if end <= len(tokens) and norms[end - 1] in _FRACTION_DENOMS:
                value, consumed = _parse_cardinal_window(tokens[: end - 1])
                if value is not None and consumed == end - 1:
                    return value, end
    else:
        fraction, consumed = _parse_fraction(tokens, norms)
        if fraction is not None:
            return fraction, consumed
    decimal, consumed = _parse_decimal(tokens, norms)
    if decimal is not None:
        return decimal, consumed

    # Bare «نیم» means 0.5 («نیم ساعت»).
    if first == _HALF_WORD:
        return 0.5, 1
    value, consumed = _parse_cardinal_window(tokens)
    if value is None:
        return None, 0
    # Trailing «و نیم» halves the step: «دو و نیم» → 2.5.
    if (
        consumed + 1 < len(tokens)
        and norms[consumed] == _CONNECTOR
        and norms[consumed + 1] == _HALF_WORD
        and value.is_integer()
    ):
        return value + 0.5, consumed + 2
    return value, consumed


# ---------------------------------------------------------------------------
# Rewriter
# ---------------------------------------------------------------------------


def _next_is_unit(tokens: list[str], index: int) -> bool:
    if index >= len(tokens):
        return False
    return _word_norm(tokens[index]) in _UNIT_WORDS


def _bare_word_allowed(
    value: float,
    tokens: list[str],
    consumed: int,
    *,
    is_ordinal: bool,
    ordinal_context: bool,
) -> bool:
    """Gate single-token conversions that are ambiguous out of context.

    «نه» doubles as "no", «یک» as an article and «ده» as "village", so bare
    digit words, scale words and ordinals convert only with clear evidence:
    multi-word phrases are always fine; single words need a following unit,
    and ordinals additionally accept a preceding time/step unit.
    """
    if consumed > 1:
        return True
    if is_ordinal and ordinal_context:
        return True
    if is_ordinal:
        return False
    if not value.is_integer():
        return _next_is_unit(tokens, consumed)  # bare «نیم»
    ivalue = int(value)
    if ivalue >= 20 and ivalue not in {1000, 1000000}:
        return True
    return _next_is_unit(tokens, consumed)


def _rewrite_tokens(tokens: list[str]) -> tuple[list[str], int]:
    out: list[str] = []
    changes = 0
    index = 0
    while index < len(tokens):
        token = tokens[index]
        lead, core, trail = _core(token)
        if not core or not _is_family(token):
            out.append(token)
            index += 1
            continue
        window = tokens[index:]
        prev_core = _core(out[-1])[1] if out else ""
        ordinal_context = _norm_word(prev_core) in _ORDINAL_CONTEXT
        value, consumed = _parse_window(window, ordinal_context=ordinal_context)
        if value is None or consumed <= 0:
            out.append(token)
            index += 1
            continue
        is_ordinal = consumed == 1 and _norm_word(core) in _ORDINALS
        if not _bare_word_allowed(
            value, window, consumed, is_ordinal=is_ordinal, ordinal_context=ordinal_context
        ):
            out.append(token)
            index += 1
            continue
        replacement = f"{lead}{format_persian_number(value)}"
        # «پنج درصد» → «۵٪»: the percent sign attaches to the number.
        next_index = index + consumed
        if next_index < len(tokens):
            _plead, pcore, ptrail = _core(tokens[next_index])
            if not _plead and _norm_word(pcore) == _PERCENT_WORD:
                replacement += _PERCENT_SIGN
                trail = f"{ptrail}{trail}"
                consumed += 1
        out.append(f"{replacement}{trail}")
        changes += 1
        index += consumed
    return out, changes


def apply_itn(text: str) -> tuple[str, bool]:
    """Rewrite spoken-form numbers in ``text``; returns (text, changed).

    Whitespace layout and every untouched token are preserved exactly.
    """
    if not text or not re.search(r"[\u0600-\u06FF]", text):
        return text, False
    tokens = text.split(" ")
    rewritten, changes = _rewrite_tokens(tokens)
    if not changes:
        return text, False
    return " ".join(rewritten), True


# ---------------------------------------------------------------------------
# Engine gate (PHLOX_ITN=auto|on|off)
# ---------------------------------------------------------------------------

_ITN_MODES = frozenset({"auto", "on", "off"})


def itn_mode() -> str:
    """Validated ``PHLOX_ITN`` value (default ``auto`` = Shenava only)."""
    raw = str(os.environ.get("PHLOX_ITN", "auto")).strip().lower()
    return raw if raw in _ITN_MODES else "auto"


def maybe_apply_itn(text: str, *, engine: str) -> tuple[str, Any]:
    """Apply ITN to one transcript according to the mode/engine gate.

    Returns ``(text, itn_applied)``; with ``off`` (or a non-Shenava engine
    in ``auto`` mode) the input is returned byte-exact.
    """
    mode = itn_mode()
    if not text or mode == "off":
        return text, False
    if mode == "auto" and engine != "shenava":
        return text, False
    rewritten, changed = apply_itn(text)
    return rewritten, changed
