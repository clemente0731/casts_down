#!/usr/bin/env python3
"""
小宇宙播客下载器
支持单集和批量下载（前15集）
"""

import asyncio
import json
import re
import sys
from pathlib import Path

import aiohttp
import click
from tqdm import tqdm


class XiaoyuzhouDownloader:
    """小宇宙下载器"""

    def __init__(self, concurrent: int = 3):
        self.concurrent = concurrent
        self.semaphore = asyncio.Semaphore(concurrent)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

    def extract_episode_data(self, html: str) -> dict:
        """从页面HTML提取剧集数据"""
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
            html,
            re.DOTALL
        )
        if not match:
            raise ValueError("无法找到 __NEXT_DATA__ 数据")

        data = json.loads(match.group(1))
        return data['props']['pageProps']

    async def get_episode_info(self, session: aiohttp.ClientSession, episode_url: str) -> dict:
        """获取单集信息"""
        async with session.get(episode_url, headers=self.headers) as response:
            html = await response.text()
            page_props = self.extract_episode_data(html)

            episode = page_props.get('episode')
            if not episode:
                raise ValueError("无法提取剧集信息")

            return {
                'eid': episode['eid'],
                'title': episode['title'],
                'audio_url': episode['enclosure']['url'],
                'duration': episode.get('duration', 0),
                'description': episode.get('description', ''),
                'pubDate': episode.get('pubDate', ''),
            }

    async def get_podcast_episodes(self, session: aiohttp.ClientSession, podcast_url: str) -> tuple[str, list]:
        """
        获取播客的剧集列表
        注意：目前只能获取前15集，完整列表需要额外逆向
        """
        async with session.get(podcast_url, headers=self.headers) as response:
            html = await response.text()

            # 提取 buildId
            build_id_match = re.search(r'"buildId":"([^"]+)"', html)
            if not build_id_match:
                raise ValueError("无法找到 buildId")

            build_id = build_id_match.group(1)

            # 提取 podcast ID
            podcast_id = podcast_url.rstrip('/').split('/')[-1]

            # 请求 Next.js 数据端点
            data_url = f"https://www.xiaoyuzhoufm.com/_next/data/{build_id}/podcast/{podcast_id}.json"

            async with session.get(data_url, headers=self.headers) as data_response:
                data = await data_response.json()

                podcast = data['pageProps']['podcast']
                episodes = podcast.get('episodes', [])

                podcast_name = podcast['title']
                episode_count = podcast['episodeCount']

                click.echo(f"\n[*] Podcast: {podcast_name}")
                click.echo(f"[*] Total episodes: {episode_count}")
                click.echo(f"[!] Currently available: {len(episodes)}/{episode_count}")

                if len(episodes) < episode_count:
                    click.echo(f"[!] Note: Due to Xiaoyuzhou limitations, only first {len(episodes)} episodes available")
                    click.echo(f"         Full download requires additional reverse engineering\n")

                return podcast_name, episodes

    async def download_audio(
        self,
        session: aiohttp.ClientSession,
        audio_url: str,
        output_path: Path,
        skip_existing: bool = False
    ) -> tuple[bool, str]:
        """下载单个音频文件"""
        async with self.semaphore:
            try:
                if output_path.exists() and skip_existing:
                    return True, f"Skipped: {output_path.name}"

                async with session.get(audio_url, timeout=aiohttp.ClientTimeout(total=3600)) as response:
                    response.raise_for_status()

                    temp_path = output_path.with_suffix(output_path.suffix + '.tmp')

                    with open(temp_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)

                    temp_path.rename(output_path)

                    size_mb = output_path.stat().st_size / 1024 / 1024
                    return True, f"Completed: {output_path.name} ({size_mb:.1f} MB)"

            except Exception as e:
                return False, f"Failed: {output_path.name} - {str(e)}"

    async def download_episode_by_url(self, episode_url: str, output_dir: Path, skip_existing: bool = False):
        """下载单个剧集（通过 URL）"""
        async with aiohttp.ClientSession() as session:
            click.echo(f"[*] Fetching episode info...")

            episode_info = await self.get_episode_info(session, episode_url)

            click.echo(f"\nTitle: {episode_info['title']}")
            click.echo(f"Duration: {episode_info['duration']}s")
            click.echo(f"Audio: {episode_info['audio_url']}\n")

            output_dir.mkdir(parents=True, exist_ok=True)

            # 清理文件名
            safe_title = re.sub(r'[<>:"/\\|?*]', '', episode_info['title'])
            filename = f"{safe_title}.m4a"
            output_path = output_dir / filename

            click.echo("[*] Starting download...\n")

            success, message = await self.download_audio(
                session,
                episode_info['audio_url'],
                output_path,
                skip_existing
            )

            if success:
                click.echo(f"[+] {message}")
            else:
                click.echo(f"[-] {message}", err=True)
                sys.exit(1)

    async def download_podcast(
        self,
        podcast_url: str,
        output_dir: Path,
        skip_existing: bool = False,
        latest: int = None
    ):
        """批量下载播客剧集"""
        async with aiohttp.ClientSession() as session:
            click.echo(f"[*] Fetching podcast info...")

            podcast_name, episodes = await self.get_podcast_episodes(session, podcast_url)

            if not episodes:
                click.echo("[!] No episodes found", err=True)
                sys.exit(1)

            # 选择要下载的剧集
            if latest:
                episodes = episodes[:latest]

            click.echo(f"[*] Preparing to download {len(episodes)} episode(s)\n")

            output_dir.mkdir(parents=True, exist_ok=True)

            # 批量下载
            tasks = []
            for episode in episodes:
                safe_title = re.sub(r'[<>:"/\\|?*]', '', episode['title'])
                filename = f"{podcast_name} - {safe_title}.m4a"
                output_path = output_dir / filename

                task = self.download_audio(
                    session,
                    episode['enclosure']['url'],
                    output_path,
                    skip_existing
                )
                tasks.append(task)

            # 显示进度
            results = []
            with tqdm(total=len(tasks), desc="Download Progress", unit="ep") as pbar:
                for coro in asyncio.as_completed(tasks):
                    result = await coro
                    results.append(result)
                    pbar.update(1)

                    success, message = result
                    if success:
                        tqdm.write(f"[+] {message}")
                    else:
                        tqdm.write(f"[-] {message}")

            # 统计
            success_count = sum(1 for s, _ in results if s)
            click.echo(f"\nDownload complete: {success_count}/{len(results)} succeeded")


