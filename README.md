```
   ____          _         ____
  / ___|__ _ ___| |_ ___  |  _ \  _____      ___ __
 | |   / _` / __| __/ __| | | | |/ _ \ \ /\ / / '_ \
 | |__| (_| \__ \ |_\__ \ | |_| | (_) \ V  V /| | | |
  \____\__,_|___/\__|___/ |____/ \___/ \_/\_/ |_| |_|

      Intelligent Podcast Downloader
```

一个强大的跨平台命令行播客下载工具，支持多个播客平台和 RSS 源。

---

## IMPORTANT DISCLAIMER

```
+========================================================================+
|                          [!] IMPORTANT NOTICE                          |
+========================================================================+
|                                                                        |
|  This tool is provided for EDUCATIONAL and PERSONAL USE ONLY.         |
|                                                                        |
|  By using this software, you explicitly agree to:                     |
|                                                                        |
|  1. PERSONAL USE ONLY                                                 |
|     - Use for personal learning, research, and hobby purposes         |
|     - NOT for commercial distribution or public sharing               |
|     - NOT for any profit-making activities                            |
|                                                                        |
|  2. RESPECT COPYRIGHT LAWS                                            |
|     - All downloaded content remains property of original creators    |
|     - Respect intellectual property rights and copyright laws         |
|     - Support content creators through official channels              |
|                                                                        |
|  3. RESPECT BUSINESS ECOSYSTEMS                                       |
|     - Do not use this tool to circumvent paid subscriptions           |
|     - Support creators via official platforms and subscriptions       |
|     - Respect the business model of podcast platforms                 |
|                                                                        |
|  4. LEGAL COMPLIANCE                                                  |
|     - Comply with all applicable laws in your jurisdiction            |
|     - Comply with Terms of Service of podcast platforms               |
|     - Users are solely responsible for their usage                    |
|                                                                        |
|  PROHIBITED USES:                                                     |
|    X Commercial redistribution of downloaded content                  |
|    X Mass downloading for public sharing or distribution              |
|    X Bypassing paid subscription services                             |
|    X Any activity that harms content creators or platforms            |
|                                                                        |
|  The developers assume NO LIABILITY for misuse of this software.      |
|                                                                        |
+========================================================================+
```

```
+========================================================================+
|                          [!] 重要声明                                  |
+========================================================================+
|                                                                        |
|  本工具仅供学习、研究和个人爱好使用。                                      |
|                                                                        |
|  使用本软件即表示您明确同意：                                              |
|                                                                        |
|  1. 仅限个人使用                                                        |
|     - 用于个人学习、研究和爱好目的                                        |
|     - 禁止用于商业分发或公开传播                                          |
|     - 禁止用于任何盈利活动                                               |
|                                                                        |
|  2. 尊重版权法规                                                        |
|     - 所有下载内容归原创作者所有                                          |
|     - 尊重知识产权和版权法律                                             |
|     - 通过官方渠道支持内容创作者                                          |
|                                                                        |
|  3. 尊重商业生态                                                        |
|     - 不得使用本工具绕过付费订阅服务                                       |
|     - 通过官方平台和订阅支持创作者                                        |
|     - 尊重播客平台的商业模式                                             |
|                                                                        |
|  4. 遵守法律法规                                                        |
|     - 遵守您所在地区的所有适用法律                                        |
|     - 遵守播客平台的服务条款                                             |
|     - 用户对其使用行为承担全部责任                                        |
|                                                                        |
|  禁止用途：                                                             |
|    X 商业性再分发下载的内容                                              |
|    X 大规模下载用于公开分享或传播                                         |
|    X 绕过付费订阅服务                                                   |
|    X 任何损害内容创作者或平台利益的行为                                   |
|                                                                        |
|  开发者对本软件的滥用不承担任何责任。                                      |
|                                                                        |
+========================================================================+
```

---

## Features

- **Smart Detection**: Automatically identifies URL type, no need to specify downloader
- **Multi-Platform Support**:
  - Apple Podcasts (single episodes and podcast pages)
  - Xiaoyuzhou
  - Standard RSS 2.0 feeds
- **Async Concurrent Downloads**: Configurable concurrency for faster downloads
- **Progress Display**: Real-time download progress tracking
- **Episode Selection**: Download specific episodes from Apple Podcasts links
- **Smart File Management**: Auto-naming, skip existing files

## Installation

### Option 1: Install via pip (Recommended)

```bash
pip install casts_down
```

### Option 2: Install from source

```bash
git clone https://github.com/clemente0731/casts_down.git
cd casts_down
pip install -r requirements.txt
python casts_down.py <URL>
```

## Usage

### Unified Entry Point (Auto-detection)

```bash
# Smart detection - no need to specify platform
casts-down "<any-podcast-URL>"

