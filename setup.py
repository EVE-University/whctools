import os

from setuptools import find_packages, setup

# from lootsheet import __version__

__version__ = "0.0.1beta"

with open(os.path.join(os.path.dirname(__file__), "README.md")) as readme:
    README = readme.read()

os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

install_requires = ["allianceauth", "aa-memberaudit"]

setup(
    name="whctools",
    version=__version__,
    packages=find_packages(),
    include_package_data=True,
    exclude_package_data={"": ["images"]},
    license="GNU General Public License v3 (GPLv3)",
    description="Alliance Auth Lootsheet Management Plugin",
    install_requires=install_requires,
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/EveUniversity/whctools",
    author="lynkfox",
    author_email="lynkfox@gmail.com",
    classifiers=[
        "Environment :: Web Environment",
        "Framework :: Django",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.11",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
    ],
)
