# Build & Release Guide

## Prerequisites

- Python 3.10+
- pip
- (optional) make
- For PyPI publishing: `pip install build twine`

## Quick Start

### Using Makefile

```bash
# Install (editable)
make install

# Install with dev tools (pytest)
make dev

# Run tests
make test

# Build .pyz executable (<1 second)
make build

# Build wheel + sdist for PyPI
make dist

# Build and publish to PyPI
make publish

# Build and publish to TestPyPI (for testing)
make publish-test

# Full release (clean + build .pyz + wheel + sdist)
make release

# Clean build artifacts
make clean
```

### Using Python directly

```bash
# Install
pip install -e .

# Build .pyz executable
python build_exe.py

# Build wheel + sdist
python build_exe.py --mode pip

# Build and publish to PyPI
python build_exe.py --mode pip --publish

# Build and publish to TestPyPI
python build_exe.py --mode pip --publish --test-pypi

# Clean
python build_exe.py --clean
```

## Build Modes

### zipapp (.pyz) — Default

Bundles `casts_down/` into a single `.pyz` file using Python's `zipapp` (stdlib).

```bash
make build
# or
python build_exe.py
```

- Build time: **< 1 second**
- Output size: **~54 KB**
- Output: `release/casts-down-<os>-<arch>.pyz`
- Requires: Python 3.10+ and dependencies on target machine

```bash
# Run the built executable
./release/casts-down-macos-arm64.pyz --help
./release/casts-down-macos-arm64.pyz "https://feeds.example.com/podcast.rss"
```

### Wheel — For pip distribution

Builds a standard Python wheel for PyPI upload.

```bash
make wheel
# or
python build_exe.py --mode pip
```

- Requires: `pip install build`
- Output: `dist/casts_down-*.whl`

## Build Artifacts

```
release/
  casts-down-macos-arm64.pyz    # macOS Apple Silicon
  casts-down-macos-x64.pyz      # macOS Intel
  casts-down-linux-x64.pyz      # Linux x64
  casts-down-linux-arm64.pyz    # Linux ARM64
```

## Release Workflow

### Automated (GitHub Actions)

Push a version tag to trigger package build + GitHub Release:

```bash
# Update version in casts_down/__init__.py and pyproject.toml
# Then:
git tag vX.Y.Z
git push origin vX.Y.Z
```

GitHub Actions will:
1. Build the Python package
2. Check with `twine check`
3. Create a GitHub Release with artifacts

### Manual

```bash
# 1. Run tests
make test

# 2. Build
make build          # .pyz executable
make dist           # wheel + sdist for pip

# 3. Tag and push
git tag vX.Y.Z
git push origin vX.Y.Z
```

## Troubleshooting

### .pyz executable uses wrong Python

The .pyz shebang points to the Python that built it (`sys.executable`). If the target machine has a different Python path:

```bash
# Run explicitly with the correct Python
python3 release/casts-down-macos-arm64.pyz --help
```

### Missing dependencies when running .pyz

The .pyz only bundles the `casts_down` package, not its dependencies. Install them first:

```bash
pip install aiohttp beautifulsoup4 click feedparser tqdm faster-whisper
# Optional on macOS Apple Silicon:
pip install mlx-whisper
```

Transcription also requires `ffmpeg` to be available on `PATH`.

Or just install the package normally:

```bash
pip install casts_down
```
