[![Build Status](https://travis-ci.org/rienafairefr/glacier-vault-remove.svg?branch=master)](https://travis-ci.org/rienafairefr/glacier-vault-remove)
[![Coverage Status](https://coveralls.io/repos/github/rienafairefr/glacier-vault-remove/badge.svg?branch=master)](https://coveralls.io/github/rienafairefr/glacier-vault-remove?branch=master)
glacier-vault-remove-stream
======================

This tool can help you with Amazon Glacier vaults, mainly by removing one even if it's not empty.

It will remove all archives contained inside the vault, and then remove the vault itself.

It is intended to work well with vaults containing a LOT of archives. It was developed because of a  vault containing
more than 500'000 archives, and all other softwares crashed when trying to remove all of them.

The inventory can be streamed from amazon's servers, which permits to use this even when RAM is limited (by
 not loading a potentially huge json data all at once in memory)

## Install

Clone the repo and execute

```shell
python setup.py install
```

Or install with

 ```shell
pip install pyGlacierVault
```

## Configure

Then create a `credentials.json` file in the current directory:

```json
{
	"AWSAccessKeyId": "YOURACCESSKEY",
	"AWSSecretKey":   "YOURSECRETKEY"
}
```

## Use

You can then use the script like this :

```shell
python .\glaciervault.py <region-name> (ls|rm) [...]
```

Example :

```shell
python .\removeVault.py eu-west-1 rm my_vault
```

Or if you want to perform the removal using multiple processes (4 processes here) :

```shell
python .\removeVault.py eu-west-1 rm my_vault 4
```

## List

If you don't know the vault name, you can generate a list like this:

```shell
python .\removeVault.py eu-west-1 ls
```

## JSON streaming

By default, inventory is retrieved in full, and json loaded in memory all at once. If that fails because your vault contains too many archives
you can specify a buffer size to stream the json, use a 'human' name for the bytes, like:

```shell
python .\removeVault.py eu-west-1 rm my_vault 4 1M
```

to buffer stream the inventory by blocks of 1 MegaBytes

## Debug

By default, only the INFO messages will be printed to console. You can add a --debug argument to the removeVault.py script
if you want to show all messages.

Example :

```shell
python .\removeVault.py eu-west-1 rm my_vault --debug
```

## Running the Docker container

If you don't want to install all dependencies locally you can also build and use the Docker container supplied with this package.

Step 1) make sure you have docker installed and run

```
docker build -t py-glaciervault .
```

Step 2) Create a credentials.json as described above

Step 3) Run the tool in the docker container:

```
docker run -v /path/to/credentials.json:/app/credentials.json glaciervault <region> (ls|rm) [...]
```

Make sure you use the _full_ absolute path to `credentials.json`, relative paths do not work here.

Licence
======================
(The MIT License)

Copyright (C) 2013 Leeroy Brun, www.leeroy.me

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

