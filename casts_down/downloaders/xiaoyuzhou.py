"""Xiaoyuzhou (小宇宙) podcast downloader."""

import asyncio
import json
import re
from pathlib import Path
from typing import Callable

import aiohttp
import click
from tqdm import tqdm

from casts_down.downloaders.naming import build_media_filename, dedupe_filename


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
            raise ValueError("无法找到 __NEXT_DATA__ 脚本标签，页面结构可能已更改")

        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 解析失败，页面数据格式异常: {str(e)}")

        # 逐层检查，给出明确错误信息
        if not isinstance(data, dict):
            raise ValueError(f"页面数据格式异常，预期为字典但得到 {type(data).__name__}")

        if 'props' not in data:
            raise ValueError("页面数据缺少 'props' 字段")

        if 'pageProps' not in data['props']:
            raise ValueError("页面数据缺少 'pageProps' 字段")

        return data['props']['pageProps']

    async def get_episode_info(self, session: aiohttp.ClientSession, episode_url: str) -> dict:
        """获取单集信息"""
        async with session.get(episode_url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            response.raise_for_status()
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
        async with session.get(podcast_url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            response.raise_for_status()
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

            async with session.get(data_url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=30)) as data_response:
                data_response.raise_for_status()
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
        skip_existing: bool = False,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> tuple[bool, str]:
        """下载单个音频文件（带资源清理和详细错误处理）"""
        async with self.semaphore:
            temp_path = None
            try:
                if output_path.exists() and skip_existing:
                    return True, f"Skipped: {output_path.name}"

                async with session.get(audio_url, timeout=aiohttp.ClientTimeout(total=3600)) as response:
                    response.raise_for_status()
                    total_size = int(response.headers.get('content-length', 0))
                    if total_size and progress_callback:
                        progress_callback(total_size, 0)

                    temp_path = output_path.with_suffix(output_path.suffix + '.tmp')

                    with open(temp_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                            if progress_callback:
                                progress_callback(0, len(chunk))

                    # 安全重命名
                    if output_path.exists():
                        output_path.unlink()
                    temp_path.rename(output_path)
                    temp_path = None  # 标记已成功重命名

                    size_mb = output_path.stat().st_size / 1024 / 1024
                    return True, f"Completed: {output_path.name} ({size_mb:.1f} MB)"

            except asyncio.TimeoutError:
                return False, f"Timeout: {output_path.name}"
            except aiohttp.ClientError as e:
                error_type = type(e).__name__
                return False, f"Network error({error_type}): {output_path.name}"
            except (OSError, IOError) as e:
                return False, f"File error: {output_path.name} - {str(e)}"
            except Exception as e:
                return False, f"Unknown error: {output_path.name} - {type(e).__name__}"
            finally:
                # 确保清理临时文件
                if temp_path and temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass

    async def download_episode_by_url(
        self,
        episode_url: str,
        output_dir: Path,
        skip_existing: bool = False,
        on_file_done: Callable[[Path, dict, str], None] | None = None,
    ) -> list[Path]:
        """下载单个剧集（通过 URL），返回已下载文件路径列表"""
        downloaded_files: list[Path] = []
        async with aiohttp.ClientSession() as session:
            click.echo(f"[*] Fetching episode info...")

            episode_info = await self.get_episode_info(session, episode_url)

            click.echo(f"\nTitle: {episode_info['title']}")
            click.echo(f"Duration: {episode_info['duration']}s")
            click.echo(f"Audio: {episode_info['audio_url']}\n")

            output_dir.mkdir(parents=True, exist_ok=True)

            filename = build_media_filename(
                episode_title=episode_info['title'],
                audio_url=episode_info['audio_url'],
                default_ext=".m4a",
            )
            output_path = output_dir / filename

            click.echo("[*] Starting download...\n")

            byte_pbar = tqdm(
                total=0,
                desc="Download Bytes",
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                leave=True,
            )

            def _report_byte_progress(total_bytes: int, downloaded_bytes: int) -> None:
                if total_bytes:
                    byte_pbar.total = (byte_pbar.total or 0) + total_bytes
                    byte_pbar.refresh()
                if downloaded_bytes:
                    byte_pbar.update(downloaded_bytes)

            success, message = await self.download_audio(
                session,
                episode_info['audio_url'],
                output_path,
                skip_existing,
                progress_callback=_report_byte_progress,
            )
            byte_pbar.close()

            if success:
                click.echo(f"[+] {message}")
                downloaded_files.append(output_path)
                if on_file_done:
                    on_file_done(output_path, episode_info, message)
            else:
                click.echo(f"[-] {message}", err=True)
                raise RuntimeError(message)

        return downloaded_files

    async def download_podcast(
        self,
        podcast_url: str,
        output_dir: Path,
        skip_existing: bool = False,
        latest: int | None = None,
        on_file_done: Callable[[Path, dict, str], None] | None = None,
    ) -> list[Path]:
        """批量下载播客剧集，返回已下载文件路径列表"""
        downloaded_files: list[Path] = []
        async with aiohttp.ClientSession() as session:
            click.echo(f"[*] Fetching podcast info...")

            podcast_name, episodes = await self.get_podcast_episodes(session, podcast_url)

            if not episodes:
                raise ValueError("No episodes found")

            # 选择要下载的剧集
            if latest:
                episodes = episodes[:latest]

            click.echo(f"[*] Preparing to download {len(episodes)} episode(s)\n")

            output_dir.mkdir(parents=True, exist_ok=True)

            # 批量下载
            path_map: dict[int, Path] = {}

            byte_pbar = tqdm(
                total=0,
                desc="Download Bytes",
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                leave=True,
            )

            def _report_byte_progress(total_bytes: int, downloaded_bytes: int) -> None:
                if total_bytes:
                    byte_pbar.total = (byte_pbar.total or 0) + total_bytes
                    byte_pbar.refresh()
                if downloaded_bytes:
                    byte_pbar.update(downloaded_bytes)

            async def _indexed(idx: int, audio_url: str, path: Path):
                result = await self.download_audio(
                    session, audio_url, path, skip_existing,
                    progress_callback=_report_byte_progress,
                )
                return idx, result

            try:
                futs = []
                used_names: set[str] = set()
                for i, episode in enumerate(episodes):
                    filename = dedupe_filename(build_media_filename(
                        episode_title=episode['title'],
                        audio_url=episode['enclosure']['url'],
                        podcast_name=podcast_name,
                        default_ext=".m4a",
                    ), used_names)
                    used_names.add(filename)
                    output_path = output_dir / filename
                    path_map[i] = output_path
                    futs.append(asyncio.ensure_future(
                        _indexed(i, episode['enclosure']['url'], output_path)
                    ))

                # 显示进度和 ETA
                results = []
                with tqdm(total=len(futs), desc="Download Episodes", unit="ep") as pbar:
                    for coro in asyncio.as_completed(futs):
                        idx, result = await coro
                        results.append((idx, result))
                        pbar.update(1)

                        success, message = result
                        if success:
                            tqdm.write(f"[+] {message}")
                            output_path = path_map[idx]
                            downloaded_files.append(output_path)
                            if on_file_done:
                                on_file_done(output_path, episodes[idx], message)
                        else:
                            tqdm.write(f"[-] {message}")
            finally:
                byte_pbar.close()

            # 统计
            success_count = sum(1 for _, (s, _) in results if s)
            click.echo(f"\nDownload complete: {success_count}/{len(results)} succeeded")

        return downloaded_files
