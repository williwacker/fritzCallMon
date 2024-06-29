#!/usr/bin/env python

try:
    from setuptools import find_packages, setup
    from setuptools.command.test import test
except ImportError:
    from ez_setup import use_setuptools

    use_setuptools()
    from setuptools import setup, find_packages
    from setuptools.command.test import test

import os

here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, 'README.md'), encoding='utf-8', mode='r') as f:
    long_description = f.read().strip()

setup(
    name='fritzCallMon',
    version='0.3.1',
    author='Werner Kühn',
    author_email='willi1wacker@gmx.de',
    url='http://github.com/williwacker/fritzCallMon',
    description='Monitor incoming and outgoing external calls in the Fritz!Box and do a backward search for the callers name',
    packages=find_packages(),
    long_description=long_description,
    keywords='fritz fritzconnection',
    zip_safe=False,
    install_requires=['Python>=3.8'],
    test_suite='runtests.runtests',
    include_package_data=True,
    classifiers=[
        'Framework :: Python',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Operating System :: OS Independent',
        'Topic :: Software Development',
    ],
)
