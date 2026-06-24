"""Environment detection and transcription dependency installer."""
import platform
import subprocess
import sys
import click

def detect_platform() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        return "mac_arm64" if machine in {"arm64", "aarch64"} else "mac_intel"
    if system == "linux":
        return "linux"
    if system == "windows":
        return "windows"
    return "unknown"

def get_install_packages(plat: str, backend: str = "auto") -> list[str]:
    base = ["faster-whisper>=1.0.0,<2.0.0"]
    if backend == "faster-whisper":
        return base
    if backend == "mlx-whisper":
        return ["mlx-whisper>=0.4.0,<1.0.0"] + base
    # auto
    if plat == "mac_arm64":
        return ["mlx-whisper>=0.4.0,<1.0.0"] + base
    return base

def _pip_install(packages: list[str]) -> bool:
    cmd = [sys.executable, "-m", "pip", "install"] + packages
    click.echo(f"[*] Running: pip install {' '.join(packages)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        click.echo(f"[!] pip install failed:\n{result.stderr}", err=True)
        return False
    return True

def _predownload_model(model: str = "small") -> bool:
    click.echo(f"[*] Downloading model: {model}...")
    try:
        from faster_whisper import WhisperModel
        WhisperModel(model)
        click.echo(f"[+] Model '{model}' ready")
        return True
    except Exception as e:
        click.echo(f"[!] Model download failed: {e}", err=True)
        return False

def run_setup(model: str = "small", backend: str = "auto") -> None:
    click.echo("[*] Detecting environment...")
    plat = detect_platform()
    labels = {
        "mac_arm64": "macOS arm64 (Apple Silicon)",
        "mac_intel": "macOS x86_64 (Intel)",
        "linux": "Linux",
        "windows": "Windows",
        "unknown": "unknown platform",
    }
    click.echo(f"[*] Platform: {labels.get(plat, plat)}")
    packages = get_install_packages(plat, backend=backend)
    click.echo(f"[*] Installing: {', '.join(packages)}")
    click.confirm(
        "[?] Install the above packages via pip?",
        default=True,
        abort=True,
    )
    if not _pip_install(packages):
        if plat == "mac_arm64" and backend == "auto":
            click.echo("[*] Retrying with faster-whisper only...")
            if not _pip_install(["faster-whisper>=1.0.0,<2.0.0"]):
                click.echo("[!] Setup failed. Check error messages above.", err=True)
                sys.exit(1)
        else:
            click.echo("[!] Setup failed. Check error messages above.", err=True)
            sys.exit(1)
    _predownload_model(model)
    click.echo("[+] Setup complete!")
