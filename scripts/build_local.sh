#!/usr/bin/env bash
#
# scripts/build_local.sh — build, smoke-test and package the earcongen GUI
# binary the same way the Release workflow does, on this machine.
#
# The point is that a local build and a CI build are the same build. Every
# step here mirrors a step in .github/workflows/release.yml: the same preflight
# on the checkout, the same `pyinstaller packaging/earcongen.spec --noconfirm
# --clean`, the same `--cli version` smoke test, the same archive layout with
# the licence texts LGPLv3 4(b) requires, and the same SHA-256 file. If this
# passes and CI does not, the difference is the runner, not the tree — which is
# the whole reason to be able to run it here.
#
# Only the GUI is frozen. earcongen.py and earconcheck.py need numpy alone and
# are shipped as source inside the archive, so the command-line tools work
# without the binary and the binary is not the only way to use the project.
#
# PyInstaller does not cross-compile: this builds for the platform it runs on.
# Linux and macOS run it directly; on Windows use Git Bash or MSYS2.
#
# Usage:
#   scripts/build_local.sh                 build, test, package
#   scripts/build_local.sh --no-package    build and test only
#   scripts/build_local.sh --skip-tests    build and package, no smoke test
#   scripts/build_local.sh --dir           directory layout instead of onefile
#   scripts/build_local.sh --check         run the test suite first
#
# Local builds are not signed. Signing belongs to the release workflow, which
# holds the key; a signature made here would prove nothing about the artefacts
# that workflow publishes.
#
set -euo pipefail

# Resolved before the cd below, so --help still finds this file when the
# script is invoked by a relative path from somewhere else.
SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PACKAGE=1
RUN_TESTS=1
RUN_CHECKS=0
ONEDIR=0

while [ $# -gt 0 ]; do
  case "$1" in
    --no-package) PACKAGE=0; shift ;;
    --skip-tests) RUN_TESTS=0; shift ;;
    --check)      RUN_CHECKS=1; shift ;;
    --dir)        ONEDIR=1; PACKAGE=0; shift ;;
    -h|--help)    awk 'NR>1 && /^#/ { sub(/^#[[:space:]]?/, ""); print; next }
                       NR>1 { exit }' "$SELF"; exit 0 ;;
    *) echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
done

say()  { printf '\n\033[96m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# ── Platform ─────────────────────────────────────────────────────────────────
case "$(uname -s)" in
  Linux)                      OS=linux;   PLATFORM="linux-$(uname -m)" ;;
  Darwin)                     OS=macos
                              case "$(uname -m)" in
                                arm64) PLATFORM="macos-arm64" ;;
                                *)     PLATFORM="macos-x86_64" ;;
                              esac ;;
  MINGW*|MSYS*|CYGWIN*)       OS=windows; PLATFORM="windows-x86_64" ;;
  *) die "Unsupported platform: $(uname -s)" ;;
esac

VERSION="$(tr -d '[:space:]' < version)"
BINARY="EarconGen"
say "earcongen ${VERSION} — ${PLATFORM}"

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || PY=python
command -v "$PY" >/dev/null 2>&1 || die "No python3 on PATH. Set PYTHON=/path/to/python."
echo "python:      $("$PY" --version 2>&1)  ($(command -v "$PY"))"

# ── Preflight: the same paths the workflow's verify job checks ───────────────
# A file missing here fails in seconds with a clear message; without this the
# same problem surfaces as a build error several dependency installs later.
say "Preflight"
MISSING=0
for path in packaging/earcongen.spec packaging/build_common.py \
            packaging/entitlements.plist licenses THIRD-PARTY-NOTICES.md \
            requirements.txt requirements-gui.txt requirements-dev.txt \
            version earcongui.py earcongen.py earconcheck.py gui; do
  [ -e "$path" ] || { echo "  missing: $path"; MISSING=1; }
done
[ "$MISSING" -eq 0 ] || die "Checkout is incomplete. Check .gitignore is not excluding these."

# Untracked-but-required is the specific trap: the file is here, so the build
# works locally and fails in CI. Warn early rather than let CI find it.
if command -v git >/dev/null 2>&1 && git rev-parse --git-dir >/dev/null 2>&1; then
  for path in packaging/earcongen.spec packaging/build_common.py \
              packaging/entitlements.plist gui; do
    if git check-ignore -q "$path" 2>/dev/null; then
      warn "$path is git-ignored — it will be missing from a CI checkout."
    fi
  done
fi
echo "  all required paths present"

# ── Build tooling ────────────────────────────────────────────────────────────
"$PY" - <<'EOF' || die "Build dependencies missing. Run: pip install -r requirements-dev.txt"
import importlib.util, sys
missing = [m for m in ("PyInstaller", "PySide6", "numpy") if importlib.util.find_spec(m) is None]
if missing:
    print("  missing modules: " + ", ".join(missing), file=sys.stderr)
    sys.exit(1)
print("  build dependencies present")
EOF

# ── Optional test suite ──────────────────────────────────────────────────────
# Off by default because the build is the thing being asked for; --check runs
# it first for the case where this is the last step before tagging.
if [ "$RUN_CHECKS" -eq 1 ]; then
  say "Tests"
  QT_QPA_PLATFORM=offscreen "$PY" -m pytest -q tests || die "Tests failed."
fi

# ── Build ────────────────────────────────────────────────────────────────────
# Everything is rebuilt from scratch, so a stale archive or manifest from an
# earlier run cannot end up in this one's checksum file.
rm -rf build dist

