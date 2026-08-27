// ثابت‌های سراسری برنامه، مانند پیکربندی پیش‌فرض و داده‌های پایه
export const DEFAULT_TOAST_CONFIG = {
    duration: 3000,
};

export const SPECIALTIES = [
    "Anaesthetics",
    "Cardiology",
    "Dermatology",
    "Emergency Medicine",
    "Endocrinology",
    "Family Medicine",
    "Gastroenterology",
    "General Practice",
    "General Surgery",
    "Geriatrics",
    "Haematology",
    "Internal Medicine",
    "Neurology",
    "Obstetrics and Gynaecology",
    "Oncology",
    "Ophthalmology",
    "Orthopaedics",
    "Paediatrics",
    "Psychiatry",
    "Radiology",
    "Respiratory Medicine",
    "Rheumatology",
    "Urology",
];

const SUGGESTION_PATTERNS = [
    "آخرین شواهد علمی برای ارزیابی و درمان این حوزه چیست؟",
    "چه نکات ایمنی، موارد منع مصرف و تداخل‌هایی را باید در نظر گرفت؟",
    "چه زمانی بررسی، ارجاع یا پیگیری تخصصی لازم است؟",
    "بهترین رویکرد تشخیصی مرحله‌به‌مرحله چیست؟",
    "چه گزینه‌های درمانی بر اساس راهنماهای معتبر پیشنهاد می‌شوند؟",
    "چه یافته‌هایی نیازمند اقدام فوری هستند؟",
    "برای پایش پاسخ به درمان از چه شاخص‌هایی استفاده کنیم؟",
    "چه تفاوتی میان گزینه‌های رایج مدیریت این وضعیت وجود دارد؟",
    "چگونه این موضوع را برای بیمار به زبان ساده توضیح دهیم؟",
];

const SPECIALTY_LABELS: Record<string, string> = {
    anaesthetics: "بیهوشی",
    cardiology: "قلب و عروق",
    dermatology: "پوست",
    "emergency medicine": "طب اورژانس",
    endocrinology: "غدد درون‌ریز",
    "family medicine": "پزشکی خانواده",
    gastroenterology: "گوارش",
    "general practice": "پزشکی عمومی",
    "general surgery": "جراحی عمومی",
    geriatrics: "طب سالمندی",
    haematology: "هماتولوژی",
    "internal medicine": "طب داخلی",
    neurology: "نورولوژی",
    "obstetrics and gynaecology": "زنان و زایمان",
    oncology: "انکولوژی",
    ophthalmology: "چشم‌پزشکی",
    orthopaedics: "ارتوپدی",
    paediatrics: "پزشکی کودکان",
    psychiatry: "روان‌پزشکی",
    radiology: "رادیولوژی",
    "respiratory medicine": "بیماری‌های تنفسی",
    rheumatology: "روماتولوژی",
    urology: "اورولوژی",
};

// پیشنهادها از تخصص انتخاب‌شده ساخته می‌شوند تا داشبورد بدون فهرست تکراری، فارسی بماند.
export const SPECIALTY_SUGGESTIONS: Record<string, string[]> = Object.fromEntries(
    SPECIALTIES.map((specialty) => {
        const key = specialty.toLowerCase();
        return [
            key,
            SUGGESTION_PATTERNS.map((suggestion) => `${SPECIALTY_LABELS[key]}; ${suggestion}`),
        ];
    }),
);
