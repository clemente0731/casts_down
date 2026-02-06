# 📦 Release Notes

## ✨ 新功能概览

### 1. 🎯 统一入口脚本 (`casts_down.py`)

**智能 URL 路由**，无需手动选择下载器：

```bash
# 自动识别并使用正确的下载器
casts-down "<任意播客URL>"

# Apple Podcasts → podcast_dl.py
casts-down "https://podcasts.apple.com/..."

# 小宇宙 → xiaoyuzhou_dl.py
casts-down "https://xiaoyuzhoufm.com/..."

# RSS 源 → podcast_dl.py
casts-down "https://feeds.example.com/podcast.rss"
```

**特点**：
- ✅ 自动识别 URL 类型
- ✅ 无缝集成现有下载器
- ✅ 统一的命令行接口
- ✅ 支持所有原有参数

### 2. 🎬 Apple Podcasts 单集智能匹配

**支持下载特定单集**（不只是最新集）：

```bash
# 之前：只能下载最新集
podcast-dl "https://podcasts.apple.com/podcast/id123?i=456"
# 下载的是：最新一集 ❌

# 现在：智能匹配单集
casts-down "https://podcasts.apple.com/podcast/id123?i=456"
# 下载的是：URL 中指定的那一集 ✅
```

**工作原理**：
1. 检测 URL 中的 `?i=` 参数
2. 提取单集标题
3. 在 RSS feed 中模糊匹配标题
4. 只下载匹配的那一集

### 3. 📦 跨平台打包系统

**一键构建可执行文件**，无需 Python 环境：

```bash
# 使用 Makefile
make build

# 或使用 Python 脚本
python build.py

# 输出
release/
├── casts-down-macos-x64
├── casts-down-macos-arm64
├── casts-down-linux-x64
└── casts-down-windows-x64.exe
```

**特点**：
- ✅ 基于 PyInstaller
- ✅ 单文件可执行
- ✅ 支持 Windows、macOS、Linux
- ✅ 自动压缩（UPX）
- ✅ 平台自动识别

### 4. 🤖 GitHub Actions 自动构建

**自动化 CI/CD 流程**：

```bash
# 创建版本标签
git tag v1.0.0
git push origin v1.0.0

# GitHub Actions 自动：
# 1. 构建 4 个平台版本
# 2. 运行测试
# 3. 创建 Release
# 4. 上传二进制文件
```

**构建矩阵**：
- Windows x64
- macOS Intel (x64)
- macOS Apple Silicon (arm64)
- Linux x64

### 5. 📝 完善的文档

**新增文档**：
- `BUILD.md` - 详细的构建和发布指南
- `RELEASE_NOTES.md` - 版本发布说明
- 更新的 `README.md` - 包含所有新特性

## 📁 新增文件

```
casts_down/
├── casts_down.py           # 统一入口脚本 ⭐
├── casts_down.spec         # PyInstaller 配置 ⭐
├── build.py                # 构建脚本 ⭐
├── Makefile                # Make 构建配置 ⭐
├── BUILD.md                # 构建指南 ⭐
├── RELEASE_NOTES.md        # 发布说明 ⭐
├── .github/
│   └── workflows/
│       └── build.yml       # GitHub Actions ⭐
├── podcast_dl.py           # 改进：单集匹配 ✨
├── xiaoyuzhou_dl.py        # 保持不变
└── ...
```

## 🔄 改进的功能

### podcast_dl.py

**新增方法**：
- `ApplePodcastsParser.extract_episode_id()` - 提取单集 ID
- `ApplePodcastsParser.extract_episode_title()` - 提取单集标题
- `RSSParser.parse(episode_title=...)` - 支持按标题匹配

**改进逻辑**：
- ✅ 自动识别单集链接 vs 播客主页
- ✅ 智能标题匹配（模糊匹配）
- ✅ 正确的字符编码处理
- ✅ 更好的用户反馈

## 🚀 使用示例

### 统一入口

```bash
# Apple Podcasts - 单集
casts-down "https://podcasts.apple.com/cn/podcast/id1834069371?i=1000747967318"
# 输出：
# 🔍 检测到: Apple Podcasts
# 🎯 检测到单集链接
# 📝 剧集标题: 蒋奇明&双雪涛×罗永浩！如何成为飞行家
# ✓ 找到匹配的单集
# ✓ 完成: 罗永浩的十字路口 - 蒋奇明&双雪涛×罗永浩！如何成为飞行家.m4a

# 小宇宙
casts-down "https://www.xiaoyuzhoufm.com/episode/xxx"
# 输出：
# 🔍 检测到: 小宇宙播客
# ...

# RSS 源
casts-down "https://feeds.example.com/podcast.rss" --all
# 输出：
# 🔍 检测到: RSS 源
# ...
```

### 构建和发布

```bash
# 本地构建
make build

# 查看构建产物
ls -lh release/

# 测试
./release/casts-down-macos-arm64 --help

# 发布（使用 GitHub Actions）
git tag v1.0.0
git push origin v1.0.0
```

## 🎯 技术亮点

1. **模块化设计**：
   - 统一入口 + 独立下载器
   - 易于扩展新平台

2. **智能路由**：
   - 基于 URL 模式自动选择下载器
   - 无需用户干预

3. **跨平台兼容**：
   - PyInstaller 打包
   - 支持主流操作系统和架构

4. **自动化流程**：
   - GitHub Actions CI/CD
   - 一键发布多平台版本

5. **用户友好**：
   - 清晰的进度提示
   - 智能错误处理
   - 详细的帮助文档

## 📊 性能

- **下载速度**：异步并发，可配置（默认 3）
- **构建大小**：~15-25 MB（压缩后）
- **构建时间**：2-5 分钟（首次）
- **启动时间**：< 1 秒

## 🔮 未来计划

- [ ] 支持更多播客平台（Spotify、Google Podcasts 等）
- [ ] 下载历史管理
- [ ] 配置文件支持
- [ ] 播放列表导入
- [ ] 批量 URL 处理
- [ ] Web UI 界面

## 🙏 致谢

感谢所有贡献者和用户的支持！

---

**完整文档**：
- [README.md](README.md) - 使用指南
- [BUILD.md](BUILD.md) - 构建指南
- [LIMITATIONS.md](LIMITATIONS.md) - 限制说明
