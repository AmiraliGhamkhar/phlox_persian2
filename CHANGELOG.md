# تغییرات نسخه‌های فلوکس

این فایل خلاصه تغییرات مهم هر نسخه را به فارسی ثبت می‌کند. شناسه‌های commit و لینک‌ها برای پیگیری فنی دست‌نخورده باقی مانده‌اند.

## نسخه توسعه فعلی

### ساده‌سازی محصول (تغییر عمدی معماری)

- محصول به جریان سه‌صفحه‌ای ساده شد: انتخاب تخصص، فضای پیاده‌سازی/گزارش و تنظیمات. ماژول‌های چت، RAG و پایگاه برداری، ابزارهای MCP، پرونده/جست‌وجوی بیمار، کارها و قالب‌های بالینی و صف تأیید اقدامات از برنامه حذف شدند؛ جداول مرتبط تنها برای سازگاری مهاجرت‌ها در طرح باقی مانده‌اند.
- با حذف جست‌وجوهای بیرونی (PubMed/ویکی‌پدیا) و ابزارهای بیرونی، مسیر پاک‌سازی PHI برای خروجی و درگاه تأیید انسانی نیز از برنامه خارج شد؛ لایه‌های امنیتی باقی‌مانده (رمزگذاری پایگاه داده، توکن درخواست محلی، سخت‌سازی شبکه) همچنان فعال‌اند.

### قابلیت‌ها و سخت‌سازی‌های باقی‌مانده در نسخه فعلی

- سخت‌سازی شبکه اعمال شد: پیش‌فرض CORS فقط same-origin، فهرست Hostهای مجاز (مقابله با DNS rebinding)، اعتماد گزینشی به `X-Forwarded-For` فقط برای CIDRهای پروکسی معتمد و محدودسازی نرخ توکن-سطل.
- سقف حجم بدنه درخواست‌های API اعمال شد.
- اگر تولید گزارش با مدل زبانی ناکام بماند، خطای قابل‌فهم نمایش داده می‌شود؛ بررسی احراز هویت WebSocket تشخیص زنده اجرا می‌شود و آدرس پایه خالی دیگر با رشته «null» به سمت فهرست مدل‌ها فرستاده نمی‌شود.
- کنتراست رنگ‌های دکمه‌ها و متن‌ها مطابق WCAG 2.1 AA اصلاح شد و فونت وزیرمتن به‌صورت خودمیزبان با preload مستقیم سرو می‌شود (حذف Roboto).
- جریان کاری CodeQL برای تحلیل امنیتی JS/TS و Python به CI اضافه شد.
- رابط کاربری و متن‌های راهنما برای فارسی و راست‌به‌چپ بازبینی شدند.
- واژه‌های ASR و تشخیص گفتار جایگزین نام‌گذاری قدیمی STT شدند.
- سه مدل محلی Whisper large-v3-turbo شامل F16، Q5_0 و Q8_0 اضافه شدند.
- مدل فارسی `Shenava-Koochik-v1.0-tract-streaming` با گراف INT4 و واژگان همراه اضافه شد.
- امکان انتخاب مستقل حالت محلی/برخط، ارائه‌دهنده، مدل و زبان ASR فراهم شد.
- Speechmatics Realtime با مدیریت امن کلید API و پشتیبانی از فارسی و گفتار ترکیبی اضافه شد.
- کلیدهای API در پاسخ تنظیمات پوشانده می‌شوند و مقدار پوشانده‌شده جایگزین کلید واقعی نمی‌شود.
- مدل‌های ASR محلی از داخل برنامه دانلود، فعال و حذف می‌شوند؛ انتخاب Shenava هرگز C++ sidecar را راه‌اندازی نمی‌کند.
- پردازش صدای مرورگر روی WAV تک‌کاناله ۱۶ کیلوهرتز و مسیر فارسی/انگلیسی ترکیبی استاندارد شد.
- گزارش درخواست‌های API در جدول رمزگذاری‌شده `audit_log` با ماندگاری قابل‌تنظیم (AUDIT_RETENTION_DAYS) فعال شد.

## [2.3.0](https://github.com/AmiraliGhamkhar/phlox_persian2/compare/v2.2.4...v2.3.0) (2026-09-10)


### Features

