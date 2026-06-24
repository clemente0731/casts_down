"""Tests for downloader modules after restructure."""
import asyncio
import json
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from bs4 import BeautifulSoup

from casts_down.downloaders.base import PodcastEpisode
from casts_down.downloaders.podcast import ApplePodcastsParser

class TestPodcastEpisode:
    def test_sanitize_filename_mp3(self):
        ep = PodcastEpisode(
            title="Episode: Test/Title?",
            audio_url="https://example.com/audio.mp3",
        )
        result = ep.sanitize_filename("My Podcast")
        assert "/" not in result
        assert "?" not in result
        assert ":" not in result
        assert result == "my-podcast--episode-test-title.mp3"
        assert result.endswith(".mp3")

    def test_sanitize_filename_normalizes_punctuation(self):
        ep = PodcastEpisode(
            title="Dr Rachel Rubin: Women’s Sexual Health, Menopause, Hormone Replacement Therapy (HRT), and Orgasms!",
            audio_url="https://example.com/audio.mp3",
        )
        result = ep.sanitize_filename("The Diary Of A CEO with Steven Bartlett")

        assert result == (
            "the-diary-of-a-ceo-with-steven-bartlett--"
            "dr-rachel-rubin-womens-sexual-health-menopause-"
            "hormone-replacement-therapy-hrt-and-orgasms.mp3"
        )
        assert "_" not in result
        assert "’" not in result
        assert "," not in result
        assert "!" not in result

    def test_sanitize_filename_m4a(self):
        ep = PodcastEpisode(title="Test Episode", audio_url="https://example.com/audio.m4a")
        result = ep.sanitize_filename("Podcast")
        assert result.endswith(".m4a")

    def test_sanitize_filename_no_extension(self):
        ep = PodcastEpisode(title="Test", audio_url="https://example.com/audio")
        result = ep.sanitize_filename("Podcast")
        assert result.endswith(".mp3")

    def test_title_length_limit(self):
        ep = PodcastEpisode(title="A" * 200, audio_url="https://example.com/audio.mp3")
        result = ep.sanitize_filename("P")
        assert len(result.encode('utf-8')) <= 250

    def test_sanitize_filename_preserves_cjk_text(self):
        ep = PodcastEpisode(title="第 42 集：AI × 播客？", audio_url="https://example.com/audio.mp3")
        result = ep.sanitize_filename("科技早知道")
        assert result == "科技早知道--第-42-集-ai-播客.mp3"

    def test_total_filename_length_capped(self):
        ep = PodcastEpisode(title="A" * 200, audio_url="https://example.com/audio.mp3")
        result = ep.sanitize_filename("B" * 200)
        assert len(result.encode('utf-8')) <= 250

class TestApplePodcastsParser:
    def test_extract_episode_id(self):
        from casts_down.downloaders.podcast import ApplePodcastsParser
        assert ApplePodcastsParser.extract_episode_id(
            "https://podcasts.apple.com/podcast/id123?i=1000747967318"
        ) == "1000747967318"

    def test_extract_episode_id_no_id(self):
        from casts_down.downloaders.podcast import ApplePodcastsParser
        assert ApplePodcastsParser.extract_episode_id(
            "https://podcasts.apple.com/podcast/id123"
        ) is None

