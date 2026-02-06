#!/usr/bin/env python3
"""
Podcast Downloader CLI Tool
支持从 RSS 源和 Apple Podcasts 下载播客音频
"""

import asyncio
import re
import sys
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

import aiohttp
import click
import feedparser
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm


class PodcastEpisode:
    """播客剧集数据类"""
    def __init__(self, title: str, audio_url: str, published: str = ""):
        self.title = title
        self.audio_url = audio_url
        self.published = published

    def sanitize_filename(self, podcast_name: str) -> str:
        """生成安全的文件名"""
        # 移除非法字符
        safe_title = re.sub(r'[<>:"/\\|?*]', '', self.title)
        safe_podcast = re.sub(r'[<>:"/\\|?*]', '', podcast_name)

        # 限制长度
        safe_title = safe_title[:100]

        # 获取文件扩展名
        parsed = urlparse(self.audio_url)
        ext = Path(parsed.path).suffix or '.mp3'

        return f"{safe_podcast} - {safe_title}{ext}"


class RSSParser:
    """RSS 解析器"""

    @staticmethod
    def parse(rss_url: str, episode_title: Optional[str] = None) -> tuple[str, List[PodcastEpisode]]:
        """
        解析 RSS 源
        返回: (播客名称, 剧集列表)

        参数:
            rss_url: RSS 源地址
            episode_title: 可选的单集标题，如果提供则只返回匹配的剧集
        """
        try:
            feed = feedparser.parse(rss_url)

            if feed.bozo:  # 解析错误
                raise ValueError(f"RSS 解析失败: {feed.bozo_exception}")

            podcast_name = feed.feed.get('title', 'Unknown Podcast')
            episodes = []

            for entry in feed.entries:
                # 查找音频链接
                audio_url = None

                # 方式1: enclosures
                if hasattr(entry, 'enclosures') and entry.enclosures:
                    for enc in entry.enclosures:
                        if 'audio' in enc.get('type', ''):
                            audio_url = enc.get('href')
                            break

                # 方式2: links
                if not audio_url and hasattr(entry, 'links'):
                    for link in entry.links:
                        if link.get('type', '').startswith('audio'):
                            audio_url = link.get('href')
                            break

                if audio_url:
                    episode = PodcastEpisode(
                        title=entry.get('title', 'Untitled'),
                        audio_url=audio_url,
                        published=entry.get('published', '')
                    )

                    # 如果指定了单集标题，检查是否匹配
                    if episode_title:
                        # 清理标题进行模糊匹配
                        rss_title = episode.title.strip().lower()
                        target_title = episode_title.strip().lower()

                        # 移除播客名称（可能在 Apple Podcasts 标题中）
                        podcast_name_lower = podcast_name.lower()
                        target_title = target_title.replace(podcast_name_lower, '').strip()
                        target_title = target_title.lstrip(':：- ')

                        # 检查标题是否匹配（包含或被包含）
                        if target_title in rss_title or rss_title in target_title:
                            episodes = [episode]  # 只保留匹配的剧集
                            break
                    else:
                        episodes.append(episode)

            return podcast_name, episodes

        except Exception as e:
            raise ValueError(f"RSS 解析错误: {str(e)}")


