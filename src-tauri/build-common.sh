#!/usr/bin/env bash
#
# Shared build helpers for the Phlox native sidecar builds.
#
# Centralizes two cross-cutting concerns that were previously duplicated (and
# left unoptimized) in build-server.sh / build-llama.sh / build-whisper.sh /
# build-parakeet.sh:
#
#   1. Compiler cache (ccache / sccache) discovery for both Nuitka (Python->C)
#      and CMake (C/C++) builds. ccache gives near-instant *repeat* builds by
#      caching compiled object files; it is a strict no-op when not installed.
#
#   2. Incremental CMake build-directory management. Previously every script ran
#      `rm -rf build` unconditionally, discarding the incremental object cache on
#      every run (3-5 min of recompilation even when nothing changed). We now
#      keep the build directory and only wipe it when the configuration that
#      produced it changes (pinned source SHA / backend flags), or when an
#      explicit FORCE_CLEAN=1 is requested.
#
# Source this file; do not execute it directly. All helpers are safe on macOS
# (bash 3.2) and Linux and degrade to no-ops when optional tooling is absent.
#
# Environment overrides:
#   FORCE_CLEAN=1         Force a clean rebuild (wipe Nuitka output / CMake dir)
#   PHLOX_CACHE_ROOT=...  Where to keep local tool caches (default src-tauri/.build-cache)
#   NUITKA_CACHE_DIR=...  Nuitka cache base dir (set automatically on local builds)
#   CI=1                  (GitHub Actions etc.) Keeps the platform-standard cache
#                         paths so actions/cache restore steps keep working.

# Guard against being sourced more than once.
if [ -n "${_PHLOX_BUILD_COMMON_LOADED:-}" ]; then
  # `return` only works when sourced; the `|| true` keeps direct execution safe.
  return 0 2>/dev/null || true
fi
_PHLOX_BUILD_COMMON_LOADED=1

# This file lives in src-tauri/, so the project root is its parent directory.
PHLOX_COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PHLOX_PROJECT_DIR="$(dirname "$PHLOX_COMMON_DIR")"

# Repository-local tool caches (git-ignored). Used only for *local* builds so a
# developer gets a warm cache without polluting their home directory; CI keeps
# its own platform-standard caches.
export PHLOX_CACHE_ROOT="${PHLOX_CACHE_ROOT:-$PHLOX_COMMON_DIR/.build-cache}"

phlox_is_windows() {
  case "$OSTYPE" in
    msys* | win32* | cygwin*) return 0 ;;
    *) return 1 ;;
  esac
}

# Echo a safe number of parallel build jobs for the current machine.
phlox_jobs_count() {
  local jobs
  if [[ "$OSTYPE" == "darwin"* ]]; then
    jobs="$(sysctl -n hw.logicalcpu 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)"
  elif phlox_is_windows; then
    jobs="${NUMBER_OF_PROCESSORS:-4}"
  else
    jobs="$(nproc 2>/dev/null || echo 4)"
  fi
  echo "$jobs"
}

# Echo the name of an available compiler launcher ("ccache" or "sccache"), or
# nothing when none is found. On Windows/MSVC we deliberately do not force a
# launcher - Nuitka ships its own clcache there and the CMake side relies on the
# toolchain default, keeping behaviour unchanged.
phlox_find_compiler_cache() {
  if phlox_is_windows; then
    return 0
  fi
  if command -v ccache >/dev/null 2>&1; then
    echo "ccache"
  elif command -v sccache >/dev/null 2>&1; then
    echo "sccache"
  fi
}

# Echo CMake flags that route C/C++ compilation through the available cache
# launcher (supported since CMake 3.4). Emits nothing when no launcher exists,
# so callers can splice the output unconditionally.
phlox_cmake_launcher_args() {
  local launcher
  launcher="$(phlox_find_compiler_cache)"
  if [ -n "$launcher" ]; then
    echo "-DCMAKE_C_COMPILER_LAUNCHER=$launcher"
    echo "-DCMAKE_CXX_COMPILER_LAUNCHER=$launcher"
  fi
}

# Populate CMAKE_LAUNCHER_ARGS (a bash array) with launcher flags, if any.
# Usage: phlox_collect_cmake_launcher; then use "${CMAKE_LAUNCHER_ARGS[@]}"
phlox_collect_cmake_launcher() {
  CMAKE_LAUNCHER_ARGS=()
  local line
  while IFS= read -r line; do
    [ -n "$line" ] && CMAKE_LAUNCHER_ARGS+=("$line")
  done < <(phlox_cmake_launcher_args)
  if [ "${#CMAKE_LAUNCHER_ARGS[@]}" -gt 0 ]; then
    echo "✅ Compiler cache enabled: $(phlox_find_compiler_cache)"
  else
    echo "ℹ️  No ccache/sccache found (install ccache for much faster repeat C/C++ builds)"
  fi
}