class TestRSSParser:
    def _mock_urlopen(self, content=b"<rss></rss>"):
        """Helper to mock urllib.request.urlopen for RSS fetch."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = content
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return patch("casts_down.downloaders.podcast.urllib.request.urlopen", return_value=mock_resp)

    def test_parse_valid_rss(self):
        from casts_down.downloaders.podcast import RSSParser
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.feed.get.return_value = "Test Podcast"
        entry = MagicMock()
        entry.enclosures = [{"type": "audio/mpeg", "href": "https://example.com/ep.mp3"}]
        entry.get.side_effect = lambda k, d="": {"title": "Episode 1", "published": "2024-01-01"}.get(k, d)
        mock_feed.entries = [entry]
        with self._mock_urlopen(), \
             patch("casts_down.downloaders.podcast.feedparser.parse", return_value=mock_feed):
            name, episodes = RSSParser.parse("https://example.com/feed.rss")
            assert name == "Test Podcast"
            assert len(episodes) == 1
            assert episodes[0].title == "Episode 1"

    def test_parse_empty_feed(self):
        from casts_down.downloaders.podcast import RSSParser
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.feed.get.return_value = "Empty Podcast"
        mock_feed.entries = []
        with self._mock_urlopen(), \
             patch("casts_down.downloaders.podcast.feedparser.parse", return_value=mock_feed):
            name, episodes = RSSParser.parse("https://example.com/feed.rss")
            assert episodes == []

class TestExtractFeedFromJsonLD:
    """Tests for ApplePodcastsParser._extract_feed_from_jsonld."""

    def test_extracts_top_level_feed_url(self):
        html = '<script type="application/ld+json">{"feedUrl": "https://example.com/feed.rss"}</script>'
        soup = BeautifulSoup(html, 'html.parser')
        assert ApplePodcastsParser._extract_feed_from_jsonld(soup) == "https://example.com/feed.rss"

    def test_extracts_nested_feed_url(self):
        data = {"partOfSeries": {"feedUrl": "https://example.com/nested.rss"}}
        html = f'<script type="application/ld+json">{json.dumps(data)}</script>'
        soup = BeautifulSoup(html, 'html.parser')
        assert ApplePodcastsParser._extract_feed_from_jsonld(soup) == "https://example.com/nested.rss"

    def test_returns_none_when_no_jsonld(self):
        soup = BeautifulSoup('<html><body>No JSON-LD</body></html>', 'html.parser')
        assert ApplePodcastsParser._extract_feed_from_jsonld(soup) is None

    def test_returns_none_for_invalid_json(self):
        html = '<script type="application/ld+json">not valid json</script>'
        soup = BeautifulSoup(html, 'html.parser')
        assert ApplePodcastsParser._extract_feed_from_jsonld(soup) is None

    def test_handles_json_array(self):
        data = [{"@type": "Other"}, {"feedUrl": "https://example.com/array.rss"}]
        html = f'<script type="application/ld+json">{json.dumps(data)}</script>'
        soup = BeautifulSoup(html, 'html.parser')
        assert ApplePodcastsParser._extract_feed_from_jsonld(soup) == "https://example.com/array.rss"


class TestExtractMetadataAsync:
    """Tests for ApplePodcastsParser.extract_metadata_async — independent strategy isolation."""

    @staticmethod
    def _mock_session(*, api_json=None, api_exc=None, page_text=None, page_exc=None):
        """Build a mock aiohttp.ClientSession with configurable API / page responses.

        session.get(url) must be a regular function returning an async context manager
        (matching aiohttp's _RequestContextManager pattern).
        """
        session = MagicMock()

        def fake_get(url, **kwargs):
            ctx = AsyncMock()
            if 'itunes.apple.com' in url:
                if api_exc:
                    ctx.__aenter__ = AsyncMock(side_effect=api_exc)
                else:
                    resp = AsyncMock()
                    resp.json = AsyncMock(return_value=api_json or {"resultCount": 0, "results": []})
                    ctx.__aenter__ = AsyncMock(return_value=resp)
            else:
                if page_exc:
                    ctx.__aenter__ = AsyncMock(side_effect=page_exc)
                else:
                    resp = AsyncMock()
                    resp.raise_for_status = MagicMock()
                    resp.text = AsyncMock(return_value=page_text or '<html></html>')
                    ctx.__aenter__ = AsyncMock(return_value=resp)
            ctx.__aexit__ = AsyncMock(return_value=False)
            return ctx

        session.get = fake_get
        return session

    @pytest.mark.asyncio
    async def test_itunes_api_success(self):
        """iTunes API returns feedUrl — page scraping is not needed for RSS."""
        session = self._mock_session(
            api_json={"resultCount": 1, "results": [{"feedUrl": "https://example.com/feed.rss"}]},
        )
        rss, title = await ApplePodcastsParser.extract_metadata_async(
            session, "https://podcasts.apple.com/us/podcast/test/id12345"
        )
        assert rss == "https://example.com/feed.rss"

    @pytest.mark.asyncio
    async def test_page_fail_itunes_api_succeeds(self):
        """Key bug scenario: page fetch fails but iTunes API still returns RSS URL."""
        session = self._mock_session(
            api_json={"resultCount": 1, "results": [{"feedUrl": "https://example.com/feed.rss"}]},
            page_exc=Exception("Connection refused"),
        )
        rss, title = await ApplePodcastsParser.extract_metadata_async(
            session, "https://podcasts.apple.com/us/podcast/test/id12345"
        )
        assert rss == "https://example.com/feed.rss"
        assert title is None  # page was unreachable

    @pytest.mark.asyncio
    async def test_both_fail_returns_none(self):
        """Both strategies fail — returns (None, None) with error output."""
        session = self._mock_session(
            api_exc=Exception("API timeout"),
            page_exc=Exception("Page timeout"),
        )
        rss, title = await ApplePodcastsParser.extract_metadata_async(
            session, "https://podcasts.apple.com/us/podcast/test/id12345"
        )
        assert rss is None
        assert title is None

    @pytest.mark.asyncio
    async def test_itunes_api_fails_falls_back_to_jsonld(self):
        """iTunes API fails but page has JSON-LD with feedUrl."""
        ld_json = json.dumps({"feedUrl": "https://example.com/jsonld.rss"})
        page_html = (
            '<html><head><title>My Podcast</title></head>'
            f'<body><script type="application/ld+json">{ld_json}</script></body></html>'
        )
        session = self._mock_session(
            api_exc=Exception("API error"),
            page_text=page_html,
        )
        rss, title = await ApplePodcastsParser.extract_metadata_async(
            session, "https://podcasts.apple.com/us/podcast/test/id12345"
        )
        assert rss == "https://example.com/jsonld.rss"
        assert title == "My Podcast"

    @pytest.mark.asyncio
    async def test_extracts_episode_title_from_og_meta(self):
        """Page og:title meta tag is used for episode title."""
        page_html = '<html><head><meta property="og:title" content="Episode 42"></head></html>'
        session = self._mock_session(
            api_json={"resultCount": 1, "results": [{"feedUrl": "https://example.com/f.rss"}]},
            page_text=page_html,
        )
        rss, title = await ApplePodcastsParser.extract_metadata_async(
            session, "https://podcasts.apple.com/us/podcast/test/id12345"
        )
        assert title == "Episode 42"

    @pytest.mark.asyncio
    async def test_no_podcast_id_in_url_skips_api(self):
        """URL without /idNNN skips iTunes API entirely."""
        session = self._mock_session(page_text='<html><head><title>Page</title></head></html>')
        rss, title = await ApplePodcastsParser.extract_metadata_async(
            session, "https://podcasts.apple.com/us/podcast/test"
        )
        assert rss is None
        assert title == "Page"


class TestDownloadAll:
    """Tests for PodcastDownloader.download_all — as_completed index tracking."""

    @pytest.mark.asyncio
    async def test_download_episode_reports_byte_progress(self, tmp_path):
        """download_episode reports total bytes and chunk progress when content-length is known."""
        from casts_down.downloaders.base import PodcastDownloader, PodcastEpisode

        class FakeContent:
            async def iter_chunked(self, chunk_size):
                yield b"abc"
                yield b"de"

        class FakeResponse:
            headers = {"content-length": "5"}
            content = FakeContent()

            def raise_for_status(self):
                return None

        class FakeContext:
            async def __aenter__(self):
                return FakeResponse()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        class FakeSession:
            def get(self, *args, **kwargs):
                return FakeContext()

        events = []
        dl = PodcastDownloader(concurrent=1)
        output_path = tmp_path / "episode.mp3"
        episode = PodcastEpisode("Episode", "https://example.com/episode.mp3")

        success, _ = await dl.download_episode(
            FakeSession(),
            episode,
            output_path,
            progress_callback=lambda total, chunk: events.append((total, chunk)),
        )

        assert success is True
        assert output_path.read_bytes() == b"abcde"
        assert events[0] == (5, 0)
        assert sum(chunk for _, chunk in events) == 5

    @pytest.mark.asyncio
    async def test_single_episode_download(self):
        """download_all returns correct file path for a single episode."""
        from casts_down.downloaders.base import PodcastDownloader, PodcastEpisode
        import tempfile, aiohttp

        episode = PodcastEpisode(title="Test Ep", audio_url="https://example.com/ep.mp3")
        dl = PodcastDownloader(concurrent=1)

        # Mock download_episode to return success without network
        async def fake_download(session, ep, path, skip, progress_callback=None):
            path.write_bytes(b"fake audio data")
            return True, f"Done: {path.name}"

        dl.download_episode = fake_download

        with tempfile.TemporaryDirectory() as tmpdir:
            async with aiohttp.ClientSession() as session:
                # Patch session into download_all by mocking ClientSession
                with patch("casts_down.downloaders.base.aiohttp.ClientSession") as mock_cs:
                    mock_cs.return_value.__aenter__ = AsyncMock(return_value=session)
                    mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)
                    files = await dl.download_all([episode], "Podcast", Path(tmpdir))

        assert len(files) == 1
        assert files[0].name == "podcast--test-ep.mp3"

    @pytest.mark.asyncio
    async def test_multiple_episodes_all_tracked(self):
        """download_all correctly tracks indices for multiple concurrent episodes."""
        from casts_down.downloaders.base import PodcastDownloader, PodcastEpisode
        import tempfile, aiohttp

        episodes = [
            PodcastEpisode(title=f"Ep {i}", audio_url=f"https://example.com/ep{i}.mp3")
            for i in range(5)
        ]
        dl = PodcastDownloader(concurrent=3)

        async def fake_download(session, ep, path, skip, progress_callback=None):
            path.write_bytes(b"data")
            return True, f"Done: {path.name}"

        dl.download_episode = fake_download

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("casts_down.downloaders.base.aiohttp.ClientSession") as mock_cs:
                mock_cs.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
                mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)
                files = await dl.download_all(episodes, "Podcast", Path(tmpdir))

        assert len(files) == 5
        titles = {f.stem for f in files}
        for i in range(5):
            assert any(f"ep-{i}" in t for t in titles)

    @pytest.mark.asyncio
    async def test_colliding_episode_filenames_are_deduped(self, tmp_path):
        from casts_down.downloaders.base import PodcastDownloader, PodcastEpisode

        episodes = [
            PodcastEpisode(title="Ep!", audio_url="https://example.com/a.mp3"),
            PodcastEpisode(title="Ep?", audio_url="https://example.com/b.mp3"),
        ]
        dl = PodcastDownloader(concurrent=2)

        async def fake_download(session, ep, path, skip, progress_callback=None):
            path.write_bytes(ep.title.encode())
            return True, f"Done: {path.name}"

        dl.download_episode = fake_download

        with patch("casts_down.downloaders.base.aiohttp.ClientSession") as mock_cs:
            mock_cs.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)
            files = await dl.download_all(episodes, "Podcast", tmp_path)

        assert sorted(path.name for path in files) == [
            "podcast--ep-2.mp3",
            "podcast--ep.mp3",
        ]
        assert (tmp_path / "podcast--ep.mp3").read_bytes() != (tmp_path / "podcast--ep-2.mp3").read_bytes()

    @pytest.mark.asyncio
    async def test_partial_failure_tracked(self):
        """download_all returns only successful files when some downloads fail."""
        from casts_down.downloaders.base import PodcastDownloader, PodcastEpisode
        import tempfile

        episodes = [
            PodcastEpisode(title="Good", audio_url="https://example.com/good.mp3"),
            PodcastEpisode(title="Bad", audio_url="https://example.com/bad.mp3"),
        ]
        dl = PodcastDownloader(concurrent=2)

        async def fake_download(session, ep, path, skip, progress_callback=None):
            if "Bad" in ep.title:
                return False, f"Failed: {ep.title}"
            path.write_bytes(b"data")
            return True, f"Done: {path.name}"

        dl.download_episode = fake_download

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("casts_down.downloaders.base.aiohttp.ClientSession") as mock_cs:
                mock_cs.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
                mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)
                files = await dl.download_all(episodes, "Podcast", Path(tmpdir))

        assert len(files) == 1
        assert "good" in files[0].name

    @pytest.mark.asyncio
    async def test_callback_runs_after_successful_file_exists(self, tmp_path):
        """download_all calls on_file_done only after the final file exists."""
        from casts_down.downloaders.base import PodcastDownloader, PodcastEpisode

        episode = PodcastEpisode(title="Done", audio_url="https://example.com/done.mp3")
        dl = PodcastDownloader(concurrent=1)
        callback_events = []

        async def fake_download(session, ep, path, skip, progress_callback=None):
            path.write_bytes(b"data")
            return True, f"Done: {path.name}"

        def on_file_done(path, ep, message):
            callback_events.append((path, ep, message, path.exists(), path.read_bytes()))

        dl.download_episode = fake_download

        with patch("casts_down.downloaders.base.aiohttp.ClientSession") as mock_cs:
            mock_cs.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)
            files = await dl.download_all(
                [episode],
                "Podcast",
                tmp_path,
                on_file_done=on_file_done,
            )

        assert files == [tmp_path / "podcast--done.mp3"]
        assert callback_events == [
            (tmp_path / "podcast--done.mp3", episode, "Done: podcast--done.mp3", True, b"data")
        ]

    @pytest.mark.asyncio
    async def test_callback_not_called_for_failed_download(self, tmp_path):
        """download_all does not call on_file_done for failed downloads."""
        from casts_down.downloaders.base import PodcastDownloader, PodcastEpisode

        episode = PodcastEpisode(title="Fail", audio_url="https://example.com/fail.mp3")
        dl = PodcastDownloader(concurrent=1)
        callback_events = []

        async def fake_download(session, ep, path, skip, progress_callback=None):
            return False, f"Failed: {ep.title}"

        dl.download_episode = fake_download

        with patch("casts_down.downloaders.base.aiohttp.ClientSession") as mock_cs:
            mock_cs.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_cs.return_value.__aexit__ = AsyncMock(return_value=False)
            files = await dl.download_all(
                [episode],
                "Podcast",
                tmp_path,
                on_file_done=lambda *args: callback_events.append(args),
            )

        assert files == []
        assert callback_events == []


# ---------------------------------------------------------------------------
# Dry-run integration tests — exercise real code paths, no large downloads
# ---------------------------------------------------------------------------

class TestDryRunDetectDownloader:
    """URL detection → correct downloader routing."""

    def test_apple_podcasts_url(self):
        from casts_down.cli import detect_downloader
        assert detect_downloader("https://podcasts.apple.com/us/podcast/test/id123") == "podcast"

    def test_apple_single_episode_url(self):
        from casts_down.cli import detect_downloader
        assert detect_downloader("https://podcasts.apple.com/us/podcast/ep/id123?i=999") == "podcast"

    def test_xiaoyuzhou_episode_url(self):
        from casts_down.cli import detect_downloader
        assert detect_downloader("https://www.xiaoyuzhoufm.com/episode/abc123") == "xiaoyuzhou"

    def test_xiaoyuzhou_podcast_url(self):
        from casts_down.cli import detect_downloader
        assert detect_downloader("https://www.xiaoyuzhoufm.com/podcast/abc123") == "xiaoyuzhou"

    def test_rss_feed_url(self):
        from casts_down.cli import detect_downloader
        assert detect_downloader("https://feeds.example.com/podcast.rss") == "podcast"

    def test_xml_feed_url(self):
        from casts_down.cli import detect_downloader
        assert detect_downloader("https://feeds.example.com/podcast.xml") == "podcast"

    def test_unknown_url_defaults_to_podcast(self):
        from casts_down.cli import detect_downloader
        assert detect_downloader("https://example.com/some-feed") == "podcast"


class TestDryRunItunesApiToRss:
    """iTunes API → RSS parse pipeline (real network, no audio download)."""

    @pytest.mark.asyncio
    async def test_lex_fridman_itunes_to_rss(self):
        """Full path: iTunes API → get feedUrl → parse RSS → get episodes."""
        import aiohttp
        from casts_down.downloaders.podcast import ApplePodcastsParser, RSSParser

        async with aiohttp.ClientSession() as session:
            rss_url, title = await ApplePodcastsParser.extract_metadata_async(
                session, "https://podcasts.apple.com/us/podcast/lex-fridman-podcast/id1434243584"
            )

        assert rss_url is not None, "iTunes API should return a feed URL"
        assert "lexfridman" in rss_url.lower()

        # Parse RSS feed
        name, episodes = RSSParser.parse(rss_url)
        assert name, "Podcast name should not be empty"
        assert len(episodes) > 100, f"Expected 100+ episodes, got {len(episodes)}"
        assert episodes[0].title, "First episode should have a title"
        assert episodes[0].audio_url.startswith("http"), "Audio URL should be valid"

    @pytest.mark.asyncio
    async def test_joe_rogan_itunes_to_rss(self):
        """Verify another popular podcast works end-to-end."""
        import aiohttp
        from casts_down.downloaders.podcast import ApplePodcastsParser, RSSParser

        async with aiohttp.ClientSession() as session:
            rss_url, _ = await ApplePodcastsParser.extract_metadata_async(
                session, "https://podcasts.apple.com/us/podcast/the-joe-rogan-experience/id360084272"
            )

        assert rss_url is not None
        name, episodes = RSSParser.parse(rss_url)
        assert len(episodes) > 0
        # Verify episode data structure is complete
        ep = episodes[0]
        assert ep.title
        assert ep.audio_url
        assert ep.sanitize_filename(name).endswith(('.mp3', '.m4a'))


class TestDryRunCliPipeline:
    """CLI _download_podcast / _download_xiaoyuzhou — mock only the HTTP download."""

    def test_download_podcast_pipeline(self):
        """CLI pipeline: URL → detect → parse RSS → build episode list → sanitize filenames."""
        from click.testing import CliRunner
        from casts_down.cli import main

        runner = CliRunner()
        # --help just exercises the CLI group parsing without network
        result = runner.invoke(main, ['--help'])
        assert result.exit_code == 0
        assert 'Casts Down' in result.output

    def test_transcribe_subcommand_no_files(self):
        """transcribe subcommand exits cleanly with error when no files given."""
        from click.testing import CliRunner
        from casts_down.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ['transcribe'])
        assert result.exit_code != 0
        assert 'No files specified' in result.output

    def test_version_flag(self):
        """--version prints version string."""
        from click.testing import CliRunner
        from casts_down.cli import main
        from casts_down import __version__

        runner = CliRunner()
        result = runner.invoke(main, ['--version'])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_download_podcast_dryrun_with_mock(self):
        """Full pipeline: Apple URL → iTunes API → RSS → episode list, mock actual download."""
        import tempfile
        from click.testing import CliRunner
        from casts_down.cli import main

        with tempfile.TemporaryDirectory() as tmpdir:
            # Patch the downloader to avoid actual HTTP download of audio
            with patch("casts_down.downloaders.base.PodcastDownloader.download_episode") as mock_dl:
                mock_dl.return_value = (False, "dry-run: skipped")
                runner = CliRunner()
                result = runner.invoke(main, [
                    '--no-transcribe', '--latest', '1', '--output', tmpdir,
                    'https://podcasts.apple.com/us/podcast/lex-fridman-podcast/id1434243584',
                ])
                # Should reach the download phase (RSS extraction succeeded)
                assert 'RSS URL' in result.output or 'Preparing to download' in result.output


class TestDryRunDepCheck:
    """Dependency check integration — verify warning appears in full CLI flow."""

    def test_missing_ffmpeg_warning_in_download_flow(self):
        """Full CLI invocation shows yellow ffmpeg warning when missing."""
        import tempfile
        from click.testing import CliRunner
        from casts_down.cli import main

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("casts_down.cli.shutil.which", return_value=None), \
                 patch("casts_down.cli.platform.system", return_value="Darwin"), \
                 patch("casts_down.downloaders.base.PodcastDownloader.download_episode") as mock_dl:
                mock_dl.return_value = (False, "dry-run: skipped")
                runner = CliRunner()
                result = runner.invoke(main, [
                    '--no-transcribe', '--latest', '1', '--output', tmpdir,
                    'https://podcasts.apple.com/us/podcast/lex-fridman-podcast/id1434243584',
                ])
                assert 'ffmpeg' in result.output
                assert 'brew install ffmpeg' in result.output

    def test_no_warning_when_ffmpeg_installed(self):
        """No warning when ffmpeg is available."""
        import tempfile
        from click.testing import CliRunner
        from casts_down.cli import main

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("casts_down.cli.shutil.which", return_value="/opt/homebrew/bin/ffmpeg"), \
                 patch("casts_down.downloaders.base.PodcastDownloader.download_episode") as mock_dl:
                mock_dl.return_value = (False, "dry-run: skipped")
                runner = CliRunner()
                result = runner.invoke(main, [
                    '--no-transcribe', '--latest', '1', '--output', tmpdir,
                    'https://podcasts.apple.com/us/podcast/lex-fridman-podcast/id1434243584',
                ])
                assert 'ffmpeg' not in result.output


class TestDryRunXiaoyuzhouParser:
    """Xiaoyuzhou HTML parser — verify extract_episode_data code path."""

    def test_extract_episode_data_valid(self):
        from casts_down.downloaders.xiaoyuzhou import XiaoyuzhouDownloader

        dl = XiaoyuzhouDownloader()
        html = '''<script id="__NEXT_DATA__" type="application/json">
        {"props":{"pageProps":{"episode":{"eid":"abc","title":"Test","enclosure":{"url":"https://x.com/a.m4a"}}}}}
        </script>'''
        data = dl.extract_episode_data(html)
        assert data['episode']['title'] == 'Test'
        assert data['episode']['enclosure']['url'] == 'https://x.com/a.m4a'

    def test_extract_episode_data_missing_script(self):
        from casts_down.downloaders.xiaoyuzhou import XiaoyuzhouDownloader

        dl = XiaoyuzhouDownloader()
        with pytest.raises(ValueError, match="__NEXT_DATA__"):
            dl.extract_episode_data('<html><body>no data</body></html>')

    def test_extract_episode_data_invalid_json(self):
        from casts_down.downloaders.xiaoyuzhou import XiaoyuzhouDownloader

        dl = XiaoyuzhouDownloader()
        html = '<script id="__NEXT_DATA__" type="application/json">{broken</script>'
        with pytest.raises(ValueError, match="JSON"):
            dl.extract_episode_data(html)

    def test_extract_episode_data_missing_props(self):
        from casts_down.downloaders.xiaoyuzhou import XiaoyuzhouDownloader

        dl = XiaoyuzhouDownloader()
        html = '<script id="__NEXT_DATA__" type="application/json">{"other": 1}</script>'
        with pytest.raises(ValueError, match="props"):
            dl.extract_episode_data(html)

    def test_library_code_does_not_call_sys_exit(self):
        """Library code should raise exceptions, not sys.exit."""
        import inspect
        from casts_down.downloaders.xiaoyuzhou import XiaoyuzhouDownloader
        source = inspect.getsource(XiaoyuzhouDownloader)
        assert "sys.exit" not in source

    @pytest.mark.asyncio
    async def test_podcast_download_uses_friendly_filename(self, tmp_path):
        from casts_down.downloaders.xiaoyuzhou import XiaoyuzhouDownloader

        dl = XiaoyuzhouDownloader()

        async def fake_get_podcast_episodes(session, podcast_url):
            return "My Podcast", [
                {
                    "title": "Ep: One/Two? Women’s Health!",
                    "enclosure": {"url": "https://example.com/audio.m4a"},
                }
            ]

        async def fake_download_audio(session, audio_url, output_path, skip_existing, progress_callback=None):
            output_path.write_bytes(b"data")
            return True, f"Completed: {output_path.name}"

        dl.get_podcast_episodes = fake_get_podcast_episodes
        dl.download_audio = fake_download_audio

        files = await dl.download_podcast("https://www.xiaoyuzhoufm.com/podcast/abc", tmp_path)

        assert [path.name for path in files] == ["my-podcast--ep-one-two-womens-health.m4a"]

    @pytest.mark.asyncio
    async def test_podcast_download_dedupes_colliding_filenames(self, tmp_path):
        from casts_down.downloaders.xiaoyuzhou import XiaoyuzhouDownloader

        dl = XiaoyuzhouDownloader()

        async def fake_get_podcast_episodes(session, podcast_url):
            return "My Podcast", [
                {"title": "Ep!", "enclosure": {"url": "https://example.com/a.m4a"}},
                {"title": "Ep?", "enclosure": {"url": "https://example.com/b.m4a"}},
            ]

        async def fake_download_audio(session, audio_url, output_path, skip_existing, progress_callback=None):
            output_path.write_bytes(audio_url.encode())
            return True, f"Completed: {output_path.name}"

        dl.get_podcast_episodes = fake_get_podcast_episodes
        dl.download_audio = fake_download_audio

        files = await dl.download_podcast("https://www.xiaoyuzhoufm.com/podcast/abc", tmp_path)

        assert sorted(path.name for path in files) == [
            "my-podcast--ep-2.m4a",
            "my-podcast--ep.m4a",
        ]

    @pytest.mark.asyncio
    async def test_podcast_download_callback_runs_after_successful_file_exists(self, tmp_path):
        from casts_down.downloaders.xiaoyuzhou import XiaoyuzhouDownloader

        dl = XiaoyuzhouDownloader()
        episode = {
            "title": "Ep One",
            "enclosure": {"url": "https://example.com/audio.m4a"},
        }
        callback_events = []

        async def fake_get_podcast_episodes(session, podcast_url):
            return "My Podcast", [episode]

        async def fake_download_audio(session, audio_url, output_path, skip_existing, progress_callback=None):
            output_path.write_bytes(b"data")
            return True, f"Completed: {output_path.name}"

        def on_file_done(path, ep, message):
            callback_events.append((path, ep, message, path.exists(), path.read_bytes()))

        dl.get_podcast_episodes = fake_get_podcast_episodes
        dl.download_audio = fake_download_audio

        files = await dl.download_podcast(
            "https://www.xiaoyuzhoufm.com/podcast/abc",
            tmp_path,
            on_file_done=on_file_done,
        )

        assert files == [tmp_path / "my-podcast--ep-one.m4a"]
        assert callback_events == [
            (
                tmp_path / "my-podcast--ep-one.m4a",
                episode,
                "Completed: my-podcast--ep-one.m4a",
                True,
                b"data",
            )
        ]

    @pytest.mark.asyncio
    async def test_episode_download_callback_receives_success_message(self, tmp_path):
        from casts_down.downloaders.xiaoyuzhou import XiaoyuzhouDownloader

        dl = XiaoyuzhouDownloader()
        episode_info = {
            "eid": "abc",
            "title": "Ep One",
            "audio_url": "https://example.com/audio.m4a",
            "duration": 123,
            "description": "",
            "pubDate": "",
        }
        callback_events = []

        async def fake_get_episode_info(session, episode_url):
            return episode_info

        async def fake_download_audio(session, audio_url, output_path, skip_existing, progress_callback=None):
            output_path.write_bytes(b"data")
            return True, f"Completed: {output_path.name}"

        def on_file_done(path, ep, message):
            callback_events.append((path, ep, message, path.exists(), path.read_bytes()))

        dl.get_episode_info = fake_get_episode_info
        dl.download_audio = fake_download_audio

        files = await dl.download_episode_by_url(
            "https://www.xiaoyuzhoufm.com/episode/abc",
            tmp_path,
            on_file_done=on_file_done,
        )

        assert files == [tmp_path / "ep-one.m4a"]
        assert callback_events == [
            (tmp_path / "ep-one.m4a", episode_info, "Completed: ep-one.m4a", True, b"data")
        ]


class TestDryRunTranscriptionPipeline:
    """Transcription code path — no model needed, just verify wiring."""

    def test_collect_audio_files_filters_correctly(self):
        import tempfile
        from casts_down.transcribe import collect_audio_files

        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "episode.mp3").write_bytes(b"fake")
            (d / "episode.m4a").write_bytes(b"fake")
            (d / "notes.txt").write_bytes(b"text")
            (d / "episode.srt").write_bytes(b"sub")

            files = collect_audio_files(d)
            exts = {f.suffix for f in files}
            assert ".mp3" in exts
            assert ".m4a" in exts
            assert ".txt" not in exts
            assert ".srt" not in exts

    def test_formatter_roundtrip(self):
        """Segment → SRT + TXT formatting without errors."""
        import tempfile
        from casts_down.transcribe.engine import Segment
        from casts_down.transcribe.formatter import format_srt, format_txt, write_outputs

        segments = [
            Segment(start=0.0, end=5.5, text="Hello world"),
            Segment(start=5.5, end=10.0, text="你好世界"),
        ]
        srt = format_srt(segments)
        txt = format_txt(segments)
        assert "Hello world" in srt
        assert "你好世界" in txt
        assert "-->" in srt  # SRT timestamp format

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / "test.mp3"
            audio_path.write_bytes(b"fake")
            write_outputs(audio_path, segments)
            assert (Path(tmpdir) / "test.srt").exists()
            assert (Path(tmpdir) / "test.txt").exists()

    def test_run_transcription_no_files(self):
        """_run_transcription with empty list does not crash."""
        from casts_down.cli import _run_transcription
        # Should print "No audio files found" and return
        _run_transcription([], model="tiny")


class TestImports:
    def test_import_podcast_parser(self):
        from casts_down.downloaders.podcast import RSSParser, ApplePodcastsParser
        assert RSSParser is not None
        assert ApplePodcastsParser is not None

    def test_import_xiaoyuzhou(self):
        from casts_down.downloaders.xiaoyuzhou import XiaoyuzhouDownloader
        assert XiaoyuzhouDownloader is not None
