from setuptools import setup, find_packages

setup(
    name="yt-downloader",
    version="1.0.0",
    author="Your Name",
    description="A Flask web application for downloading YouTube videos and audio",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.11",
    install_requires=[
        "Flask==3.0.0",
        "yt-dlp>=2026.1.31",
        "gunicorn==21.2.0",    
    ],
)