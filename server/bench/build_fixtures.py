"""Author/validate the precision fixtures against the REAL detectors.

Run with the repo root as CWD. Exits non-zero if any gold bullet fails the
guards or any planted failure is not caught by its mapped detector — so the
fixtures can never drift away from what the code actually detects.
"""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {rel}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


V = load("bench_verify", "server/transcription/verification.py")
H = load("bench_hygiene", "server/transcription/hygiene.py")

FA1_TRANSCRIPT = (
    "بیمار مرد ۵۲ ساله با سابقه فشار خون برای پیگیری مراجعه کرد. "
    "از سوزش سر دل بعد از غذا شکایت دارد. "
    "درد قفسه سینه ندارد و تنگی نفس ندارد. "
    "آموزشتانول ۴۰ میلی گرم هر شب مصرف می کند. "
    "فشار خون امروز ۱۳۰ روی ۸۵ اندازه گیری شد. "
    "آزمایش کراتینین ۱.۱ نرمال است. "
    "برای سه ماه دیگر ویزیت مجدد با آزمایش خون لازم است."
)
FA1 = {
    "id": "fa-reflux-001",
    "lang": "fa",
    "transcript": FA1_TRANSCRIPT,
    "gold_fields": {
        "hpi": [
            "بیمار مرد ۵۲ ساله با سابقه فشار خون",
            "سوزش سر دل بعد از غذا",
            "درد قفسه سینه ندارد",
        ],
        "meds": ["آموزشتانول ۴۰ میلی گرم هر شب"],
        "vitals": ["فشار خون امروز ۱۳۰ روی ۸۵"],
        "plan": ["برای سه ماه دیگر ویزیت مجدد با آزمایش خون"],
    },
    "mutations": [
        {
            "kind": "fabrication",
            "field": "hpi",
            "detector": "quote",
            "bullet": "بیمار سابقه سکته مغزی در سال گذشته دارد و دوبینی دارد",
        },
        {
            "kind": "number_drift",
            "field": "meds",
            "detector": "number",
            "detail": "80",
            "bullet": "آموزشتانول ۸۰ میلی گرم هر شب",
        },
        {
            "kind": "negation_flip",
            "field": "hpi",
            "detector": "negation",
            "bullet": "بیمار درد قفسه سینه دارد",
        },
        {
            "kind": "artifact",
            "field": "plan",
            "detector": "artifact",
            "detail": "known_hallucination_artifact",
            "bullet": "لطفاً لایک و سابسکرایب را یادتان باشد",
        },
    ],
}

FA2_TRANSCRIPT = (
    "بیمار دیابت نوع دو از ۱۰ سال پیش دارد. "
    "متفورمین ۵۰۰ میلی گرم دو بار در روز و انسولین گلاژین ۱۰ واحد شبانه مصرف می کند. "
    "قند خون ناشتا ۱۲۶ و هموگلوبین ای ۱ سی ۷.۲ است. "
    "بی حسی پا ندارد و تاری دید ندارد. "
    "وزن ۸۲ کیلوگرم است. "
    "رژیم غذایی و ورزش روزانه ۳۰ دقیقه توصیه شد. "
    "مراجعه بعدی دو ماه دیگر."
)
FA2 = {
    "id": "fa-diabetes-002",
    "lang": "fa",
    "transcript": FA2_TRANSCRIPT,
    "gold_fields": {
        "hpi": ["بیمار دیابت نوع دو از ۱۰ سال پیش", "قند خون ناشتا ۱۲۶", "بی حسی پا ندارد"],
        "meds": ["متفورمین ۵۰۰ میلی گرم دو بار در روز", "انسولین گلاژین ۱۰ واحد شبانه"],
        "labs": ["هموگلوبین ای ۱ سی ۷.۲"],
        "plan": ["رژیم غذایی و ورزش روزانه ۳۰ دقیقه", "مراجعه بعدی دو ماه دیگر"],
    },
    "mutations": [
        {
            "kind": "fabrication",
            "field": "hpi",
            "detector": "quote",
            "bullet": "بیمار زخم پای چپ با ترشح دارد و به ارتوپد ارجاع شد",
        },
        {
            "kind": "number_drift",
            "field": "meds",
            "detector": "number",
            "detail": "1000",
            "bullet": "متفورمین ۱۰۰۰ میلی گرم دو بار در روز",
        },
        {
            "kind": "negation_flip",
            "field": "hpi",
            "detector": "negation",
            "bullet": "بیمار بی حسی پا و تاری دید دارد",
        },
        {
            "kind": "artifact",
            "field": "labs",
            "detector": "artifact",
            "detail": "duplicated_line",
            "bullet": "هموگلوبین ای ۱ سی ۷.۲\nهموگلوبین ای ۱ سی ۷.۲",
        },
    ],
}

