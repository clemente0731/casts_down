"""Base classes for podcast downloading."""

import asyncio
from pathlib import Path
from typing import Callable

import aiohttp
import click
from tqdm import tqdm

from casts_down.downloaders.naming import build_media_filename, dedupe_filename


class PodcastEpisode:
    """播客剧集数据类"""
    def __init__(self, title: str, audio_url: str, published: str = ""):
        self.title = title
        self.audio_url = audio_url
        self.published = published

    def sanitize_filename(self, podcast_name: str) -> str:
        """生成安全、可读的媒体文件名。"""
        return build_media_filename(
            episode_title=self.title,
            audio_url=self.audio_url,
            podcast_name=podcast_name,
            default_ext=".mp3",
        )


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
        skip_existing: bool = False,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> tuple[bool, str]:
        """
        下载单个剧集（带资源清理和详细错误处理）
        返回: (是否成功, 消息)
        """
        async with self.semaphore:
            temp_path = None
            try:
                if output_path.exists() and skip_existing:
                    return True, f"跳过: {output_path.name}"

                async with session.get(episode.audio_url, timeout=aiohttp.ClientTimeout(total=3600)) as response:
                    response.raise_for_status()

                    total_size = int(response.headers.get('content-length', 0))
                    if total_size and progress_callback:
                        progress_callback(total_size, 0)

                    # 创建临时文件
                    temp_path = output_path.with_suffix(output_path.suffix + '.tmp')

                    with open(temp_path, 'wb') as f:
                        downloaded = 0
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback:
                                progress_callback(0, len(chunk))

                    # 下载完成后安全重命名
                    if output_path.exists():
                        output_path.unlink()  # 删除已存在的文件
                    temp_path.rename(output_path)
                    temp_path = None  # 标记已成功重命名

                    size_mb = output_path.stat().st_size / 1024 / 1024
                    return True, f"完成: {output_path.name} ({size_mb:.1f} MB)"

            except asyncio.TimeoutError:
                return False, f"超时: {episode.title}"
            except aiohttp.ClientError as e:
                error_type = type(e).__name__
                return False, f"网络错误({error_type}): {episode.title}"
            except (OSError, IOError) as e:
                return False, f"文件操作失败: {episode.title} - {str(e)}"
            except Exception as e:
                # 记录未预期的错误但不崩溃
                return False, f"未知错误: {episode.title} - {type(e).__name__}"
            finally:
                # 确保清理临时文件
                if temp_path and temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass  # 忽略清理失败

    async def download_all(
        self,
        episodes: list[PodcastEpisode],
        podcast_name: str,
        output_dir: Path,
        skip_existing: bool = False
    ) -> list[Path]:
        """批量下载剧集，返回已下载文件路径列表"""
        output_dir.mkdir(parents=True, exist_ok=True)
        downloaded_files: list[Path] = []

        async with aiohttp.ClientSession() as session:
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

            async def _indexed(idx: int, episode: PodcastEpisode, path: Path):
                result = await self.download_episode(
                    session, episode, path, skip_existing,
                    progress_callback=_report_byte_progress,
                )
                return idx, result

            try:
                futs = []
                used_names: set[str] = set()
                for i, episode in enumerate(episodes):
                    filename = dedupe_filename(episode.sanitize_filename(podcast_name), used_names)
                    used_names.add(filename)
                    output_path = output_dir / filename
                    path_map[i] = output_path
                    futs.append(asyncio.ensure_future(
                        _indexed(i, episode, output_path)
                    ))

                # 使用 tqdm 显示进度和 ETA
                results = []
                with tqdm(total=len(futs), desc="Download Episodes", unit="ep") as pbar:
                    for coro in asyncio.as_completed(futs):
                        idx, result = await coro
                        results.append((idx, result))
                        pbar.update(1)

                        # 实时显示结果
                        success, message = result
                        if success:
                            tqdm.write(f"[+] {message}")
                            downloaded_files.append(path_map[idx])
                        else:
                            tqdm.write(f"[-] {message}")
            finally:
                byte_pbar.close()

            # 统计结果
            success_count = sum(1 for _, (s, _) in results if s)
            click.echo(f"\nDownload complete: {success_count}/{len(results)} succeeded")

        return downloaded_files
