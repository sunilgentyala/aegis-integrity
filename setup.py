import re
from pathlib import Path
from setuptools import setup, find_packages

_version_match = re.search(
    r'^__version__\s*=\s*"([^"]+)"',
    Path(__file__).parent.joinpath("aegis", "__init__.py").read_text(encoding="utf-8"),
    re.MULTILINE,
)
VERSION = _version_match.group(1)

setup(
    name="aegis-integrity",
    version=VERSION,
    description=(
        "Open-source, offline, bias-aware academic integrity checker: "
        "plagiarism, AI content detection, LLM watermark detection, "
        "citation integrity & network analysis, stylometric authorship "
        "profiling, semantic coherence analysis, and batch classroom scanning."
    ),
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="Sunil Gentyala",
    author_email="sunil.gentyala@ieee.org",
    url="https://github.com/sunilgentyala/aegis-integrity",
    project_urls={
        "Homepage": "https://sunilgentyala.github.io/aegis-integrity",
        "Bug Tracker": "https://github.com/sunilgentyala/aegis-integrity/issues",
        "Documentation": "https://sunilgentyala.github.io/aegis-integrity",
    },
    license="MIT",
    packages=find_packages(exclude=["tests*"]),
    python_requires=">=3.10",
    install_requires=[
        # Security-floor rationale for the bumps below lives in
        # requirements.txt (same package list, same CVE citations).
        "PyMuPDF>=1.26.7",
        "python-docx>=1.1.0",
        "TexSoup>=0.3.1",
        "datasketch>=1.6.4",
        "scikit-learn>=1.4.0",
        "requests>=2.32.2",
        "fastapi>=0.115.0",
        "starlette>=0.47.2",
        "uvicorn[standard]>=0.29.0",
        "python-multipart>=0.0.18",
        "jinja2>=3.1.6",
        "pydantic>=2.7.0",
        "python-dotenv>=1.0.1",
        "tqdm>=4.66.4",
        "click>=8.1.7",
        "rich>=13.7.1",
        "numpy>=1.26.0",
    ],
    extras_require={
        "ml": [
            "sentence-transformers>=3.0.0",
            "faiss-cpu>=1.8.0",
            "transformers>=4.48.0",
            "torch>=2.6.0",
            "langdetect>=1.0.9",
        ],
        "nlp": [
            "nltk>=3.8.1",
            "spacy>=3.7.0",
            "textstat>=0.7.3",
        ],
        "bib": [
            "bibtexparser>=1.4.0",
            "habanero>=1.2.3",
        ],
    },
    entry_points={
        "console_scripts": [
            "aegis=aegis.cli:cli",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Science/Research",
        "Intended Audience :: Education",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Text Processing :: Linguistic",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Education",
    ],
    keywords=[
        "academic integrity", "plagiarism detection", "AI content detection",
        "citation verification", "ghostwriting detection", "LLM watermark",
        "stylometrics", "essay mill", "self-plagiarism", "OpenAlex",
    ],
)
