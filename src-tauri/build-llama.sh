#!/bin/bash
# Build script for llama.cpp server
# This script compiles the llama.cpp HTTP server as a standalone binary
#
# Use --debug to copy binaries to target/debug/ for development (tauri dev)

set -e

# Parse arguments
DEBUG_MODE=false
for arg in "$@"; do
    case $arg in
        --debug)
            DEBUG_MODE=true
            shift
            ;;
    esac
done

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LLAMA_DIR="$SCRIPT_DIR/llama.cpp"

# Shared build helpers (compiler cache + incremental build-dir management)
source "$SCRIPT_DIR/build-common.sh"

echo "Building llama.cpp server from: $LLAMA_DIR"

if [ "$DEBUG_MODE" = true ]; then
    echo "Mode: DEBUG (for tauri dev)"
else
    echo "Mode: RELEASE (for production)"
fi

LLAMA_PINNED_SHA="aa46bda89b9a8378ae76bb15fc2ce2f571f0983c"

if [ ! -d "$LLAMA_DIR" ]; then
  echo "llama.cpp not found. Cloning at pinned SHA $LLAMA_PINNED_SHA..."
  git clone https://github.com/ggml-org/llama.cpp.git "$LLAMA_DIR"
  cd "$LLAMA_DIR"
  git checkout "$LLAMA_PINNED_SHA"
  cd "$SCRIPT_DIR"
  echo "✅ llama.cpp cloned at pinned SHA"
elif [ -d "$LLAMA_DIR/.git" ]; then
  # Verify the existing checkout matches the pinned SHA; warn (don't fail) if not.
  CURRENT_SHA="$(cd "$LLAMA_DIR" && git rev-parse HEAD 2>/dev/null)"
  if [ -n "$CURRENT_SHA" ] && [ "$CURRENT_SHA" != "$LLAMA_PINNED_SHA" ]; then
    echo "⚠️  llama.cpp is at $CURRENT_SHA, expected $LLAMA_PINNED_SHA"
    echo "   To pin: cd src-tauri/llama.cpp && git checkout $LLAMA_PINNED_SHA"
  fi
fi

# Detect platform-specific build settings
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS: Metal + Accelerate
    CMAKE_BACKEND_FLAGS=(
        -DLLAMA_METAL=ON
        -DLLAMA_ACCELERATE=ON
    )
    BACKEND_DESC="Metal"
else
    # Linux local dev: CPU-only.
    # Production Flatpak build re-enables Vulkan via CMake flags
    CMAKE_BACKEND_FLAGS=(
        -DGGML_NATIVE=OFF
    )
    BACKEND_DESC="CPU"
fi

JOBS="$(phlox_jobs_count)"

# Route compilation through ccache/sccache when available (no-op otherwise).
phlox_collect_cmake_launcher
# Use Ninja when installed (faster, parallel incremental builds); else Makefiles.
phlox_collect_cmake_generator

# Reuse the incremental CMake build dir; only wipe it when the pinned source
# SHA, the generator, or the backend flags change (or FORCE_CLEAN=1). CMake/Make
# still track source mtimes, so a manual `git checkout` of llama.cpp triggers
# recompilation.
LLAMA_BUILD_SIG="llama:${LLAMA_PINNED_SHA}:$(phlox_cmake_generator_tag):${BACKEND_DESC}:Release"
phlox_prepare_build_dir "$LLAMA_DIR/build" "$LLAMA_BUILD_SIG"

cd "$LLAMA_DIR/build"

echo "Configuring llama.cpp build with $BACKEND_DESC support (static libs)..."
cmake .. \
  "${CMAKE_GENERATOR_ARGS[@]}" \
  -DCMAKE_BUILD_TYPE=Release \
  "${CMAKE_LAUNCHER_ARGS[@]}" \
  "${CMAKE_BACKEND_FLAGS[@]}" \
  -DLLAMA_ALL_WARNINGS=OFF \
  -DGGML_CCACHE=ON \
  -DBUILD_SHARED_LIBS=OFF \
  -DLLAMA_CURL=OFF \
  -DLLAMA_OPENSSL=OFF \
  -DLLAMA_BUILD_SERVER=ON \
  -DLLAMA_BUILD_UI=OFF \
  -DLLAMA_BUILD_APP=OFF \
  -DLLAMA_BUILD_EXAMPLES=OFF \
  -DLLAMA_BUILD_TESTS=OFF