* ability to replace stored forms ([e83c252](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/e83c252fb15080355105b8f2823f8e9178e680db))
* **api:** add granular options reset endpoint ([c85e2d3](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/c85e2d34382bb57749702ba35b18ea524a85b1f6))
* **api:** search patients by name as well as UR number ([c3b1d0e](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/c3b1d0ef0a47cb0db98c65452eab0e59809f9cb5))
* **asr:** W2.1 deterministic Persian ITN for spoken-form numbers ([df81c68](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/df81c683b9f09f4f9a59da843b96c8e79d5d04a4))
* **asr:** W2.2 Silero VAD strategy for silence trimming ([6158d3d](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/6158d3d085579ae3847624182ebd355333355837))
* **asr:** W2.3 SNR-gated server-side denoise for files (PHLOX_DENOISE) ([f9ba639](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/f9ba639e2f6bcdb6d9224a9b4f7a5fb405f03d15))
* **asr:** W2.5 biasing — spoken-form prefix, term variants ([359d237](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/359d237451663828969218076d40a703c8486a51))
* **audio:** replace MediaRecorder with WebAudio AudioContext ([a4498ee](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/a4498ee3097e817b12fb6ae9bf38eba04b7f6ef4))
* **audit:** add audit log repository and middleware ([e2f7b01](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/e2f7b01a241c455fbd1785656188b0c5a7fae9cf))
* **audit:** add read/export endpoints and tests ([6722145](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/67221451bde30407246f8b75a0c1ad8812a93dea))
* **build:** add Linux build paths with pinned SHAs and CPU fallback ([da43bb3](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/da43bb38169b3b900407922a735031cf27e7c9c0))
* **chat:** global citation numbering across multi-tool turns ([bec4426](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/bec44263041b328fe5a53ec97044ba5cca587f24))
* **chat:** hide literature tool when the knowledge base is empty ([66020e2](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/66020e21810b99ef2e8c77dde6b308b45e9d4d8f))
* **chat:** include demographics in patient context ([521f208](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/521f208c56cb64c6b2e9e58af89e3dcfbe33923f))
* **chat:** structured citations for wiki tool ([a41a2c7](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/a41a2c794c8499bc88f60847c8cd650d8d90d611))
* **chat:** structured citations from search tools ([a803dbc](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/a803dbcb8e55db791b1209250f5ba37f024fea5e))
* **consent:** persist ambient-scribe consent in patient_profiles ([d9757ae](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/d9757ae12d52a1e45f6c4c8506bc411b76910ce4))
* **consent:** prompt for consent before ambient recording ([e6aa049](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/e6aa0493143c0049f3216f32ba7946061e95fd96))
* **db:** add audit_log table and retention config (v7 migration) ([d776f8e](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/d776f8ef0d3fa2ba7a2aaadd9deba43e4b808a51))
* **db:** enable WAL mode and back up -wal/-shm sidecars ([4d25f0e](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/4d25f0e828dc58d67635655a9e8286a193662bf9))
* **db:** store patient demographics in patient_profiles ([1f31a90](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/1f31a90e722f15cc50fbdb5770ed8309a086457d))
* **demo:** seed fullsome demo data on tauri dev launch ([b3625c2](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/b3625c2965e15fba589dbfbf6ce428e05a3b6f98))
* **dev:** force onboarding splash on every dev launch ([2d97e70](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/2d97e70a7cb63c47ce572f32c5f78b210c4a835a))
* **dict:** W2.4 term provenance, whole-word context matching ([9fae500](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/9fae50086240c5d5fc9b94f91ec73c97e8c7c933))
* **embedding:** add embedding model API stubs and download service ([9d77dea](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/9d77dea20a94b0015fcb234d8217c263348831cb))
* **embedding:** add embedding model download and endpoints ([2964db8](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/2964db89bfe03c8f7668bab65c98dd64cca6a4fd))
* **embedding:** expose embedding lifecycle as Tauri commands ([7a40e8c](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/7a40e8cdafb3b099f01ac2de37905ce6f740bcb4))
* **embedding:** manage embedding server in process manager ([3a5d45d](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/3a5d45df14afca4bb738929063de60a0494f5fc4))
* **embedding:** wire UI to Qwen3 embedding endpoints ([3cb8d9b](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/3cb8d9b81f1b90bec53419c7786f56aa6c20eae8))
* extract patient demographics from documents ([9596436](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/9596436a903803be3c0abac8a2b48738cc97435f))
* **helpers:** add toastApiError and toastApiSuccess helpers ([d554acc](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/d554acccae007f654af126fdf46c2be4ad6e733e))
* introduce SWR cache layer with 6 initial migrations ([fe27acd](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/fe27acd71e72630efe5eeb72f85c887c81296fad))
* **linux:** add Flatpak packaging ([e7c439a](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/e7c439accda1b1c7b2a2340bd443f01e4584fb45))
* **linux:** auto-grant WebKit getUserMedia permission ([3fd370d](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/3fd370d2f7e86697bc7861c7a92328617c6d3bb9))
* localize Phlox to Persian and add Persian ASR providers ([28480ca](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/28480ca6c032493e8cbc589cc1215e6653ce49eb))
* **note:** auto-open demographics and gate recording on required fields ([a81fcdd](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/a81fcdda3d0d652a55e85dd4e8e712ed58ceff1b))
* **notes:** add candidate results and confirm flow to modal ([91d57b3](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/91d57b3123f6edd55183a6c3fe7138a8b6fb7960))
* **perf:** add calibrated LLM estimate to model popovers ([7c70e11](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/7c70e116511c7ea3a6a0d7e7a125ab8df86f7067))
* **rag:** editable document metadata ([949f3ba](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/949f3ba7132e7a01230a93d8613012dc27850ee9))
* **rag:** gate RAG on embedding model availability for Tauri ([95ec1da](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/95ec1da1c050e46648df592266175f1dda360b16))
* **rag:** improve ingestion pipeline; allow collection rename ([dc43939](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/dc439396b8672db820ebcbc63f8d60a97211b3bd))
* **reasoning:** citation rule in system prompt ([89164b1](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/89164b14782ea0f1a90506b72e327dfb286decd1))
* **scribe:** gate recording, recover failed, refactor scribe ([ed8ba66](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/ed8ba66481ba1b7f7684049d9273acc688140f1a))
* **security:** add origin validation to get_request_token command ([a70b4bc](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/a70b4bc447a5c776d60393b3fc20cb6766e03c71))
* **security:** add parent-PID watchdog so server self-terminates if Tauri dies ([07b7e4a](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/07b7e4a6be50208ef1fe9e5127e31aa5371e36e9))
* **security:** enable rate limiting for Tauri builds ([ca4b594](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/ca4b5944d3016b3ffa8a8010ea7bbb65c0a3f47b))
* **security:** enforce strict CSP and disable global Tauri API ([2569971](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/256997155b616f7647319b9da8f07b993343114f))
* **security:** mask API keys in config endpoint responses ([d334279](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/d3342799658596c83e1099404ccd3de2f381255a))
* **server:** use parakeet OpenAI endpoint and single Omi Med STT model ([cea0513](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/cea0513fd7e6367507154b7cf291ac14d971b4b1))
* **server:** write API requests to the encrypted audit_log table (F-02) ([b68c280](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/b68c280b0bb64238b78728ff0282d2867693ca2e))
* **sidebar:** active states, accent discipline, and restructured nav ([33b82ee](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/33b82ee7d0fc7bcf69752ba61f5dd0c8819f4c48))
* **sidebar:** add tooltips to sidebar controls ([d4ba96d](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/d4ba96d483e1f6078773092b8ad8709b0c021c38))
* **sidebar:** hide day summary when no patients for the date ([3c92e16](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/3c92e16f767bcd33c285cd520d906d5e4743849a))
* **sidebar:** mark New Note active on the new-note route ([abe747b](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/abe747b12f8048919d0832755f30351e367298e4))
* **sidebar:** use flat full-height sidebar in web/docker mode ([fb3e6ba](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/fb3e6ba5de464547e577fdb56766a03210f1d1ca))
* **tauri:** launch parakeet STT server and drop legacy process monitor ([6d73231](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/6d73231a29156f16faf0ae64fbbacab021d724ba))
* **tauri:** Linux dGPU VRAM detection and pooled RAM/VRAM model filter ([bb13d39](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/bb13d39300fec536381055836d08ac1edf463b05))
* **tool:** search by primary condition and fuzzy name. ([86bfef1](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/86bfef1bdce6fa06b086602798ca60c2994d3469))
* **ui:** add patient demographics modal ([859e555](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/859e555a2849124d1e63ed51ee41d38b774ffd4c))
* **ui:** auto-fill demographics from a dropped document ([44276a9](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/44276a97ad5d24d614d416cd43ce023a4d4e684b))
* **ui:** compact summary-only table view ([3cae57f](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/3cae57f02f373d75cb2e2a1917f834618555c85a))
* **ui:** gate onboarding splash on Omi Med STT model download ([bff7a73](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/bff7a73790fc6cf06715f3de85581fda0b0b402d))
* **ui:** inline citation pills with popovers + sources footer ([6ed8254](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/6ed8254406276c42463e6e119e7b52b37f15460e))
* **ui:** migrate to Chakra UI v3 foundation (React 19) ([470a8e4](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/470a8e41c0d20f188ae229c336f5d2154a836849))
* **ui:** new note splash for clarity ([500f95a](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/500f95aeccef137a7a5bbeb0a0f51ea6646bfe46))
* **ui:** polish elements ([b53678d](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/b53678d8c77fb4d30a64d7a6892ac0b5ae6a0d7e))
* **ui:** replace framer-motion with theme keyframes ([81029b0](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/81029b0702e931ec028c4f8c25dcf3a09ea62b85))
* **vision:** assume vision capable for local models ([77398d4](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/77398d4d087a0a9690d84187549704e35452516c))
* **vision:** download multimodal projector with local models ([a04f5e6](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/a04f5e6cfd40b7e7621cafd13dbc5bdecb0d117a))
* **vision:** load mmproj projector in local llama-server ([fa0b5c6](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/fa0b5c6745e5e329c2247fdd2cf24f8515adc9bc))


