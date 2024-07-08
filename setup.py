import os

import setuptools


def get_install_requires():
    install_requires = []

    try:
        import importlib
    except ImportError:
        install_requires.append('importlib')

    try:
        from collections import OrderedDict
    except ImportError:
        install_requires.append('ordereddict')

    return install_requires


here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, 'README.md'), encoding='utf-8', mode='r') as f:
    long_description = f.read().strip()

setuptools.setup(
    name='fritzCallMon',
    version='0.3.3',
    author='Werner Kühn',
    author_email='willi1wacker@gmx.de',
    url='https://github.com/williwacker/fritzCallMon',
    description='Monitor incoming and outgoing external calls in the Fritz!Box and do a backward search for the callers name',
    packages=setuptools.find_packages(),
    long_description=long_description,
    keywords='fritz fritzconnection',
    zip_safe=False,
    install_requires=["fritzconnection", "urllib3", "xmltodict",
                      "certifi", "SpeechRecognition"] + get_install_requires(),
    setup_requires=['setuptools-git-versioning<1.8.0'],
    python_requires='>=3',
    test_suite='runtests.runtests',
    include_package_data=True,
    classifiers=[
        "Programming Language :: Python :: 3",
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Topic :: Software Development',
    ],
)
