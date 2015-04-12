#!/usr/bin/env python

# Usage of ycsb.py script:
# Need to run within a salloc allocation.
# 
# setup: Download and install ycsb into a shared directory.
# start: Start a ycsb cluster.
# stop: Stop the ycsb cluster.

# Contributors:
# Joao Carreira <joao@eecs.berkeley.edu> (2015)

import argparse
import getpass
import os
import urllib
import subprocess
import shutil
import re
import datetime
import time
import atexit
import json

run_timestamp = time.time()

# -------------------------------------------------------------------------------------------------

version='1.0'

user_dir = '/nscratch/' + getpass.getuser()
outdir = user_dir + '/memcached_bits'
ycsb_dir = outdir + '/ycsb-memcached'
workdir = os.getcwd() + '/work'
rundir = workdir + '/ycsb-' +  datetime.datetime.fromtimestamp(run_timestamp). \
	strftime('%Y-%m-%d-%H-%M-%S')

ycsb_url = 'git@github.com:jcarreira/ycsb-memcached.git'

# -------------------------------------------------------------------------------------------------

def make_dir(mydir):
	if not os.path.exists(mydir):
                print "Creating " + mydir
    		os.makedirs(mydir)
        else:
                print "Directory " + mydir + " already exists"

# Return the list of nodes in the current SLURM allocation
def get_slurm_nodelist():
	nodelist = subprocess.check_output( \
		['scontrol', 'show', 'hostname', os.environ['SLURM_NODELIST']], \
		universal_newlines=True)
	nodelist = nodelist.strip().split('\n')
	return nodelist

# -------------------------------------------------------------------------------------------------

def do_setup():
	print '> Setting up YCSB in directory ' + outdir
	print '>'

	if os.path.exists(outdir): # make sure it was setup already
                make_dir(outdir)        
                print '> Entering directory: ' + outdir
                print '> Downloading YCSB..'
                p = subprocess.Popen(['git', 'clone', ycsb_url], cwd = outdir)
                p.wait()

                print '> Compiling ycsb..'

                p = subprocess.Popen(['make', '-j', '16'], cwd = ycsb_dir)
                p.wait()
                        
                if p.returncode != 0:
                    print "Error compiling YCSB."
                    exit(-1);

                print '> DONE'
	else:
                print '> Make sure memcached was already setup.'
	print '>'
	print '> DONE'
	print '>'

# -------------------------------------------------------------------------------------------------

ycsb_instances = {}

def check_slurm_allocation():
        if (not 'SLURM_NODELIST' in os.environ) or (not os.environ['SLURM_NODELIST']):
            print '[ERROR] Need to run script within SLURM allocation'
            exit(1)


def shutdown_ycsb_instances():
	print '> Shutting down ycsb instances'
	for c in ycsb_instances.values():
                print "Terminating node " + c['node_id']
		c['process'].terminate()

	print '> Waiting for processes to terminate...'
	all_done = True
	while not all_done:
		all_done = True
		for c in ycsb_instances.values():
			if (c['process'].poll() == None):
				all_done = False
		time.sleep(0.01)
	print '> DONE'	

def get_ycsb_cmd(memcached_node):
    srun_cmd = ['sh', 'bin/ycsb.sh'];
    srun_cmd += ['com.yahoo.ycsb.Client', '-db', 'com.yahoo.ycsb.db.Memcached']
    srun_cmd += ['-p', 'workload=com.yahoo.ycsb.workloads.CoreWorkload', '-p', 'updateretrycount=1000']
    srun_cmd += ['-p', 'recordcount=500000000', '-p', 'exportmeasurementsinterval=30000']
    srun_cmd += ['-p', 'fieldcount=10', '-p', 'timeseries.granularity=100']
    srun_cmd += ['-p', 'measurementtype=timeseries']
    srun_cmd += ['-P', 'workloads/workloadd', '-p', 'memcached.server=' + memcached_node]
    return srun_cmd

def do_start(memcached_node):
	print '> Launching YCSB...'
	print '>'
	print '> Output redirected to ' + rundir
	print '>'

	# Create symlink for latest run
        make_dir(workdir)
	subprocess.call(['ln', '-s', '-f', '-T', rundir, workdir + '/latest'])

	nodelist = get_slurm_nodelist()
	nodes = nodelist
	node = nodelist[0]

	print '> Nodes: ' + ', '.join(nodes)
	print '>'
	
	atexit.register(shutdown_ycsb_instances)

	print '> Launching YCSB client'
	print '>'

        print '> Launching YCSB client on ' + node

        srun_cmd =  get_ycsb_cmd(memcached_node)

        myrundir = rundir + '/ycsb-server-' + node
        make_dir(myrundir)
        myoutfile = myrundir + '/stdout'
        myerrfile = myrundir + '/stderr'

        fout = open(myoutfile, 'w')
        ferr = open(myerrfile, 'w')
        p = subprocess.Popen(srun_cmd, stdout=fout, stderr=ferr, cwd=ycsb_dir)

        ycsb_instances[node] = {'process': p, 'out': myoutfile, \
            'err': myerrfile, 'type': 'worker', 'node_id' : node}

	print '>'
	print '> YCSB RUNNING..'
        
        p.wait()

        ycsb_instances.clear()

# -------------------------------------------------------------------------------------------------

parser = argparse.ArgumentParser(description='Run YCSB on Memcached on FireBox-0 cluster.')
parser.add_argument('action', nargs=1, help='the action to perform (setup|start|stop)')
parser.add_argument('memcached_node', nargs=2, help='the node where memcached runs')

args = parser.parse_args()

print '> ================================================================================'
print '> YCSB RUN SCRIPT FOR FIREBOX-0 CLUSTER (VERSION ' + str(version) + ')'
print '> ================================================================================'
print '>'

git_rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'])
print '> GIT revision: ' + git_rev.replace('\n','')

if not args.memcached_node:
    print "memcached_node argument missing."

print '>'

print '> COMMAND = ' + str(args.action)

if args.action[0] == 'setup':
	do_setup()
elif args.action[0] == 'start':
        check_slurm_allocation()
	do_start(args.memcached_node[1])
elif args.action[0] == 'stop':
	shutdown_ycsb_instances()
else:
	print '[ERROR] Unknown action \'' + args.action[0] + '\''


