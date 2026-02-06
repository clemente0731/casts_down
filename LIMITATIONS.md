# ⚠️ 平台限制说明文档

本文档详细说明各播客平台的技术限制和可行性分析。

---

## 1. 🍎 Apple Podcasts

### ✅ 可行性：完全支持

**实现方式：**
1. 从 Apple Podcasts URL 提取 podcast ID
2. 调用 iTunes Search API: `https://itunes.apple.com/lookup?id={podcast_id}`
3. 从 API 响应中获取 `feedUrl`（RSS 源）
4. 解析 RSS 获取音频 URL

**示例：**
```python
# Apple Podcasts URL
url = "https://podcasts.apple.com/us/podcast/the-daily/id1200361736"

# 提取 ID: 1200361736
# API 请求
api_response = requests.get(
    "https://itunes.apple.com/lookup?id=1200361736&entity=podcast"
)

# 获取 RSS:
# feedUrl: "https://feeds.simplecast.com/54nAGcIl"
```

**风险等级：1/5**
- Apple Podcasts 本质是 RSS 聚合器
- API 稳定，无认证要求
- RSS 源标准化，无 DRM

---

## 2. 🎧 小宇宙（Xiaoyuzhou）

### ⚠️ 可行性：部分支持，有显著限制

**场景 A：播客提供 RSS 源**

✅ **可行**
- 部分播客在详情页底部提供 RSS URL
- 示例：`https://www.xiaoyuzhoufm.com/podcast/{podcast_id}`
- 页面中搜索 "RSS" 或查看源码查找 feed URL
- 使用标准 RSS 解析即可

**场景 B：小宇宙独家播客（无 RSS）**

❌ **严重限制**

**技术障碍：**
1. **音频 URL 加密**
   - 音频 URL 包含签名 token
   - Token 有时效性（通常 1-4 小时）
   - Token 生成算法未公开

2. **反爬机制**
   ```
   - User-Agent 检测
   - Referer 验证
   - 频率限制（Rate Limiting）
   - 可能的设备指纹识别
   ```

3. **需要登录**
   - 部分内容需要小宇宙账号登录
   - Cookie/JWT 认证
   - 可能有会员限制

**示例音频 URL 结构：**
```
https://media.xyzcdn.net/xxxxx.m4a?sign=abc123&expires=1234567890
```

**可能的实现方式（不保证可行）：**
```python
# ⚠️ 此方法可能随时失效
import requests
from bs4 import BeautifulSoup

def get_xiaoyuzhou_audio(episode_url):
    """
    尝试从小宇宙剧集页面提取音频 URL
    警告：可能需要登录，且随时可能失效
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 ...',
        'Referer': 'https://www.xiaoyuzhoufm.com/',
        # 可能需要 Cookie
    }

    response = requests.get(episode_url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')

    # 查找音频标签或 JSON 数据
    audio_tag = soup.find('audio')
    if audio_tag and audio_tag.get('src'):
        return audio_tag['src']

    # 或从页面嵌入的 JSON 提取
    # 具体实现取决于页面结构
    return None
```

**风险等级：4/5**
- 高度依赖页面结构（随时可能变化）
- Token 时效性问题
- 可能触发反爬封禁

**推荐方案：**
- 优先使用提供 RSS 的播客
- 联系播客主获取 RSS 源
- 使用小宇宙官方客户端

---

## 3. 📱 Pocket Casts

### ❌ 可行性：无法直接实现

**问题：**
1. **Pocket Casts 不托管音频**
   - 仅作为播客客户端/聚合器
   - 音频文件在原始播客提供商服务器

2. **无公开 API**
   - 没有官方 API 获取用户订阅
   - 播放列表需要登录

3. **数据源是 RSS**
   - Pocket Casts 自己也是从 RSS 获取数据
   - 直接从原始 RSS 下载更可靠

**解决方案：**
```
用户场景：想下载 Pocket Casts 中订阅的播客

步骤：
1. 在 Pocket Casts 中找到播客详情页
2. 复制播客名称或 URL
3. 在 Apple Podcasts / Google Podcasts 搜索该播客
4. 获取 RSS URL
5. 使用本工具下载
```

**风险等级：5/5（不可行）**

---

## 4. 🌐 其他平台

### Spotify Podcasts
❌ **不可行**
- 音频流加密
- 需要 Premium 账号
- DRM 保护

### Google Podcasts
✅ **可行**
- 本质也是 RSS 聚合器
- 可从页面提取 RSS URL
- 与 Apple Podcasts 类似实现

### 喜马拉雅 FM
⚠️ **部分可行**
- 免费内容可能可以抓取
- 付费内容有 DRM
- 强反爬机制
- 不推荐

---

## 5. ⚡ 通用 RSS 播客

### ✅ 可行性：完全支持（推荐）

**支持的 RSS 格式：**
- RSS 2.0
- Atom（部分）
- iTunes Podcast RSS 扩展

**音频格式支持：**
- MP3
- M4A
- OGG
- WAV
- FLAC

**示例 RSS 源：**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>示例播客</title>
    <item>
      <title>第 1 集</title>
      <enclosure url="https://example.com/episode1.mp3"
                 type="audio/mpeg"
                 length="12345678"/>
    </item>
  </channel>
</rss>
```

**风险等级：1/5**

---

## 📊 总结对比表

| 平台 | 可行性 | 风险等级 | 推荐方式 | 备注 |
|------|--------|----------|----------|------|
| RSS 源 | ✅ 完全可行 | 1/5 | 直接解析 | 最推荐 |
| Apple Podcasts | ✅ 完全可行 | 1/5 | API + RSS | 稳定可靠 |
| Google Podcasts | ✅ 完全可行 | 2/5 | 页面解析 + RSS | 类似 Apple |
| 小宇宙（有 RSS） | ✅ 可行 | 1/5 | RSS | 部分播客支持 |
| 小宇宙（无 RSS） | ⚠️ 困难 | 4/5 | 页面解析 | 不稳定 |
| Pocket Casts | ❌ 不可行 | 5/5 | 转用 RSS | 不托管音频 |
| Spotify | ❌ 不可行 | 5/5 | 官方客户端 | DRM 保护 |
| 喜马拉雅 | ⚠️ 困难 | 4/5 | 不推荐 | 反爬 + DRM |

---

## 🔧 最佳实践

### 1. 优先使用 RSS
- 最标准、最稳定
- 无需担心反爬
- 播客主通常会公开 RSS

### 2. 查找 RSS 源的方法
```bash
# 方法 1: 查看播客官网
# 通常在底部有 RSS 图标

# 方法 2: 使用浏览器插件
# "Get RSS Feed URL" (Chrome)

# 方法 3: 查看页面源码
# 搜索 "application/rss+xml"

# 方法 4: 使用在线工具
# https://getrssfeed.com/
```

### 3. 尊重版权
- 仅供个人学习使用
- 不要再分发
- 支持原创播客主

---

## 📅 知识时间戳

**最后更新：2025-01**

以下信息可能已过期：
- 小宇宙页面结构
- Apple Podcasts API 响应格式
- 各平台反爬策略

建议定期检查官方文档和更新实现。
