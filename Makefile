.PHONY: help install build clean release test

help:
	@echo "Casts Down - 播客下载工具"
	@echo ""
	@echo "可用命令:"
	@echo "  make install    - 安装依赖"
	@echo "  make build      - 构建可执行文件"
	@echo "  make clean      - 清理构建文件"
	@echo "  make release    - 构建发布版本"
	@echo "  make test       - 测试工具"
	@echo ""

install:
	@echo "📦 安装依赖..."
	pip install -r requirements.txt
	pip install pyinstaller
	@echo "✓ 安装完成"

build:
	@echo "🔨 构建可执行文件..."
	python build.py
	@echo "✓ 构建完成"

clean:
	@echo "🧹 清理构建文件..."
	python build.py --clean
	rm -rf __pycache__ *.pyc
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ 清理完成"

release: clean install build
	@echo "✨ 发布版本已准备完成"
	@echo "📦 查看 release/ 目录"

test:
	@echo "🧪 运行测试..."
	python casts_down.py --help
	@echo "✓ 测试通过"
