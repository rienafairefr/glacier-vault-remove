import unittest
from threading import Thread
from unittest.mock import Mock, patch

import boto3
import sys

import re

import itertools

import multiprocessing


class Tests(unittest.TestCase):
	def test_mock(self):
		vaultname = 'VAULTNAME'
		vaultarn = 'VAULTARN'
		inventorydate = '2017-04-04T17:14:26Z'
		creationdate = '2016-02-08T21:28:06Z'

		class MockStsClient(object):
			def get_caller_identity(self):
				return {'Account':1}

		def _get_mock_data(narchives):
			for c in '{"VaultARN":"'+vaultarn+'","InventoryDate":"'+inventorydate+'","ArchiveList":[':
				yield c
			first = True
			for i in range(narchives):
				if first:
					first=False
				else:
					yield ','
				for c in '{"ArchiveId":"' + str(i) + '","ArchiveDescription":"","CreationDate":"'+creationdate+'","Size":13865,"SHA256TreeHash":""}':
					yield c
			yield ']'
			yield '}'

		def get_mock_data(narchives):
			for string in _get_mock_data(narchives):
				yield string.encode('utf-8')

		regex = re.compile('bytes\=(\d*)\-(\d*)')
		class MockDataStream(object):
			def __init__(self,range,narchives):
				self.mock_data = get_mock_data(narchives)
				self.range = range

			def read(self,n=-1):
				if n==-1:
					list_data = list(self.mock_data)
					return b''.join(list_data)
				else:
					if self.range is not None:
						if regex.match(self.range):
							pass
					else:
						return b''.join((itertools.islice(self.mock_data,n)))

		deleted = []

		class MockGlacierClient(object):
			removed = False
			def describe_vault(self,vaultName):
				return {'VaultARN':vaultarn}

			def list_jobs(self,vaultName):
				return {'JobList':[{'Action':'InventoryRetrieval','JobId':'1'}]}

			def describe_job(self,vaultName,jobId):
				return {'CreationDate':'2017-05-01','StatusCode':'Succeeded','JobId':'1'}

			def get_job_output(self,vaultName,jobId,range=None):
				return {'body':MockDataStream(range,10)}

			def delete_archive(self,vaultName,archiveId):
				if vaultName == vaultname:
					deleted.append(archiveId)

			def delete_vault(self,vaultName):
				if vaultName == vaultname:
					MockGlacierClient.removed=True

		def mockclient(string):
			if string == 'sts':
				return MockStsClient()
			if string == 'glacier':
				return MockGlacierClient()

		class MockGlacierResource(object):
			pass

		def mockresource(string):
			if string == 'glacier':
				return MockGlacierResource()

		class mockProcess(object):
			def __init__(self,target,args):
				self.target=target
				self.args=args
				self.thread = Thread(target=self.target, args=self.args)

			def start(self):
				self.thread.start()

			def join(self):
				self.thread.join()

		testargs = ["prog", "eu-west-1",vaultname,"2"]
		with patch.object(sys, 'argv', testargs),\
			 patch.object(boto3,'client',mockclient),\
			 patch.object(boto3,'resource',mockresource),\
			 patch.object(multiprocessing,'Process',mockProcess):
			import removeVault
			removeVault.main()

		self.assertEqual(deleted,list(map(str,range(10))))
		self.assertTrue(MockGlacierClient.removed)