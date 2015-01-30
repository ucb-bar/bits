#!/usr/bin/env python

# Usage of aerospike.py script:
# Need to run within a salloc allocation.
# 
# setup: Download and install aerospike into a shared directory.
# start: Start an Aerospike cluster.
# stop: Stop the Aerospike cluster.

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

version = '1.0'

user_dir = '/nscratch/' + getpass.getuser()
outdir = user_dir + '/aerospike_bits'
aerospike_dir = outdir + '/aerospike-server'
workdir = os.getcwd() + '/work'
rundir = workdir + '/aerospike-' +  datetime.datetime.fromtimestamp(run_timestamp). \
	strftime('%Y-%m-%d-%H-%M-%S')

network_if = 'eth0'

aerospike_url = 'git@github.com:aerospike/aerospike-server.git'

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
	print '> Setting up AeroSpike in directory ' + outdir
	print '>'

	if not os.path.exists(outdir):
                make_dir(outdir)        
                print '> Entering directory: ' + outdir
                print '> Cloning AeroSpike..'
                p = subprocess.Popen(['git', 'clone', aerospike_url], cwd = outdir)
                p.wait()

                print '> Compiling Aerospike..'

                p =  subprocess.Popen(['git', 'submodule', 'update', '--init'], cwd = aerospike_dir)
                p.wait()

                # aerospike makefile seems not to have all dependencies right
                # need to run multiple times 
                while True:
                        p =  subprocess.Popen(['make', '-j', '16'], cwd = aerospike_dir)
                        p.wait()
                        if p.returncode == 0:
                                break

                print '> DONE'
	else:
                print '> Aerospike was already setup. To perform setup' + \
                        'again please remove folder'
	print '>'
	print '> DONE'
	print '>'

# -------------------------------------------------------------------------------------------------

aerospike_instances = {}

def check_slurm_allocation():
        if (not 'SLURM_NODELIST' in os.environ) or (not os.environ['SLURM_NODELIST']):
            print '[ERROR] Need to run script within SLURM allocation'
            exit(1)


def shutdown_aerospike_instances():
	print '> Shutting down Aerospike instances'
	for c in aerospike_instances.values():
                print "Terminating node " + c['node_id']
		c['process'].terminate()

	print '> Waiting for processes to terminate...'
	all_done = True
	while not all_done:
		all_done = True
		for c in aerospike_instances.values():
			if (c['process'].poll() == None):
				all_done = False
		time.sleep(0.01)
	print '> DONE'	

def get_aerospike_server_cmd(node):
	srun_cmd = ['srun', '--nodelist=' + node, '-N1']
        srun_cmd += ['make' ,'-C']
        srun_cmd += [aerospike_dir, 'start']
        return srun_cmd

def wait_for_aerospike_servers(nodes):
	print '>'
	print '> Waiting for all Servers to finish starting up...'
	unfinished_nodes = nodes

	while unfinished_nodes:
		done_nodes = []
		for node in unfinished_nodes:
			with open(aerospike_instances[node]['err'], 'r') as fout:
				outdata = fout.read()	
			if re.search("service ready: soon there will be cake", outdata) != None:
				done_nodes.append(node)
		for node in done_nodes:
			unfinished_nodes.remove(node)
		time.sleep(0.01)

	print '> ALL SERVERS ARE UP!'

def do_start():
	print '> Launching Aerospike cluster...'
	print '>'
	print '> Output redirected to ' + rundir
	print '>'

	# Create symlink for latest run
        make_dir(workdir)
	subprocess.call(['ln', '-s', '-f', '-T', rundir, workdir + '/latest'])

	nodelist = get_slurm_nodelist()
	nodes = nodelist

	print '> Nodes: ' + ', '.join(nodes)
	print '>'
	
	atexit.register(shutdown_aerospike_instances)

	print '> Launching Aerospike servers'
	print '>'

	for node in nodes:
		print '> Launching Aerospike server on ' + node

                srun_cmd = get_aerospike_server_cmd(node)

		myrundir = rundir + '/server-' + node
		make_dir(myrundir)
		myoutfile = myrundir + '/stdout'
		myerrfile = myrundir + '/stderr'

		fout = open(myoutfile, 'w')
		ferr = open(myerrfile, 'w')
		p = subprocess.Popen(srun_cmd, stdout=fout, stderr=ferr, cwd=aerospike_dir)
		aerospike_instances[node] = {'process': p, 'out': myoutfile, \
                    'err': myerrfile, 'type': 'worker', 'node_id' : node}


        wait_for_aerospike_servers(nodes)

	print '>'
	print '> ALL NODES ARE UP! TERMINATE THIS PROCESS TO SHUT DOWN AEROSPIKE CLUSTER.'
	while True:
		time.sleep(0.5)

# -------------------------------------------------------------------------------------------------

parser = argparse.ArgumentParser(description='Run script for AeroSpike on FireBox-0 cluster.')
parser.add_argument('action', nargs=1, help='the action to perform (setup|start|stop)')

args = parser.parse_args()

print '> ================================================================================'
print '> AEROSPIKE RUN SCRIPT FOR FIREBOX-0 CLUSTER (VERSION ' + str(version) + ')'
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
else:
	print '[ERROR] Unknown action \'' + args.action[0] + '\''
