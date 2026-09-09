> [!WARNING]
> فلوکس یک پروژه آزمایشی است. پیش از استفاده، بخش **[هشدار استفاده](#هشدار-استفاده)** را با دقت بخوانید.

<p align="center">
  <img src="/assets/phlox_icon.png" width="150" alt="نشان فلوکس">
</p>

<div align="center" dir="rtl">

[![وضعیت CI](https://github.com/AmiraliGhamkhar/phlox_persian/actions/workflows/ci.yml/badge.svg)](https://github.com/AmiraliGhamkhar/phlox_persian/actions/workflows/ci.yml)
[![وضعیت پوشش آزمون](https://coveralls.io/repos/github/AmiraliGhamkhar/phlox_persian/badge.svg?branch=main)](https://coveralls.io/github/AmiraliGhamkhar/phlox_persian?branch=main)
[![CodeQL](https://github.com/AmiraliGhamkhar/phlox_persian/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/AmiraliGhamkhar/phlox_persian/actions/workflows/github-code-scanning/codeql)
[![سبک کد: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![مجوز: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![مستندات](https://img.shields.io/badge/docs-phlox.bloodworks.io-blue)](https://phlox.bloodworks.io/docs)

</div>

# فلوکس؛ دستیار پیاده‌سازی و گزارش بالینی فارسی

فلوکس یک دستیار رایگان و متن‌باز برای پزشکان است: گفتار ویزیت را به متن تبدیل می‌کند و از روی آن، گزارش بالینی ساختاریافته فارسی می‌سازد. برنامه فقط سه صفحه دارد ــ **انتخاب تخصص، پیاده‌سازی و گزارش، تنظیمات** ــ و با رویکرد «محلی در اولویت» روی سخت‌افزار خودتان اجرا می‌شود. رابط کاربری، متن‌های راهنما و چیدمان برنامه برای فارسی و راست‌به‌چپ آماده شده‌اند.

## قابلیت‌های اصلی

- **🔒 خصوصی و محلی:** در حالت محلی، صدا و متن روی دستگاه شما می‌مانند و برای پردازش به سرویس شخص ثالث ارسال نمی‌شوند.
- **🎤 پیاده‌سازی زنده و دیکته:** صدای ویزیت را به‌صورت زنده (محیطی) یا با دیکته مستقیم به متن فارسی/انگلیسی تبدیل کنید.
- **📝 گزارش بالینی ساختاریافته:** از متن پیاده‌سازی‌شده، یادداشت دارای بخش‌های شکایت اصلی، شرح‌حال، معاینه، ارزیابی و برنامه بسازید و با یک کلیک کپی کنید.
- **🩺 تخصص‌محور:** تخصص خود را انتخاب کنید تا لحن و تمرکز گزارش با آن هماهنگ شود.
- **📖 واژه‌نامه پزشکی فارسی–انگلیسی:** بیش از ۵٬۰۰۰ اصطلاح پزشکی برای دقت بیشتر پیاده‌سازی و گزارش، با جست‌وجوی داخلی.
- **💻 مدل محلی با یک کلیک:** مدل زبانی و مدل تشخیص گفتار را از داخل برنامه دانلود کنید؛ فعال‌سازی خودکار انجام می‌شود. در دسکتاپ و Docker.
- **🌐 ارائه‌دهندگان برخط آماده:** نشانی سرویس‌های OpenAI، Anthropic، Fireworks، Groq، OpenRouter، Ollama و LM Studio از پیش وارد شده؛ فقط کلید API را بچسبانید.

<p align="center">
  <img src="/assets/readme_screenshot.png" width="600" alt="تصویر محیط فلوکس">
</p>

## شروع کار

### برنامه دسکتاپ

نسخه‌های آماده برای Apple Silicon در macOS و Flatpak برای Linux با پشتیبانی Vulkan از [صفحه انتشارهای GitHub](https://github.com/AmiraliGhamkhar/phlox_persian/releases) در دسترس هستند.

برنامه دسکتاپ موتورهای `llama.cpp` و `whisper.cpp` را همراه دارد. مدل‌ها را از داخل برنامه (**تنظیمات ← مدل ← Local**) دانلود کنید؛ پس از دانلود، فعال‌سازی و راه‌اندازی موتور خودکار انجام می‌شود. برای ASR محلی، سه نسخه از Whisper large-v3-turbo در دسترس است:

1. نسخه دقیق `F16`
2. نسخه کم‌حجم `Q5_0` (پیشنهاد پیش‌فرض)
3. نسخه `Q8_0` با دقت بالاتر و مصرف حافظه متوسط

همچنین مدل فارسی `Shenava-Koochik-v1.0` با نسخه کم‌حجم `INT4` و مدل چندزبانه کوچک Parakeet ارائه می‌شود. مدل‌های Whisper برای فارسی و گفتار فارسی/انگلیسی ترکیبی مناسب‌اند، Shenava برای پیاده‌سازی محلی فارسی بهینه شده و Parakeet فارسی را پوشش نمی‌دهد.

### ASR محلی و برخط

در بخش **تنظیمات ← مدل ← تشخیص گفتار** یکی از گزینه‌های زیر را انتخاب کنید:

- **مدل محلی:** Whisper.cpp برای فارسی و گفتار ترکیبی، Shenava برای فارسی، یا Parakeet چندزبانه.
- **سرویس سازگار با OpenAI:** نشانی پایه، شناسه مدل و در صورت نیاز کلید API را وارد کنید.
- **OpenAI Audio:** مدل‌های `gpt-4o-transcribe`، `gpt-4o-mini-transcribe` و `whisper-1`.
- **Speechmatics:** کلید API را در تنظیمات رمزگذاری‌شده برنامه وارد کنید؛ زبان `auto` در فایل‌ها تشخیص خودکار و در حالت زنده به فارسی نگاشت می‌شود. در صورت نیاز، کلید جداگانه Batch برای فایل‌ها قابل تنظیم است.
- **AssemblyAI:** با یک کلید هم فایل‌های ضبط‌شده (پیش‌ثبت `universal-3-5-pro`) و هم جریان بلادرنگ پشتیبانی می‌شود. کلید بدون پیشوند Bearer ارسال می‌شود. برای فارسی از `universal-2` (پشتیبانی از ۹۹ زبان) استفاده کنید؛ `universal-3-5-pro` در زبان‌های خارج از ۱۸ زبان بومی به‌طور خودکار به `universal-2` برمی‌گردد.
- **Fireworks AI ASR:** مدل‌های `fireworks-asr-v2` و `fireworks-asr-large` برای حالت زنده و مدل‌های Whisper v3 برای دسته‌ای.

زبان‌های `فارسی`، `انگلیسی` و `تشخیص خودکار؛ فارسی و انگلیسی ترکیبی` پشتیبانی می‌شوند. کلیدهای API هرگز در کد یا مخزن ذخیره نمی‌شوند و پاسخ تنظیمات، کلید ذخیره‌شده را به‌صورت پوشانده نمایش می‌دهد.

### مدل زبانی (LLM)

در بخش **تنظیمات ← مدل ← مدل زبانی** ارائه‌دهنده را انتخاب کنید؛ نشانی پایه به‌طور خودکار پر می‌شود و برای سرویس‌های ابری فقط کلید API لازم است. پشتیبانی می‌شوند: مدل محلی (llama.cpp)، Ollama، LM Studio، llama.cpp server، OpenAI، Anthropic، Fireworks، Groq، OpenRouter و هر سرویس سازگار با OpenAI.

### Docker و Podman

تصاویر آماده از [GitHub Container Registry](https://github.com/AmiraliGhamkhar/phlox_persian/pkgs/container/phlox_persian) در دسترس هستند:

```bash
docker pull ghcr.io/amiralighamkhar/phlox_persian:latest
```

توصیه می‌شود از `docker-compose.yml` این مخزن استفاده کنید؛ یک ظرف هم API و هم رابط کاربری ساخته‌شده را روی پورت `5000` ارائه می‌کند:

```bash
cp .env.example .env          # سپس DB_ENCRYPTION_KEY را در .env وارد کنید
docker compose up -d --build  # ساخت تصویر از همین مخزن
docker compose ps             # وضعیت باید healthy شود
docker compose logs -f
```

نکات مهم:

- `DB_ENCRYPTION_KEY` الزامی است و بعد از ساخت پایگاه داده نباید عوض شود (بدون کلید درست، داده رمزگشایی نمی‌شود). برای ساخت کلید: `openssl rand -hex 32`.
- پایگاه داده رمزگذاری‌شده، مدل‌های محلی دانلودشده و گزارش‌ها همه داخل `/usr/src/app/data` قرار می‌گیرند، بنابراین یک volume برای همین مسیر کافی است.
- `docker-compose.yml` به‌طور پیش‌فرض از named volume (`phlox_data`) استفاده می‌کند، چون مالکیت و اجازه‌های آن از تصویر کپی می‌شود و کاربر بدون امتیاز ظرف (uid/gid 1000) می‌تواند بنویسد. اگر bind mount را ترجیح می‌دهید: `sudo mkdir -p data && sudo chown -R 1000:1000 data`.
- پورت فقط روی `127.0.0.1` منتشر می‌شود. برای دسترسی از بیرون، reverse proxy دارای احراز هویت بگذارید، `ALLOWED_ORIGINS` و در صورت نیاز `ALLOWED_HOSTS` را روی نشانی واقعی تنظیم کنید و `PROXY_AUTH_ENABLED=true` را فعال کنید. در این حالت `HEALTHCHECK` پاسخ‌های `401/403` را نیز سالم می‌شمارد.
- تنظیمات امنیتی شبکه: `ALLOWED_ORIGINS` به‌طور پیش‌فرض خالی است (فقط same-origin)، `ALLOWED_HOSTS` فهرست Hostهای مجاز برای مقابله با DNS rebinding است و `TRUSTED_PROXY_CIDRS` تعیین می‌کند کدام پروکسی‌ها مجاز به ارسال `X-Forwarded-For` هستند (پیش‌فرض: بازه‌های شبکه Docker و loopback).
- با Podman نیز همین فایل‌ها کار می‌کنند (`podman compose`). به‌جای متغیر محیطی می‌توانید کلید را به‌صورت secret در `/run/secrets/db_encryption_key` قرار دهید؛ سرور آن را به‌طور خودکار می‌خواند.
- برای توسعه با hot reload: `docker compose -f docker-compose.dev.yml up` (رابط کاربری روی پورت `3000`، API روی پورت `5000`).

تصویر Docker موتورهای `llama-server` و `whisper-server` (نسخه CPU) را همراه دارد و سرور API خود آن‌ها را مدیریت می‌کند؛ بنابراین دانلود و فعال‌سازی مدل محلی با یک کلیک، دقیقاً مثل نسخه دسکتاپ کار می‌کند. مدل‌های Shenava و Parakeet با آداپتور ONNX داخل خود سرور اجرا می‌شوند و به موتور جداگانه نیاز ندارند.

### توسعه

برای نصب وابستگی‌های رابط کاربری و اجرای آن:

```bash
npm ci
npm run dev
```

برای اجرای آزمون‌ها و بررسی کیفیت:

```bash
npm run typecheck
npm run lint
npm test -- --run
cd server && uv run ruff check . && uv run ruff format --check .
cd server && DB_ENCRYPTION_KEY='یک-کلید-آزمایشی-محلی' uv run pytest -q
```

برای ساخت نسخه دسکتاپ، پیش‌نیازهای Tauri، Rust، CMake و ابزارهای توسعه سیستم‌عامل را نصب کنید و سپس `npm run tauri-build` را اجرا کنید.

## معماری

فلوکس صدای ضبط‌شده را از مسیر ASR (محلی یا ابری) به متن تبدیل می‌کند و سپس مدل زبانی با یک پرامپت سیستمی پزشکی و واژه‌نامه فارسی–انگلیسی، گزارش ساختاریافته می‌سازد.

رابط کاربری هرگز مستقیم با ارائه‌دهنده هوش مصنوعی صحبت نمی‌کند. مسیر درخواست:

```text
Frontend (React / Tauri)
  → FastAPI (/api/*) + auth / validation
  → domain services (transcription, workspace, report)
  → get_llm_client / resolve_asr_connection
  → provider adapter (OpenAI-compatible, Anthropic Messages, STT)
  → SQLCipher (encrypted config + user settings)
```

```mermaid
flowchart TD
  User --> UI[React / Tauri]
  UI --> API[FastAPI /api]
  API --> Auth[Token or proxy auth]
  Auth --> Svc[Application services]
  Svc --> Orch[Provider resolvers]
  Orch --> LLM[LLM adapter]
  Orch --> STT[ASR adapter]
  LLM --> LocalLLM[llama.cpp / Ollama / LM Studio]
  LLM --> CloudLLM[OpenAI / Anthropic / Fireworks / Groq / OpenRouter]
  STT --> LocalSTT[Whisper.cpp / Shenava / Parakeet]
  STT --> CloudSTT[OpenAI Audio / Speechmatics / AssemblyAI / Fireworks]
  Svc --> DB[SQLCipher]
```

ارائه‌دهندگان از تنظیمات رمزگذاری‌شده عوض می‌شوند، نه با بازنویسی منطق کسب‌وکار. خطاهای گذرا (۴۲۹، ۵xx، شبکه، وقفه) حداکثر دو بار با backoff تکرار می‌شوند؛ خطاهای ۴xx دیگر تکرار نمی‌شوند و failover خودکار به ابر وجود ندارد.

### پشته فنی

- **رابط کاربری:** React و [Chakra UI](https://github.com/chakra-ui/chakra-ui)
- **سرور:** [FastAPI](https://github.com/fastapi/fastapi) و Python
- **پایگاه داده:** [SQLCipher](https://github.com/sqlcipher/sqlcipher)
- **پوسته دسکتاپ:** [Tauri](https://github.com/tauri-apps/tauri)
- **مدل زبانی:** سرور [llama.cpp](https://github.com/ggml-org/llama.cpp)، Ollama، LM Studio، 9Router/OmniRoute، OpenAI-compatible، OpenAI، Anthropic Messages، Fireworks، Groq، OpenRouter
- **ASR:** Whisper.cpp محلی، Shenava، Parakeet (غیر فارسی)، سرور Whisper.cpp، OpenAI Audio، Speechmatics، AssemblyAI، Fireworks live/batch

## لایه‌های امنیتی و حریم خصوصی

- **محلی در اولویت:** پردازش روی دستگاه شما انجام می‌شود و پایگاه داده با [SQLCipher](https://github.com/sqlcipher/sqlcipher) رمزنگاری می‌شود؛ کلیدهای API هرگز در کد یا مخزن ذخیره نمی‌شوند و در پاسخ تنظیمات پوشانده نمایش داده می‌شوند.
- **سخت‌سازی درخواست‌ها:** CORS به‌طور پیش‌فرض فقط same-origin است، فهرست Host مجاز در برابر DNS rebinding می‌ایستد، هدر `X-Forwarded-For` فقط برای CIDRهای پروکسی معتمد پذیرفته می‌شود، نرخ درخواست‌ها با الگوریتم توکن-سطل محدود می‌شود، حجم بارگذاری صدا سقف دارد و نشانی‌های اینترنتی ورودی کاربر با محافظ SSRF بررسی می‌شوند.
- **بررسی پیوسته:** در CI، تحلیل استاتیک CodeQL برای JS/TS و Python به همراه `npm audit`، `pip-audit` و `cargo audit` اجرا می‌شود و `ruff` مرز سبک کد را نگه می‌دارد.

## هشدار استفاده

فلوکس یک پروژه آزمایشی برای استفاده آموزشی و شخصی است. **این برنامه وسیله پزشکی تأییدشده نیست، نباید برای تصمیم‌گیری بالینی استفاده شود و در وضعیت فعلی برای استقرار تولیدی مناسب نیست.** اگر قصد استفاده بالینی دارید، مسئولیت رعایت قوانین و الزامات محلی مانند HIPAA، GDPR و سایر مقررات بر عهده شماست.

خروجی هوش مصنوعی ممکن است نادرست باشد. همیشه محتوای تولیدشده را بررسی کنید و برای همه تصمیم‌های بالینی به قضاوت حرفه‌ای و راهنماهای معتبر تکیه کنید. برنامه هنگام شروع، هشدار کامل را نمایش می‌دهد.

## مجوز

[مجوز MIT](LICENSE)

برای اطلاعات مدل‌ها و وابستگی‌های شخص ثالث، [صفحه اعتبارها](https://phlox.bloodworks.io/docs/credits) را ببینید.

## مشارکت

[راهنمای مشارکت](.github/CONTRIBUTING.md)

این مخزن با کمک ابزارهای توسعه هوش مصنوعی ساخته شده است. همه مشارکت‌کنندگان باید پیش از ارسال تغییرات، کد تولیدشده و اثر آن بر حریم خصوصی و ایمنی داده‌های بالینی را بررسی کنند.