FA3_TRANSCRIPT = (
    "مراجعه کننده زن ۳۴ ساله با سردردهای روزانه از دو هفته پیش. "
    "سردازن ۵۰ میلی گرم در ماه دوبار مصرف می کرد. "
    "سی تی اسکن مغز نرمال است و ضایعه space occupying ندارد. "
    "خواب آلودگی روزانه دارد. "
    "فشار ۱۱۸ روی ۷۲. "
    "آملودیپین قطع شد و پرولازک ۲۵ میلی گرم هر شب شروع شد. "
    "کنترل یک ماه دیگر."
)
FA3 = {
    "id": "fa-headache-003",
    "lang": "fa",
    "transcript": FA3_TRANSCRIPT,
    "gold_fields": {
        "hpi": ["زن ۳۴ ساله با سردردهای روزانه از دو هفته پیش", "خواب آلودگی روزانه دارد"],
        "exam": ["سی تی اسکن مغز نرمال است", "ضایعه space occupying ندارد"],
        "meds": ["آملودیپین قطع شد", "پرولازک ۲۵ میلی گرم هر شب"],
        "plan": ["کنترل یک ماه دیگر"],
    },
    "mutations": [
        {
            "kind": "fabrication",
            "field": "exam",
            "detector": "quote",
            "bullet": "ام آر آی با کنتراست ضایعه هیپوفیزی نشان داد",
        },
        {
            "kind": "number_drift",
            "field": "meds",
            "detector": "number",
            "detail": "75",
            "bullet": "پرولازک ۷۵ میلی گرم هر شب",
        },
        {
            "kind": "negation_flip",
            "field": "exam",
            "detector": "negation",
            "bullet": "ضایعه space occupying مغز وجود دارد",
        },
        {
            "kind": "artifact",
            "field": "hpi",
            "detector": "artifact",
            "detail": "repetition_loop",
            "bullet": "سردرد سردرد سردرد سردرد سردرد شدید",
        },
    ],
}

EN1_TRANSCRIPT = (
    "52 year old male with hypertension and GERD presents for follow up. "
    "Reports burning epigastric pain after meals. "
    "Denies chest pain and denies shortness of breath. "
    "Takes omeprazole 40 mg nightly and lisinopril 10 mg daily. "
    "Blood pressure today 130 over 85. Creatinine 1.1. "
    "Recheck in three months with fasting labs."
)
EN1 = {
    "id": "en-gerd-004",
    "lang": "en",
    "transcript": EN1_TRANSCRIPT,
    "gold_fields": {
        "hpi": [
            "52 year old male with hypertension and GERD",
            "burning epigastric pain after meals",
            "denies chest pain",
        ],
        "meds": ["omeprazole 40 mg nightly", "lisinopril 10 mg daily"],
        "vitals": ["blood pressure today 130 over 85"],
        "plan": ["recheck in three months with fasting labs"],
    },
    "mutations": [
        {
            "kind": "fabrication",
            "field": "hpi",
            "detector": "quote",
            "bullet": "patient reports melena and unintentional weight loss of 12 kg",
        },
        {
            "kind": "number_drift",
            "field": "meds",
            "detector": "number",
            "detail": "20",
            "bullet": "lisinopril 20 mg daily",
        },
        {
            "kind": "negation_flip",
            "field": "hpi",
            "detector": "negation",
            "bullet": "patient reports chest pain and shortness of breath",
        },
        {
            "kind": "artifact",
            "field": "plan",
            "detector": "artifact",
            "detail": "known_hallucination_artifact",
            "bullet": "Thanks for watching and subscribe to our channel",
        },
    ],
}

