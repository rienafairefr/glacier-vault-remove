#!/usr/bin/env python

# -*- coding: UTF-8 -*-

import sys
import json
import time
import os
import logging
import boto3
from multiprocessing import Process, Queue
from socket import gethostbyname, gaierror

queue = Queue(100)
def process_archive(q):
	while True:
		try:
			archive = q.get()
		except:
			time.sleep(5)
			try:
				archive = q.get()
			except:
				break
		if archive['ArchiveId'] != '':
			logging.info('%s Remove archive ID : %s', os.getpid(), archive['ArchiveId'])
			try:
				glacier.delete_archive(
				    vaultName=vaultName,
				    archiveId=archive['ArchiveId']
				)
			except:
				printException()

				logging.info('Sleep 2s before retrying...')
				time.sleep(2)

				logging.info('Retry to remove archive ID : %s', archive['ArchiveId'])
				try:
					glacier.delete_archive(
					    vaultName=vaultName,
					    archiveId=archive['ArchiveId']
					)
					logging.info('Successfully removed archive ID : %s', archive['ArchiveId'])
				except:
					logging.error('Cannot remove archive ID : %s', archive['ArchiveId'])
					break

def printException():
	exc_type, exc_value = sys.exc_info()[:2]
	logging.error('Exception "%s" occured with message "%s"', exc_type.__name__, exc_value)

# Default logging config
logging.basicConfig(format='%(asctime)s - %(levelname)s : %(message)s', level=logging.INFO, datefmt='%H:%M:%S')

# Get arguments
if len(sys.argv) >= 3:
	regionName = sys.argv[1]
	vaultName = sys.argv[2]
else:
	# If there are missing arguments, display usage example and exit
	logging.error('Usage: %s <region_name> [<vault_name>|LIST] [DEBUG] [NUMPROCESS]', sys.argv[0])
	sys.exit(1)

# Get custom logging level
if len(sys.argv) == 4 and sys.argv[3] == 'DEBUG':
	logging.info('Logging level set to DEBUG.')
	logging.getLogger().setLevel(logging.DEBUG)

# Get number of processes
numProcess = 1
if len(sys.argv) == 4:
	if sys.argv[3].isdigit():
		numProcess = int(sys.argv[3])
elif len(sys.argv) == 5:
	if sys.argv[4].isdigit():
		numProcess = int(sys.argv[4])
logging.info('Running with %s processes', numProcess)

os.environ['AWS_DEFAULT_REGION'] = regionName

# Load credentials
try:
	f = open('credentials.json', 'r')
	config = json.loads(f.read())
	f.close()

 	os.environ['AWS_ACCESS_KEY_ID'] = config['AWSAccessKeyId']
	os.environ['AWS_SECRET_ACCESS_KEY'] = config['AWSSecretKey']

except:
	logging.error('Cannot load "credentials.json" file... Assuming Role Authentication.')

sts_client = boto3.client("sts")
accountId = sts_client.get_caller_identity()["Account"]

logging.info("Working on AccountID: {id}".format(id=accountId))

try:
	logging.info('Connecting to Amazon Glacier...')
	glacier = boto3.client('glacier')
except:
	printException()
	sys.exit(1)

if vaultName == 'LIST':
	try:
		logging.info('Getting list of vaults...')
		response = glacier.list_vaults()
	except:
		printException()
		sys.exit(1)

	for vault in response['VaultList']:
		logging.info(vault['VaultName'])

	exit(0)

try:
	logging.info('Getting selected vault... [{v}]'.format(v=vaultName))
	vault = glacier.describe_vault(vaultName=vaultName)
	logging.info("Working on ARN {arn}".format(arn=vault['VaultARN']))
except:
	printException()
	sys.exit(1)

logging.info('Getting jobs list...')
response = glacier.list_jobs(vaultName=vaultName)
jobID = ''

# Check if a job already exists
for job in response['JobList']:
	if job['Action'] == 'InventoryRetrieval':
		logging.info('Found existing inventory retrieval job...')
		jobID = job['JobId']

if jobID == '':
	logging.info('No existing job found, initiate inventory retrieval...')
	try:
		glacier_resource = boto3.resource('glacier')
		vault = glacier_resource.Vault(accountId, vaultName)
		job = vault.initiate_inventory_retrieval()

		jobID = job.id
	except:
		printException()
		sys.exit(1)

logging.info('Job ID : %s', jobID)

# Get job status
job = glacier.describe_job(vaultName=vaultName, jobId=jobID)

logging.info('Job Creation Date: {d}'.format(d=job['CreationDate']))

while job['StatusCode'] == 'InProgress':
	# Job are usualy ready within 4hours of request.
	logging.info('Inventory not ready, sleep for 10 mins...')

	time.sleep(60*10)

	job = glacier.describe_job(vaultName=vaultName, jobId=jobID)

if __name__ == "__main__" and job['StatusCode'] == 'Succeeded':
	logging.info('Inventory retrieved, parsing data...')

	bufferSize = 5*1024*1024

	class InventoryRead(object):
		def __init__(self):
			self.seek=0
		def read(self,n):
			returnvalue = glacier.get_job_output(vaultName=vaultName, jobId=job['JobId'],
												 range='bytes=%d-%d' % (self.seek, self.seek + n))['body'].read(n).decode('utf-8')
			self.seek += n
			return returnvalue

		def get(self):
			if bufferSize==-1:
				job_output = glacier.get_job_output(vaultName=vaultName, jobId=job['JobId'])
				inventory = json.loads(job_output['body'].read().decode('utf-8'))
				for archive in inventory['ArchiveList']:
					yield archive
			else:
				prefix = reader.read(bufferSize)
				archiveList=None
				for i in range(1, bufferSize):
					try:
						schema = json.loads(prefix[0:i] + ']}')
						# Okay, we have our prefix
						archiveList = prefix[i:]
						prefix = prefix[0:i]
						break
					except:
						pass

				if archiveList is None:
					logging.error('Error in the JSON format, can''t stream it from get_job_output')

				while True:
					# read a big block
					archiveList += self.read(bufferSize)
					try:
						inventory = json.loads(prefix+archiveList)
						# if this parses, it means we are at the end of the list
						for archive in inventory['ArchiveList']:
							yield archive
						break
					except:
						for i in range(1,5000):
							# loooping, each loop removes a character until the string is valid json
							try:
								inventory = json.loads(prefix + archiveList[0:-i] + ']}')
								# json parsed okay, we have our json string
								for archive in inventory['ArchiveList']:
									yield archive
								break
							except:
								pass



	reader = InventoryRead()

	jobs = []
	for i in range(numProcess):
		p = Process(target=process_archive, args=(queue,))
		jobs.append(p)
		p.start()

	for archive in reader.get():
		queue.put(archive)

	for j in jobs:
		j.join()

	logging.info('Removing vault...')
	try:
		glacier.delete_vault(
		    vaultName=vaultName
		)
		logging.info('Vault removed.')
	except:
		printException()
		logging.error('We cant remove the vault now. Please wait some time and try again. You can also remove it from the AWS console, now that all archives have been removed.')

else:
	logging.info('Vault retrieval failed.')
