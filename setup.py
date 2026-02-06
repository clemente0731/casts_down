from setuptools import setup

setup(
    name='podcast-dl',
    version='1.0.0',
    py_modules=['podcast_dl'],
    install_requires=[
        'aiohttp>=3.8.0',
        'beautifulsoup4>=4.11.0',
        'click>=8.1.0',
        'feedparser>=6.0.10',
        'requests>=2.28.0',
        'tqdm>=4.65.0',
    ],
    entry_points={
        'console_scripts': [
            'podcast-dl=podcast_dl:main',
        ],
    },
    python_requires='>=3.8',
    author='Podcast Downloader',
    description='A CLI tool to download podcasts from RSS feeds',
    long_description=open('README.md').read() if __name__ == '__main__' else '',
    long_description_content_type='text/markdown',
)
