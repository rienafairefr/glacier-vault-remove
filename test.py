import unittest
from collections import namedtuple
from threading import Thread
try:
	from unittest.mock import Mock, patch
except ImportError:
	from mock import Mock, patch

import boto3
import sys
import re
import itertools
import multiprocessing

vaultname = 'VAULTNAME'
vaultarn = 'VAULTARN'
accountid = 'ACCOUNTID'
inventorydate = '2017-04-04T17:14:26Z'
creationdate = '2016-02-08T21:28:06Z'

class MockStsClient(object):
	def get_caller_identity(self):
		return {'Account': accountid}


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


class MockGlacierClient(object):
	def __init__(self, narchives):
		results.reset()
		self.narchives = narchives

	def describe_vault(self, vaultName):
		return {'VaultARN': vaultarn}

	def list_jobs(self, vaultName):
		return {'JobList': [{'Action': 'InventoryRetrieval', 'JobId': '1'}]}

	def describe_job(self, vaultName, jobId):
		return {'CreationDate': '2017-05-01', 'StatusCode': 'Succeeded', 'JobId': '1', 'InventorySizeInBytes':Narchives*10}

	def get_job_output(self, vaultName, jobId, range=None):
		return {'body': MockDataStream(range, self.narchives)}

	def delete_archive(self, vaultName, archiveId):
		if vaultName == vaultname:
			results.deleted.append(archiveId)

	def delete_vault(self, vaultName):
		if vaultName == vaultname:
			results.removed = True

Narchives=10

def mockclient(string):
	if string == 'sts':
		return MockStsClient()
	if string == 'glacier':
		return MockGlacierClient(Narchives)


class MockGlacierResource(object):
	pass



class mockProcess(object):
	def __init__(self, target, args):
		self.target = target
		self.args = args
		self.thread = Thread(target=self.target, args=self.args)

	def start(self):
		self.thread.start()

	def join(self):
		self.thread.join()

	@property
	def _identity(self):
		return ()

try:
	from Queue import Queue, Empty
except:
	from queue import Queue, Empty

class mockManager(object):
	q = Queue(100)
	def Queue(self,size):
		return self.q

TestArgumentsrm = namedtuple("TestArguments",['regionName','command','vaultName','numProcess','debug','bufferSize'])
TestArgumentsls = namedtuple("TestArguments",['regionName','command','debug'])
testargs = TestArgumentsrm("eu-west-1", 'rm', vaultname, 2, True,'-1')
testargs_buffer = TestArgumentsrm("eu-west-1", 'rm',vaultname, 2, True, '1M')
testargs_buffer_large_data = TestArgumentsrm("eu-west-1", 'rm',vaultname, 1, True, '100B')
testargs3 = TestArgumentsls("eu-west-1", 'ls',True)


class Tests(unittest.TestCase):
	def setUp(self):
		results.reset()

	def test_mock(self):
		print('test_mock')
		with patch.object(boto3,'client',mockclient):
			with patch.object(multiprocessing,'Process',mockProcess):
				with patch.object(multiprocessing, 'Manager', mockManager):
					import glacier_vault
					glacier_vault.main(testargs)

		self.assertTrue(checkEqual(results.deleted,list(map(str,range(Narchives)))),msg='Actually deleted:'+str(results.deleted))
		self.assertTrue(results.removed)

	def test_remove_vault_exception(self):
		print('test_remove_vault_exception')
		class newMockGlacierClient(MockGlacierClient):
			def delete_vault(self, vaultName):
				raise Exception()


		MockGlacierClient.removed=False

		with patch.object(boto3, 'client', mockclient):
			with patch.object(multiprocessing, 'Process', mockProcess):
				with patch('test.MockGlacierClient',newMockGlacierClient):
					with patch.object(multiprocessing, 'Manager', mockManager):
						import glacier_vault
						glacier_vault.main(testargs)

			self.assertTrue(checkEqual(results.deleted, list(map(str, range(Narchives)))),msg='Actually deleted:'+str(results.deleted))
		self.assertFalse(MockGlacierClient.removed)

	def test_mock_with_buffer(self):
		print('test_mock_with_buffer')
		with patch.object(boto3,'client',mockclient):
			with patch.object(multiprocessing,'Process',mockProcess):
				with patch.object(multiprocessing,'Manager',mockManager):
					import glacier_vault
					glacier_vault.main(testargs_buffer)

		self.assertTrue(checkEqual(results.deleted,list(map(str,range(Narchives)))),msg='Actually deleted:'+str(results.deleted))
		self.assertTrue(results.removed)

	def test_mock_with_buffer_large_data(self):
		def mockclient2(string):
			if string == 'sts':
				return MockStsClient()
			if string == 'glacier':
				return MockGlacierClient(Narchives)
		print('test_mock_with_buffer_large_data')
		with patch.object(boto3,'client',mockclient2):
			with patch.object(multiprocessing,'Process',mockProcess):
				with patch.object(multiprocessing, 'Manager', mockManager):
					import glacier_vault
					glacier_vault.main(testargs_buffer_large_data)

		self.assertTrue(checkEqual(results.deleted,list(map(str,range(Narchives)))),msg='Actually deleted:'+str(results.deleted))
		self.assertTrue(results.removed)

	def test_list_vaults(self):
		class MockGlacierClient2(object):
			def list_vaults(self):
				self.called=True
				return {'VaultList':[{'VaultName':vaultname}]}
		client = MockGlacierClient2()
		client.called=False
		def mockclient2(string):
			if string == 'sts':
				return MockStsClient()
			if string == 'glacier':
				return client
		print('test_mock_with_buffer_large_data')
		with patch.object(boto3,'client',mockclient2):
			with patch.object(multiprocessing,'Process',mockProcess):
				with patch.object(multiprocessing, 'Manager', mockManager):
					import glacier_vault
					try:
						glacier_vault.main(testargs3)
					except SystemExit:
						pass

		self.assertTrue(client.called)

	def test_inventory_retrieval(self):
		class MockGlacierClient3(object):
			def list_jobs(s,vaultName):
				self.assertEqual(vaultName, vaultname)
				return {'JobList':[]}
			def describe_vault(s, vaultName):
				self.assertEqual(vaultName, vaultname)
				return {'VaultARN': vaultarn}

		def mockclient2(string):
			if string == 'sts':
				return MockStsClient()
			if string == 'glacier':
				return MockGlacierClient3()
		class MockVault(object):
			called = False
			def initiate_inventory_retrieval(self):
				MockVault.called=True
		class MockGlacierResource2(object):
			def Vault(s,accountId,vaultName):
				self.assertEqual(accountId, accountid)
				self.assertEqual(vaultName, vaultname)
				return MockVault()
		def mockresource2(string):
			if string == 'glacier':
				return MockGlacierResource2()
		print('test_mock_with_buffer_large_data')
		with patch.object(boto3,'client',mockclient2):
			with patch.object(boto3,'resource',mockresource2):
				with patch.object(multiprocessing,'Process',mockProcess):
					with patch.object(multiprocessing, 'Manager', mockManager):
						import glacier_vault
						try:
							glacier_vault.main(testargs)
						except SystemExit:
							pass
		self.assertTrue(MockVault.called)

if __name__ == '__main__':
	unittest.main()