### Bug Fixes

* align route names and improve checkbox visibility ([91bb265](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/91bb26512d6a4d1974aa616678d369852ec2b43a))
* **api:** route document and patient fetches through buildApiUrl ([a2323fb](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/a2323fbecadf0a037235b914c324675568fa120c))
* **api:** sanitize error responses ([eba7a9e](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/eba7a9eb5b5daeefdb4b5a8d70e84e4da06eaed8))
* **chat:** dash chat rendering issue ([8d34f5b](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/8d34f5bcc42287b1cbae24807f8330c566e34c76))
* **chat:** drop distance threshold from literature search ([f411b37](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/f411b37862a6fe612a6ac9006242d4245bfab5cd))
* **chat:** include more demographic info in context ([ce99a53](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/ce99a5366740e393ca38195377917524c0ee9dac))
* **chat:** return error message when model calls unknown tool ([d094856](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/d09485633edfa26a975bc396cce5ec9564239c2b))
* **chat:** runtime error ([0791d69](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/0791d6915c8310b331eefc765f989a7df168c94c))
* **chat:** use local firstChunkSeen flag instead of state in sendMessage ([5445903](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/54459036566b127a8c10a829cb1f47dde1d8fdd8))
* **ci:** Cargo lockfile drift corrected (again) ([0a3c0b7](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/0a3c0b73df3bf5c267b42084dd7354e3cc4ad8dd))
* **ci:** keep Cargo.lock in sync on release ([08300ba](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/08300ba57f6afb272e2c5a648e99232b02ed0b80))
* **database:** escape SQLCipher passphrase in PRAGMA key ([592e504](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/592e5047de87916d819a399786c1ed38b479ab79))
* **demo:** give demo patients unique ur numbers ([9dcb8ba](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/9dcb8bae3b2b703b0c04a21f8cf8b09020c1f741))
* **demo:** str for type check ([5b35632](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/5b356321d4d673db5323211a3ed5aef93bd3cd05))
* **deps:** regenerate server/uv.lock, add pip-audit, set 3-day uv cooldown ([4c56daf](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/4c56dafd6fa2de564aa90c8866153c51d742d95a))
* **desktop:** Persian-aware passphrase strength scoring (F-05) ([aef0cbb](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/aef0cbbc300fee4203ed2d82dd1faebcb393952e))
* **desktop:** redact request token from process-manager logs (F-01) ([beef1d6](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/beef1d6c44c1b16ee4c2ebd7d66dd7b94e41ee63))
* **dev:** anonymous volume for python in dev container ([f1a1bc4](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/f1a1bc4591b51d25c3ba398ffef278835d0f3854))
* **dev:** re-enable PHLOX_DEMO_MODE in debug builds ([7237da4](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/7237da42a5ea41d9aa80238fec4ba8d71675138e))
* **docker:** force LF line endings for container and env files ([31bd629](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/31bd6292d982a65594c1cec4d424c7d3d665d087))
* **docker:** make all Docker files build and run the project correctly ([6dfb445](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/6dfb4453e70a50bd026ad27e3dc29f69b371c962))
* **docker:** map host.docker.internal so host-run model servers are reachable ([bb78c9b](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/bb78c9bba07d872c04981d5b3a267021b8b12c0b))
* drop orphaned rag/processing.py ([72ad3ff](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/72ad3ffc6242b217618e364c30d10459e02034b3))
* **helpers:** preserve error detail and tolerate empty bodies in ([1d30ddb](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/1d30ddb91ef8602460f0f2bb6c1478356ec144a0))
* incorrect new-note modal routing ([833a76c](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/833a76cf14f9e9b06b484ce7d1da32a7e58d1087))
* **layout:** unify content padding between Tauri and web modes ([e022e99](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/e022e9923d8f53e625b20df6b6fdbe96d19373b8))
* **lint:** clear remaining singletons for v7 rules ([b10c086](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/b10c0864f9c0938ca40838b1096d6bea3002e044))
* **linux:** data directory case ([d8d5e6e](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/d8d5e6e4fb7128dd14f85c51eb9897230a7baa32))
* **live-asr:** speak the whole Realtime protocol and fail loudly ([90a1997](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/90a1997e42494a047cea3cb50e3cdc9ecb903c93))
* **llm:** increase context size to 16384 for multi-page vision ([67e092d](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/67e092d2e86114c572f06dd95738fd19be981e53))
* lockfile update for build ([165f0d8](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/165f0d8de53e2f7cd0dfb42aaee8049e30ccae2a))
* **note:** always show confirmable search results in start card ([bf39797](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/bf39797d874b56db26bbf506888239ca86e013fc))
* **note:** clear patient state when starting a new note after wrap-up ([0e623dd](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/0e623dd479c68f48c34e18a9244dfb870966636f))
* **note:** dismiss start card after successful patient search ([ddd0e4e](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/ddd0e4ecbe4e0becb99b4cf5f009d7b6b39e4bba))
* **note:** show start card after wrap-up on new patient ([aba5c08](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/aba5c08f6218f8e6a211e12b8cc8d92cd7f3c1f7))
* **pages:** force revalidateOnMount on ClinicSummary and OutstandingJobs ([c4f45df](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/c4f45dfd1c0fff5190887fe2286464d207d3aab3))
* **patient:** immutable jobs_list update for SWR compatibility ([e5ea8f8](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/e5ea8f8e1e5c0848230635f8595a080770b2d59e))
* **patient:** revert reset effect deps to unbreak PatientDetails ([4b7d8da](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/4b7d8da9b2a6a62c3103e2be8ce954af7d09bdf3))
* **pdf:** configure pdfjs wasmUrl to fix JBIG2 image decoding in scanned ([75b419e](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/75b419e51fab65761872156436975d5df62bb5e8))
* prevent stale settings wipe on partial save ([22018f6](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/22018f6a246b5f9d1baf02ac4229fae0a34394b4))
* **rag:** prevent path traversal in PDF upload via filename ([5402e22](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/5402e2279ae9bc1132a5db68311868f167da0147))
* **rag:** repair broken try/except for PDF download lookup ([533d911](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/533d9117b795af85f31dbbb63995aa0c4a4ef40b))
* **rag:** resolve local embedding base url from dynamic port ([4ecee95](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/4ecee9502e6eaf97e567571e0e8c0bbae66fe37b))
* **rag:** spinners on file upload ([049e0f6](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/049e0f6855b23ada8efb775c27152b510a77aa49))
* **rag:** store source PDF on single-file upload ([26caeca](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/26caecaaf2d8019d43bd0869a3aa0275dc13cf31))
* **security:** anchor middleware suffix bypass to non-API paths ([db28862](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/db28862f49b4f7058819906625fc564e5f7663f2))
* **security:** make LocalTokenMiddleware fail closed when token unset ([257515d](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/257515da98c6d2f6259cf543b4d2469ae7c4f3a1))
* **security:** remediate HIGH/MED audit findings across API, SSRF, authz, and ASR ([#7](https://github.com/AmiraliGhamkhar/phlox_persian2/issues/7)) ([fec366c](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/fec366c31da1599a77650e632987359ceb83b4e4))
* **security:** stop logging bearer token in plaintext ([d7dc97f](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/d7dc97f0950821b212965f7f4bc71239f79e2314))
* **security:** whitelist model paths to prevent path traversal ([5b2ba4a](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/5b2ba4a20964dd1c806a6cefba15d542487b888b))
* **server:** bundle sqlite-vec into into tauri; split OCR libs ([b869680](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/b8696801fd6fb642727e9695c2b91c247cb993a1))
* **server:** cancel model downloads when the SSE client disconnects (F-11) ([a9f3f6e](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/a9f3f6e10986a7137e35e6a96dd2f51952bfa9b5))
* **server:** register RequestIdMiddleware in the app factory (F-07) ([c4ef25a](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/c4ef25a032f6196bf697acfd6d1430a05afdd985))
* **sidebar:** repair collapsed-logo hover-to-expand ([d9e27a7](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/d9e27a7ff1202a5063843ab05ccd33c4e56bb8b6))
* **status:** detect whisper/embedding services via /health ([743e127](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/743e1274affcdb9c7af86e9c000a63ba0fd2f15b))
* synchronize uv version across docker, flatpak, and ci ([46f3b15](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/46f3b15ad6fa5571024c64b9363ab5242f613bcb))
* **tauri:** disable native window drag-drop ([430c6a5](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/430c6a5d20a153de0e602faddd62dae72925eb9d))
* **tauri:** make the readiness wait non-blocking; surface stderr on ([21f961b](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/21f961b6e0dbd2e2d6b159c173d9845afb5b2ac7))
* **tauri:** reap the server on handshake failure; make start_server ([3499058](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/3499058f5924a0872f730662ba526134ebdb5277))
* **tauri:** replace window.__TAURI__ guards with isTauri() ([289f9ad](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/289f9ad5142ea9869b3708528c95cff67865e4e3))
* **tauri:** scheme-based origin check for production webview ([99fa2fb](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/99fa2fbe56fe858aa6d8082bf9ad70c0c7c92f43))
* **tauri:** sqlite extensions not enabled ([9aadc47](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/9aadc479da35e11f8448dade2c96c4da44b8922d))
* **templates:** route provider toasts through useApiToast ([541b465](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/541b465fa119e67476415e46c6d7abd2a5452496))
* **theme:** add !important to nav-button for Chakra v3 override ([2b7657f](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/2b7657f30023c6ed5b53832f5e92e99eee020837))
* **theme:** correct latent colorMode bugs in styles modules ([480cecc](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/480cecc095dcb91a66b6b8d8f8981e24d7533a42))
* **theme:** correct semantic token registration and chat input colors" ([48fcf85](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/48fcf85e6aa012d057c3c61e1ee05baf06a85028))
* **ui:** always follow system color mode instead of persisting manual ([0adc566](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/0adc566f1125232821182ca05a4920da80e46c84))
* **ui:** autosave posts only changed config keys (U-9) ([6280ed2](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/6280ed29387b4ea143becd5aeb2ab1325d9368bd))
* **ui:** capture audio via AudioWorklet and accumulate 16-bit PCM (U-4, U-5) ([332e422](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/332e422eb5cde47dff1f6882b2310b6ab668c4f4))
* **ui:** correct mode-blind color reads in PatientTable and ([1a5c390](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/1a5c39067c9f2a2e5d20cf2770b17d892f073544))
* **ui:** correct v3 prop leaks from v2 migration ([a038eca](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/a038ecad33522c3f3fd3e0cab16b8596572d5de6))
* **ui:** drop dictionary hits as soon as the transcript changes (U-6) ([e51741b](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/e51741bb233a0e62c88fb0c740a221a34801396f))
* **ui:** finish v3 prop renames ([0733eb8](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/0733eb804adbc45231e98816a09ec4b1b2ff0266))
* **ui:** floating action menu width ([12e8090](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/12e8090c3485807a6f4d51ed4da6e873197e0814))
* **ui:** improve patient table colours ([d2acc50](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/d2acc50b51fe619dbe0025eae96ba3157a0e47c4))
* **ui:** incorrect border on sidebar ([2f2a09e](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/2f2a09e2194164aee2266687b03d7e9f4bed67a4))
* **ui:** isthmus not appearing for reasoning ([5c18ccd](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/5c18ccdaaa71a740ff7a7f2f051deb12faedcb43))
* **ui:** keep custom base URLs when switching AI providers (U-11) ([b65ba55](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/b65ba557f976d72e28a7457fa006518e26218f9b))
* **ui:** line break on hover in sidebar ([c0af43c](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/c0af43cae8180437ee45370672c17422b7336992))
* **ui:** make masked API-key editing explicit instead of silently dropped (F-10, U-3) ([f4286db](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/f4286dbdab0b999430765530c62420a6855a5e15))
* **ui:** make server-startup retry restart the server, fix stale timing (U-7) ([05a32bd](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/05a32bdae97e3e38e5be9f0698fca19f808d2485))
* **ui:** Persianize remaining English interface strings (U-1) ([543035f](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/543035fa13cf5248f0a12872a5647c455e77ad17))
* **ui:** Phase 2b runtime fixes ([ee829a4](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/ee829a483cf238493d2a95408694ce1d0927e6f2))
* **ui:** position inference-mode indicator with logical RTL property (F-04) ([1fa9e30](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/1fa9e30735e57dadb97bd1a7aff74bef48ff18cc))
* **ui:** prevent dashboard flash before unlock splash on Tauri boot ([3eacf97](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/3eacf97579204c52ee13fd57ab4684784ed8497d))
* **ui:** reasoning icons ([dbb37d2](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/dbb37d2e9d72be16c9ff1b86078d089da01eb23a))
* **ui:** recalibrate RAM requirements and tier assignments ([0ccfb92](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/0ccfb92ff4eba38d9bf53616ea0ecf265e2a2c04))
* **ui:** remove dead whisper-model fetch causing settings crash ([e3277b4](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/e3277b415a95c7c2a88ac342b0f744aa2ab6a2c0))
* **ui:** remove redundant legacy redirect routes (U-8) ([fb6325d](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/fb6325d7238a60434d44f36033762837453bf03c))
* **ui:** remove stale '1 of 4' step counter from encryption setup (U-2) ([753ef53](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/753ef533feb465b7444a482f3abf256132f0267e))
* **ui:** render safety banners with Chakra v3 warning semantic tokens (F-03) ([61541cc](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/61541cc84411bc1f0551b00a3a0a333877346cc7))
* **ui:** reposition reasoning panel resize handle ([6d08fcf](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/6d08fcf71e402f520223be84f83b1ea804ff5992))
* **ui:** resolve Maximum update depth loop on New Note ([63eae52](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/63eae527f1758559b309b08f51e07217b21ec7d0))
* **ui:** restore styling for tabs, tables, modals, form controls etc ([e11da91](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/e11da919bbc025c4e49ca50be415dd30ca4e7116))
* **ui:** revert sidebar border ([dc48951](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/dc489511e5a67709de5993f34b5d0c42382224fb))
* **ui:** Runtime fixes for Chakra v3 ([0c5f64f](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/0c5f64fe3af4301847b12f9fc3a7491e20324d73))
* **ui:** save patient demographics ([f98d50f](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/f98d50fa15b5f2b5ae4049a9d9ddf0594d62e0a0))
* **ui:** search and toast feedback ([364a4c4](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/364a4c4a025f28692b9c7f358e971cfc712c6f24))
* **ui:** sidebar cleanup ([72d87c1](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/72d87c14b602131e5a022e1ca304f25ebe812b5c))
* **ui:** stop misreporting server-startup failures; retry re-warms ([2d2249a](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/2d2249aee5cf1c88ce92fd98b72cbc2a6b099a05))
* **ui:** suppress redundant default-template toast on first start ([e8559bd](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/e8559bdb3343a5195c66bf013da5623ecd3f766f))
* **ui:** toast styling ([c596ee4](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/c596ee42ff35ed9f79eae34d8c9ffe6a47c2ecad))
* **ui:** use dynamic viewport units for full-height layouts ([98c61b0](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/98c61b0a9f37f4e90a2516c71fa095fbd96335cc))
* **ui:** use logical (RTL-aware) spacing and borders (U-10) ([918ef12](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/918ef129e7bac0678fadf7b618dcc3127bf99eb4))
* **ui:** various styling inconsistencies ([6799d70](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/6799d70851e59d9e652145787e88edaec6729675))
* **ui:** wire embedding model into splash ([c1c154a](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/c1c154a9a586badcf72107c67ea381ede43a524e))
* unblock and pass frontend typecheck ([a1b3298](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/a1b329821152e9b91604a5a36ff44e0a6d677049))
* **vision:** route image-only PDFs through vision, not legacy text ([566e557](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/566e557e477120942748f8609e9c0bac34eaf625))


### Performance Improvements

* **api:** run blocking DB handlers in threadpool; offload mixed-handler DB calls ([6fb8191](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/6fb819183b85f18e7e5646070c6bdf89512dd139))
* **embedding:** cap context and quantize KV to cut idle memory ([870996b](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/870996b7fa47d39eb6b2bf92e0a48973a5bacf85))
* improve template loading behaviour ([cc9f02f](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/cc9f02fc89441f8e36409a70ef9c04bed0dbcffc))
* **models:** filter models exceeding RAM with 4GB buffer ([bfadfed](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/bfadfedaff6d7bdcd42a85668099dc15e42e7e09))
* serve dashboard chat suggestions from static client-side map ([85aec4f](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/85aec4f882869d6fff88b51d0a7a25a153f1ff7b))
* settings load improvement ([8114035](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/8114035d6841789a337ebf6e633ce1721d698ce1))
* **settings:** memoize smartRecommendations ([f88ff8c](https://github.com/AmiraliGhamkhar/phlox_persian2/commit/f88ff8cb5d758aba69447f98737f5403e632be0f))

## [2.2.4](https://github.com/bloodworks-io/phlox/compare/v2.2.3...v2.2.4) — ۲۰۲۶-۰۷-۳۰

- نسخه `uv` در Docker، Flatpak و CI هماهنگ شد. ([46f3b15](https://github.com/bloodworks-io/phlox/commit/46f3b15ad6fa5571024c64b9363ab5242f613bcb))

## [2.2.3](https://github.com/bloodworks-io/phlox/compare/v2.2.2...v2.2.3) — ۲۰۲۶-۰۷-۲۷

- ناسازگاری دوباره‌به‌دوباره فایل قفل Cargo در CI اصلاح شد. ([0a3c0b7](https://github.com/bloodworks-io/phlox/commit/0a3c0b73df3bf5c267b42084dd7354e3cc4ad8dd))

## [2.2.2](https://github.com/bloodworks-io/phlox/compare/v2.2.1...v2.2.2) — ۲۰۲۶-۰۷-۲۷

- فایل `Cargo.lock` هنگام انتشار همگام نگه داشته شد.
- حجم ناشناس Python برای محیط توسعه اضافه شد.

## [2.2.1](https://github.com/bloodworks-io/phlox/compare/v2.2.0...v2.2.1) — ۲۰۲۶-۰۷-۲۷

- فایل قفل وابستگی‌ها برای ساخت به‌روزرسانی شد.

## [2.2.0](https://github.com/bloodworks-io/phlox/compare/v2.1.1...v2.2.0) — ۲۰۲۶-۰۷-۲۷

- گزارش ممیزی، endpointهای خواندن/خروجی و نگهداری گزارش اضافه شد.
- حالت WAL پایگاه داده و پشتیبان‌گیری از فایل‌های همراه فعال شد.
- ناظر فرایند والد برای توقف امن سرور در صورت خروج Tauri اضافه شد.
- وابستگی‌ها و مدت خنک‌سازی `uv` بهبود یافتند.
- از پیمایش مسیر در بارگذاری PDF جلوگیری شد.
- مدیریت مدل‌های تصویری، پایگاه برداری و ابزارهای MCP تکمیل شد.
- اعتبارسنجی origin، محدودسازی نرخ، CSP سخت‌گیرانه و پوشاندن کلیدهای API اضافه شد.
- ناوبری، وضعیت‌های فعال، پنل‌ها، فهرست بیماران و اعلان‌ها بازطراحی شدند.

## [2.1.1](https://github.com/bloodworks-io/phlox/compare/v2.1.0...v2.1.1) — ۲۰۲۶-۰۷-۲۳

- افزونه‌های SQLite در نسخه دسکتاپ فعال شدند.

## [2.1.0](https://github.com/bloodworks-io/phlox/compare/v2.0.0...v2.1.0) — ۲۰۲۶-۰۷-۲۳

- فرم‌های PDF، استخراج اطلاعات، بارگذاری گروهی و مدل بردارسازی اضافه شدند.
- جست‌وجوی فهرست بیماران بر اساس نام و شماره پرونده فراهم شد.
- رضایت بیمار برای ثبت محیطی و ذخیره آن در پرونده اضافه شد.
- قابلیت‌های پایگاه دانش، citationهای ساختاریافته و جست‌وجوی منابع علمی تکمیل شدند.
- سرورهای llama.cpp و موتورهای محلی برای مدل‌های زبانی و تشخیص گفتار آماده شدند.
- بهبودهای گسترده در پنل کناری، پنل استدلال، قالب‌ها و حالت راه‌اندازی اعمال شد.

## [2.0.0](https://github.com/bloodworks-io/phlox/compare/v1.0.5...v2.0.0) — ۲۰۲۶-۰۶-۲۸

- معماری پایگاه برداری به `sqlite-vec` منتقل شد؛ داده‌های RAG قدیمی نیاز به بازسازی دارند.
- قالب‌های یادداشت، نامه، فرم، کارها و پروفایل بیمار توسعه یافتند.
- پردازش اسناد، OCR، مدل تصویری و نمایش artifactها در گفت‌وگو اضافه شد.
- قفل‌گشایی پایگاه داده، رمزگذاری، ثبت رضایت و ایمنی درخواست‌ها بهبود یافت.

## نسخه‌های قدیمی‌تر

جزئیات نسخه‌های پیش از ۲.۰ در تاریخچه Git و [صفحه انتشارها](https://github.com/bloodworks-io/phlox/releases) موجود است.
