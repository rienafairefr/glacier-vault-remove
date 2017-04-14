import unittest
from collections import namedtuple
from threading import Thread
from unittest.mock import Mock, patch

import boto3
import sys
import re
import itertools
import multiprocessing

vaultname = 'VAULTNAME'
vaultarn = 'VAULTARN'
inventorydate = '2017-04-04T17:14:26Z'
creationdate = '2016-02-08T21:28:06Z'

class MockStsClient(object):
	def get_caller_identity(self):
		return {'Account': 1}


def _get_mock_data(narchives):
	for c in '{"VaultARN":"' + vaultarn + '","InventoryDate":"' + inventorydate + '","ArchiveList":[':
		yield c
	first = True
	for i in range(narchives):
		if first:
			first = False
		else:
			yield ','
		for c in '{"ArchiveId":"' + str(
				i) + '","ArchiveDescription":"","CreationDate":"' + creationdate + '","Size":13865,"SHA256TreeHash":""}':
			yield c
	yield ']'
	yield '}'


def get_mock_data(narchives):
	for string in _get_mock_data(narchives):
		yield string.encode('utf-8')


regex = re.compile('bytes\=(\d*)\-(\d*)')


class MockDataStream(object):
	def __init__(self, range, narchives):
		self.mock_data = get_mock_data(narchives)
		self.range = range

	def read(self, n=-1):
		if n == -1:
			list_data = list(self.mock_data)
			return b''.join(list_data)
		else:
			if self.range is not None:
				regex_match = regex.match(self.range)
				if regex_match:
					start = int(regex.match(self.range).groups()[0])
					stop = int(regex.match(self.range).groups()[1])
					data = b''.join((itertools.islice(self.mock_data, start, stop)))
					print('data '+str(data))
					return data
			else:
				data = b''.join((itertools.islice(self.mock_data, n)))
				print('data ' + str(data))
				return data


def checkEqual(L1, L2):
	return len(L1) == len(L2) and sorted(L1) == sorted(L2)

class Results(object):
	def __init__(self):
		self.removed = False
		self.deleted = []
	def reset(self):
		self.removed = False
		self.deleted = []

results = Results()

Narchives = 10

class MockGlacierClient(object):
	def __init__(self):
		results.reset()

	def describe_vault(self, vaultName):
		return {'VaultARN': vaultarn}

	def list_jobs(self, vaultName):
		return {'JobList': [{'Action': 'InventoryRetrieval', 'JobId': '1'}]}

	def describe_job(self, vaultName, jobId):
		return {'CreationDate': '2017-05-01', 'StatusCode': 'Succeeded', 'JobId': '1'}

	def get_job_output(self, vaultName, jobId, range=None):
		return {'body': MockDataStream(range, Narchives)}

	def delete_archive(self, vaultName, archiveId):
		if vaultName == vaultname:
			results.deleted.append(archiveId)

	def delete_vault(self, vaultName):
		if vaultName == vaultname:
			results.removed = True

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
	def __init__(self, target, args):
		self.target = target
		self.args = args
		self.thread = Thread(target=self.target, args=self.args)

	def start(self):
		self.thread.start()

	def join(self):
		self.thread.join()

TestArguments = namedtuple("TestArguments",['regionName','vaultName','numProcess','debug','bufferSize'])
testargs = TestArguments("eu-west-1", vaultname,2, True,-1)
testargs2 = TestArguments("eu-west-1", vaultname,2, True,1)



class Tests(unittest.TestCase):
	def setUp(self):
		results.reset()

	def test_mock(self):
		print('test_mock')
		with patch.object(boto3,'client',mockclient),\
			 patch.object(boto3,'resource',mockresource),\
			 patch.object(multiprocessing,'Process',mockProcess):
			import removeVault
			removeVault.main(testargs)

		self.assertTrue(checkEqual(results.deleted,list(map(str,range(Narchives)))),msg='Actually deleted:'+str(results.deleted))
		self.assertTrue(results.removed)

	def test_remove_vault_exception(self):
		print('test_remove_vault_exception')
		class newMockGlacierClient(MockGlacierClient):
			def delete_vault(self, vaultName):
				raise Exception()


		MockGlacierClient.removed=False

		with patch.object(boto3, 'client', mockclient), \
			 patch.object(boto3, 'resource', mockresource), \
			 patch.object(multiprocessing, 'Process', mockProcess), \
		     patch('test.MockGlacierClient',newMockGlacierClient):
			import removeVault
			removeVault.main(testargs)

			self.assertTrue(checkEqual(results.deleted, list(map(str, range(Narchives)))),msg='Actually deleted:'+str(results.deleted))
		self.assertFalse(MockGlacierClient.removed)

	def test_mock_with_buffer(self):
		print('test_mock_with_buffer')
		with patch.object(boto3,'client',mockclient),\
			 patch.object(boto3,'resource',mockresource),\
			 patch.object(multiprocessing,'Process',mockProcess):
			import removeVault
			removeVault.main(testargs2)

		self.assertTrue(checkEqual(results.deleted,list(map(str,range(Narchives)))),msg='Actually deleted:'+str(results.deleted))
		self.assertTrue(results.removed)