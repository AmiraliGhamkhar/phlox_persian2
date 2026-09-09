"""Persian inverse text normalization (ITN) — W2.1.

The load-bearing property: ITN is *value-preserving*. Every test that
asserts an emitted number builds the expected Persian digits
programmatically (never hand-typed) and compares canonical values.
"""

import random

import pytest

from server.transcription.itn import (
    apply_itn,
    format_persian_number,
    maybe_apply_itn,
    parse_number_words,
    parse_written_number,
)

# --------------------------------------------------------------------------
# Programmatic digit/word helpers (no hand-typed Persian digits)
# --------------------------------------------------------------------------

FA_DIGITS = [chr(0x06F0 + i) for i in range(10)]
FA_DECIMAL = "\u066b"
FA_PERCENT = "\u066a"


def fa_num(text: str) -> str:
    """'500' -> Persian-digit string, built char-by-char."""
    return "".join(FA_DIGITS[int(ch)] if ch.isdigit() else ch for ch in text)


ONES_W = ["صفر", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه"]
TEENS_W = [
    "ده",
    "یازده",
    "دوازده",
    "سیزده",
    "چهارده",
    "پانزده",
    "شانزده",
    "هفده",
    "هجده",
    "نوزده",
]
TENS_W = ["", "", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود"]
HUNDREDS_W = [
    "",
    "صد",
    "دویست",
    "سیصد",
    "چهارصد",
    "پانصد",
    "ششصد",
    "هفتصد",
    "هشتصد",
    "نهصد",
]


def spoken_int(n: int) -> str:
    """Spoken Persian form of 0 <= n < 10**9 (parser-compatible)."""
    if n == 0:
        return ONES_W[0]
    parts: list[str] = []
    millions, rest = divmod(n, 1_000_000)
    if millions:
        parts.append("میلیون" if millions == 1 else f"{spoken_int(millions)} میلیون")
    thousands, rest = divmod(rest, 1000)
    if thousands:
        parts.append("هزار" if thousands == 1 else f"{spoken_int(thousands)} هزار")
    hundreds, low = divmod(rest, 100)
    if hundreds:
        parts.append(HUNDREDS_W[hundreds])
    if low:
        if low < 10:
            parts.append(ONES_W[low])
        elif low < 20:
            parts.append(TEENS_W[low - 10])
        else:
            ten, one = divmod(low, 10)
            word = TENS_W[ten]
            if one:
                word += f" و {ONES_W[one]}"
            parts.append(word)
    return " و ".join(parts)


def converted_number(text: str) -> str | None:
    """Extract the first Persian-digit number run from ITN output."""
    import re

    match = re.search(f"[{''.join(FA_DIGITS)}]+(?:{FA_DECIMAL}[{''.join(FA_DIGITS)}]+)?", text)
    return match.group(0) if match else None


# --------------------------------------------------------------------------
# Basic conversions
# --------------------------------------------------------------------------


class TestCardinals:
    def test_hundreds(self):
        out, changed = apply_itn("پانصد تجویز شد")
        assert changed
        assert out == f"{fa_num('500')} تجویز شد"

    def test_compound_with_connector(self):
        out, _ = apply_itn("دوز دارو دویست و پنجاه است")
        assert fa_num("250") in out

    def test_thousands(self):
        out, _ = apply_itn("گلبول سفید سه هزار و دویست بود")
        assert fa_num("3200") in out

    def test_large_composite(self):
        out, _ = apply_itn("بودجه سه میلیون و دویست و پنجاه هزار ریال است")
        assert fa_num("3250000") in out

    def test_teens(self):
        out, _ = apply_itn("بیمار دوازده قرص مصرف کرد")
        assert f"{fa_num('12')} قرص" in out

    def test_bare_tens_convert(self):
        out, _ = apply_itn("تعداد پنجاه است")
        assert fa_num("50") in out

    def test_already_written_digits_untouched(self):
        text = "دوز ۵۰۰ میلی‌گرم باقی می‌ماند"
        out, changed = apply_itn(text)
        assert out == text and not changed


class TestFractionsDecimals:
    def test_tenths_fraction(self):
        out, _ = apply_itn("هفت دهم گرم مصرف شود")
        assert out.startswith(f"{fa_num('0')}{FA_DECIMAL}{fa_num('7')} گرم")

    def test_hundredths_fraction(self):
        out, _ = apply_itn("پنج صدم میلی‌لیتر")
        assert out.startswith(f"{fa_num('0')}{FA_DECIMAL}{fa_num('05')}")

    def test_decimal_with_momayyez(self):
        out, _ = apply_itn("قند خون هفت ممیز دو بود")
        assert fa_num("7") + FA_DECIMAL + fa_num("2") in out

    def test_decimal_two_digit_fraction(self):
        out, _ = apply_itn("هفت ممیز بیست و پنج درصد")
        assert fa_num("7") + FA_DECIMAL + fa_num("25") in out

    def test_half_after_number(self):
        out, _ = apply_itn("دو و نیم میلی‌گرم تزریق شد")
        assert out.startswith(f"{fa_num('2')}{FA_DECIMAL}{fa_num('5')} میلی‌گرم")

    def test_bare_half_before_unit(self):
        out, _ = apply_itn("نیم ساعت استراحت کند")
        assert out.startswith(f"{fa_num('0')}{FA_DECIMAL}{fa_num('5')} ساعت")

    def test_percent_word_becomes_sign(self):
        out, _ = apply_itn("اشباع اکسیژن نود و پنج درصد است")
        assert fa_num("95") + FA_PERCENT in out


class TestOrdinalsAndContext:
    def test_ordinal_next_to_unit(self):
        out, _ = apply_itn("روز سوم بستری")
        assert out.startswith(f"روز {fa_num('3')}")

    def test_bare_ordinal_stays_without_unit_context(self):
        text = "مریض سوم را فراموش کرد"  # not a licencing context
        out, changed = apply_itn(text)
        assert out == text and not changed

    def test_fraction_word_after_unit_reads_ordinal(self):
        out, _ = apply_itn("روز دهم بستری است")
        assert out.startswith(f"روز {fa_num('10')}")


class TestConservativeGates:
    def test_no_word_not_converted(self):
        text = "نه، درد قفسه سینه ندارد"
        out, changed = apply_itn(text)
        assert out == text and not changed

    def test_article_yek_not_converted(self):
        text = "یک بیمار ۵۲ ساله مراجعه کرد"
        out, _ = apply_itn(text)
        assert out.startswith("یک بیمار")

    def test_latin_text_untouched(self):
        text = "HbA1c 7.2% and amoxicillin 500 mg"
        out, changed = apply_itn(text)
        assert out == text and not changed

    def test_mixed_sentence_only_converts_words(self):
        out, _ = apply_itn("amoxicillin پانصد میلی‌گرم هر هشت ساعت")
        assert out.startswith(f"amoxicillin {fa_num('500')} میلی‌گرم")
        assert "هر" in out

    def test_unit_preserved_verbatim_with_zwnj(self):
        out, _ = apply_itn("پانصد میلی‌گرم")
        assert out == f"{fa_num('500')} میلی‌گرم"

    def test_punctuation_around_number_preserved(self):
        out, _ = apply_itn("دوز پانصد، تکرار شود")
        assert out == f"دوز {fa_num('500')}، تکرار شود"


# --------------------------------------------------------------------------
# Value preservation (property-style: hundreds of generated cases)
# --------------------------------------------------------------------------


class TestValuePreservation:
    def test_spoken_parse_equals_written_parse(self):
        rng = random.Random(20260909)
        for _ in range(300):
            value = rng.randrange(0, 9_999_999)
            spoken = f"{spoken_int(value)} میلی‌گرم"
            out, changed = apply_itn(spoken)
            assert changed, spoken
            written = converted_number(out)
            assert written is not None, out
            assert parse_number_words(spoken_int(value)) == parse_written_number(written)
            assert parse_written_number(written) == float(value)

    def test_decimal_round_trip(self):
        rng = random.Random(42)
        for _ in range(150):
            integer = rng.randrange(0, 1000)
            frac_digits = "".join(str(rng.randrange(0, 10)) for _ in range(rng.randrange(1, 3)))
            expected = float(f"{integer}.{frac_digits}")
            spoken_frac = " ".join(ONES_W[int(d)] for d in frac_digits)
            phrase = f"{spoken_int(integer)} ممیز {spoken_frac} درصد"
            out, changed = apply_itn(phrase)
            assert changed, phrase
            written = converted_number(out)
            assert written is not None, out
            assert parse_written_number(written) == expected

    def test_halves_round_trip(self):
        for value in range(0, 60):
            phrase = f"{spoken_int(value)} و نیم ساعت" if value else "نیم ساعت"
            out, changed = apply_itn(phrase)
            assert changed, phrase
            written = converted_number(out)
            assert written is not None, out
            assert parse_written_number(written) == value + 0.5

    def test_tenths_round_trip(self):
        for numerator in range(1, 10):
            phrase = f"{ONES_W[numerator]} دهم"
            value, consumed = _parse(phrase)
            assert value == numerator / 10 and consumed == 2

    def test_format_and_parse_inverse(self):
        rng = random.Random(7)
        for _ in range(200):
            value = rng.randrange(0, 10**7) / 100
            assert parse_written_number(format_persian_number(value)) == float(
                f"{value:.10f}".rstrip("0").rstrip(".")
            )


def _parse(phrase: str):
    from server.transcription.itn import _parse_window

    return _parse_window(phrase.split(), ordinal_context=False)


# --------------------------------------------------------------------------
# Engine gate / rollback safety
# --------------------------------------------------------------------------


class TestModeGate:
    def test_auto_applies_only_to_shenava(self, monkeypatch):
        monkeypatch.setenv("PHLOX_ITN", "auto")
        text = "پانصد میلی‌گرم"
        out, applied = maybe_apply_itn(text, engine="shenava")
        assert applied and out.startswith(fa_num("500"))
        out, applied = maybe_apply_itn(text, engine="whisper")
        assert not applied and out == text

    def test_on_applies_everywhere(self, monkeypatch):
        monkeypatch.setenv("PHLOX_ITN", "on")
        out, applied = maybe_apply_itn("پانصد میلی‌گرم", engine="whisper")
        assert applied and out.startswith(fa_num("500"))

    def test_off_is_byte_exact(self, monkeypatch):
        monkeypatch.setenv("PHLOX_ITN", "off")
        text = "پانصد میلی‌گرم و هفت دهم"
        out, applied = maybe_apply_itn(text, engine="shenava")
        assert not applied and out == text

    def test_invalid_mode_falls_back_to_auto(self, monkeypatch):
        monkeypatch.setenv("PHLOX_ITN", "bogus")
        out, applied = maybe_apply_itn("پانصد", engine="whisper")
        assert not applied and out == "پانصد"

    def test_empty_text_never_applies(self, monkeypatch):
        monkeypatch.setenv("PHLOX_ITN", "on")
        assert maybe_apply_itn("", engine="shenava") == ("", False)


@pytest.mark.asyncio
class TestShenavaPath:
    async def test_off_restores_byte_exact_old_output(self, monkeypatch):
        from server.transcription import audio

        spoken = "بیمار پانصد میلی‌گرم و هفت دهم دریافت کرد"
        monkeypatch.setattr(audio, "_run_shenava_inference", lambda *_args: spoken)
        monkeypatch.setenv("PHLOX_ITN", "off")
        result = await audio._transcribe_local_shenava(b"RIFF-fake", {})
        assert result["text"] == spoken  # byte-exact rollback
        assert result["itn_applied"] is False

    async def test_auto_applies_on_shenava(self, monkeypatch):
        from server.transcription import audio

        spoken = "بیمار پانصد میلی‌گرم دریافت کرد"
        monkeypatch.setattr(audio, "_run_shenava_inference", lambda *_args: spoken)
        monkeypatch.setenv("PHLOX_ITN", "auto")
        result = await audio._transcribe_local_shenava(b"RIFF-fake", {})
        assert fa_num("500") in result["text"]
        assert result["itn_applied"] is True