say "Building ${BINARY}"
if [ "$ONEDIR" -eq 1 ]; then
  "$PY" -m PyInstaller packaging/earcongen.spec --noconfirm --clean -D
else
  "$PY" -m PyInstaller packaging/earcongen.spec --noconfirm --clean
fi

case "$OS" in
  windows) BIN="dist/${BINARY}.exe" ;;
  macos)   BIN="dist/${BINARY}"; APPBUNDLE="dist/${BINARY}.app" ;;
  *)       BIN="dist/${BINARY}" ;;
esac
[ -e "$BIN" ] || die "Build produced no $BIN — see the PyInstaller output above."
chmod +x "$BIN" 2>/dev/null || true
echo "  built: $BIN ($(du -h "$BIN" | cut -f1))"

# ── Smoke test ───────────────────────────────────────────────────────────────
# The binary is built windowed (console=False), so this is also the check
# that the --cli path still reaches stdout — the same thing the workflow's
# Windows step guards with its two capture attempts.
#
# --cli version never imports Qt, so unlike a GUI application this needs no
# display and no xvfb.
if [ "$RUN_TESTS" -eq 1 ] && [ "$ONEDIR" -eq 0 ]; then
  say "Smoke test"
  set +e
  OUTPUT="$("./$BIN" --cli version 2>&1)"; RC=$?
  set -e
  echo "  --- binary output (exit $RC) ---"
  printf '%s\n' "$OUTPUT" | sed 's/^/  /'
  echo "  --------------------------------"
  [ "$RC" -eq 0 ] || die "Binary exited with status $RC."

  ACTUAL="$(printf '%s\n' "$OUTPUT" | tail -n1 | tr -d '[:space:]')"
  [ -n "$ACTUAL" ] || die "No output from the binary. A windowed build cannot
write to stdout unless it attaches to the parent console — check
gui/win_console.py."
  [ "$ACTUAL" = "$VERSION" ] \
    || die "Version mismatch: binary reported '$ACTUAL', version says '$VERSION'."
  echo "  version OK: $ACTUAL"
fi

# ── Package ──────────────────────────────────────────────────────────────────
# Every archive carries the licence texts: LGPLv3 section 4(b) wants a copy to
# accompany the binary, and a link does not satisfy it. The command-line tools
# travel with it so the archive is the whole project, not just the window.
if [ "$PACKAGE" -eq 1 ]; then
  say "Packaging"
  STEM="${BINARY}-${VERSION}-${PLATFORM}"
  EXTRAS=(LICENSE THIRD-PARTY-NOTICES.md README.md USAGE.md CHANGELOG.md
          earcongen.py earconcheck.py licenses)

  case "$OS" in
    windows)
      if command -v 7z >/dev/null 2>&1; then
        7z a "dist/${STEM}.zip" "./dist/${BINARY}.exe" \
          "${EXTRAS[@]/#/./}" >/dev/null
      else
        "$PY" - "$STEM" "$BINARY" <<'EOF'
import sys, zipfile
from pathlib import Path
stem, binary = sys.argv[1], sys.argv[2]
extras = ["LICENSE", "THIRD-PARTY-NOTICES.md", "README.md", "USAGE.md",
          "CHANGELOG.md", "earcongen.py", "earconcheck.py"]
with zipfile.ZipFile(f"dist/{stem}.zip", "w", zipfile.ZIP_DEFLATED) as z:
    z.write(f"dist/{binary}.exe", f"{binary}.exe")
    for f in extras:
        z.write(f, f)
    for p in Path("licenses").rglob("*"):
        if p.is_file():
            z.write(p, str(p))
EOF
      fi
      ART="dist/${STEM}.zip" ;;
    macos)
      if [ -d "${APPBUNDLE:-}" ] && command -v ditto >/dev/null 2>&1; then
        ditto -c -k --keepParent "$APPBUNDLE" "dist/${STEM}.zip"
        ART="dist/${STEM}.zip"
      else
        tar -czf "dist/${STEM}.tar.gz" -C dist "$BINARY" -C .. "${EXTRAS[@]}"
        ART="dist/${STEM}.tar.gz"
      fi ;;
    *)
      tar -czf "dist/${STEM}.tar.gz" -C dist "$BINARY" -C .. "${EXTRAS[@]}"
      ART="dist/${STEM}.tar.gz" ;;
  esac
  echo "  packaged: $ART ($(du -h "$ART" | cut -f1))"

  # ── Checksum ───────────────────────────────────────────────────────────────
  # The unpackaged binary is called EarconGen with no version, so matching the
  # version in the stem picks out the archive alone. The manifest is excluded
  # so a re-run cannot hash the previous one into the new file.
  ( cd dist
    shopt -s nullglob
    ARCHIVES=()
    for f in "${BINARY}-${VERSION}"-*; do
      case "$f" in
        *.sha256) continue ;;
      esac
      ARCHIVES+=("$f")
    done
    shopt -u nullglob

    [ "${#ARCHIVES[@]}" -gt 0 ] || { echo "No archives to checksum in dist/." >&2; exit 1; }

    if command -v sha256sum >/dev/null 2>&1; then
      sha256sum "${ARCHIVES[@]}" > "earcongen-${VERSION}.sha256"
    else
      shasum -a 256 "${ARCHIVES[@]}" > "earcongen-${VERSION}.sha256"
    fi
    sed 's/^/  /' "earcongen-${VERSION}.sha256" )
fi

say "Done"
ls -la dist/
