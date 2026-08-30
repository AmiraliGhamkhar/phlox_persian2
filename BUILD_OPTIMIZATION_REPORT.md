# Phlox Build Optimization — Research, Evaluation & Implementation

Date: 2026-08-30 · Branch: `arena/01a052f4-phlox-persian`

This document covers the four requested phases: (1) research into 2025–2026 build
tooling, (2) evaluation of each optimization, (3) a prioritized recommendation
plan with exact file paths / commands / verification / rollback, and (4) the
implementation of the top safe optimizations, which are already applied on this
branch.

**Constraints honored throughout:** no functionality/behavior changes, no
dependency version upgrades, no test-file changes, security features
(codesigning, CSP, notarization) untouched, macOS + Linux compatibility, CI
(`.github/workflows/build.yml`) kept working, and `build-all.sh --skip-cpp`
unchanged.

---

## 1. Baseline measurements (this checkout)

| Check | Command | Result |
|---|---|---|
| Type check | `npm run typecheck` | ✅ pass |
| Unit tests | `npm test -- --run` | ✅ 23 passed / 5 files |
| Lint | `npm run lint` | ✅ pass |
| Frontend build | `npm run build` | ✅ ~2.1–2.7 s |
| Largest entry chunk | `index-*.js` | **543.5 kB** (gzip 142.9 kB), >500 kB warning |
| Eagerly-loaded JS (in `index.html`) | baseline | 1085 KB total |

Native/Docker builds (Nuitka ~10 min, CMake ~5–9 min, Docker ~5–8 min first run)
cannot be executed in this sandbox (no `cmake`/`uv`/`docker`/`ccache`), so those
changes were verified by `bash -n` syntax checks, isolated unit tests of the new
helper logic, and careful reading against the documented tool behavior.

---

## 2. Phase 1 — Research findings (2025–2026)

### 2.1 Nuitka (Python → C)

