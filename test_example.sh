#!/bin/bash
# 测试脚本示例

echo "🧪 测试 Podcast Downloader"
echo "=========================="
echo ""

# 测试 1: NPR Up First (可靠的测试源)
echo "📝 测试 1: 下载 NPR Up First 最新一集"
python podcast_dl.py "https://feeds.npr.org/510318/podcast.xml" --latest 1 -o ./test_downloads

echo ""
echo "=========================="
echo ""

# 测试 2: The Daily from Apple Podcasts
echo "📝 测试 2: 从 Apple Podcasts 下载 The Daily"
python podcast_dl.py "https://podcasts.apple.com/us/podcast/the-daily/id1200361736" --latest 1 -o ./test_downloads

echo ""
echo "=========================="
echo ""

# 测试 3: 并发下载多集
echo "📝 测试 3: 并发下载多集"
python podcast_dl.py "https://feeds.npr.org/510318/podcast.xml" --latest 3 --concurrent 2 -o ./test_downloads --skip-existing

echo ""
echo "✅ 测试完成！检查 ./test_downloads 目录"
