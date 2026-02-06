# 🎙️ Casts Down

一个强大的跨平台命令行播客下载工具，支持多个播客平台和 RSS 源。

## ✨ 特性

- 🎯 **智能识别**：自动识别 URL 类型，无需手动选择下载器
- 🌐 **多平台支持**：
  - ✅ Apple Podcasts（支持单集和播客主页）
  - ✅ 小宇宙（Xiaoyuzhou）
  - ✅ 标准 RSS 2.0 源
- ⚡ **异步并发下载**：可配置并发数，提升下载速度
- 📊 **进度条显示**：实时查看下载进度
- 🎬 **单集下载**：支持从 Apple Podcasts 链接下载特定单集
- 💾 **智能文件管理**：自动命名、跳过已存在文件
- 📦 **独立可执行文件**：打包为跨平台二进制文件，无需 Python 环境

## 📦 安装

### 方式 1：下载预编译二进制文件（推荐）

从 [Releases](https://github.com/your-repo/releases) 页面下载对应平台的可执行文件：

```bash
# macOS / Linux
chmod +x casts-down-*
./casts-down-* <URL>

# Windows
casts-down-windows-x64.exe <URL>
```

### 方式 2：使用 Python 运行

```bash
# 安装依赖
pip install -r requirements.txt

# 运行统一入口
python casts_down.py <URL>
```

### 方式 3：从源码构建

```bash
# 安装依赖和打包工具
make install

# 构建可执行文件
make build

# 查看 release/ 目录
ls release/
```

## 🚀 使用方法

### 统一入口（自动识别平台）

```bash
# 🎯 智能识别，无需指定下载器
casts-down "<任意播客URL>"

# Apple Podcasts - 下载单集
casts-down "https://podcasts.apple.com/podcast/id123?i=456"

# Apple Podcasts - 下载最新 3 集
casts-down "https://podcasts.apple.com/podcast/id123" --latest 3

# 小宇宙 - 下载单集
casts-down "https://www.xiaoyuzhoufm.com/episode/xxx"

# 小宇宙 - 下载播客
casts-down "https://www.xiaoyuzhoufm.com/podcast/xxx" --latest 5

# RSS 源 - 下载全部
casts-down "https://feeds.example.com/podcast.rss" --all
```

### 高级选项

```bash
# 指定输出目录
casts-down "<URL>" -o ./my_podcasts

# 设置并发下载数
casts-down "<URL>" --concurrent 5

# 跳过已存在的文件
casts-down "<URL>" --all --skip-existing
```

## 📖 命令行参数

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--all` | `-a` | 下载所有剧集 | False（仅最新） |
| `--latest N` | `-l N` | 下载最新 N 集 | 1 |
| `--output DIR` | `-o DIR` | 输出目录 | `./podcasts` |
| `--concurrent N` | `-c N` | 并发下载数 | 3 |
| `--skip-existing` | `-s` | 跳过已存在文件 | False |

## 🔍 平台支持说明

### ✅ 完全支持

- **Apple Podcasts**：
  - ✅ 播客主页（下载所有或最新 N 集）
  - ✅ 单集链接（智能匹配并下载特定单集）
  - ✅ 自动提取 RSS 源
- **小宇宙（Xiaoyuzhou）**：
  - ✅ 单集链接
  - ✅ 播客链接（获取前 15 集）
  - ⚠️ 完整播客列表需要额外逆向
- **RSS 源**：
  - ✅ 标准 RSS 2.0 播客源（最推荐）

### ❌ 不支持

- **Pocket Casts**：客户端应用，不托管音频文件
  - 建议：从原始播客 RSS 源下载

## 🏗️ 构建和打包

### 本地构建

```bash
# 快速构建（使用 Makefile）
make build

# 或手动构建
python build.py

# 清理构建文件
make clean
```

### 跨平台构建

使用 GitHub Actions 自动构建多平台版本：

1. 推送带标签的提交：
```bash
git tag v1.0.0
git push origin v1.0.0
```

2. GitHub Actions 会自动构建：
   - Windows (x64)
   - macOS (Intel x64)
   - macOS (Apple Silicon arm64)
   - Linux (x64)

3. 在 Releases 页面下载构建产物

### 手动打包

```bash
# 安装 PyInstaller
pip install pyinstaller

# 构建可执行文件
python build.py

# 查看输出
ls release/
```

## 🛠️ 技术栈

- **Python 3.8+**
- **feedparser**：RSS 解析
- **aiohttp**：异步并发下载
- **click**：命令行接口
- **tqdm**：进度条显示
- **BeautifulSoup4**：HTML 解析

## 📝 示例

### 下载 NPR 的 "Up First" 播客

```bash
podcast-dl "https://feeds.npr.org/510318/podcast.xml" --latest 3
```

### 从 Apple Podcasts 下载

```bash
podcast-dl "https://podcasts.apple.com/us/podcast/the-daily/id1200361736" --all
```

### 批量下载并跳过已存在文件

```bash
podcast-dl "https://feeds.example.com/podcast.rss" --all -o ./downloads --skip-existing
```

## ⚠️ 注意事项

1. **RSS 源失效**：部分播客源可能需要认证或已失效
2. **音频 URL 时效性**：某些播客的音频 URL 可能包含时效 token
3. **反爬机制**：频繁请求可能触发限制，建议适当设置并发数
4. **版权**：请确保下载的播客内容供个人使用，遵守版权法规

## 🐛 故障排除

### 问题：无法提取 Apple Podcasts RSS

**解决方案**：
- 确保 URL 格式正确（包含 podcast ID）
- 检查网络连接
- 使用浏览器开发者工具手动查找 RSS URL

### 问题：下载超时

**解决方案**：
- 减少并发数：`--concurrent 1`
- 检查网络连接
- 某些服务器可能限速

### 问题：文件名异常

**解决方案**：
- 工具会自动清理非法字符
- 如仍有问题，请提交 Issue

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request!

## ⚡ 快速测试

```bash
# 测试 RSS 解析（无实际下载）
python podcast_dl.py "https://feeds.npr.org/510318/podcast.xml" --latest 1

# 测试 Apple Podcasts
python podcast_dl.py "https://podcasts.apple.com/us/podcast/the-daily/id1200361736" --latest 1
```
