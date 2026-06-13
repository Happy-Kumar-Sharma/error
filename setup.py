import os
from setuptools import setup, find_packages

def get_requirements(file_path: str) -> list:
    """This function will return the list of packages"""
    print(f"Looking for requirements file at: {os.path.abspath(file_path)}")
    requirements = []
    if os.path.exists(file_path):
        with open(file_path) as file_obj:
            requirements = file_obj.readlines()

        requirements = [
            requirement.replace("\n", "").strip() for requirement in requirements
        ]
        if "-e ." in requirements:
            requirements.remove("-e .")
    return [req for req in requirements if req and not req.startswith("#")]

setup(
    name='pyerror-intel',
    version='0.2.0',
    description='A Python error intelligence library for learners and production systems.',
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="Happy Sharma",
    author_email="happycse54@gmail.com",
    url='https://github.com/Happy-Kumar-Sharma/error',
    project_urls={
        "Bug Tracker": "https://github.com/Happy-Kumar-Sharma/error/issues",
        "Source Code": "https://github.com/Happy-Kumar-Sharma/error",
        "Web Viewer": "https://happy-kumar-sharma.github.io/error/viewer.html",
    },
    packages=find_packages(),
    install_requires=get_requirements("requirements.txt"),
    extras_require={
        "otel": ["opentelemetry-api>=1.20"],
        "ai": [],
        "metrics": ["prometheus-client"],
        "dashboard": ["flask"],
        "structlog": ["structlog"],
        "redis": ["redis"],
        "django": ["django"],
        "celery": ["celery"],
        "rq": ["rq"],
        "dramatiq": ["dramatiq"],
        "sqlalchemy": ["sqlalchemy"],
        "all": [
            "opentelemetry-api>=1.20", "prometheus-client", "flask",
            "structlog",
        ],
    },
    entry_points={
        "console_scripts": [
            "pyerror=pyerror.cli:main",
        ],
        "pytest11": [
            "pyerror=pyerror.pytest_plugin",
        ],
    },
    python_requires='>=3.7',
    license='MIT',
    keywords='error traceback debugger debug humanize logging exception analytics sentry slack flask fastapi',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Intended Audience :: Education',
        'Topic :: Software Development :: Debuggers',
        'Topic :: Software Development :: Quality Assurance',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
)
