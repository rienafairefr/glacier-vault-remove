#!/usr/bin/env python

# -*- coding: UTF-8 -*-

import sys
import json
import time
import os
import logging
from queue import Empty

import boto3
from multiprocessing import Process, Queue
import shutil

im_done = 'I''m done'
queue = Queue(100)
def process_archive(q,args):
	glacier = get_glacier(args)
	while True:
		try:
			archive = q.get(timeout=10)
		except Empty:
			time.sleep(1)
			continue
		except:
			printException()

		if archive == im_done:
			break

		if archive['ArchiveId'] != '':
			logging.info('%s Remove archive ID : %s', os.getpid(), archive['ArchiveId'])
			try:
				glacier.delete_archive(
				    vaultName=args.vaultName,
				    archiveId=archive['ArchiveId']
				)
			except:
				printException()

				logging.info('Sleep 2s before retrying...')
				time.sleep(2)

				logging.info('Retry to remove archive ID : %s', archive['ArchiveId'])
				try:
					glacier.delete_archive(
					    vaultName=args.vaultName,
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

import argparse

parser = argparse.ArgumentParser(description='Removes a Glavier vault by first removing all archives in it')
parser.add_argument('-regionName',type=str,help='The name of the region')
parser.add_argument('-vaultName',type=str,help='The name of the vault to remove, or LIST to list the vaults')
parser.add_argument('--debug',action='store_true',help='An optional argument to generate debugging log events')
parser.add_argument('-numProcess',type=int,help='The number of processes for treating the archives removal jobs')
parser.add_argument('-bufferSize',type=int,default=-1,help='The size of the buffer, in MiB, to stream json')


def get_glacier(args):
	regionName = args.regionName
	# Get custom logging level
	if args.debug:
		logging.info('Logging level set to DEBUG.')
		logging.getLogger().setLevel(logging.DEBUG)

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

	try:
		logging.info('Connecting to Amazon Glacier...')
		return boto3.client('glacier')

	except:
		printException()
		sys.exit(1)

def main(args):
	vaultName = args.vaultName
	sts_client = boto3.client("sts")
	accountId = sts_client.get_caller_identity()["Account"]

	logging.info("Working on AccountID: {id}".format(id=accountId))

	glacier = get_glacier(args)
	if args.vaultName == 'LIST':
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

	if job['StatusCode'] == 'Succeeded':
		logging.info('Inventory retrieved, parsing data...')

		bufferSize = args.bufferSize*1024*1024

		class InventoryRead(object):
			def __init__(self):
				self.seek=0
			def read(self,n):
				returnvalue = glacier.get_job_output(vaultName=vaultName, jobId=job['JobId'],
													 range='bytes=%d-%d' % (self.seek, self.seek + n))['body'].read(n).decode('utf-8')
				self.seek += n
				return returnvalue

			def get(self):
				if args.bufferSize==-1:
					job_output = glacier.get_job_output(vaultName=vaultName, jobId=job['JobId'])
					with open('job_output_data.json','wb') as f:
						shutil.copyfileobj(job_output['body'],f)
					with open('job_output_data.json','r',encoding='utf-8') as f:
						inventory = json.load(f)
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
						return

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
		for i in range(args.numProcess):
			p = Process(target=process_archive, args=(queue,args,))
			jobs.append(p)
			p.start()

		for archive in reader.get():
			logging.debug('queue put archive: '+str(archive))
			queue.put(archive)

		#put end of work tokens in the queue
		for i in range(args.numProcess):
			queue.put(im_done)

		for j in jobs:
			j.join()

		logging.info('Removing vault...')
		try:
			glacier.delete_vault(
				vaultName=args.vaultName
			)
			logging.info('Vault removed.')
		except:
			printException()
			logging.error('We cant remove the vault now. Please wait some time and try again. You can also remove it from the AWS console, now that all archives have been removed.')

	else:
		logging.info('Vault retrieval failed.')

if __name__ == '__main__':
	arguments = parser.parse_args()
	main(arguments)
