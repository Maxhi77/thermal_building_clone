#! /usr/bin/env python
# -*- encoding: utf-8 -*-

from glob import glob
from os.path import basename, join, splitext
from setuptools import find_packages, setup
import os


def read(fname):

    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name="oemof.thermal_building_model",
    version="0.0.1.dev",
    author="oemof developer group",
    author_email="contact@oemof.org",
    description=(
        "Thermal building mode for the open energy modelling framework."),
    url="https://github.com/Maxhi77/thermal-building-model",  # todo add correct adress
    long_description=read("README.rst"),
    long_description_content_type="text/x-rst",
    packages=find_packages("src"),
    package_dir={"": "src"},
    py_modules=[splitext(basename(path))[0] for path in glob("src/*.py")],
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "oemof.solph",
        "matplotlib",
        "numpy >= 1.16.5",
        "pandas >= 0.18.0",
    ],
    package_data={
        "demandlib": [join("bdew_data", "*.csv")],
    },
    extras_require={
        "dev": ["pytest", "sphinx", "sphinx_rtd_theme", "matplotlib"],
    },
)
