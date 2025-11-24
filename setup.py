from setuptools import setup, find_packages

setup(
    name="shimo",
    version="0.0.1",
    package_dir={"": "src"},
    packages=["shimo3"],
    #find_packages(where="saudefense"),  # Specify saudefense directory
    #,  # Tell setuptools that packages are under saudefense
    install_requires=[
        "pygame",
        "python-telegram-bot==20.3",
        "pyyaml",
        "python-telegram-bot[job-queue]"
    ],
    author="Danilo Tardioli",
    author_email="dantard@unizar.es",
    description="A Slideshow integrated with Telegram to display images received via bot.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/dantard/shimo3",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.10',
    entry_points={
        "console_scripts": [
            "shimo=shimo3.shimo:main",
        ]
    }
)
