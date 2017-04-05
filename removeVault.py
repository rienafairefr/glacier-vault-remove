#!/usr/bin/env python

# -*- coding: UTF-8 -*-

import sys
import json
import time
import os
import logging
import boto3
from multiprocessing import Process

suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
def humansize(nbytes):
    if nbytes == 0: return '0 B'
    i = 0
    while nbytes >= 1024 and i < len(suffixes) - 1:
        nbytes /= 1024.
        i += 1
    f = ('%.2f' % nbytes).rstrip('0').rstrip('.')
    return '%s %s' % (f, suffixes[i])

def split_list(alist, wanted_parts=1):
    length = len(alist)
    return [ alist[i*length // wanted_parts: (i+1)*length // wanted_parts]
        for i in range(wanted_parts) ]

def process_archive(archive_list):
    worker_pid = os.getpid()
    n_archives = len(archive_list)
    logging.info('Starting work on %s items',n_archives)
    for index, archive in enumerate(archive_list):
        if archive['ArchiveId'] != '':
            logging.info('%s Remove archive number %s of %s, ID : %s', worker_pid, index, n_archives, archive['ArchiveId'])
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
    logging.info('%s Ended work on %s items',worker_pid,n_archives)


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
    logging.error('Usage: %s <region_name> [<vault_name>|LIST] [DEBUG] [NUMPROCESS] [BLOCKSIZE]', sys.argv[0])
    sys.exit(1)


# Get custom logging level
if sys.argv[3] == 'DEBUG':
    logging.info('Logging level set to DEBUG.')
    logging.getLogger().setLevel(logging.DEBUG)

numProcess = 1
# Get number of processes
if sys.argv[3] == 'DEBUG':
    if len(sys.argv) >= 5:
        if sys.argv[4].isdigit():
            numProcess = int(sys.argv[4])
else:
    if len(sys.argv) >= 4:
        if sys.argv[3].isdigit():
            numProcess = int(sys.argv[3])

bufferSize_MB = -1
# Get bufferSize
if sys.argv[3] == 'DEBUG':
    if len(sys.argv) >= 6:
        if sys.argv[5].isdigit():
            bufferSize_MB = int(sys.argv[5])
else:
    if len(sys.argv) >= 5:
        if sys.argv[4].isdigit():
            bufferSize_MB = int(sys.argv[4])

logging.info('Running with %s processes', numProcess)

if bufferSize_MB==-1:
    logging.info('Reading the inventory all at once')
else:
    logging.info('Streaming the inventory in blocks of %s MB', bufferSize_MB)

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

def treat_inventory(archiveList):
    logging.info('Removing %s archives... please be patient, this may take some time...', len(archiveList))
    archiveParts = split_list(archiveList, numProcess)
    jobs = []

    for archive in archiveParts:
        p = Process(target=process_archive, args=(archive,))
        jobs.append(p)
        p.start()

    for j in jobs:
        j.join()
    logging.info('all workers finished')

def remove_vault():
    logging.info('Removing vault...')
    try:
        glacier.delete_vault(
            vaultName=vaultName
        )
        logging.info('Vault removed.')
    except:
        printException()
        logging.error('We cant remove the vault now. Please wait some time and try again. You can also remove it from the AWS console, now that all archives have been removed.')

class Reader(object):
    def __init__(self):
        self.seek = 0

    def read(self,n):
        logging.info('range %u-%u',self.seek,self.seek+n)
        returnvalue = glacier.get_job_output(vaultName=vaultName, jobId=job['JobId'],range='bytes=%d-%d'%(self.seek,self.seek+n))['body'].read(n).decode('utf-8')
        self.seek += n
        return returnvalue

if __name__ == '__main__':
    if job['StatusCode'] == 'Succeeded':
        logging.info('Inventory retrieved, parsing data...')
        job_size = job['InventorySizeInBytes']

        if bufferSize_MB==-1:
            inventory = glacier.get_job_output(vaultName=vaultName, jobId=job['JobId'])['body'].read().decode('utf-8')
            treat_inventory(inventory)
            remove_vault()
            exit(0)

        bufferSize = bufferSize_MB * 1024 * 1024
        reader = Reader()

        logging.info(
            'Streaming a %s archives list in blocks of roughly %s ' % (humansize(job_size), humansize(bufferSize)))

        prefix = reader.read(bufferSize)
        for i in range(1,bufferSize):
            try:
                schema = json.loads(prefix[0:i] + ']}')
                # Okay, we have our prefix
                archiveList=prefix[i:]
                prefix = prefix[0:i]
                break
            except:
                pass
        if 'ArchiveList' not in schema:
            logging.error('Couldnt retrieve inventory, expecting ArchiveList key in job output')

        open('archiveList', 'w').write(archiveList)
        pass
        average_object_size = 460
        is_last = False


        def get_data():

        while True:
            testparse = prefix + archiveList
            try:
                inventory = json.loads(testparse)
                #last case
                is_last=True
            except:
                for i in range(1,5000):
                    toparse = prefix + archiveList[:-i] + ']}'
                    #open('toparse.json','w').write(toparse)
                    logging.debug('Trying to parse json length %u %s [...] %s ', len(toparse), toparse[:100], toparse[-100:])
                    try:
                        inventory = json.loads(toparse)
                        # OK found a json parsable
                        archiveList = archiveList[-i+1:]
                        archiveList += reader.read(bufferSize)
                        break
                    except:
                        pass


            #treat_inventory(inventory['ArchiveList'])
            logging.info('treating an inventory of %u items', len(inventory['ArchiveList']))
            # treat_inventory(inventory['ArchiveList'])
            # read a big block
            if is_last:
                break