def print_banner():
    """打印 ASCII 横幅"""
    banner = r"""
__  __(_) __ _  ___  _   _ _   _ ______ __   _  ___  _   _
\ \/ /| |/ _` |/ _ \| | | | | | |_  / _` \ | | |/ _ \| | | |
 \  / | | (_| | (_) | |_| | |_| |/ / (_| |\ \_/ / (_) | |_| |
 /\_\ |_|\__,_|\___/ \__, |\__,_/___\__, | \___/ \___/ \__,_|
                     |___/           __/ |
                                    |___/
                Xiaoyuzhou Podcast Downloader
"""
    click.echo(banner)


def print_disclaimer():
    """打印免责声明"""
    disclaimer = """
+================================================================+
|                      [!] DISCLAIMER                            |
+================================================================+
|                                                                |
| This project is for EDUCATIONAL purposes ONLY.                 |
| Any destructive or commercial infringement is PROHIBITED.      |
|                                                                |
| 该项目仅用于学习端到端项目开发使用                                  |
| 严禁用于任何破坏或者商业侵害活动                                    |
|                                                                |
| By using this tool, you agree to:                              |
| - Use for personal learning and research only                  |
| - Comply with laws and platform terms of service               |
| - Respect content creators' copyrights                         |
|                                                                |
+================================================================+
"""
    click.echo(disclaimer)


@click.command()
@click.argument('url')
@click.option('--output', '-o', type=click.Path(), default='./xiaoyuzhou_downloads', help='输出目录')
@click.option('--concurrent', '-c', type=int, default=3, help='并发下载数')
@click.option('--skip-existing', '-s', is_flag=True, help='跳过已存在的文件')
@click.option('--latest', '-l', type=int, help='仅下载最新 N 集（仅播客链接）')
def main(url: str, output: str, concurrent: int, skip_existing: bool, latest: int):
    """
    小宇宙播客下载器

    \b
    支持两种链接：
    1. 单集链接：https://www.xiaoyuzhoufm.com/episode/{eid}
    2. 播客链接：https://www.xiaoyuzhoufm.com/podcast/{pid}

    \b
    示例：
    # 下载单集
    xiaoyuzhou-dl "https://www.xiaoyuzhoufm.com/episode/6850d2ed4abe6e29cb814160"

    \b
    # 下载播客的所有可获取剧集（前15集）
    xiaoyuzhou-dl "https://www.xiaoyuzhoufm.com/podcast/6388760f22567e8ea6ad070f"

    \b
    # 仅下载最新3集
    xiaoyuzhou-dl "https://www.xiaoyuzhoufm.com/podcast/6388760f22567e8ea6ad070f" --latest 3

    \b
    [!] Limitations:
    Due to Xiaoyuzhou technical limitations, podcast links can only fetch first 15 episodes.
    To download full podcast, consider:
    1. Run multiple times to get more episodes (if platform supports pagination)
    2. Wait for complete list API reverse engineering
    3. Use episode links to download one by one
    """
    try:
        # 打印横幅和免责声明
        print_banner()
        print_disclaimer()
        downloader = XiaoyuzhouDownloader(concurrent=concurrent)
        output_dir = Path(output)

        # 判断链接类型
        if '/episode/' in url:
            # 单集下载
            asyncio.run(downloader.download_episode_by_url(url, output_dir, skip_existing))
        elif '/podcast/' in url:
            # 播客批量下载
            asyncio.run(downloader.download_podcast(url, output_dir, skip_existing, latest))
        else:
            click.echo("[!] Unrecognized URL format", err=True)
            click.echo("Supported formats:", err=True)
            click.echo("  - https://www.xiaoyuzhoufm.com/episode/{eid}", err=True)
            click.echo("  - https://www.xiaoyuzhoufm.com/podcast/{pid}", err=True)
            sys.exit(1)

    except ValueError as e:
        click.echo(f"[!] Error: {str(e)}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\n\n[!] Download interrupted by user", err=True)
        sys.exit(130)
    except Exception as e:
        click.echo(f"[!] Unexpected error: {str(e)}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