# Build the llama-server binary (incremental - only recompiles changed sources)
echo "Building llama-server binary..."
cmake --build . --target llama-server -j"$JOBS"

echo "Fixing rpath in llama-server..."
if [ -f "bin/llama-server" ]; then
    cp bin/llama-server "$SCRIPT_DIR/phlox-llama-server"
    chmod +x "$SCRIPT_DIR/phlox-llama-server"

    if [[ "$OSTYPE" == "darwin"* ]]; then
        install_name_tool -delete_rpath "$LLAMA_DIR/build/src" "$SCRIPT_DIR/phlox-llama-server" 2>/dev/null || true
        install_name_tool -delete_rpath "$LLAMA_DIR/build/ggml" "$SCRIPT_DIR/phlox-llama-server" 2>/dev/null || true
        echo "phlox-llama-server binary built successfully at: $SCRIPT_DIR/phlox-llama-server"
        echo "Checking for remaining rpath entries:"
        otool -L "$SCRIPT_DIR/phlox-llama-server" | grep "@rpath" || echo "✓ No problematic rpath entries"

        if otool -L "$SCRIPT_DIR/phlox-llama-server" | grep -q "/opt/homebrew\|/usr/local/opt"; then
            echo "❌ ERROR: Binary contains Homebrew dependencies!"
            otool -L "$SCRIPT_DIR/phlox-llama-server" | grep "/opt/homebrew\|/usr/local/opt"
            exit 1
        fi
        echo "✓ No Homebrew dependencies found"
    else
        patchelf --remove-rpath "$SCRIPT_DIR/phlox-llama-server" 2>/dev/null || true
        echo "phlox-llama-server binary built successfully at: $SCRIPT_DIR/phlox-llama-server"
        echo "Linked libraries:"
        ldd "$SCRIPT_DIR/phlox-llama-server" || echo "(static build, no dynamic libs)"

        if ldd "$SCRIPT_DIR/phlox-llama-server" 2>/dev/null | grep -qE "/usr/local/|/opt/"; then
            echo "❌ ERROR: Binary links against non-system paths (would break AppImage portability)!"
            ldd "$SCRIPT_DIR/phlox-llama-server" | grep -E "/usr/local/|/opt/"
            exit 1
        fi
        echo "✓ No non-system library dependencies"
    fi
else
    echo "Error: llama-server binary not found after build"
    echo "Looking in: $(pwd)"
    echo "Contents of bin/:"
    ls -la bin/ || echo "bin/ directory not found"
    exit 1
fi

# Sign binary if on macOS with signing identity (release builds only)
if [[ "$OSTYPE" == "darwin"* ]] && [ "$DEBUG_MODE" != true ]; then
    # Support both APPLE_SIGNING_IDENTITY (Tauri convention) and SIGNING_IDENTITY
    SIGNING_IDENTITY="${APPLE_SIGNING_IDENTITY:-${SIGNING_IDENTITY:-$(security find-identity -v -p codesigning 2>/dev/null | grep "Developer ID Application" | head -1 | sed 's/.*"\(.*\)".*/\1/')}}"

    if [ -n "$SIGNING_IDENTITY" ]; then
        echo "Signing phlox-llama-server with: $SIGNING_IDENTITY"
        codesign --force --options runtime --timestamp \
            --sign "$SIGNING_IDENTITY" \
            "$SCRIPT_DIR/phlox-llama-server"
        echo "✅ phlox-llama-server signed"
    fi
fi

# In debug mode, also copy to target/debug for dev mode (tauri dev)
if [ "$DEBUG_MODE" = true ]; then
    echo "Copying to target/debug for development..."
    mkdir -p "$SCRIPT_DIR/target/debug"
    cp "$SCRIPT_DIR/phlox-llama-server" "$SCRIPT_DIR/target/debug/phlox-llama-server"
    chmod +x "$SCRIPT_DIR/target/debug/phlox-llama-server"
    echo "✅ Copied to target/debug/phlox-llama-server"
fi