# Apple Podcasts - Download single episode
casts-down "https://podcasts.apple.com/podcast/id123?i=456"

# Apple Podcasts - Download latest 3 episodes
casts-down "https://podcasts.apple.com/podcast/id123" --latest 3

# Xiaoyuzhou - Download single episode
casts-down "https://www.xiaoyuzhoufm.com/episode/xxx"

# Xiaoyuzhou - Download podcast
casts-down "https://www.xiaoyuzhoufm.com/podcast/xxx" --latest 5

# RSS Feed - Download all
casts-down "https://feeds.example.com/podcast.rss" --all
```

### Advanced Options

```bash
# Specify output directory
casts-down "<URL>" -o ./my_podcasts

# Set concurrent downloads
casts-down "<URL>" --concurrent 5

# Skip existing files
casts-down "<URL>" --all --skip-existing
```

## Command Line Arguments

```
+------------------+--------+---------------------------+------------------+
| Argument         | Short  | Description               | Default          |
+------------------+--------+---------------------------+------------------+
| --all            | -a     | Download all episodes     | False (latest)   |
| --latest N       | -l N   | Download latest N eps     | 1                |
| --output DIR     | -o DIR | Output directory          | ./podcasts       |
| --concurrent N   | -c N   | Concurrent downloads      | 3                |
| --skip-existing  | -s     | Skip existing files       | False            |
+------------------+--------+---------------------------+------------------+
```

## Platform Support

### Fully Supported

**Apple Podcasts**
  - [x] Podcast homepage (download all or latest N episodes)
  - [x] Single episode links (smart matching and download)
  - [x] Automatic RSS extraction

**Xiaoyuzhou**
  - [x] Single episode links
  - [x] Podcast links (first 15 episodes)
  - [!] Full podcast list requires additional reverse engineering

**RSS Feeds**
  - [x] Standard RSS 2.0 podcast feeds (most recommended)

### Not Supported

**Pocket Casts**
  - Client application, does not host audio files
  - Recommendation: Download from original podcast RSS feed

## Technical Stack

```
+------------------+--------------------------------+
| Component        | Technology                     |
+------------------+--------------------------------+
| Language         | Python 3.8+                    |
| RSS Parsing      | feedparser                     |
| HTTP Client      | aiohttp (async downloads)      |
| CLI Framework    | click                          |
| Progress Display | tqdm                           |
| HTML Parsing     | BeautifulSoup4                 |
+------------------+--------------------------------+
```

## Examples

### Download NPR's "Up First" podcast

```bash
casts-down "https://feeds.npr.org/510318/podcast.xml" --latest 3
```

### Download from Apple Podcasts

```bash
casts-down "https://podcasts.apple.com/us/podcast/the-daily/id1200361736" --all
```

### Batch download with skip existing

```bash
casts-down "https://feeds.example.com/podcast.rss" --all -o ./downloads --skip-existing
```

## Notes

```
[!] WARNING
+------------------------------------------------------------------+
| 1. RSS Feed Expiration: Some feeds may require auth or expired   |
| 2. Audio URL Validity: Some URLs may contain time-limited tokens |
| 3. Rate Limiting: Frequent requests may trigger restrictions     |
| 4. Copyright: Ensure downloads are for personal use only         |
+------------------------------------------------------------------+
```

## Troubleshooting

### Issue: Cannot extract Apple Podcasts RSS

**Solution:**
- Ensure URL format is correct (contains podcast ID)
- Check network connection
- Use browser developer tools to manually find RSS URL

### Issue: Download timeout

**Solution:**
- Reduce concurrency: `--concurrent 1`
- Check network connection
- Some servers may have rate limiting

### Issue: Abnormal file names

**Solution:**
- Tool automatically cleans illegal characters
- If issues persist, please submit an Issue

## License

```
+------------------------------------------------------------------+
| MIT License                                                      |
|                                                                  |
| Copyright (c) 2024 Casts Down Contributors                       |
+------------------------------------------------------------------+
```

## Contributing

Contributions are welcome! Please submit Issues and Pull Requests.

## Quick Test

```bash
# Test RSS parsing (no actual download)
casts-down "https://feeds.npr.org/510318/podcast.xml" --latest 1

# Test Apple Podcasts
casts-down "https://podcasts.apple.com/us/podcast/the-daily/id1200361736" --latest 1
```

---

```
Made with <3 by open source contributors
```
