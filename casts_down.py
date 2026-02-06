#!/usr/bin/env python3
"""
Casts Down - 统一播客下载工具
自动识别 URL 类型并调用对应的下载器
"""

import sys
from urllib.parse import urlparse

import click


def detect_downloader(url: str) -> str:
    """
    根据 URL 检测应该使用哪个下载器

    返回: 'podcast' 或 'xiaoyuzhou'
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # 小宇宙
    if 'xiaoyuzhoufm.com' in domain:
        return 'xiaoyuzhou'

    # Apple Podcasts 或通用 RSS
    if 'podcasts.apple.com' in domain or url.endswith('.rss') or url.endswith('.xml'):
        return 'podcast'

    # 默认使用通用播客下载器（支持 RSS）
    return 'podcast'


def print_banner():
    """打印简洁横幅"""
    banner = "\n🎙️  Casts Down - Intelligent Podcast Downloader v1.0\n"
    click.echo(banner)


def print_disclaimer():
    """打印免责声明"""
    disclaimer = """
⚠️  DISCLAIMER: For educational purposes only. Respect copyrights.
    该项目仅用于学习，请遵守版权法律法规。
"""
    click.echo(disclaimer)


@click.command(context_settings=dict(
    ignore_unknown_options=True,
    allow_extra_args=True,
))
@click.argument('url')
@click.pass_context
def main(ctx, url: str):
    """
    Casts Down - 智能播客下载工具

    自动识别 URL 类型并使用对应的下载器：

    \b
    支持的平台:
    • Apple Podcasts (podcasts.apple.com)
    • 小宇宙 (xiaoyuzhoufm.com)
    • 通用 RSS 源

    \b
    示例:
    # Apple Podcasts - 下载单集
    casts-down "https://podcasts.apple.com/podcast/id123?i=456"

    \b
    # Apple Podcasts - 下载最新 3 集
    casts-down "https://podcasts.apple.com/podcast/id123" --latest 3

    \b
    # 小宇宙 - 下载单集
    casts-down "https://www.xiaoyuzhoufm.com/episode/xxx"

    \b
    # 小宇宙 - 下载播客
    casts-down "https://www.xiaoyuzhoufm.com/podcast/xxx"

    \b
    # RSS 源
    casts-down "https://feeds.example.com/podcast.rss" --all
    """

    # 打印横幅和免责声明
    print_banner()
    print_disclaimer()

    downloader_type = detect_downloader(url)

    click.echo(f"[*] Detected: ", nl=False)

    if downloader_type == 'xiaoyuzhou':
        click.echo("Xiaoyuzhou Podcast\n")
        from xiaoyuzhou_dl import main as xiaoyuzhou_main

        # 重新构建参数列表
        sys.argv = ['xiaoyuzhou-dl', url] + ctx.args

        try:
            xiaoyuzhou_main(standalone_mode=False)
        except SystemExit:
            pass

    else:  # podcast
        if 'podcasts.apple.com' in url:
            click.echo("Apple Podcasts\n")
        elif url.endswith(('.rss', '.xml')):
            click.echo("RSS Feed\n")
        else:
            click.echo("Podcast RSS Feed\n")

        from podcast_dl import main as podcast_main

        # 重新构建参数列表
        sys.argv = ['podcast-dl', url] + ctx.args

        try:
            podcast_main(standalone_mode=False)
        except SystemExit:
            pass


if __name__ == '__main__':
    main()
