#!/usr/bin/env python

# Usage of memcached.py script:
# Need to run within a salloc allocation.
# 
# setup: Download and install memcached into a shared directory.
# start: Start a memcached cluster.
# stop: Stop the memcached cluster.

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
import signal

run_timestamp = time.time()

# -----------------------------------------------------------------------------------------------

version='1.0'
memcached_version = '1.4.22'

user_dir = '/nscratch/' + getpass.getuser()

# -----------------------------------------------------------------------------------------------

# Return the list of nodes in the current SLURM allocation
def get_slurm_nodelist():
	nodelist = subprocess.check_output( \
		['scontrol', 'show', 'hostname', os.environ['SLURM_NODELIST']], \
		universal_newlines=True)
	nodelist = nodelist.strip().split('\n')
	return nodelist


# -----------------------------------------------------------------------------------------------

memcached_instances = []
ycsb_instances = []

def do_setup():
        p = subprocess.Popen(['python', 'memcached.py', 'setup'])#, cwd = outdir)
        p.wait()

        memcached_node = get_slurm_nodelist()[0]

        p = subprocess.Popen(['python', 'ycsb.py', 'setup', 
                'memcached_node',memcached_node])#, cwd = outdir)
        p.wait()

def shutdown_memcached_ycsb_instances():
	print '> Shutting down memcached instances'
	for c in memcached_instances:
		c.terminate()
	
        print '> Shutting down ycsb instances'
	for c in ycsb_instances:
		c.terminate()

	print '> Waiting for processes to terminate...'
	all_done = True
	while not all_done:
		all_done = True
		for c in memcached_instances:
			if (c.poll() == None):
				all_done = False
		for c in ycsb_instances:
			if (c.poll() == None):
				all_done = False
		time.sleep(0.01)
	print '> DONE'	

def do_start():
	atexit.register(shutdown_memcached_ycsb_instances)
    
        print "Starting memcached"        
        memcached_p = subprocess.Popen(['python', 'memcached.py', 'start'])#, cwd = outdir)
        memcached_instances.append(memcached_p)

        time.sleep(2);

        memcached_node = get_slurm_nodelist()[0]

        print "Starting YCSB"        
        ycsb_p = subprocess.Popen(['python', 'ycsb.py', 'start', 'memcached_node', memcached_node])#, cwd=outdir)
        ycsb_instances.append(ycsb_p)

        print "Waiting for YCSB"        
        ycsb_p.wait();

        print "Termianting memcached for YCSB"        
        os.kill(memcached_p.pid, signal.SIGINT)

        time.sleep(1)
        memcached_p.terminate()

        del memcached_instances[:]
        del ycsb_instances[:]

# -----------------------------------------------------------------------------------------------

parser = argparse.ArgumentParser(description='Benchmark memcached with YCSB on FireBox-0 cluster.')
parser.add_argument('action', nargs=1, help='the action to perform (setup|start|stop)')

args = parser.parse_args()

print '> ================================================================================'
print '> YCSB/MEMCACHED RUN SCRIPT FOR FIREBOX-0 CLUSTER (VERSION ' + str(version) + ')'
print '> ================================================================================'
print '>'

git_rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'])
print '> GIT revision: ' + git_rev.replace('\n','')
print '>'

print '>'

print '> COMMAND = ' + str(args.action)

if args.action[0] == 'setup':
	do_setup()
elif args.action[0] == 'start':
	do_start()
elif args.action[0] == 'stop':
        shutdown_memcached_ycsb_instances()

else:
	print '[ERROR] Unknown action \'' + args.action[0] + '\''


