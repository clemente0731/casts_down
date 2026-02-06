# 🏗️ 构建和发布指南

本文档说明如何构建和发布 Casts Down 的跨平台二进制文件。

## 📋 前置要求

- Python 3.8+
- pip
- (可选) make

## 🚀 快速开始

### 方式 1：使用 Makefile

```bash
# 安装所有依赖（包括 PyInstaller）
make install

# 构建可执行文件
make build

# 清理构建文件
make clean

# 完整发布流程（清理 + 安装 + 构建）
make release
```

### 方式 2：使用 Python 脚本

```bash
# 安装依赖
pip install -r requirements.txt
pip install pyinstaller

# 构建
python build.py

# 清理
python build.py --clean
```

## 📦 构建产物

构建完成后，可执行文件位于 `release/` 目录：

```
release/
├── casts-down-macos-x64          # macOS Intel
├── casts-down-macos-arm64        # macOS Apple Silicon
├── casts-down-linux-x64          # Linux x64
└── casts-down-windows-x64.exe    # Windows x64
```

## 🧪 测试构建产物

```bash
# macOS / Linux
./release/casts-down-* --help

# Windows
.\release\casts-down-windows-x64.exe --help
```

## 🌐 跨平台构建

### 使用 GitHub Actions（推荐）

1. **创建版本标签**：
```bash
git tag v1.0.0
git push origin v1.0.0
```

2. **自动构建**：
   - GitHub Actions 会自动为所有平台构建
   - 构建产物会上传到 Artifacts
   - Release 会自动创建并附加文件

3. **下载**：
   - 访问 GitHub Releases 页面
   - 下载对应平台的文件

### 手动构建多平台

如果需要手动为多个平台构建：

#### macOS

```bash
# Intel
python build.py

# Apple Silicon (需要在 M1/M2 Mac 上)
python build.py
```

#### Linux

```bash
# 在 Linux 机器上
python build.py
```

或使用 Docker：

```bash
docker run -v $(pwd):/app -w /app python:3.11-slim bash -c "
  apt-get update && apt-get install -y binutils &&
  pip install -r requirements.txt pyinstaller &&
  python build.py
"
```

#### Windows

```bash
# 在 Windows 上
python build.py
```

或使用 Wine（Linux 上交叉编译）：

```bash
# 需要安装 wine 和 Python for Windows
wine python build.py
```

## 📝 构建选项

### PyInstaller 配置

编辑 `casts_down.spec` 自定义构建：

```python
# 添加图标
icon='icon.ico'

# 添加额外数据文件
datas=[
    ('README.md', '.'),
    ('config.yaml', '.'),
]

# 排除不需要的模块
excludes=['tkinter', 'matplotlib']
```

### 优化构建大小

1. **使用 UPX 压缩**（已启用）：
```python
upx=True
```

2. **排除不需要的包**：
```python
excludes=['test', 'unittest', 'pytest']
```

3. **单文件模式**（当前已启用）

## 🔍 故障排除

### 问题：构建失败 - ModuleNotFoundError

**解决方案**：
```bash
# 确保所有依赖已安装
pip install -r requirements.txt
pip install pyinstaller
```

### 问题：可执行文件过大

**解决方案**：
1. 启用 UPX 压缩（在 .spec 文件中）
2. 排除不需要的模块
3. 使用虚拟环境减少依赖

### 问题：可执行文件无法运行

**解决方案**：
```bash
# macOS/Linux - 添加执行权限
chmod +x release/casts-down-*

# macOS - 如果被阻止
xattr -cr release/casts-down-*
```

### 问题：Windows Defender 误报

**解决方案**：
- 这是 PyInstaller 常见问题
- 可以对二进制文件进行代码签名
- 或提交给 Microsoft 进行白名单申请

## 📤 发布流程

### 1. 准备发布

```bash
# 更新版本号
# 编辑 setup.py 和其他相关文件

# 确保所有测试通过
make test

# 清理旧文件
make clean
```

### 2. 构建所有平台

```bash
# 使用 GitHub Actions（推荐）
git tag v1.0.0
git push origin v1.0.0

# 或手动在每个平台上构建
python build.py
```

### 3. 测试构建产物

```bash
# 在每个平台上测试
./release/casts-down-* --help
./release/casts-down-* "https://example.com/podcast.rss" --latest 1
```

### 4. 创建 Release

- 在 GitHub 上创建 Release
- 上传所有平台的二进制文件
- 编写 Release Notes

### 5. 发布

- 发布 Release
- 更新 README.md 的下载链接
- 通知用户

## 🔐 代码签名（可选）

### macOS

```bash
# 使用 Apple Developer 证书签名
codesign --sign "Developer ID Application: Your Name" release/casts-down-macos-*

# 公证
xcrun notarytool submit release/casts-down-macos-*.zip --wait
```

### Windows

```bash
# 使用代码签名证书
signtool sign /f certificate.pfx /p password /t http://timestamp.digicert.com release/casts-down-windows-*.exe
```

## 📊 构建统计

典型构建大小（启用 UPX 压缩）：

- Windows: ~15-20 MB
- macOS: ~18-25 MB
- Linux: ~15-20 MB

构建时间（取决于硬件）：

- 首次构建: 2-5 分钟
- 增量构建: 30-60 秒

## 🤝 贡献

如果你有改进构建流程的建议，欢迎提交 PR！
