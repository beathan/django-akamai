#!/usr/bin/env python
# -*- coding: utf-8 -*-
from setuptools import setup

setup(
    name='django-akamai',
    version='0.0.1',
    description='A Django app for performing Akamai CCUAPI purge requests',
    author='Ben Boyd',
    author_email='beathan@gmail.com',
    long_description=open('README.rst', 'r').read(),
    url='https://github.com/beathan/django-akamai',
    packages=['django_akamai'],
    requires=['suds'],

    # We need to include our WSDL file which means that we can't be installed
    # as an egg and must include a non-Python resource:
    include_package_data=True,
    zip_safe=False,
)
