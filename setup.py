import setuptools
import os

here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, 'README.md'), encoding='utf-8', mode='r') as f:
    long_description = f.read().strip()

setuptools.setup(
    name='fritzCallMon',
    version='0.3.1',
    author='Werner Kühn',
    author_email='willi1wacker@gmx.de',
    url='http://github.com/williwacker/fritzCallMon',
    description='Monitor incoming and outgoing external calls in the Fritz!Box and do a backward search for the callers name',
    packages=setuptools.find_packages(),
    long_description=long_description,
    keywords='fritz fritzconnection',
    zip_safe=False,
    install_requires=['fritzconnection>=1.4.0'],
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
