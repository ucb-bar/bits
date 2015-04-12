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

run_timestamp = time.time()

# -------------------------------------------------------------------------------------------------

version='1.0'
memcached_version = '1.4.22'

user_dir = '/nscratch/' + getpass.getuser()
outdir = user_dir + '/memcached_bits'
memcached_file = 'memcached-' + memcached_version
memcached_dir = outdir + '/' + memcached_file
workdir = os.getcwd() + '/work'
rundir = workdir + '/memcached-' +  datetime.datetime.fromtimestamp(run_timestamp). \
	strftime('%Y-%m-%d-%H-%M-%S')

network_if = 'eth0'

memcached_tar_file = memcached_file + '.tar.gz'
memcached_url = 'http://www.memcached.org/files/' + memcached_tar_file

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
	print '> Setting up Memcached in directory ' + outdir
	print '>'

	if not os.path.exists(outdir):
                make_dir(outdir)        
                print '> Entering directory: ' + outdir
                print '> Downloading Memcached..'
                p = subprocess.Popen(['wget', memcached_url], cwd = outdir)
                p.wait()

                print '> Untaring memcached..'

                p = subprocess.Popen(['tar', '-xof', memcached_tar_file], cwd = outdir)
                p.wait()
                
                print '> ./configure\'ing memcached..'
                p = subprocess.Popen(['./configure'], cwd = memcached_dir)
                p.wait()
                
                print '> Compiling memcached..'
                p = subprocess.Popen(['make', '-j', '10'], cwd = memcached_dir)
                p.wait()
                        
                if p.returncode != 0:
                    print "Error compiling Memcached."
                    exit(-1);

                print '> DONE'
	else:
                print '> Memcached was already setup. To perform setup' + \
                        'again please remove folder'
	print '>'
	print '> DONE'
	print '>'

# -------------------------------------------------------------------------------------------------

memcached_instances = {}

def check_slurm_allocation():
        if (not 'SLURM_NODELIST' in os.environ) or (not os.environ['SLURM_NODELIST']):
            print '[ERROR] Need to run script within SLURM allocation'
            exit(1)


def shutdown_memcached_instances():
	print '> Shutting down memcached instances'
	for c in memcached_instances.values():
                print "Terminating node " + c['node_id']
		c['process'].terminate()

	print '> Waiting for processes to terminate...'
	all_done = True
	while not all_done:
		all_done = True
		for c in memcached_instances.values():
			if (c['process'].poll() == None):
				all_done = False
		time.sleep(0.01)
	print '> DONE'	

def wait_for_memcached_server(node):
	print '>'
	print '> Waiting for memcached server to finish starting up...'

	while True:
		with open(memcached_instances[node]['err'], 'r') as fout:
		    outdata = fout.read()	
		if re.search("server listening", outdata) != None:
                    break
		time.sleep(0.01)

	print '> ALL SERVERS ARE UP!'

def do_start():
	print '> Launching Memcached cluster...'
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
	
	atexit.register(shutdown_memcached_instances)

	print '> Launching Memcached servers'
	print '>'

        print '> Launching Memcached server on ' + node

        srun_cmd = ['srun', '--nodelist=' + node, '-N1']
        srun_cmd += ['./memcached','-m', '64']

        myrundir = rundir + '/server-' + node
        make_dir(myrundir)
        myoutfile = myrundir + '/stdout'
        myerrfile = myrundir + '/stderr'

        fout = open(myoutfile, 'w')
        ferr = open(myerrfile, 'w')
        p = subprocess.Popen(srun_cmd, stdout=fout, stderr=ferr, cwd=memcached_dir)
        memcached_instances[node] = {'process': p, 'out': myoutfile, \
            'err': myerrfile, 'type': 'worker', 'node_id' : node}


#wait_for_memcached_server(node)

	print '>'
	print '> ALL NODES ARE UP! TERMINATE THIS PROCESS TO SHUT DOWN MEMCACHED CLUSTER.'
	while True:
		time.sleep(0.5)

# -------------------------------------------------------------------------------------------------

parser = argparse.ArgumentParser(description='Run script for Memcached on FireBox-0 cluster.')
parser.add_argument('action', nargs=1, help='the action to perform (setup|start|stop)')

args = parser.parse_args()

print '> ================================================================================'
print '> MEMCACHED RUN SCRIPT FOR FIREBOX-0 CLUSTER (VERSION ' + str(version) + ')'
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
        check_slurm_allocation()
	do_start()
elif args.action[0] == 'stop':
	shutdown_memcached_instances()
else:
	print '[ERROR] Unknown action \'' + args.action[0] + '\''


