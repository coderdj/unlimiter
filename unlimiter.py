import time
import configparser
import argparse
import datetime
import os
import json
import shutil

from pymongo import MongoClient

def ClearRun(run_number, directory):
    # Delete a run. Careful with this guy!
    fn = str(run_number).zfill(6)
    path = os.path.join(directory['path'], fn)

    # Make sure we can find a run doc with this entry
    run_doc = coll.find_one({"number": run_number})
    if run_doc is None:
        print("Not clearing run %i because can't find in runs DB"%run_number)
        return -1
    dentry = None
    for entry in run_doc['data']:
        if (entry['host'] == directory['host'] and
            entry['location'] == directory['path'] and
            entry['type'] == directory['type']):
            dentry = entry
    if dentry is None:
        print("Not clearing run %i because can't find data entry"%run_number)
        return -2
    if 'save' in dentry:
        print("Not clearing run %i because it is marked as 'save'"%run_number)
        return -3
    
    # Nobody tell me not to... time to "unlimit" this data!
    print("%s: Run %i from path %s is being unlimited"%(datetime.datetime.utcnow(), run_number, path))
    shutil.rmtree(path)
    print("%s: Finished run %i!"%(datetime.datetime.utcnow(), run_number))

    coll.update_one({"number": run_number, "data.type": dentry['type'],
                     "data.host": dentry['host'], "data.location": dentry['location']},
                    {"$set": {"data.$.status": "unlimited"}})
    

# Parse command line
parser = argparse.ArgumentParser(description='Destroy your limit but keep the DAQ running')
parser.add_argument('--config', type=str, help='Path to your configuration file')
args = parser.parse_args()
config = configparser.ConfigParser()
cfile = args.config
if cfile is None:
    cfile = 'config.ini'
config.read(cfile)

# Establish MongoDB Connection
client = MongoClient(config['base']['RunsURI']%os.environ[config['base']['RunsPassEnv']])
coll = client[config['base']['RunsDBName']][config['base']['RunsDBCollection']]

# Main program loop. Run until ctl+c'd
sleep_iter = 60
iteration = 0
while(1):
    iteration += 1
    print("%s: Program iteration %i, press Ctl+C to quit"%(datetime.datetime.utcnow(), iteration))

    for item in config.items('directories'):
        directory = json.loads(item[1])

        # Found some files that are not actually numbers. Nuke those babies right away
        rfiles = list(os.listdir(directory['path']))
        files = []
        for f in rfiles:
            try:
                files.append(int(f))
            except:                
                print("Untracked file found in directory: '%s'"%f)
        files.sort(reverse=False)

        # We now have a list of run numbers sorted oldest to newest
        for run_number in files:

            # Are we checking for free space?
            if (directory['space_free_frac'] is not None and
                directory['space_free_frac'] != 0):
                usage = shutil.disk_usage(directory['path'])
                pct_free = float(usage.free)/float(usage.total)
                if pct_free < directory['space_free_frac']:
                    print("Found %.2f%% pct free but want %.2f%%... Clearing run %i."%(pct_free*100, directory['space_free_frac']*100, run_number))

                    ret = ClearRun(run_number, directory)

            # Are we checking for maximum age of a run?
            if (directory['older_than'] is not None and
                directory['older_than'] != 0):
                run_doc = coll.find_one({"number": run_number})
                if run_doc is None:
                    print("WARNING! Runs DB can't find run %i!"%run_number)
                    continue
                run_age = (datetime.datetime.utcnow() - run_doc['start']).total_seconds()
                if run_age > directory['older_than']:
                    print("Found a run that is %i seconds old. Cutoff is %i seconds. So removing run %i"%(run_age, directory['older_than'], run_number))
                    ret = ClearRun(run_number, directory)


        time.sleep(sleep_iter)


    