# Ninja is the generator ggml/llama.cpp recommend for fast, parallel, incremental
# builds (it avoids the make re-check overhead). Echo "-G Ninja" when ninja is
# installed; emit nothing so CMake falls back to its default (Unix Makefiles).
phlox_cmake_generator_args() {
  if command -v ninja >/dev/null 2>&1 || command -v ninja-build >/dev/null 2>&1; then
    echo "-G Ninja"
  fi
}

# Populate CMAKE_GENERATOR_ARGS (a bash array) with "-G Ninja" when available.
phlox_collect_cmake_generator() {
  CMAKE_GENERATOR_ARGS=()
  local line
  while IFS= read -r line; do
    [ -n "$line" ] && CMAKE_GENERATOR_ARGS+=("$line")
  done < <(phlox_cmake_generator_args)
  if [ "${#CMAKE_GENERATOR_ARGS[@]}" -gt 0 ]; then
    echo "✅ CMake generator: Ninja (fast parallel incremental builds)"
  else
    echo "ℹ️  Ninja not found - using CMake default generator (install ninja for faster C++ builds)"
  fi
}

# Echo a short tag naming the active CMake generator, for use in build signatures
# so switching generators triggers a one-time clean rebuild.
phlox_cmake_generator_tag() {
  if command -v ninja >/dev/null 2>&1 || command -v ninja-build >/dev/null 2>&1; then
    echo "Ninja"
  else
    echo "Make"
  fi
}

# Configure Nuitka's cache locations and, when available, pin ccache.
#
# On local (non-CI) builds we point NUITKA_CACHE_DIR at a persistent,
# git-ignored directory so Nuitka's downloads, compiled-object cache (ccache),
# frozen bytecode and DLL-dependency scans survive across builds. On CI we leave
# the platform default untouched so the actions/cache restore (e.g.
# ~/Library/Caches/Nuitka, ~/.cache/ccache) keeps working unchanged.
phlox_setup_nuitka_cache() {
  if [ -z "${CI:-}" ]; then
    mkdir -p "$PHLOX_CACHE_ROOT/nuitka"
    export NUITKA_CACHE_DIR="${NUITKA_CACHE_DIR:-$PHLOX_CACHE_ROOT/nuitka}"
    echo "✅ Nuitka cache directory: $NUITKA_CACHE_DIR"
  else
    echo "ℹ️  CI detected - using platform-default Nuitka/cache locations"
  fi

  local launcher
  launcher="$(phlox_find_compiler_cache)"
  if [ "$launcher" = "ccache" ]; then
    # Nuitka auto-detects ccache on PATH; pin the full path for non-standard
    # environments (documented NUITKA_CCACHE_BINARY hook).
    export NUITKA_CCACHE_BINARY="${NUITKA_CCACHE_BINARY:-$(command -v ccache 2>/dev/null)}"
    # Give the object cache a sensible ceiling so it cannot grow unbounded.
    ccache --max-size="${CCACHE_MAXSIZE:-5G}" >/dev/null 2>&1 || true
    echo "✅ Nuitka will use ccache: $NUITKA_CCACHE_BINARY"
  else
    echo "ℹ️  ccache not found - Nuitka repeat builds will be slower (install ccache)"
  fi
}

# Manage an incremental CMake build directory.
#
#   phlox_prepare_build_dir <build_dir> <signature>
#
# The <signature> is an opaque string describing the inputs that invalidate the
# build (pinned source SHA, backend flags, build type). The directory is reused
# verbatim when the signature matches (CMake/Ninja then only recompiles what
# changed) and wiped when the signature changes or when FORCE_CLEAN=1. A marker
# file inside the build dir stores the previous signature.
phlox_prepare_build_dir() {
  local build_dir="$1"
  local sig="$2"
  local sig_file="$build_dir/.phlox-build-sig"

  if [ "${FORCE_CLEAN:-0}" = "1" ]; then
    echo "🧹 FORCE_CLEAN=1 - wiping $build_dir"
    rm -rf "$build_dir"
  elif [ -d "$build_dir" ] && [ -f "$sig_file" ]; then
    local old_sig
    old_sig="$(cat "$sig_file" 2>/dev/null || true)"
    if [ "$old_sig" != "$sig" ]; then
      echo "🔄 Build configuration changed (source SHA / flags) - wiping stale $build_dir"
      rm -rf "$build_dir"
    else
      echo "♻️  Reusing incremental build directory (cached objects): $build_dir"
    fi
  elif [ -d "$build_dir" ]; then
    # Build dir exists but has no signature marker (created by an older script
    # or a partial run). Start clean once so we never mix configurations.
    echo "🧹 No build signature found - initializing fresh build directory"
    rm -rf "$build_dir"
  fi

  mkdir -p "$build_dir"
  echo "$sig" > "$sig_file"
}