EN2_TRANSCRIPT = (
    "Type 2 diabetic on metformin 500 mg twice daily. "
    "Home glucose readings around 126 fasting. HbA1c is 7.2. "
    "Denies numbness in feet and denies blurred vision. "
    "Weight 82 kg. Advised thirty minutes of daily exercise. "
    "Next visit in two months."
)
EN2 = {
    "id": "en-diabetes-005",
    "lang": "en",
    "transcript": EN2_TRANSCRIPT,
    "gold_fields": {
        "hpi": ["type 2 diabetic", "glucose readings around 126 fasting"],
        "meds": ["metformin 500 mg twice daily"],
        "assessment": ["HbA1c is 7.2", "denies numbness in feet"],
        "plan": ["thirty minutes of daily exercise", "next visit in two months"],
    },
    "mutations": [
        {
            "kind": "fabrication",
            "field": "assessment",
            "detector": "quote",
            "bullet": "fundoscopy shows proliferative retinopathy in the left eye",
        },
        {
            "kind": "number_drift",
            "field": "meds",
            "detector": "number",
            "detail": "1000",
            "bullet": "metformin 1000 mg twice daily",
        },
        {
            "kind": "negation_flip",
            "field": "assessment",
            "detector": "negation",
            "bullet": "patient has numbness in feet",
        },
        {
            "kind": "artifact",
            "field": "hpi",
            "detector": "artifact",
            "detail": "known_hallucination_artifact",
            "bullet": "Subtitles by Interactive transcription service",
        },
    ],
}

FIXTURES = [FA1, FA2, FA3, EN1, EN2]


def check(fixture: dict) -> list[str]:
    problems: list[str] = []
    transcript = fixture["transcript"]

    # gold sanity: quotes supported, numbers present, no negation conflicts
    for key, bullets in fixture["gold_fields"].items():
        _, report = V.verify_draft({key: bullets}, transcript, mode="flag")
        if report.unsupported:
            problems.append(f"gold quote unsupported: {key}: {report.unsupported}")
        rep2 = V.verify_final_fields(
            {key: V.join_bullets(bullets)}, transcript, V.VerificationReport(mode="flag")
        )
        if rep2.number_problems:
            problems.append(f"gold numbers flagged: {key}: {rep2.number_problems}")
        if rep2.negation_problems:
            problems.append(f"gold negations flagged: {key}: {rep2.negation_problems}")

    # mutations: each plant must be caught by its mapped detector
    for m in fixture["mutations"]:
        det = m["detector"]
        caught = False
        if det == "quote":
            _, rep = V.verify_draft({m["field"]: [m["bullet"]]}, transcript, mode="flag")
            caught = bool(rep.unsupported)
        elif det == "number":
            rep = V.verify_final_fields(
                {m["field"]: V.join_bullets([m["bullet"]])},
                transcript,
                V.VerificationReport(mode="flag"),
            )
            caught = any(str(p["value"]) == str(m.get("detail", "")) for p in rep.number_problems)
        elif det == "negation":
            caught = bool(V.negation_conflicts([m["bullet"]], transcript))
        elif det == "artifact":
            reasons = H.detect_artifacts(m["bullet"])
            caught = m.get("detail") in reasons if m.get("detail") else bool(reasons)
        if not caught:
            problems.append(f"plant NOT caught: {m['kind']}/{det}: {m['bullet'][:60]}")
    return problems


def main() -> int:
    failures = 0
    for fx in FIXTURES:
        problems = check(fx)
        status = "OK " if not problems else "FAIL"
        print(f"[{status}] {fx['id']} ({len(fx['mutations'])} plants)")
        for p in problems:
            failures += 1
            print(f"    - {p}")
    if failures:
        return 1
    out = ROOT / "server/bench/fixtures/precision_fa_en.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for fx in FIXTURES:
            fh.write(json.dumps(fx, ensure_ascii=False) + "\n")
    print(f"wrote {out} ({len(FIXTURES)} fixtures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
