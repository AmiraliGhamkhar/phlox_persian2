"""Canonical specialty catalog for the simplified first page."""

from __future__ import annotations

SPECIALTIES: list[dict[str, str]] = [
    {
        "id": "General Practice",
        "fa": "پزشکی عمومی",
        "en": "General Practice",
        "blurb": "ویزیت‌های روزمره، بیماری‌های شایع و مراقبت اولیه",
    },
    {
        "id": "Family Medicine",
        "fa": "پزشکی خانواده",
        "en": "Family Medicine",
        "blurb": "مراقبت جامع خانواده، بیماری‌های مزمن و پیشگیری",
    },
    {
        "id": "Internal Medicine",
        "fa": "طب داخلی",
        "en": "Internal Medicine",
        "blurb": "بیماری‌های داخلی بزرگسالان و پیگیری مزمن",
    },
    {
        "id": "Emergency Medicine",
        "fa": "طب اورژانس",
        "en": "Emergency Medicine",
        "blurb": "شکایت حاد، پایدارسازی و اقدامات فوری",
    },
    {
        "id": "Cardiology",
        "fa": "قلب و عروق",
        "en": "Cardiology",
        "blurb": "درد قفسه سینه، فشار خون، آریتمی و نارسایی قلب",
    },
    {
        "id": "Respiratory Medicine",
        "fa": "بیماری‌های تنفسی",
        "en": "Respiratory Medicine",
        "blurb": "آسم، COPD، سرفه و تنگی نفس",
    },
    {
        "id": "Gastroenterology",
        "fa": "گوارش",
        "en": "Gastroenterology",
        "blurb": "درد شکم، کبد، روده و آندوسکوپی",
    },
    {
        "id": "Endocrinology",
        "fa": "غدد درون‌ریز",
        "en": "Endocrinology",
        "blurb": "دیابت، تیروئید و اختلالات هورمونی",
    },
    {
        "id": "Neurology",
        "fa": "نورولوژی",
        "en": "Neurology",
        "blurb": "سردرد، سکته، تشنج و بیماری‌های عصبی",
    },
    {
        "id": "Psychiatry",
        "fa": "روان‌پزشکی",
        "en": "Psychiatry",
        "blurb": "خلق، اضطراب، خواب و وضعیت روانی",
    },
    {
        "id": "Paediatrics",
        "fa": "پزشکی کودکان",
        "en": "Paediatrics",
        "blurb": "تب، رشد، تغذیه و بیماری‌های کودکان",
    },
    {
        "id": "Obstetrics and Gynaecology",
        "fa": "زنان و زایمان",
        "en": "Obstetrics and Gynaecology",
        "blurb": "بارداری، خونریزی و مراقبت زنان",
    },
    {
        "id": "General Surgery",
        "fa": "جراحی عمومی",
        "en": "General Surgery",
        "blurb": "شکم حاد، زخم و ارزیابی پیش از عمل",
    },
    {
        "id": "Orthopaedics",
        "fa": "ارتوپدی",
        "en": "Orthopaedics",
        "blurb": "تروما، مفاصل، ستون فقرات و محدودیت حرکت",
    },
    {
        "id": "Urology",
        "fa": "اورولوژی",
        "en": "Urology",
        "blurb": "ادرار، پروستات، سنگ و عفونت ادراری",
    },
    {
        "id": "Dermatology",
        "fa": "پوست",
        "en": "Dermatology",
        "blurb": "ضایعات پوستی، خارش و بیماری‌های پوست",
    },
    {
        "id": "Ophthalmology",
        "fa": "چشم‌پزشکی",
        "en": "Ophthalmology",
        "blurb": "کاهش دید، قرمزی و فشار چشم",
    },
    {
        "id": "Oncology",
        "fa": "انکولوژی",
        "en": "Oncology",
        "blurb": "سرطان، درمان و پیگیری انکولوژی",
    },
    {
        "id": "Haematology",
        "fa": "هماتولوژی",
        "en": "Haematology",
        "blurb": "کم‌خونی، اختلال انعقاد و بیماری‌های خون",
    },
    {
        "id": "Rheumatology",
        "fa": "روماتولوژی",
        "en": "Rheumatology",
        "blurb": "درد مفاصل، بیماری‌های خودایمنی و خشکی صبحگاهی",
    },
    {
        "id": "Geriatrics",
        "fa": "طب سالمندی",
        "en": "Geriatrics",
        "blurb": "چنددارویی، سقوط و مراقبت سالمندان",
    },
    {
        "id": "Radiology",
        "fa": "رادیولوژی",
        "en": "Radiology",
        "blurb": "تفسیر تصویربرداری و توصیه بررسی",
    },
    {
        "id": "Anaesthetics",
        "fa": "بیهوشی",
        "en": "Anaesthetics",
        "blurb": "ارزیابی پیش از بیهوشی و راه هوایی",
    },
]

SPECIALTY_BY_KEY = {item["id"].lower(): item for item in SPECIALTIES}