- **ccache is the official answer.** Nuitka auto-detects `ccache` on `PATH`
  (and `sccache`-style launchers work for the CMake side). On MSVC/ClangCL it
  bundles its own `clcache`. The binary path can be pinned with
  `NUITKA_CCACHE_BINARY`; cache lives under the platform cache dir, overridable
  with `NUITKA_CACHE_DIR`. Nuitka also documents sub-caches
  (`NUITKA_CACHE_DIR_CCACHE`, `..._DOWNLOADS`, `..._BYTECODE`,
  `..._DLL_DEPENDENCIES`). Source: Nuitka user manual / GitHub tips
  ([nuitka.net](https://nuitka.net/user-documentation/tips.html),
  [github.com/Nuitka/Nuitka](https://github.com/Nuitka/Nuitka)).
- Nuitka keeps per-module C build outputs in the output build tree. Deleting the
  standalone folder every build forces a full recompile; keeping it lets
  ccache + Nuitka skip unchanged modules.
- **Mode choice:** `--mode=standalone` (folder) is correct for a Tauri resource
  bundle; `--mode=onefile` adds a self-extract/bootstrap step and (inside Docker)
  can need elevated privileges — it would change the launch model the wrapper
  scripts depend on. Not recommended here.
- **Alternatives evaluated and rejected for this project:**
  - *PyOxidizer* — effectively unmaintained in 2025/2026; poor fit for a
    Nuitka-shaped native bundle.
  - *Shiv / PEX / zipapp* — ship **bytecode**, require a CPython interpreter at
    runtime and do not hide source; Phlox deliberately compiles with Nuitka for
    distribution + obfuscation. Not a drop-in.
  - *Cython / mypyc* — require manual annotation/module selection and a large
    refactor; mypyc only compiles type-annotated modules. High effort, risky.

### 2.2 CMake / C++ (llama.cpp, whisper.cpp, parakeet.cpp)

- **Compiler launcher is a first-class CMake feature** (≥3.4):
  `-DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache`
  (or `sccache`). CMake ≥3.17 also honors the
  `CMAKE_C/CXX_COMPILER_LAUNCHER` environment variables. The launcher is a
  no-op when the binary is absent, so it is safe to pass unconditionally.
  Sources: CMake docs via
  [StackOverflow](https://stackoverflow.com/questions/1815688/how-to-use-ccache-with-cmake),
  [sccache PyPI](https://pypi.org/project/sccache/).
- **Incremental builds:** CMake/Make/Ninja already skip up-to-date objects. The
  scripts defeated this by running `rm -rf build` on every invocation. Keeping
  the build dir (and only wiping when configure inputs change) restores
  incremental builds. Wiping on a *configure-signature* change guards against
  stale objects after a backend/SHA switch.
- **sccache** adds Rust + cloud backends (S3/GCS) and works for C/C++ too; useful
  if a shared/CI cache is ever wanted. Local ccache is simpler and is what the
  CI already installs (`brew install ccache`).
- **distcc** (distributed compilation) adds operational complexity and a
  security surface; not warranted for a single-developer desktop build.
- **Pre-built sidecar binaries** (downloading llama.cpp/whisper.cpp release
  artifacts instead of compiling) is the single biggest *future* time saver, but
  requires (a) releases for the exact pinned SHAs, (b) matching static-lib /
  Metal / rpath packaging that the current scripts carefully enforce, and
  (c) notarization of downloaded binaries. Classed as a medium-term architectural
  change, not a quick win.

### 2.3 Tauri / Cargo

- Tauri’s official size/perf guidance is a `[profile.release]` with
  `lto = true`, `codegen-units = 1`, `strip`, `opt-level` — these **shrink** the
  binary but make release compiles *slower*, so they are the wrong lever for
  build *time* ([v2.tauri.app/concept/size](https://v2.tauri.app/concept/size/)).
- Cargo already caches the registry/target and uses incremental compilation in
  dev. The `src-tauri/target/` dir is **not** deleted by the scripts, so the
  Rust side is already incremental. The main avoidable cost is the sidecars,
  which are rebuilt by `build-all.sh`.
- Dev tip from the community: align `MACOSX_DEPLOYMENT_TARGET` between
  rust-analyzer and `tauri dev` to avoid double-recompiles; that is an IDE-config
  nicety, not a CI/build-script issue here.

### 2.4 Docker / BuildKit

- **Cache mounts are the biggest BuildKit win.** `RUN --mount=type=cache,target=…`
  persists package-manager caches across builds even when a layer is invalidated,
  and never ships in the image. Key paths: npm `~/.npm` (or `/root/.npm`),
  apt `/var/cache/apt` + `/var/lib/apt`, uv `/root/.cache/uv`.
  Requires `# syntax=docker/dockerfile:1` and BuildKit (default in Docker 23+/
  buildx). Sources:
  [Grizzly Peak](https://www.grizzlypeaksoftware.com/library/docker-buildkit-features-and-optimization-nc1u9ncy),
  [oneuptime](https://oneuptime.com/blog/post/2026-02-08-how-to-use-run-mounttypecache-for-package-manager-caching/view).
- **uv official Docker guidance:** set `UV_LINK_MODE=copy` (cache mount is absent
  at runtime, so files must be copied not hard-linked) and mount
  `--mount=type=cache,target=/root/.cache/uv` for `uv sync`. Splitting the
  dependency install from the source copy keeps the dependency layer cached.
  Sources: [astral-sh/uv#15586](https://github.com/astral-sh/uv/issues/15586),
  [hynek.me](https://hynek.me/articles/docker-uv/),
  [pydevtools](https://pydevtools.com/handbook/how-to/how-to-use-uv-in-a-dockerfile/).
- **Layer ordering:** least→most volatile (base → apt → manifests → install →
  source). The production Dockerfile already copies manifests before source for
  uv; the frontend stage copied source together with manifests, which invalidated
  `npm ci` on any frontend edit — now split.
- **CI:** the workflow already uses `cache-from: type=gha, cache-to: type=gha`.
  GHA cache and BuildKit cache mounts compose (mounts accelerate within/across
  builds on a runner; GHA transfers layers between runs). No CI change needed.
- **distroless/scratch** base: would shrink the runtime image but drops tesseract,
  tzdata, CA certs and the uvicorn signal model the app relies on; out of scope
  for a no-behavior-change pass.

### 2.5 Vite / React (rolldown-vite 8)

- `build.rollupOptions.output.manualChunks` splits the entry into stable vendor
  chunks. **This Vite is rolldown-based: `manualChunks` must be a *function***
  (object form is rejected with “manualChunks is not a function”).
- **Two pitfalls found and avoided during implementation:**
  1. Substring matching (`id.includes("/react/")`) also matches
     `@tauri-apps/plugin-http` and `react-markdown`, silently ballooning the
     chunk. Must match **package path boundaries** with a regex,
     e.g. `/node_modules\/(react|react-dom|react-router|scheduler)\//`.
  2. Pinning a **lazily-loaded** library (pdfjs is loaded via
     `import("pdfjs-dist/legacy/build/pdf")`) into a vendor chunk that an eager
     module also touches (pdf-lib) drags the whole chunk into the initial load.
     Measured: a `vendor-pdf` pin made the 904 kB PDF chunk eager. Reverted;
     lazy libs are left for rolldown’s natural on-demand splitting.
- Splitting Chakra/Emotion/icons measured **larger** eager JS (runtime/wrapper
  duplication) and only moved the >500 kB warning to a different file; Chakra
  tracks app versions, so it gave no caching benefit. Dropped.
- **React.lazy route splitting is already in use** (`AppRoutes.jsx` lazy-loads
  PatientDetails/Settings), and pdfjs is dynamically imported — no app-code
  changes needed (and none made).

### 2.6 Node / npm

- Benchmarks consistently rank install speed Bun > pnpm > npm, with pnpm offering
  disk savings via a content-addressable store
  ([techsy.io](https://techsy.io/en/blog/bun-vs-pnpm-vs-yarn-vs-npm),
  [PkgPulse](https://www.pkgpulse.com/guides/pnpm-vs-npm-vs-yarn-vs-bun-2026)).
- **Switching package manager is an architectural change**, not a quick win: it
  replaces the lockfile (`package-lock.json` → `pnpm-lock.yaml`/`bun.lock`),
  changes the `packageManager` field, Dockerfiles, CI `setup-node` cache, and the
  `.npmrc` policy (`ignore-scripts`, `min-release-age`). Risk of subtle
  resolution differences with native-ish deps. **Not done** — recommended only as
  an opt-in later.
- Safe, no-migration wins: stop running `npm cache clean --force` (it throws away
  the warm cache; with BuildKit the cache mount is what persists anyway) and add
  `--no-audit --no-fund` to CI/Docker installs to skip network noise.

### 2.7 Python / uv

- `uv sync --locked`/`--frozen` already used. Docker best-practice additions are
  `UV_LINK_MODE=copy` + a uv cache mount (done) and optionally
  `UV_COMPILE_BYTECODE=1` (faster container startup, slightly larger image; left
  out to keep behavior/image neutral).
- zipapp/Shiv/PEX don’t apply to the compiled sidecar (see 2.1).

---

## 3. Phase 2 — Evaluation matrix

Impact: **High** >5 min · **Med** 1–5 min · **Low** <1 min. Risk: Safe / Moderate /
Risky. Effort: Trivial <5 min · Easy <30 min · Moderate <2 hr · Hard >2 hr.

| # | Optimization | Impact | Risk | Effort | Notes |
|---|---|---|---|---|---|
| 1 | Keep CMake build dirs (incremental) for llama/whisper/parakeet | **High** (repeat C++ builds drop to seconds–<1 min) | Safe | Easy | Wipe on configure-signature change or `FORCE_CLEAN=1` |
| 2 | ccache/sccache launcher for CMake **and** Nuitka | **High** (Nuitka + C++ repeat) | Safe | Easy | No-op when absent; CI already caches `~/.cache/ccache` |
| 3 | Persistent `NUITKA_CACHE_DIR` for local builds; don’t `rm -rf dist` | **High** | Safe–Mod | Easy | `--clean`/`FORCE_CLEAN=1` escape hatch; CI path untouched |
| 4 | BuildKit cache mounts (npm/apt/uv) + layer split in Dockerfile(s) | **Med–High** (Docker rebuilds) | Safe | Easy | Composes with existing GHA cache |
| 5 | Stop `rm -rf node_modules/.vite` on every `npm run dev`/`tauri dev` | Low–Med (dev startup) | Safe | Trivial | Vite invalidates its own dep cache correctly |
| 6 | `manualChunks` vendor-react split | Low (entry 543→346 kB; caching) | Safe–Mod | Easy | Carefully scoped; lazy libs verified to stay lazy |
| 7 | `npm ci --no-audit --no-fund`; drop `npm cache clean --force` in Docker | Low | Safe | Trivial | Done with #4 |
| 8 | Add a `.cargo/config.toml` lld/mold linker + sccache for Rust | Med | Moderate | Easy | macOS linker differs; not needed (Rust already incremental) |
| 9 | Download pre-built sidecars instead of compiling C++ | **High** | Moderate–Risky | Hard | Needs exact-SHA static/Metal builds + notarization |
| 10 | Migrate npm → pnpm/bun | Med (install speed/disk) | Moderate–Risky | Moderate | Lockfile + CI + Docker + policy churn; opt-in only |
| 11 | Nuitka `--mode=onefile` / PyOxidizer / Shiv / Cython | — | Risky | Hard | Changes launch model / unmaintained / large refactor — rejected |
| 12 | Cargo `lto`/`codegen-units=1` release profile | (size only) | Moderate | Easy | Makes compiles *slower*; opposite of build-time goal |
| 13 | distroless/scratch runtime image | Low (image size) | Risky | Moderate | Drops tesseract/tzdata/certs/uvicorn signals — rejected |

---

## 4. Phase 3 — Prioritized recommendations

### Quick wins (no risk) — **IMPLEMENTED on this branch**

1. **Incremental CMake builds** (eval #1) — files:
   `src-tauri/build-llama.sh`, `build-whisper.sh`, `build-parakeet.sh`,
   new `src-tauri/build-common.sh`.
   - *Before:* every build ran `rm -rf <repo>/build` → full 3–5 min recompile.
   - *After:* build dir is reused; wiped only when the pinned SHA / backend /
     patch changes or `FORCE_CLEAN=1`.
   - *Verify:* run `bash src-tauri/build-whisper.sh` twice; second run logs
     `♻️ Reusing incremental build directory` and finishes in seconds.
   - *Rollback:* `git checkout -- src-tauri/build-*.sh` (or `FORCE_CLEAN=1`).
2. **ccache/sccache for CMake + Nuitka** (eval #2) — `build-common.sh`,
   `build-server.sh`.
   - *Before:* no local compiler cache.
   - *After:* auto-detects `ccache` then `sccache`; passes
     `-DCMAKE_C/CXX_COMPILER_LAUNCHER=…` and sets `NUITKA_CCACHE_BINARY`.
   - *Verify:* `brew install ccache` (macOS) / `apt install ccache` (Linux),
     rebuild twice; `ccache -s` shows hits. Absent → informative message, no
     failure.
   - *Rollback:* uninstall ccache, or revert files.
3. **Persistent Nuitka cache + keep `server/dist`** (eval #3) —
   `build-server.sh`, `.gitignore`.
   - *Before:* `rm -rf server/dist` every build (full Nuitka recompile).
   - *After:* `NUITKA_CACHE_DIR=src-tauri/.build-cache/nuitka` on local builds;
     output reused; `--clean`/`FORCE_CLEAN=1` forces a full rebuild. CI keeps
     platform-default paths (`~/Library/Caches/Nuitka`, `~/.cache/ccache`).
   - *Verify:* `bash src-tauri/build-server.sh` twice; second run reuses cache.
   - *Rollback:* `bash src-tauri/build-server.sh --clean`.
4. **BuildKit cache mounts + Docker layer split** (eval #4/#7) — `Dockerfile`,
   `Dockerfile.dev`.
   - *Before:* `npm ci` layer invalidated by any frontend edit; caches cleaned.
   - *After:* `# syntax=docker/dockerfile:1`, `--mount=type=cache` for npm/apt/
     uv, `UV_LINK_MODE=copy`, manifests copied before source, `--no-audit
     --no-fund`.
   - *Verify (Docker required):*
     `docker buildx build -t phlox:test .` twice; second build reuses mounts.
     Compare with `time docker build …`.
   - *Rollback:* `git checkout -- Dockerfile Dockerfile.dev`.
5. **Dev startup: stop wiping Vite dep cache** (eval #5) — `package.json`
   `start-react`.
   - *Before:* `rm -rf node_modules/.vite && vite` (full re-optimize each start).
   - *After:* just `vite` (Vite re-optimizes only when deps change).
   - *Verify:* `npm run start-react` twice; second start skips “optimizing
     dependencies”.
   - *Rollback:* restore the `rm -rf` prefix.
6. **Vite vendor-react chunk split** (eval #6) — `vite.config.js`.
   - *Before:* `index` chunk 543.5 kB with the >500 kB warning.
   - *After:* React runtime isolated (`vendor-react` ~229 kB, gzip 73 kB), entry
     `index` ~346 kB; pdfjs/pdf-lib/Chakra verified to remain lazy/unchanged.
   - *Verify:* `npm run build`; confirm `vendor-react-*.js`, that `index.html`
     does **not** list a `vendor-pdf` chunk, and that `pdf-*.js` is lazy.
   - *Rollback:* remove the `manualChunks` block.

> All of the above keep `build-all.sh --skip-cpp`, codesigning/notarization, CSP,
> and the CI workflow unchanged. `build-all.sh` itself required **no** edits
> (it calls the individual scripts, which now self-manage caching).

### Medium-term (needs testing)

- **Pre-built sidecar binaries** (eval #9): publish/download static
  llama-server/whisper-server for the pinned SHAs per OS/arch, verify
  Metal/static/rpath + notarization, then have `build-all.sh` download when a
  matching artifact exists and fall back to compiling. Cuts ~5–9 min.
- **Rust linker** (eval #8): add `.cargo/config.toml` with `mold`/`lld` on Linux
  (and sccache via `RUSTC_WRAPPER`) after validating on the macOS toolchain.
- **`UV_COMPILE_BYTECODE=1`** in Docker for faster container cold-start (measure
  image-size delta first).

### Architectural changes (only with explicit approval)

- **npm → pnpm** (eval #10): ~3× faster cold installs and ~70% less disk, but
  lockfile/CI/Docker/`.npmrc` policy migration with a validation cycle.
- **distroless runtime** or **Nuitka onefile** (eval #11/#13): change the
  runtime/launch contract; not compatible with a no-behavior-change pass.

---

## 5. Phase 4 — What was implemented (this branch)

| File | Change |
|---|---|
| `src-tauri/build-common.sh` *(new)* | Shared helpers: `phlox_find_compiler_cache`, `phlox_cmake_launcher_args`, `phlox_collect_cmake_launcher`, `phlox_setup_nuitka_cache`, `phlox_prepare_build_dir` (signature-based incremental dir), `phlox_jobs_count`, `phlox_is_windows`. Safe on macOS bash 3.2 + Linux; degrades to no-ops. |
| `src-tauri/build-llama.sh` | Sources helper; removes unconditional `rm -rf build` (now signature-gated); adds compiler launcher; incremental `cmake --build`. |
| `src-tauri/build-whisper.sh` | Same incremental + launcher treatment; build signature includes pinned whisper SHA + backend. |
| `src-tauri/build-parakeet.sh` | Same; signature includes a hash of the Omi adapter patch so patch changes force a clean rebuild. |
| `src-tauri/build-server.sh` | Sources helper; `phlox_setup_nuitka_cache` (local persistent `NUITKA_CACHE_DIR`, ccache pin); `rm -rf server/dist` now only on `--clean`/`FORCE_CLEAN=1`; adds `--clean` flag. |
| `.gitignore` | Ignores `src-tauri/.build-cache/`. |
| `Dockerfile` | `# syntax=docker/dockerfile:1`; BuildKit cache mounts for npm/apt/uv; `UV_LINK_MODE=copy`; frontend manifests copied before source; `npm ci --no-audit --no-fund`; removed cache-clean. |
| `Dockerfile.dev` | Same cache-mount treatment for npm/apt/uv + `UV_LINK_MODE=copy`. |
| `package.json` | `start-react` no longer deletes `node_modules/.vite`. |
| `vite.config.js` | Scoped `manualChunks` isolating the React runtime into `vendor-react`; lazy PDF/Chakra chunks left untouched (verified). |

### Verification performed

- `npm run typecheck` — **pass**
- `npm test -- --run` — **23/23 pass** (5 files)
- `npm run lint` — **pass**
- `npm run build` — **pass**; `index` chunk 543.5 kB → **346 kB**, new stable
  `vendor-react` chunk (~229 kB / gzip 73 kB); pdfjs worker + `pdf-*.js` and
  `fillForm`/`Settings`/`PatientDetails` confirmed **still lazy**; total eager JS
  unchanged (1084 KB vs baseline 1085 KB).
- All shell scripts pass `bash -n`; the `build-common.sh` state machine
  (fresh / reuse / signature-change wipe / `FORCE_CLEAN` / legacy-dir reset) was
  unit-tested in isolation and the local-vs-CI cache branch verified.

### Expected impact (repeat builds)

- **C++ sidecars (llama+whisper+parakeet):** a no-op rebuild goes from
  ~5–9 min (full recompile) to **seconds–~1 min** (incremental + ccache).
- **Nuitka server:** unchanged-source rebuilds reuse ccache/Nuitka caches; the
  largest cost (recompiling generated C) is skipped. First build unchanged.
- **Docker:** rebuilds after a frontend-only or source-only edit skip the
  npm/uv download/install cost via cache mounts and split layers.
- **Dev (`tauri dev` / `npm run dev`):** Vite skips dependency re-optimization.

### How to opt out / force a clean build

- Full native rebuild: `FORCE_CLEAN=1 ./build-all.sh`
- Server only: `bash src-tauri/build-server.sh --clean`
- Uninstall `ccache`/`sccache` to disable compiler caching (scripts auto-detect).
- Revert everything: `git checkout -- . ` (and remove `src-tauri/build-common.sh`).
