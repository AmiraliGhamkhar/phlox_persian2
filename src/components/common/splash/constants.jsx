import {
  FaUserMd,
  FaRobot,
  FaFileAlt,
  FaInfoCircle,
  FaLock,
} from "react-icons/fa";

export const SPLASH_STEPS = {
  ENCRYPTION: -1,
  ABOUT_YOU: 0,
  TEMPLATES: 1,
  AI_MODELS: 2,
  // Retained for hook compatibility — not shown in splash
  QUICK_CHAT: 4,
  LETTERS: 5,
};

export const STEP_TITLES = {
  [SPLASH_STEPS.ENCRYPTION]: "از داده‌های خود محافظت کنید",
  [SPLASH_STEPS.ABOUT_YOU]: "درباره شما",
  [SPLASH_STEPS.AI_MODELS]: "مدل‌های هوش مصنوعی",
  [SPLASH_STEPS.TEMPLATES]: "قالب خود را انتخاب کنید",
};

export const STEP_DESCRIPTIONS = {
  [SPLASH_STEPS.ENCRYPTION]:
    "یک عبارت عبور برای رمزگذاری و محافظت از داده‌های بیماران ایجاد کنید.",
  [SPLASH_STEPS.ABOUT_YOU]:
    "نام و تخصص شما یادداشت‌ها و نامه‌ها را شخصی‌سازی می‌کند.",
  [SPLASH_STEPS.TEMPLATES]:
    "قالب یادداشتی را که برای ویزیت بیماران استفاده می‌کنید انتخاب کنید.",
  [SPLASH_STEPS.AI_MODELS]:
    "برای اجرای مدل روی رایانه خود آن را دانلود کنید یا به یک API متصل شوید.",
};

export const TEMPLATE_DESCRIPTIONS = {
  phlox_01:
    "ویزیت پزشک — بیماری اصلی، شرح‌حال، برداشت بالینی و برنامه درمانی.",
  soap_01: "قالب استاندارد SOAP — ذهنی، عینی، ارزیابی و برنامه.",
  progress_01: "ویزیت‌های پیگیری — شرح‌حال فاصله‌ای، وضعیت فعلی و برنامه.",
  procedure_01:
    "مستندسازی اقدامات — اندیکاسیون، جزئیات و عوارض.",
  consult_01:
    "ویزیت تخصصی — علت مراجعه، یافته‌ها، برداشت بالینی و توصیه‌ها.",
};

export const getStepIcon = (step) => {
  switch (step) {
    case SPLASH_STEPS.ENCRYPTION:
      return FaLock;
    case SPLASH_STEPS.ABOUT_YOU:
      return FaUserMd;
    case SPLASH_STEPS.AI_MODELS:
      return FaRobot;
    case SPLASH_STEPS.TEMPLATES:
      return FaFileAlt;
    default:
      return FaInfoCircle;
  }
};
