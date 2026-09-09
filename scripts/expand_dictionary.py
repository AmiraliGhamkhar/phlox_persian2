#!/usr/bin/env python3
"""Expand the bundled Persian-English medical dictionary to 5000+ terms.

Generates combinatorial entries (lab flags, severity grades, acute/chronic
variants, pain/fracture sites, histories, suspected conditions, allergies,
gestational ages, bilateral anatomy, imaging by region, obstetric terms,
drug classes, dosage forms, dosing schedules, exam signs) and writes them
to ``server/data/terms/generated.json``.

Safety rules (stricter than ``validate_terms.py`` where noted):
- generated Persian text contains no Latin characters at all,
- every generated ``fa`` and ``en`` value is globally unique across the
  whole merged set (existing files + generated), which trivially satisfies
  the no-duplicate-pair and filler-loop (<4x) gates,
- after writing, the real validator is executed on the merged set and the
  script fails loudly if anything is invalid.

The script is deterministic and idempotent: it rebuilds ``generated.json``
from scratch on every run from all *other* term files.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TERMS_DIR = ROOT / "server" / "data" / "terms"
OUT_FILE = TERMS_DIR / "generated.json"

sys.path.insert(0, str(ROOT / "server" / "data"))
from validate_terms import REQUIRED_CATEGORIES, validate_all

_PERSIAN_CHAR = re.compile(r"[\u0600-\u06FF]")
_LATIN = re.compile(r"[A-Za-z]")
_FA_ALLOWED = re.compile(r"^[\u0600-\u06FF\u0660-\u0669A-Za-z0-9\u200c \-/+().%]+$")
_BAD_EN_PREFIX = re.compile(r"^(post- |the |a |an )")

FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa_num(n: int) -> str:
    return str(n).translate(FA_DIGITS)


# ---------------------------------------------------------------- families

# (fa base, en base) -> elevated/low/critical variants, cat labs
LABS_3LEVEL: list[tuple[str, str]] = [
    ("سدیم", "sodium"),
    ("پتاسیم", "potassium"),
    ("کلسیم", "calcium"),
    ("منیزیم", "magnesium"),
    ("فسفر", "phosphorus"),
    ("کلراید", "chloride"),
    ("بی‌کربنات", "bicarbonate"),
    ("گلوکز", "glucose"),
    ("کراتینین", "creatinine"),
    ("اوره", "urea"),
    ("اسید اوریک", "uric acid"),
    ("کلسترول", "cholesterol"),
    ("تری‌گلیسیرید", "triglycerides"),
    ("هموگلوبین", "hemoglobin"),
    ("هماتوکریت", "hematocrit"),
    ("پلاکت", "platelets"),
    ("گلبول سفید", "white blood cells"),
    ("گلبول قرمز", "red blood cells"),
    ("آهن", "iron"),
    ("فریتین", "ferritin"),
    ("ویتامین دی", "vitamin D"),
    ("ویتامین ب‌دوازده", "vitamin B12"),
    ("فولات", "folate"),
    ("آلبومین", "albumin"),
    ("بیلی‌روبین", "bilirubin"),
    ("آلکالن فسفاتاز", "alkaline phosphatase"),
    ("آلانین ترانس‌آمیناز", "ALT"),
    ("آسپارتات ترانس‌آمیناز", "AST"),
    ("آمیلاز", "amylase"),
    ("لیپاز", "lipase"),
    ("لاکتات", "lactate"),
    ("تروپونین", "troponin"),
    ("ناتریورتیک پپتید مغزی", "brain natriuretic peptide"),
    ("دی‌دایمر", "D-dimer"),
    ("پروتئین واکنشگر سی", "C-reactive protein"),
    ("سرعت رسوب گلبول قرمز", "erythrocyte sedimentation rate"),
    ("پروکلسی‌تونین", "procalcitonin"),
    ("هورمون محرک تیروئید", "thyroid stimulating hormone"),
    ("هموگلوبین گلیکوزیله", "glycated hemoglobin"),
    ("آنتی‌ژن اختصاصی پروستات", "prostate specific antigen"),
    ("لاکتات دهیدروژناز", "lactate dehydrogenase"),
    ("کراتین کیناز", "creatine kinase"),
    ("هورمون پاراتیروئید", "parathyroid hormone"),
    ("تستوسترون", "testosterone"),
    ("پرولاکتین", "prolactin"),
    ("کورتیزول", "cortisol"),
]

# (fa base, en base) -> mild/moderate/severe variants, cat conditions
SEVERITY: list[tuple[str, str]] = [
    ("آسم", "asthma"),
    ("بیماری انسدادی مزمن ریه", "chronic obstructive pulmonary disease"),
    ("پنومونی", "pneumonia"),
    ("نارسایی قلبی", "heart failure"),
    ("فشار خون بالا", "hypertension"),
    ("فشار خون ریوی", "pulmonary hypertension"),
    ("تنگی آئورت", "aortic stenosis"),
    ("آنمی", "anemia"),
    ("افسردگی", "depression"),
    ("میگرن", "migraine"),
    ("صرع", "epilepsy"),
    ("پسوریازیس", "psoriasis"),
    ("اگزما", "eczema"),
    ("آرتریت روماتوئید", "rheumatoid arthritis"),
    ("استئوآرتریت", "osteoarthritis"),
    ("نقرس", "gout"),
    ("لوپوس اریتماتوز سیستمیک", "systemic lupus erythematosus"),
    ("کولیت اولسراتیو", "ulcerative colitis"),
    ("بیماری کرون", "Crohn disease"),
    ("سندرم روده تحریک‌پذیر", "irritable bowel syndrome"),
    ("ریفلاکس معده", "gastroesophageal reflux disease"),
    ("سیروز کبدی", "liver cirrhosis"),
    ("بیماری مزمن کلیه", "chronic kidney disease"),
    ("چاقی", "obesity"),
    ("سپسیس", "sepsis"),
    ("سکته مغزی", "stroke"),
    ("دمانس", "dementia"),
    ("سلولیت", "cellulitis"),
    ("سل", "tuberculosis"),
    ("تب دنگی", "dengue fever"),
    ("هیپوناترمی", "hyponatremia"),
]

# (fa base, en base) -> acute/chronic variants, cat conditions
ACUTE_CHRONIC: list[tuple[str, str]] = [
    ("برونشیت", "bronchitis"),
    ("سینوزیت", "sinusitis"),
    ("اوتیت مدیا", "otitis media"),
    ("تونسیلیت", "tonsillitis"),
    ("فارنژیت", "pharyngitis"),
    ("لارنژیت", "laryngitis"),
    ("هپاتیت", "hepatitis"),
    ("گاستریت", "gastritis"),
    ("سیستیت", "cystitis"),
    ("پیلونفریت", "pyelonephritis"),
    ("پروستاتیت", "prostatitis"),
    ("اپیدیدیمیت", "epididymitis"),
    ("کنژنکتیویت", "conjunctivitis"),
    ("بلفاریت", "blepharitis"),
    ("نارسایی کبد", "liver failure"),
    ("نارسایی قلب", "heart failure"),
    ("نارسایی تنفسی", "respiratory failure"),
    ("نارسایی کلیه", "renal failure"),
    ("هماتوم ساب‌دورال", "subdural hematoma"),
    ("رینیت", "rhinitis"),
    ("پریکاردیت", "pericarditis"),
    ("میوکاردیت", "myocarditis"),
    ("اندوکاردیت", "endocarditis"),
    ("مننژیت", "meningitis"),
    ("انسفالیت", "encephalitis"),
    ("استئومیلیت", "osteomyelitis"),
    ("تیروئیدیت", "thyroiditis"),
    ("داکریوسیستیت", "dacryocystitis"),
    ("دیورتیکولیت", "diverticulitis"),
    ("ماستیت", "mastitis"),
    ("کوله‌سیستیت", "cholecystitis"),
    ("پانکراتیت", "pancreatitis"),
]

# full (fa, en) supplemental pairs, cat conditions
SUPPLEMENTAL_CONDITIONS: list[tuple[str, str]] = [
    ("سرماخوردگی", "common cold"),
    ("عفونت حاد تنفسی فوقانی", "acute upper respiratory infection"),
    ("مسمومیت غذایی", "food poisoning"),
    ("آفتاب‌سوختگی", "sunburn"),
    ("بثورات پوشک", "diaper rash"),
    ("بیماری حرکت", "motion sickness"),
    ("آپاندیسیت", "appendicitis"),
    ("آپاندیسیت حاد", "acute appendicitis"),
    ("آپاندیسیت پرفوره", "perforated appendicitis"),
    ("پریتونیت", "peritonitis"),
    ("پریتونیت ثانویه", "secondary peritonitis"),
    ("فتق محبوس", "incarcerated hernia"),
    ("فتق خفه‌شده", "strangulated hernia"),
    ("پیچ‌خوردگی تخمدان", "ovarian torsion"),
    ("شکستگی آلت", "penile fracture"),
    ("احتباس ادرار", "urinary retention"),
    ("استوماتیت", "stomatitis"),
    ("ژنژیویت", "gingivitis"),
    ("پریودنتیت", "periodontitis"),
    ("آبسه دندان", "dental abscess"),
    ("پریکورونیت", "pericoronitis"),
    ("اختلال مفصل گیجگاهی‌فکی", "temporomandibular joint disorder"),
    ("ماستوئیدیت", "mastoiditis"),
    ("خراش قرنیه", "corneal abrasion"),
    ("هایفما", "hyphema"),
    ("آسیب شیمیایی چشم", "chemical eye injury"),
    ("کرامپ گرمایی", "heat cramps"),
    ("هیپرترمی", "hyperthermia"),
    ("موی فرورفته", "ingrown hair"),
    ("گاستروانتریت ویروسی", "viral gastroenteritis"),
    ("اسهال مسافران", "traveler diarrhea"),
    ("اختلال جت‌لگ", "jet lag disorder"),
    ("اختلاف طول پا", "leg length discrepancy"),
    ("سندرم استفراغ دوره‌ای", "cyclic vomiting syndrome"),
    ("آنکیلوگلوسی", "ankyloglossia"),
    ("سوختگی درجه یک", "first-degree burn"),
    ("سوختگی درجه دو", "second-degree burn"),
    ("سوختگی درجه سه", "third-degree burn"),
    ("سوختگی با ضخامت نسبی", "partial-thickness burn"),
    ("سوختگی تمام‌ضخامت", "full-thickness burn"),
    ("سوختگی شیمیایی", "chemical burn"),
    ("آسیب استنشاقی", "inhalation injury"),
]

# full (fa, en) supplemental pairs, cat oncology
SUPPLEMENTAL_ONCOLOGY: list[tuple[str, str]] = [
    ("کرانیوفارنژیوما", "craniopharyngioma"),
    ("شوانوما", "schwannoma"),
    ("نوروفیبروما", "neurofibroma"),
    ("آدنوما", "adenoma"),
    ("آدنوکارسینوما", "adenocarcinoma"),
    ("ملانوم", "melanoma"),
    ("تراتوما", "teratoma"),
    ("دیسژرمینوما", "dysgerminoma"),
    ("تومور کیسه زرده", "yolk sac tumor"),
    ("کوریوکارسینوما", "choriocarcinoma"),
    ("مول مهاجم", "invasive mole"),
    ("گلیوما", "glioma"),
    ("هپاتوبلاستوما", "hepatoblastoma"),
    ("فیبروسارکوما", "fibrosarcoma"),
    ("آنژیوسارکوما", "angiosarcoma"),
    ("سارکوم سینوویال", "synovial sarcoma"),
    ("تومور استرومایی گوارشی", "gastrointestinal stromal tumor"),
    ("تومور دسموئید", "desmoid tumor"),
    ("کارسینوم تیموس", "thymic carcinoma"),
    ("میکسومای قلبی", "cardiac myxoma"),
    ("پاراگانگلیوما", "paraganglioma"),
    ("آلدوسترونوما", "aldosteronoma"),
    ("سرطان پوست غیرملانومایی", "nonmelanoma skin cancer"),
    ("کارسینوم سلول مرکل", "Merkel cell carcinoma"),
    ("لنفوم لنفوبلاستیک", "lymphoblastic lymphoma"),
    ("لوسمی میلومونوسیتیک مزمن", "chronic myelomonocytic leukemia"),
    ("ماستوسیتوز سیستمیک", "systemic mastocytosis"),
    ("هیستیوسیتوز", "histiocytosis"),
    ("بیماری اردهایم‌چستر", "Erdheim-Chester disease"),
    ("لنفوم آناپلاستیک سلول بزرگ", "anaplastic large cell lymphoma"),
]

# full (fa, en) supplemental pairs, cat symptoms
SUPPLEMENTAL_SYMPTOMS: list[tuple[str, str]] = [
    ("تاول", "blister"),
    ("تراشه زیر پوست", "splinter"),
    ("ترک لب", "chapped lips"),
    ("کلاه گهواره", "cradle cap"),
    ("دندان‌درآوردن", "teething"),
    ("درد رشد", "growing pains"),
    ("سردرد بستنی", "ice-cream headache"),
    ("سردرد پس‌از‌پونکسیون کمری", "post-dural puncture headache"),
    ("خماری", "hangover"),
    ("ترک کافئین", "caffeine withdrawal"),
    ("ولع نیکوتین", "nicotine craving"),
    ("تهوع بارداری", "morning sickness"),
    ("کرامپ شبانه پا", "nocturnal leg cramps"),
    ("سرفه مزمن", "chronic cough"),
    ("اسهال حاد", "acute diarrhea"),
    ("اسهال مزمن", "chronic diarrhea"),
    ("یبوست مزمن", "chronic constipation"),
    ("درد حاد شکم", "acute abdominal pain"),
    ("درد مزمن شکم", "chronic abdominal pain"),
    ("سردرد مزمن", "chronic headache"),
    ("سردرد مزمن روزانه", "chronic daily headache"),
    ("کمردرد حاد", "acute low back pain"),
    ("کمردرد مزمن", "chronic low back pain"),
    ("درد مزمن گردن", "chronic neck pain"),
    ("درد سینه غیرقلبی", "noncardiac chest pain"),
    ("بی‌خوابی مزمن", "chronic insomnia"),
    ("سرگیجه مزمن", "chronic dizziness"),
    ("تهوع مزمن", "chronic nausea"),
    ("سکسکه مداوم", "persistent hiccups"),
    ("شب‌ادراری", "bedwetting"),
    ("مکیدن انگشت", "thumb sucking"),
    ("جویدن ناخن", "nail biting"),
    ("لنگیدن", "limping"),
    ("راه رفتن روی پنجه", "toe walking"),
    ("پای پرانتزی", "bowlegs"),
    ("پای ضربدری", "knock knees"),
    ("صافی کف پا", "flat feet"),
    ("چرخش پا به داخل", "in-toeing"),
    ("چرخش پا به خارج", "out-toeing"),
]

# full (fa, en) pain pairs, cat symptoms
PAIN: list[tuple[str, str]] = [
    ("درد دست", "hand pain"),
    ("درد انگشت", "finger pain"),
    ("دندان‌درد", "toothache"),
    ("درد بازو", "arm pain"),
    ("درد ساعد", "forearm pain"),
    ("درد باسن", "buttock pain"),
    ("درد پرینه", "perineal pain"),
    ("درد آلت", "penile pain"),
    ("درد ولو", "vulvar pain"),
    ("درد واژن", "vaginal pain"),
    ("درد دنده", "rib pain"),
    ("درد جناق", "sternal pain"),
    ("درد کتف", "scapular pain"),
    ("تندرنس دیواره سینه", "chest wall tenderness"),
    ("درد مفصل بزرگ", "large joint pain"),
    ("درد ساکروایلیاک", "sacroiliac pain"),
    ("درد خارجی هیپ", "lateral hip pain"),
    ("درد قدامی زانو", "anterior knee pain"),
    ("درد جلوی پا", "forefoot pain"),
    ("درد تاندون", "tendon pain"),
    ("درد فانتوم", "phantom limb pain"),
    ("درد استامپ", "residual limb pain"),
    ("درد تخمک‌گذاری", "ovulation pain"),
    ("درد اسکروتوم", "scrotal pain"),
    ("درد نوک پستان", "nipple pain"),
]

# full (fa, en) fracture pairs, cat conditions
FRACTURE: list[tuple[str, str]] = [
    ("شکستگی جمجمه", "skull fracture"),
    ("شکستگی صورت", "facial fracture"),
    ("شکستگی انفجاری اوربیت", "orbital blowout fracture"),
    ("شکستگی گونه", "zygomatic fracture"),
    ("شکستگی فک تحتانی", "mandibular fracture"),
    ("شکستگی لفور", "Le Fort fracture"),
    ("شکستگی دنده", "rib fracture"),
    ("شکستگی جناق", "sternal fracture"),
    ("شکستگی کتف", "scapular fracture"),
    ("شکستگی پروگزیمال هومروس", "proximal humerus fracture"),
    ("شکستگی سوپراکوندیلار", "supracondylar fracture"),
    ("شکستگی اولکرانون", "olecranon fracture"),
    ("شکستگی سر رادیوس", "radial head fracture"),
    ("شکستگی مونتجیا", "Monteggia fracture"),
    ("شکستگی گالئاتزی", "Galeazzi fracture"),
    ("شکستگی دیستال رادیوس", "distal radius fracture"),
    ("شکستگی متاکارپ", "metacarpal fracture"),
    ("شکستگی بوکسور", "boxer fracture"),
    ("شکستگی فالانکس", "phalangeal fracture"),
    ("شکستگی لگن", "pelvic fracture"),
    ("شکستگی استابولوم", "acetabular fracture"),
    ("شکستگی ساکروم", "sacral fracture"),
    ("شکستگی شفت فمور", "femoral shaft fracture"),
    ("شکستگی دیستال فمور", "distal femur fracture"),
    ("شکستگی شفت تیبیا", "tibial shaft fracture"),
    ("شکستگی فیبولا", "fibular fracture"),
    ("شکستگی متاتارس", "metatarsal fracture"),
    ("شکستگی ادونتوئید", "odontoid fracture"),
    ("شکستگی هنگمن", "hangman fracture"),
    ("شکستگی جفرسون", "Jefferson fracture"),
    ("شکستگی ستون فقرات گردنی", "cervical spine fracture"),
    ("شکستگی ستون فقرات سینه‌ای", "thoracic spine fracture"),
    ("شکستگی ستون فقرات کمری", "lumbar spine fracture"),
    ("شکستگی گرین‌استیک", "greenstick fracture"),
    ("شکستگی باکل", "buckle fracture"),
    ("شکستگی سالتر‌هریس", "Salter-Harris fracture"),
    ("شکستگی باز", "open fracture"),
    ("شکستگی خردشده", "comminuted fracture"),
    ("شکستگی کندگی", "avulsion fracture"),
    ("شکستگی دور پروتز", "periprosthetic fracture"),
    ("شکستگی ناکافی", "insufficiency fracture"),
]

# (fa base, en base) -> "history of X", cat history
HISTORY: list[tuple[str, str]] = [
    ("حمله ایسکمیک گذرا", "transient ischemic attack"),
    ("بیماری دریچه قلب", "heart valve disease"),
    ("بیماری عروق کرونر", "coronary artery disease"),
    ("بیماری شریانی محیطی", "peripheral artery disease"),
    ("ترومبوز ورید عمقی", "deep vein thrombosis"),
    ("آمبولی ریه", "pulmonary embolism"),
    ("آنوریسم آئورت", "aortic aneurysm"),
    ("انسداد مزمن ریوی", "chronic obstructive pulmonary disease"),
    ("پنومونی", "pneumonia"),
    ("سل", "tuberculosis"),
    ("کووید نوزده", "COVID-19"),
    ("هپاتیت", "hepatitis"),
    ("سیروز", "cirrhosis"),
    ("بیماری التهابی روده", "inflammatory bowel disease"),
    ("سندرم روده تحریک‌پذیر", "irritable bowel syndrome"),
    ("بیماری سلیاک", "celiac disease"),
    ("سنگ کلیه", "kidney stones"),
    ("عفونت ادراری مکرر", "recurrent urinary tract infections"),
    ("بزرگی پروستات", "benign prostatic hyperplasia"),
    ("سرطان پروستات", "prostate cancer"),
    ("سرطان پستان", "breast cancer"),
    ("سرطان سرویکس", "cervical cancer"),
    ("سرطان پوست", "skin cancer"),
    ("سرطان تیروئید", "thyroid cancer"),
    ("سرطان کولون", "colon cancer"),
    ("سرطان ریه", "lung cancer"),
    ("آنمی", "anemia"),
    ("اختلال خونریزی‌دهنده", "bleeding disorder"),
    ("میگرن", "migraine"),
    ("تشنج", "seizures"),
    ("ضربه مغزی", "concussion"),
    ("تومور مغزی", "brain tumor"),
    ("مننژیت", "meningitis"),
    ("مولتیپل اسکلروزیس", "multiple sclerosis"),
    ("بیماری پارکینسون", "Parkinson disease"),
    ("دمانس", "dementia"),
    ("نوروپاتی", "neuropathy"),
    ("جراحی ستون فقرات", "spine surgery"),
    ("شکستگی", "fractures"),
    ("پوکی استخوان", "osteoporosis"),
    ("آرتریت روماتوئید", "rheumatoid arthritis"),
    ("لوپوس", "lupus"),
    ("نقرس", "gout"),
    ("پسوریازیس", "psoriasis"),
    ("اگزما", "eczema"),
    ("آلرژی", "allergies"),
    ("آلرژی غذایی", "food allergy"),
    ("آنافیلاکسی", "anaphylaxis"),
    ("دیابت بارداری", "gestational diabetes"),
    ("پره‌اکلامپسی", "preeclampsia"),
    ("مرده‌زایی", "stillbirth"),
    ("حاملگی خارج‌رحمی", "ectopic pregnancy"),
    ("ناباروری", "infertility"),
    ("اندومتریوز", "endometriosis"),
    ("فیبروم رحم", "uterine fibroids"),
    ("پاپ‌اسمیر غیرطبیعی", "abnormal Pap smear"),
    ("عفونت منتقله جنسی", "sexually transmitted infection"),
    ("اچ‌آی‌وی", "HIV"),
    ("اختلال استرس پس‌از‌سانحه", "post-traumatic stress disorder"),
    ("اختلال وسواسی‌جبری", "obsessive-compulsive disorder"),
    ("اختلال خوردن", "eating disorder"),
    ("بستری روان‌پزشکی", "psychiatric admission"),
    ("برداشتن طحال", "splenectomy"),
    ("برداشتن کیسه صفرا", "cholecystectomy"),
    ("برداشتن آپاندیس", "appendectomy"),
    ("برداشتن رحم", "hysterectomy"),
    ("برداشتن لوزه", "tonsillectomy"),
    ("ترمیم فتق", "hernia repair"),
    ("سقط القایی", "induced abortion"),
    ("مصرف ویپ", "vaping"),
]

# (fa base, en base) -> "suspected X", cat conditions
SUSPECTED: list[tuple[str, str]] = [
    ("آپاندیسیت", "appendicitis"),
    ("سکته قلبی", "myocardial infarction"),
    ("سکته مغزی", "stroke"),
    ("آمبولی ریه", "pulmonary embolism"),
    ("سپسیس", "sepsis"),
    ("مننژیت", "meningitis"),
    ("حاملگی خارج‌رحمی", "ectopic pregnancy"),
    ("پیچ‌خوردگی بیضه", "testicular torsion"),
    ("پیچ‌خوردگی تخمدان", "ovarian torsion"),
    ("انسداد روده", "bowel obstruction"),
    ("پارگی احشا", "perforated viscus"),
    ("دایسکشن آئورت", "aortic dissection"),
    ("پنوموتوراکس", "pneumothorax"),
    ("شکستگی", "fracture"),
    ("بدخیمی", "malignancy"),
    ("سل", "tuberculosis"),
    ("اندوکاردیت", "endocarditis"),
    ("کوله‌سیستیت", "cholecystitis"),
    ("پانکراتیت", "pancreatitis"),
    ("ترومبوز ورید عمقی", "deep vein thrombosis"),
    ("خونریزی گوارشی", "gastrointestinal bleeding"),
    ("عفونت ادراری", "urinary tract infection"),
    ("پنومونی", "pneumonia"),
    ("سلولیت", "cellulitis"),
    ("پره‌اکلامپسی", "preeclampsia"),
    ("دکولمان جفت", "placental abruption"),
]

# (fa base, en base) -> "X allergy", cat conditions
ALLERGY: list[tuple[str, str]] = [
    ("پنی‌سیلین", "penicillin"),
    ("سولفا", "sulfa"),
    ("آسپرین", "aspirin"),
    ("ضدالتهاب غیراستروئیدی", "NSAID"),
    ("ماده حاجب", "contrast"),
    ("صدف دریایی", "shellfish"),
    ("تخم‌مرغ", "egg"),
    ("شیر", "milk"),
    ("سویا", "soy"),
    ("گندم", "wheat"),
    ("آجیل درختی", "tree nut"),
    ("ماهی", "fish"),
    ("کنجد", "sesame"),
    ("نیش زنبور", "bee sting"),
    ("حیوان خانگی", "pet"),
    ("مایت گرد و غبار", "dust mite"),
    ("کپک", "mold"),
    ("گرده", "pollen"),
    ("گرده چمن", "grass pollen"),
    ("نیکل", "nickel"),
    ("چسب", "adhesive"),
    ("ید", "iodine"),
    ("بی‌حس‌کننده موضعی", "local anesthetic"),
    ("بیهوشی", "anesthetic"),
    ("واکسن", "vaccine"),
    ("مواد افیونی", "opioid"),
    ("انسولین", "insulin"),
    ("هپارین", "heparin"),
]

# (fa base, en base) -> "X intolerance", cat conditions
INTOLERANCE: list[tuple[str, str]] = [
    ("استاتین", "statin"),
    ("گلوتن", "gluten"),
    ("هیستامین", "histamine"),
    ("سالیسیلات", "salicylate"),
    ("سولفیت", "sulfite"),
    ("الکل", "alcohol"),
    ("ورزش", "exercise"),
    ("فروکتوز", "fructose"),
]

# full (fa, en) vitals pairs, cat vitals
VITALS_ABNORMAL: list[tuple[str, str]] = [
    ("فشار خون بالا", "high blood pressure"),
    ("فشار خون پایین", "low blood pressure"),
    ("ضربان قلب تند", "fast heart rate"),
    ("ضربان قلب کند", "slow heart rate"),
    ("تعداد تنفس بالا", "fast respiratory rate"),
    ("تعداد تنفس پایین", "slow respiratory rate"),
    ("دمای بدن بالا", "high body temperature"),
    ("دمای بدن پایین", "low body temperature"),
    ("اشباع اکسیژن پایین", "low oxygen saturation"),
    ("قند خون بالا", "high blood sugar"),
    ("قند خون پایین", "low blood sugar"),
    ("تندنفسی", "tachypnea"),
    ("کندنفسی", "bradypnea"),
    ("آپنه", "apnea"),
    ("نبض نامنظم", "irregular pulse"),
]

# (fa noun, en noun) -> right/left variants, cat anatomy
BILATERAL: list[tuple[str, str]] = [
    ("ریه", "lung"),
    ("کلیه", "kidney"),
    ("تخمدان", "ovary"),
    ("بیضه", "testis"),
    ("پستان", "breast"),
    ("چشم", "eye"),
    ("گوش", "ear"),
    ("دست", "hand"),
    ("پا", "foot"),
    ("شانه", "shoulder"),
    ("زانو", "knee"),
    ("مفصل هیپ", "hip joint"),
    ("مفصل مچ پا", "ankle joint"),
    ("مچ دست", "wrist"),
    ("آرنج", "elbow"),
    ("سوراخ بینی", "nostril"),
    ("غده آدرنال", "adrenal gland"),
    ("شریان کاروتید", "carotid artery"),
    ("شریان فمورال", "femoral artery"),
    ("شریان رادیال", "radial artery"),
    ("ورید ژوگولار", "jugular vein"),
    ("حالب", "ureter"),
    ("لوله فالوپ", "fallopian tube"),
    ("لوزه", "tonsil"),
]

ANATOMY_SINGLES: list[tuple[str, str]] = [
    ("چشم", "eye"),
    ("بازو", "arm"),
    ("سوراخ بینی", "nostril"),
]

# (fa region, en region) imaging patterns, cat procedures
ULTRASOUND: list[tuple[str, str]] = [
    ("تیروئید", "thyroid"),
    ("گردن", "neck"),
    ("پستان", "breast"),
    ("کبد", "liver"),
    ("کیسه صفرا", "gallbladder"),
    ("طحال", "spleen"),
    ("پانکراس", "pancreas"),
    ("مثانه", "bladder"),
    ("پروستات", "prostate"),
    ("اسکروتوم", "scrotal"),
    ("چشم", "ocular"),
    ("هیپ", "hip"),
    ("شانه", "shoulder"),
    ("زانو", "knee"),
    ("مچ پا", "ankle"),
    ("مچ دست", "wrist"),
    ("بافت نرم", "soft tissue"),
    ("آپاندیس", "appendix"),
    ("روده", "bowel"),
    ("ریه", "lung"),
    ("پلور", "pleural"),
    ("آئورت", "aortic"),
    ("شفافیت نوکال", "nuchal translucency"),
]

DOPPLER_EXTRA: list[tuple[str, str]] = [
    ("داپلر شریان نافی", "umbilical artery Doppler"),
    ("داپلر شریان مغزی میانی", "middle cerebral artery Doppler"),
]

CT_REGIONS: list[tuple[str, str]] = [
    ("گردن", "neck"),
    ("سینه", "chest"),
    ("لگن", "pelvic"),
    ("ستون فقرات", "spine"),
    ("صورت", "facial"),
    ("سینوس", "sinus"),
    ("استخوان تمپورال", "temporal bone"),
]

CT_ANGIO: list[tuple[str, str]] = [
    ("آنژیوگرافی کرونری با سی‌تی", "coronary CT angiography"),
    ("آنژیوگرافی ریوی با سی‌تی", "CT pulmonary angiography"),
    ("آنژیوگرافی آئورت با سی‌تی", "aortic CT angiography"),
    ("آنژیوگرافی کلیه با سی‌تی", "renal CT angiography"),
    ("آنژیوگرافی مزانتر با سی‌تی", "mesenteric CT angiography"),
    ("آنژیوگرافی اندام تحتانی با سی‌تی", "lower extremity CT angiography"),
    ("آنژیوگرافی سر با سی‌تی", "head CT angiography"),
    ("آنژیوگرافی گردن با سی‌تی", "neck CT angiography"),
]

MRI_REGIONS: list[tuple[str, str]] = [
    ("کبد", "liver"),
    ("پانکراس", "pancreas"),
    ("کلیه", "kidney"),
    ("آدرنال", "adrenal"),
    ("لگن", "pelvic"),
    ("جفت", "placental"),
    ("زانو", "knee"),
    ("شانه", "shoulder"),
    ("هیپ", "hip"),
    ("مچ پا", "ankle"),
    ("مچ دست", "wrist"),
    ("مفصل گیجگاهی‌فکی", "TMJ"),
    ("شبکه بازویی", "brachial plexus"),
]

MRA_EXTRA: list[tuple[str, str]] = [
    ("آنژیوگرافی مغز با ام‌آر‌آی", "brain MRA"),
    ("آنژیوگرافی گردن با ام‌آر‌آی", "neck MRA"),
    ("آنژیوگرافی کلیه با ام‌آر‌آی", "renal MRA"),
]

XRAY_REGIONS: list[tuple[str, str]] = [
    ("دست", "hand"),
    ("پا", "foot"),
    ("مچ پا", "ankle"),
    ("زانو", "knee"),
    ("شانه", "shoulder"),
    ("آرنج", "elbow"),
    ("مچ دست", "wrist"),
    ("هیپ", "hip"),
    ("فمور", "femur"),
    ("هومروس", "humerus"),
    ("ساعد", "forearm"),
    ("استخوان‌های صورت", "facial bones"),
    ("سینوس", "sinus"),
    ("استخوان‌های بینی", "nasal bones"),
    ("فک تحتانی", "mandible"),
    ("ستون فقرات سینه‌ای", "thoracic spine"),
    ("ستون فقرات کمری", "lumbar spine"),
    ("دنده", "rib"),
    ("ترقوه", "clavicle"),
]

XRAY_EXTRA: list[tuple[str, str]] = [
    ("رادیوگرافی کلیه‌حالب‌مثانه", "KUB X-ray"),
    ("رادیوگرافی سن استخوانی", "bone age X-ray"),
    ("سری رادیوگرافی اسکولیوز", "scoliosis X-ray series"),
]

# full (fa, en) exam-sign pairs, cat symptoms
EXAM_SIGNS: list[tuple[str, str]] = [
    ("سوفل سیستولیک", "systolic murmur"),
    ("سوفل دیاستولیک", "diastolic murmur"),
    ("سوفل مداوم", "continuous murmur"),
    ("سوفل قلبی", "heart murmur"),
    ("گالوپ اس سه", "S3 gallop"),
    ("گالوپ اس چهار", "S4 gallop"),
    ("راب اصطکاکی پریکارد", "pericardial friction rub"),
    ("اسنپ باز شدن", "opening snap"),
    ("کلیک جهشی", "ejection click"),
    ("دوپاره شدن صدای دوم", "split S2"),
    ("بلند بودن پی دو", "loud P2"),
    ("برویی کاروتید", "carotid bruit"),
    ("برویی شکمی", "abdominal bruit"),
    ("برویی کلیوی", "renal bruit"),
    ("برویی فمورال", "femoral bruit"),
    ("هام وریدی", "venous hum"),
    ("ویز اکسپیراتوری", "expiratory wheeze"),
    ("استریدور دمی", "inspiratory stridor"),
    ("کاهش صداهای تنفسی", "diminished breath sounds"),
    ("فقدان صداهای تنفسی", "absent breath sounds"),
    ("صداهای تنفسی برونکیال", "bronchial breath sounds"),
    ("فرمیتوس لمسی", "tactile fremitus"),
    ("ساکاشن اسپلش", "succussion splash"),
    ("ماتیتی جابه‌جاشونده", "shifting dullness"),
    ("موج مایع", "fluid wave"),
    ("صداهای روده‌ای پرفعال", "hyperactive bowel sounds"),
    ("صداهای روده‌ای کم‌فعال", "hypoactive bowel sounds"),
    ("فقدان صداهای روده‌ای", "absent bowel sounds"),
    ("صداهای روده‌ای زیر و بم", "high-pitched bowel sounds"),
]

# full (fa, en) obstetric pairs, cat obstetric
OBSTETRIC: list[tuple[str, str]] = [
    ("نوزاد نارس", "preterm newborn"),
    ("نوزاد دیررس نارس", "late-preterm newborn"),
    ("نوزاد ترم زودرس", "early-term newborn"),
    ("نوزاد ترم", "full-term newborn"),
    ("نوزاد پست‌ترم", "post-term newborn"),
    ("کوچک برای سن بارداری", "small for gestational age"),
    ("بزرگ برای سن بارداری", "large for gestational age"),
    ("مناسب برای سن بارداری", "appropriate for gestational age"),
    ("وزن کم هنگام تولد", "low birth weight"),
    ("وزن بسیار کم هنگام تولد", "very low birth weight"),
    ("وزن فوق‌العاده کم هنگام تولد", "extremely low birth weight"),
    ("نمره آپگار", "APGAR score"),
    ("گاز خون بند ناف", "umbilical cord blood gas"),
    ("کلمپ تأخیری بند ناف", "delayed cord clamping"),
    ("تماس پوست‌به‌پوست", "skin-to-skin contact"),
    ("نمره بالارد", "Ballard score"),
    ("مولدینگ سر جنین", "fetal head molding"),
    ("استیشن جنین", "fetal station"),
    ("نزول سر جنین به لگن", "fetal engagement"),
    ("افاسمان سرویکس", "cervical effacement"),
    ("دیلاتاسیون سرویکس", "cervical dilation"),
    ("نمره بیشاپ", "Bishop score"),
    ("سویپ غشا", "membrane sweeping"),
    ("پارگی مصنوعی کیسه آب", "artificial rupture of membranes"),
    ("الکترود اسکالپ جنین", "fetal scalp electrode"),
    ("کاتتر فشار داخل‌رحمی", "intrauterine pressure catheter"),
    ("مانیتورینگ خارجی جنین", "external fetal monitoring"),
    ("مانیتورینگ داخلی جنین", "internal fetal monitoring"),
    ("کندی متغیر قلب جنین", "variable fetal decelerations"),
    ("کندی دیررس قلب جنین", "late fetal decelerations"),
    ("کندی زودرس قلب جنین", "early fetal decelerations"),
    ("تاکی‌کاردی جنین", "fetal tachycardia"),
    ("برادی‌کاردی جنین", "fetal bradycardia"),
    ("تغییرپذیری حداقلی قلب جنین", "minimal fetal variability"),
    ("تغییرپذیری متوسط قلب جنین", "moderate fetal variability"),
    ("شتاب قلب جنین", "fetal accelerations"),
    ("تریسینگ غیراطمینان‌بخش", "non-reassuring fetal tracing"),
    ("آمنیواینفیوژن", "amnioinfusion"),
    ("توکولیز", "tocolysis"),
    ("استروئید پیش‌از‌تولد", "antenatal corticosteroids"),
    ("پروفیلاکسی استرپتوکوک گروه بی", "group B strep prophylaxis"),
    ("آتونی رحم", "uterine atony"),
    ("جفت باقی‌مانده", "retained placenta"),
    ("وارونگی رحم", "uterine inversion"),
    ("پره‌اکلامپسی پس‌از‌زایمان", "postpartum preeclampsia"),
    ("کاردیومیوپاتی پری‌پارتوم", "peripartum cardiomyopathy"),
    ("پارگی رحم", "uterine rupture"),
    ("وازا پرویا", "vasa previa"),
    ("چسبندگی ولمنتوس", "velamentous cord insertion"),
    ("جفت دوبخشی", "bilobed placenta"),
    ("لوب فرعی جفت", "succenturiate placental lobe"),
    ("کوریوآنژیوما", "chorioangioma"),
    ("بند ناف دور گردن", "nuchal cord"),
    ("گره خوردگی بند ناف", "umbilical cord entanglement"),
    ("سندرم انتقال خون دوقلویی", "twin-twin transfusion syndrome"),
    ("محدودیت رشد انتخابی جنین", "selective fetal growth restriction"),
    ("دوقلوی مونوآمنیوتیک", "monoamniotic twins"),
    ("دوقلوی مونوکوریونیک", "monochorionic twins"),
    ("دوقلوی دی‌کوریونیک", "dichorionic twins"),
    ("دوقلوی به‌هم‌چسبیده", "conjoined twins"),
    ("دوقلوی محوشونده", "vanishing twin"),
    ("حاملگی هتروتوپیک", "heterotopic pregnancy"),
    ("حاملگی شکمی", "abdominal pregnancy"),
    ("حاملگی تخمدانی", "ovarian pregnancy"),
    ("حاملگی لوله‌ای", "tubal pregnancy"),
    ("حاملگی بینابینی", "interstitial pregnancy"),
    ("تلاش برای زایمان طبیعی پس‌از‌سزارین", "trial of labor after cesarean"),
    ("زایمان طبیعی پس‌از‌سزارین", "vaginal birth after cesarean"),
    ("پارگی پرینه درجه یک", "first-degree perineal tear"),
    ("پارگی پرینه درجه دو", "second-degree perineal tear"),
    ("پارگی لابیا", "labial laceration"),
    ("پارگی واژن", "vaginal laceration"),
    ("پارگی سرویکس", "cervical laceration"),
    ("هماتوم لگن پس‌از‌زایمان", "postpartum pelvic hematoma"),
    ("هماتوم ولو", "vulvar hematoma"),
    ("عفونت زخم سزارین", "cesarean wound infection"),
    ("از شیر گرفتن", "breastfeeding weaning"),
    ("نوک پستان فرورفته", "inverted nipples"),
    ("پرتولیدی شیر", "breast milk oversupply"),
    ("انسداد مجرای شیر", "blocked milk duct"),
    ("برفک نوک پستان", "nipple thrush"),
    ("وازواسپاسم نوک پستان", "nipple vasospasm"),
    ("اعتصاب شیرخوار", "nursing strike"),
    ("تغذیه خوشه‌ای", "cluster feeding"),
    ("جهش رشد شیرخوار", "infant growth spurt"),
    ("سه‌ماهه چهارم", "fourth trimester"),
    ("بهبودی پس‌از‌زایمان", "postpartum recovery"),
    ("پیشگیری از بارداری پس‌از‌زایمان", "postpartum contraception"),
    ("آمنوره شیردهی", "lactational amenorrhea"),
]

# full (fa, en) drug-class pairs, cat medications
DRUG_CLASSES: list[tuple[str, str]] = [
    ("بتابلوکر", "beta blocker"),
    ("مسدودکننده کانال کلسیم", "calcium channel blocker"),
    ("مهارکننده آنزیم مبدل آنژیوتانسین", "ACE inhibitor"),
    ("مسدودکننده گیرنده آنژیوتانسین", "angiotensin receptor blocker"),
    ("دیورتیک", "diuretic"),
    ("استاتین", "statin"),
    ("ضدانعقاد", "anticoagulant"),
    ("ضدپلاکت", "antiplatelet"),
    ("آنتی‌بیوتیک", "antibiotic"),
    ("ضدقارچ", "antifungal"),
    ("ضدویروس", "antiviral"),
    ("آنتی‌سایکوتیک", "antipsychotic"),
    ("ضدافسردگی", "antidepressant"),
    ("ضداضطراب", "anxiolytic"),
    ("خواب‌آور", "hypnotic"),
    ("ضدصرع", "antiepileptic"),
    ("آنتی‌هیستامین", "antihistamine"),
    ("گشادکننده برونش", "bronchodilator"),
    ("کورتیکواستروئید", "corticosteroid"),
    ("ضدالتهاب غیراستروئیدی", "NSAID"),
    ("مواد افیونی", "opioid"),
    ("مهارکننده پمپ پروتون", "proton pump inhibitor"),
    ("بلوکر اچ دو", "H2 blocker"),
    ("ملین", "laxative"),
    ("ضداسهال", "antidiarrheal"),
    ("ضداستفراغ", "antiemetic"),
    ("ضددیابت", "antidiabetic"),
    ("انسولین", "insulin"),
    ("هورمون تیروئید", "thyroid hormone"),
    ("بیس‌فسفونات", "bisphosphonate"),
    ("سرکوب‌کننده ایمنی", "immunosuppressant"),
    ("داروی شیمی‌درمانی", "chemotherapy agent"),
    ("آنتی‌بادی مونوکلونال", "monoclonal antibody"),
    ("واکسن", "vaccine"),
    ("ماده حاجب", "contrast agent"),
    ("سرم وریدی", "intravenous fluid"),
    ("فرآورده خونی", "blood product"),
    ("پادزهر", "antidote"),
    ("ویتامین", "vitamin"),
    ("مکمل معدنی", "mineral supplement"),
    ("پروبیوتیک", "probiotic"),
    ("جایگزین الکترولیت", "electrolyte replacement"),
    ("حجم‌دهنده پلاسما", "plasma expander"),
]

# full (fa, en) dosage-form pairs, cat medications
DOSAGE_FORMS: list[tuple[str, str]] = [
    ("قرص خوراکی", "oral tablet"),
    ("قرص زیرزبانی", "sublingual tablet"),
    ("قرص جویدنی", "chewable tablet"),
    ("قرص آهسته‌رهش", "extended-release tablet"),
    ("کپسول خوراکی", "oral capsule"),
    ("شربت خوراکی", "oral syrup"),
    ("سوسپانسیون خوراکی", "oral suspension"),
    ("قطره خوراکی", "oral drops"),
    ("اسپری استنشاقی دوزسنج", "metered-dose inhaler"),
    ("پودر استنشاقی", "dry powder inhaler"),
    ("محلول نبولایزر", "nebulizer solution"),
    ("اسپری بینی", "nasal spray"),
    ("قطره چشمی", "eye drops"),
    ("پماد چشمی", "eye ointment"),
    ("قطره گوش", "ear drops"),
    ("کرم موضعی", "topical cream"),
    ("پماد موضعی", "topical ointment"),
    ("ژل موضعی", "topical gel"),
    ("لوسیون موضعی", "topical lotion"),
    ("چسب پوستی", "transdermal patch"),
    ("شیاف مقعدی", "rectal suppository"),
    ("محلول تزریقی", "injectable solution"),
    ("انفوزیون وریدی", "intravenous infusion"),
    ("سرنگ آماده", "prefilled syringe"),
    ("قلم تزریق", "auto-injector"),
    ("دهان‌شویه", "mouthwash"),
    ("قرص مکیدنی", "lozenge"),
]

# full (fa, en) dosing-schedule pairs, cat plan
DOSING_SCHEDULE: list[tuple[str, str]] = [
    ("روزی یک بار", "once daily"),
    ("روزی دو بار", "twice daily"),
    ("روزی سه بار", "three times daily"),
    ("روزی چهار بار", "four times daily"),
    ("هر صبح", "every morning"),
    ("هر شب", "every night"),
    ("هنگام خواب", "at bedtime"),
    ("قبل از غذا", "before meals"),
    ("بعد از غذا", "after meals"),
    ("همراه غذا", "with food"),
    ("با معده خالی", "on empty stomach"),
    ("در صورت نیاز", "as needed"),
    ("به مدت هفت روز", "for 7 days"),
    ("به مدت ده روز", "for 10 days"),
    ("به مدت چهارده روز", "for 14 days"),
    ("تا اتمام دارو", "until finished"),
    ("کاهش تدریجی دوز", "taper dose gradually"),
    ("مصرف منظم دارو", "take medication regularly"),
]


# ------------------------------------------------------------------ build


def build_candidates() -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for fa, en in LABS_3LEVEL:
        out.append((f"{fa} بالا", f"elevated {en}", "labs"))
        out.append((f"{fa} پایین", f"low {en}", "labs"))
        out.append((f"سطح بحرانی {fa}", f"critical {en} level", "labs"))
    for fa, en in SEVERITY:
        out.append((f"{fa} خفیف", f"mild {en}", "conditions"))
        out.append((f"{fa} متوسط", f"moderate {en}", "conditions"))
        out.append((f"{fa} شدید", f"severe {en}", "conditions"))
    for fa, en in ACUTE_CHRONIC:
        out.append((f"{fa} حاد", f"acute {en}", "conditions"))
        out.append((f"{fa} مزمن", f"chronic {en}", "conditions"))
    for fa, en in SUPPLEMENTAL_CONDITIONS:
        out.append((fa, en, "conditions"))
    for fa, en in SUPPLEMENTAL_ONCOLOGY:
        out.append((fa, en, "oncology"))
    for fa, en in SUPPLEMENTAL_SYMPTOMS:
        out.append((fa, en, "symptoms"))
    for fa, en in PAIN:
        out.append((fa, en, "symptoms"))
    for fa, en in FRACTURE:
        out.append((fa, en, "conditions"))
    for fa, en in HISTORY:
        out.append((f"سابقه {fa}", f"history of {en}", "history"))
    for fa, en in SUSPECTED:
        out.append((f"مشکوک به {fa}", f"suspected {en}", "conditions"))
    for fa, en in ALLERGY:
        out.append((f"آلرژی به {fa}", f"{en} allergy", "conditions"))
    for fa, en in INTOLERANCE:
        out.append((f"عدم تحمل {fa}", f"{en} intolerance", "conditions"))
    for week in range(1, 43):
        en = "1 week gestation" if week == 1 else f"{week} weeks gestation"
        out.append((f"هفته {fa_num(week)} بارداری", en, "obstetric"))
    for month in range(1, 10):
        out.append(
            (f"ماه {fa_num(month)} بارداری", f"month {month} of pregnancy", "obstetric")
        )
    out.append(("سه‌ماهه اول بارداری", "first trimester of pregnancy", "obstetric"))
    out.append(("سه‌ماهه دوم بارداری", "second trimester of pregnancy", "obstetric"))
    out.append(("سه‌ماهه سوم بارداری", "third trimester of pregnancy", "obstetric"))
    for fa, en in VITALS_ABNORMAL:
        out.append((fa, en, "vitals"))
    for fa, en in BILATERAL:
        out.append((f"{fa} راست", f"right {en}", "anatomy"))
        out.append((f"{fa} چپ", f"left {en}", "anatomy"))
    for fa, en in ANATOMY_SINGLES:
        out.append((fa, en, "anatomy"))
    for fa, en in ULTRASOUND:
        out.append((f"سونوگرافی {fa}", f"{en} ultrasound", "procedures"))
    for fa, en in DOPPLER_EXTRA:
        out.append((fa, en, "procedures"))
    for fa, en in CT_REGIONS:
        out.append((f"سی‌تی {fa}", f"{en} CT", "procedures"))
    for fa, en in CT_ANGIO:
        out.append((fa, en, "procedures"))
    for fa, en in MRI_REGIONS:
        out.append((f"ام‌آر‌آی {fa}", f"{en} MRI", "procedures"))
    for fa, en in MRA_EXTRA:
        out.append((fa, en, "procedures"))
    for fa, en in XRAY_REGIONS:
        out.append((f"رادیوگرافی {fa}", f"{en} X-ray", "procedures"))
    for fa, en in XRAY_EXTRA:
        out.append((fa, en, "procedures"))
    for fa, en in EXAM_SIGNS:
        out.append((fa, en, "symptoms"))
    for fa, en in OBSTETRIC:
        out.append((fa, en, "obstetric"))
    for fa, en in DRUG_CLASSES:
        out.append((fa, en, "medications"))
    for fa, en in DOSAGE_FORMS:
        out.append((fa, en, "medications"))
    for fa, en in DOSING_SCHEDULE:
        out.append((fa, en, "plan"))
    return out


def check_candidate(fa: str, en: str, cat: str) -> str | None:
    """Mirror the validator gates; return an error message or None."""
    if not fa or not en or not cat:
        return "empty field"
    if fa != fa.strip() or en != en.strip():
        return "leading/trailing whitespace"
    if "  " in fa or "  " in en:
        return "double space"
    if not _PERSIAN_CHAR.search(fa):
        return "fa has no Persian characters"
    if not _FA_ALLOWED.match(fa):
        return "fa has unexpected characters"
    if _LATIN.search(fa):
        return "fa contains Latin (generator forbids all Latin in fa)"
    if _PERSIAN_CHAR.search(en):
        return "en contains Persian characters"
    if not _LATIN.search(en):
        return "en has no Latin characters"
    if _BAD_EN_PREFIX.match(en):
        return "en starts with filler"
    if len(fa) > 80 or len(en) > 120:
        return "entry too long"
    if cat not in REQUIRED_CATEGORIES:
        return f"unknown category {cat!r}"
    return None


def main() -> None:
    used_fa: set[str] = set()
    used_en: set[str] = set()
    used_pairs: set[tuple[str, str]] = set()
    for path in sorted(TERMS_DIR.glob("*.json")):
        if path.name == OUT_FILE.name:
            continue
        for entry in json.loads(path.read_text(encoding="utf-8")):
            fa = entry["fa"].strip()
            en = entry["en"].strip()
            used_fa.add(fa)
            used_en.add(en.casefold())
            used_pairs.add((fa.casefold(), en.casefold()))
    print(f"existing terms (excluding generated): {len(used_pairs)}")

    candidates = build_candidates()
    print(f"raw candidates: {len(candidates)}")

    accepted: list[dict[str, str]] = []
    skipped_shape = 0
    skipped_dup = 0
    for fa, en, cat in candidates:
        err = check_candidate(fa, en, cat)
        if err is not None:
            skipped_shape += 1
            print(f"  SHAPE-SKIP {fa!r} -> {en!r}: {err}")
            continue
        key = (fa.casefold(), en.casefold())
        if key in used_pairs or fa in used_fa or en.casefold() in used_en:
            skipped_dup += 1
            continue
        used_pairs.add(key)
        used_fa.add(fa)
        used_en.add(en.casefold())
        # W2.4 provenance: machine-generated entries are marked as such.
        accepted.append({"fa": fa, "en": en, "cat": cat, "src": "generated"})

    OUT_FILE.write_text(
        "[" + ",\n".join(json.dumps(t, ensure_ascii=False) for t in accepted) + "]",
        encoding="utf-8",
    )
    print(
        f"accepted: {len(accepted)} | shape-skipped: {skipped_shape} | dup-skipped: {skipped_dup}"
    )
    print(f"wrote {OUT_FILE.relative_to(ROOT)}")

    entries = validate_all()
    print(f"VALIDATOR PASS. merged total: {len(entries)}")
    if len(entries) < 5000:
        raise SystemExit(f"below 5000-term target: {len(entries)}")


if __name__ == "__main__":
    main()