class ApplePodcastsParser:
    """Apple Podcasts URL 处理器"""

    @staticmethod
    def extract_episode_id(apple_url: str) -> Optional[str]:
        """
        从 Apple Podcasts URL 提取单集 ID
        例如: ?i=1000747967318 -> 1000747967318
        """
        match = re.search(r'[?&]i=(\d+)', apple_url)
        return match.group(1) if match else None

    @staticmethod
    async def extract_metadata_async(session: aiohttp.ClientSession, apple_url: str) -> tuple[Optional[str], Optional[str]]:
        """
        异步一次性从 Apple Podcasts 页面提取 RSS URL 和标题
        返回: (rss_url, episode_title)

        性能优化：合并原来的 extract_episode_title() 和 extract_rss_url()，
        避免对同一 URL 发送多次请求
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            async with session.get(apple_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                response.raise_for_status()
                content = await response.text()
                soup = BeautifulSoup(content, 'html.parser')

                # 提取标题
                episode_title = None
                title_meta = soup.find('meta', {'property': 'og:title'})
                if title_meta and title_meta.get('content'):
                    episode_title = title_meta['content']
                elif title_tag := soup.find('title'):
                    episode_title = title_tag.text.strip()

                # 提取 RSS URL
                rss_url = None

                # 方式1: 查找 feed URL meta 标签
                feed_meta = soup.find('meta', {'property': 'og:audio'})
                if feed_meta and feed_meta.get('content'):
                    rss_url = feed_meta['content']

                # 方式2: 查找页面中的 RSS 链接
                if not rss_url:
                    rss_link = soup.find('a', href=re.compile(r'https?://.*\.rss'))
                    if rss_link:
                        rss_url = rss_link['href']

                # 方式3: 使用 iTunes API（仅在前两种方式失败时）
                if not rss_url:
                    podcast_id = re.search(r'/id(\d+)', apple_url)
                    if podcast_id:
                        api_url = f"https://itunes.apple.com/lookup?id={podcast_id.group(1)}&entity=podcast"
                        async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=10)) as api_response:
                            data = await api_response.json()
                            if data.get('resultCount', 0) > 0:
                                rss_url = data['results'][0].get('feedUrl')

                return rss_url, episode_title

        except Exception as e:
            return None, None

    @staticmethod
    def extract_episode_title(apple_url: str) -> Optional[str]:
        """
        从 Apple Podcasts 单集页面提取剧集标题

        已弃用：请使用 extract_metadata_async() 以获得更好的性能
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            response = requests.get(apple_url, headers=headers, timeout=10)
            response.raise_for_status()

            # 确保正确的编码
            response.encoding = response.apparent_encoding or 'utf-8'

            soup = BeautifulSoup(response.content, 'html.parser')

            # 方式1: 查找 og:title
            title_meta = soup.find('meta', {'property': 'og:title'})
            if title_meta and title_meta.get('content'):
                return title_meta['content']

            # 方式2: 查找页面标题
            title_tag = soup.find('title')
            if title_tag:
                return title_tag.text.strip()

            return None

        except Exception:
            return None

    @staticmethod
    def extract_rss_url(apple_url: str) -> str:
        """
        从 Apple Podcasts 页面提取 RSS URL
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            response = requests.get(apple_url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # 方式1: 查找 feed URL meta 标签
            feed_meta = soup.find('meta', {'property': 'og:audio'})
            if feed_meta and feed_meta.get('content'):
                return feed_meta['content']

            # 方式2: 查找页面中的 RSS 链接
            rss_link = soup.find('a', href=re.compile(r'https?://.*\.rss'))
            if rss_link:
                return rss_link['href']

            # 方式3: 使用 iTunes API
            podcast_id = re.search(r'/id(\d+)', apple_url)
            if podcast_id:
                api_url = f"https://itunes.apple.com/lookup?id={podcast_id.group(1)}&entity=podcast"
                api_response = requests.get(api_url, timeout=10)
                data = api_response.json()

                if data['resultCount'] > 0:
                    feed_url = data['results'][0].get('feedUrl')
                    if feed_url:
                        return feed_url

            raise ValueError("无法从 Apple Podcasts 页面提取 RSS URL")

        except requests.RequestException as e:
            raise ValueError(f"请求 Apple Podcasts 失败: {str(e)}")


class PodcastDownloader:
    """异步下载器"""

    def __init__(self, concurrent: int = 3):
        self.concurrent = concurrent
        self.semaphore = asyncio.Semaphore(concurrent)

    async def download_episode(
        self,
        session: aiohttp.ClientSession,
        episode: PodcastEpisode,
        output_path: Path,
        skip_existing: bool = False
    ) -> tuple[bool, str]:
        """
        下载单个剧集
        返回: (是否成功, 消息)
        """
        async with self.semaphore:
            try:
                if output_path.exists() and skip_existing:
                    return True, f"跳过: {output_path.name}"

                async with session.get(episode.audio_url, timeout=aiohttp.ClientTimeout(total=3600)) as response:
                    response.raise_for_status()

                    total_size = int(response.headers.get('content-length', 0))

                    # 创建临时文件
                    temp_path = output_path.with_suffix(output_path.suffix + '.tmp')

                    with open(temp_path, 'wb') as f:
                        downloaded = 0
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                            downloaded += len(chunk)

                    # 下载完成后重命名
                    temp_path.rename(output_path)

                    size_mb = output_path.stat().st_size / 1024 / 1024
                    return True, f"完成: {output_path.name} ({size_mb:.1f} MB)"

            except asyncio.TimeoutError:
                return False, f"超时: {episode.title}"
            except aiohttp.ClientError as e:
                return False, f"下载失败: {episode.title} - {str(e)}"
            except Exception as e:
                return False, f"错误: {episode.title} - {str(e)}"

    async def download_all(
        self,
        episodes: List[PodcastEpisode],
        podcast_name: str,
        output_dir: Path,
        skip_existing: bool = False
    ):
        """批量下载剧集"""
        output_dir.mkdir(parents=True, exist_ok=True)

        async with aiohttp.ClientSession() as session:
            tasks = []
            for episode in episodes:
                filename = episode.sanitize_filename(podcast_name)
                output_path = output_dir / filename

                task = self.download_episode(session, episode, output_path, skip_existing)
                tasks.append(task)

            # 使用 tqdm 显示进度
            results = []
            with tqdm(total=len(tasks), desc="下载进度", unit="集") as pbar:
                for coro in asyncio.as_completed(tasks):
                    result = await coro
                    results.append(result)
                    pbar.update(1)

                    # 实时显示结果
                    success, message = result
                    if success:
                        tqdm.write(f"[+] {message}")
                    else:
                        tqdm.write(f"[-] {message}")

            # 统计结果
            success_count = sum(1 for s, _ in results if s)
            click.echo(f"\nDownload complete: {success_count}/{len(results)} succeeded")


def print_banner():
    """打印 ASCII 横幅"""
    banner = r"""
   ____          _         ____
  / ___|__ _ ___| |_ ___  |  _ \  _____      ___ __
 | |   / _` / __| __/ __| | | | |/ _ \ \ /\ / / '_ \
 | |__| (_| \__ \ |_\__ \ | |_| | (_) \ V  V /| | | |
  \____\__,_|___/\__|___/ |____/ \___/ \_/\_/ |_| |_|

          Podcast Downloader (Apple Podcasts/RSS)
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
@click.option('--all', '-a', is_flag=True, help='下载所有剧集')
@click.option('--latest', '-l', type=int, default=1, help='下载最新 N 集（默认 1）')
@click.option('--output', '-o', type=click.Path(), default='./podcasts', help='输出目录')
@click.option('--concurrent', '-c', type=int, default=3, help='并发下载数（默认 3）')
@click.option('--skip-existing', '-s', is_flag=True, help='跳过已存在的文件')
def main(url: str, all: bool, latest: int, output: str, concurrent: int, skip_existing: bool):
    """
    播客下载工具

    示例:

    \b
    # 下载最新一集
    podcast-dl "https://feeds.example.com/podcast.rss"

    \b
    # 下载所有剧集
    podcast-dl "https://feeds.example.com/podcast.rss" --all

    \b
    # 从 Apple Podcasts 下载播客
    podcast-dl "https://podcasts.apple.com/us/podcast/xxx/id123456789"

    \b
    # 从 Apple Podcasts 下载特定单集
    podcast-dl "https://podcasts.apple.com/us/podcast/xxx/id123456789?i=1000123456"
    """
    try:
        # 打印横幅和免责声明（已移至 casts_down.py 统一入口）
        # print_banner()
        # print_disclaimer()

        click.echo(f"[*] Parsing: {url}\n")

        # 判断 URL 类型和提取单集信息
        rss_url = url
        episode_title = None
        is_single_episode = False

        if 'podcasts.apple.com' in url:
            click.echo("[*] Detected Apple Podcasts URL, extracting info...")

            # 检查是否为单集链接
            episode_id = ApplePodcastsParser.extract_episode_id(url)
            if episode_id:
                is_single_episode = True
                click.echo(f"[*] Detected episode link")

            # 性能优化：一次请求同时获取 RSS URL 和标题
            async def fetch_metadata():
                async with aiohttp.ClientSession() as session:
                    return await ApplePodcastsParser.extract_metadata_async(session, url)

            rss_url, episode_title = asyncio.run(fetch_metadata())

            if not rss_url:
                click.echo("[!] Failed to extract RSS URL from Apple Podcasts", err=True)
                sys.exit(1)

            if episode_title:
                click.echo(f"[*] Episode title: {episode_title}")

            click.echo(f"[+] RSS URL: {rss_url}\n")

        # 解析 RSS
        podcast_name, episodes = RSSParser.parse(rss_url, episode_title=episode_title)

        if not episodes:
            click.echo("[!] No episodes found", err=True)
            sys.exit(1)

        # 如果是单集链接且找到了匹配的剧集
        if is_single_episode and len(episodes) == 1:
            click.echo(f"[*] Podcast: {podcast_name}")
            click.echo(f"[+] Found matching episode: {episodes[0].title}\n")
            selected_episodes = episodes
        else:
            # 播客链接的正常逻辑
            if is_single_episode:
                click.echo(f"[!] Could not match episode ID, will download latest episode\n")

            click.echo(f"[*] Podcast: {podcast_name}")
            click.echo(f"[*] Total episodes: {len(episodes)}\n")

            # 选择要下载的剧集
            if all:
                selected_episodes = episodes
            else:
                selected_episodes = episodes[:latest]

        click.echo(f"[*] Preparing to download {len(selected_episodes)} episode(s)\n")

        # 下载
        output_dir = Path(output)
        downloader = PodcastDownloader(concurrent=concurrent)

        asyncio.run(downloader.download_all(
            selected_episodes,
            podcast_name,
            output_dir,
            skip_existing
        ))

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
