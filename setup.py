#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from setuptools import setup, find_packages
import json

setup(
    name = "pyglaciervault",
    version = "0.2rc10",
    packages = find_packages(),

    # Project uses reStructuredText, so ensure that the docutils get
    # installed or upgraded on the target machine
    install_requires = ['boto3>=1.4.4'],

    # metadata for upload to PyPI
    author = "Leeroy Brun - json streaming from Matthieu Berthomé",
	author_email="leeroy.brun@gmail.com -- rienafairefr@gmail.com",
	description = "Tool used to remove all archives stored inside an Amazon Glacier vault.",
    license = "MIT",
    keywords = "aws amazon glacier boto archives vaults",
    url = "https://github.com/rienafairefr/glacier-vault-remove",
	py_modules = ['glacier_vault'],
	entry_points={
		'console_scripts':['glaciervault = glacier_vault:_main']
	}
)

with open("credentials.json", "w") as outfile:
    json.dump({'AWSAccessKeyId': '<key>', 'AWSSecretKey': '<secretkey>'}, outfile, indent=4)
