#!/usr/bin/env python3
"""
跨平台打包脚本
支持 Windows、macOS、Linux 平台打包
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import click


def get_platform_info():
    """获取当前平台信息"""
    system = platform.system().lower()
    machine = platform.machine().lower()

    platform_map = {
        'darwin': 'macos',
        'linux': 'linux',
        'windows': 'windows'
    }

    arch_map = {
        'x86_64': 'x64',
        'amd64': 'x64',
        'arm64': 'arm64',
        'aarch64': 'arm64',
    }

    os_name = platform_map.get(system, system)
    arch = arch_map.get(machine, machine)

    return os_name, arch


def install_pyinstaller():
    """安装 PyInstaller"""
    click.echo("📦 检查 PyInstaller...")
    try:
        import PyInstaller
        click.echo(f"✓ PyInstaller 已安装 (版本 {PyInstaller.__version__})")
    except ImportError:
        click.echo("⚠️  PyInstaller 未安装，正在安装...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pyinstaller'])
        click.echo("✓ PyInstaller 安装完成")


def clean_build():
    """清理构建目录"""
    click.echo("🧹 清理旧的构建文件...")

    dirs_to_clean = ['build', 'dist']
    for dir_name in dirs_to_clean:
        dir_path = Path(dir_name)
        if dir_path.exists():
            shutil.rmtree(dir_path)
            click.echo(f"  ✓ 删除 {dir_name}/")

    click.echo("✓ 清理完成\n")


def build_executable():
    """使用 PyInstaller 构建可执行文件"""
    click.echo("🔨 开始构建可执行文件...\n")

    # 运行 PyInstaller
    cmd = [
        'pyinstaller',
        '--clean',
        'casts_down.spec'
    ]

    click.echo(f"执行命令: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, check=False)

    if result.returncode != 0:
        click.echo("\n❌ 构建失败", err=True)
        sys.exit(1)

    click.echo("\n✓ 构建完成")


def create_release_package():
    """创建发布包"""
    os_name, arch = get_platform_info()

    click.echo(f"\n📦 创建发布包 ({os_name}-{arch})...\n")

    # 检查构建产物
    dist_dir = Path('dist')
    if not dist_dir.exists():
        click.echo("❌ dist/ 目录不存在", err=True)
        sys.exit(1)

    # 查找可执行文件
    executable_name = 'casts-down'
    if os_name == 'windows':
        executable_name += '.exe'

    executable_path = dist_dir / executable_name

    if not executable_path.exists():
        click.echo(f"❌ 找不到可执行文件: {executable_path}", err=True)
        sys.exit(1)

    # 创建 release 目录
    release_dir = Path('release')
    release_dir.mkdir(exist_ok=True)

    # 复制可执行文件到 release 目录，带平台标识
    release_name = f'casts-down-{os_name}-{arch}'
    if os_name == 'windows':
        release_name += '.exe'

    release_path = release_dir / release_name
    shutil.copy2(executable_path, release_path)

    # 显示文件信息
    file_size = release_path.stat().st_size / (1024 * 1024)  # MB

    click.echo(f"✓ 可执行文件: {release_path}")
    click.echo(f"  大小: {file_size:.2f} MB")
    click.echo(f"  平台: {os_name}-{arch}")

    return release_path


@click.command()
@click.option('--clean', is_flag=True, help='仅清理构建目录')
@click.option('--no-clean', is_flag=True, help='构建前不清理')
def main(clean, no_clean):
    """
    Casts Down 打包工具

    \b
    打包当前平台的可执行文件:
      python build.py

    \b
    仅清理构建目录:
      python build.py --clean
    """

    click.echo("=" * 60)
    click.echo("  Casts Down - 跨平台打包工具")
    click.echo("=" * 60)
    click.echo()

    os_name, arch = get_platform_info()
    click.echo(f"📋 当前平台: {os_name}-{arch}")
    click.echo(f"🐍 Python 版本: {sys.version.split()[0]}")
    click.echo()

    # 仅清理模式
    if clean:
        clean_build()
        click.echo("✓ 完成")
        return

    # 安装 PyInstaller
    install_pyinstaller()

    # 清理旧文件
    if not no_clean:
        clean_build()

    # 构建可执行文件
    build_executable()

    # 创建发布包
    release_path = create_release_package()

    click.echo()
    click.echo("=" * 60)
    click.echo("✨ 打包完成！")
    click.echo("=" * 60)
    click.echo()
    click.echo(f"📦 发布文件: {release_path}")
    click.echo()
    click.echo("使用方法:")
    click.echo(f"  ./{release_path.name} <URL>")
    click.echo()


if __name__ == '__main__':
    main()
