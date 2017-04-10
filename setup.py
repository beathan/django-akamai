#!/usr/bin/env python
# -*- coding: utf-8 -*-
from setuptools import setup

setup(
    name='django-akamai',
    use_scm_version=True,
    description='A Django app for performing Akamai purge requests',
    author='Ben Boyd',
    author_email='beathan@gmail.com',
    long_description=open('README.rst', 'r').read(),
    url='https://github.com/beathan/django-akamai',
    packages=['django_akamai'],
    install_requires=[
        'requests[security]',
        'edgegrid-python',
    ],
    setup_requires=[
        'setuptools_scm',
    ]
)
