#!/usr/bin/env python

# Usage of ramcloud.py script:
# Need to run within a salloc allocation.
# 
# setup: Download and install RAMCloud into a shared directory.
# start: Start a RAMCloud cluster.
# stop: Stop the RAMCloud cluster.
#
# Assumes zookeeper has been deployed

# Contributors:
# Joao Carreira <joao@eecs.berkeley.edu> (2014)

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
outdir = user_dir + '/ramcloud_bits'
ramcloud_dir = outdir + '/ramcloud'
workdir = os.getcwd() + '/work'
rundir = workdir + '/ramcloud-' +  datetime.datetime.fromtimestamp(run_timestamp). \
	strftime('%Y-%m-%d-%H-%M-%S')

network_if = 'eth0'

ramcloud_url = 'git://fiz.stanford.edu/git/ramcloud.git'

# paths used to set zookeeper dependencies
# XXX zookeeper version should be parameter
zookeeper_lib_path = user_dir +\
                     '/zookeeper_bits/zookeeper-3.4.6/src/c/.libs/libzookeeper_mt.a'
zookeeper_dir_path = user_dir + \
                     '/zookeeper_bits/zookeeper-3.4.6/src/c/include'

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
	print '> Setting up RAMCloud in directory ' + outdir
	print '>'

	if not os.path.exists(ramcloud_dir):
                make_dir(ramcloud_dir)        
                print '> Entering directory: ' + outdir
                print '> Cloning RAMCloud..'
                p = subprocess.Popen(['git', 'clone', ramcloud_url], cwd = outdir)
                p.wait()

                print '> Updating RAMCloud modules..'
                p = subprocess.Popen(['git', 'submodule', 'update', \
                        '--init', '--recursive'], cwd = ramcloud_dir)
                p.wait()

                print '> Compiling RAMCloud..'
                cmd_str = 'make -j 16 DEBUG=no ZOOKEEPER_LIB=' + \
                          zookeeper_lib_path + ' ZOOKEEPER_DIR=' + zookeeper_dir_path
                print cmd_str

                p =  subprocess.Popen(cmd_str, cwd = ramcloud_dir, shell=True)
                p.wait()

                print '> DONE'
	else:
                print '> RAMCloud was already setup. To perform setup' + \
                        'again please remove folder'
	print '>'
	print '> DONE'
	print '>'

# -------------------------------------------------------------------------------------------------

ramcloud_instances = {}

def check_slurm_allocation():
        if (not 'SLURM_NODELIST' in os.environ) or (not os.environ['SLURM_NODELIST']):
            print '[ERROR] Need to run script within SLURM allocation'
            exit(1)


def shutdown_ramcloud_instances():
	print '> Shutting down RAMCloud instances'
	for c in ramcloud_instances.values():
                print "Terminating node " + c['node_id']
		c['process'].terminate()

	print '> Waiting for processes to terminate...'
	all_done = True
	while not all_done:
		all_done = True
		for c in ramcloud_instances.values():
			if (c['process'].poll() == None):
				all_done = False
		time.sleep(0.01)
	print '> DONE'	

def wait_for_coordinator(coordinator_log):
	print '>'
	print '> Waiting for Coordinator to finish starting up...'
	while True:
                try:
		        with open(coordinator_log, 'r') as fout:
		    	        outdata = fout.read()	
		        if re.search('ZooKeeper connection opened', outdata) != None:
			        break
                except:
                        print 'Error opening Coordinator log file'
		time.sleep(0.1)
	print '> COORDINATOR IS UP!'
	print '>'

# note: ulimit -l unlimited must be added to
# /etc/init.d/slurm-lln
# to avoid ramcloud complaining about limitations on the locked memory
def get_ramcloud_coordinator_cmd(coordinator_node, coordinator_log):
        srun_cmd = ['srun', '--nodelist=' + coordinator_node, '-N1']
        srun_cmd += ['obj.master/coordinator']
        srun_cmd += ['-C', 'infrc:host='+coordinator_node+',port=11100']
        srun_cmd += ['-x', 'zk:f16:2181'] #XXX make Zookeeper node a parameter
        srun_cmd += ['--logFile', coordinator_log]
        return srun_cmd

def get_ramcloud_server_cmd(node, coordinator_node):
	srun_cmd = ['srun', '--nodelist=' + node, '-N1']
        srun_cmd += ['obj.master/server', '-L', 'infrc:host='+node+',port=11100']
        srun_cmd += ['zk:f16:2181'] #XXX make Zookeeper node a parameter
        srun_cmd += ['-C', 'infrc:host='+coordinator_node+',port=11100']
        srun_cmd += ['--totalMasterMemory', '16000']
        srun_cmd += ['-f', '/tmp/ramcloud_data']
        srun_cmd += ['--segmentFrames', '10000','-r','2']
        return srun_cmd

def wait_for_ramcloud_servers(worker_nodes):
	print '>'
	print '> Waiting for all Servers to finish starting up...'
	unfinished_nodes = worker_nodes

	while unfinished_nodes:
		done_nodes = []
		for node in unfinished_nodes:
			with open(ramcloud_instances[node]['err'], 'r') as fout:
				outdata = fout.read()	
			if re.search("Opened session with coordinator", outdata) != None:
				done_nodes.append(node)
		for node in done_nodes:
			unfinished_nodes.remove(node)
		time.sleep(0.01)

	print '> ALL SERVERS ARE UP!'

def do_start():
	print '> Launching RAMCloud cluster...'
	print '>'
	print '> Output redirected to ' + rundir
	print '>'

	# Create symlink for latest run
	subprocess.call(['ln', '-s', '-f', '-T', rundir, workdir + '/latest'])

	nodelist = get_slurm_nodelist()
	coordinator_node = nodelist[0]
	worker_nodes = nodelist[1:]

	print '> Coordinator Node: ' + coordinator_node
	print '> Worker Nodes: ' + ', '.join(worker_nodes)
	print '>'
	
        # Step I: Launch RAMCloud coordinator
	print '> Launching RAMCloud coordinator on node: ' + coordinator_node

        myrundir = rundir + '/coordinator-' + coordinator_node
        make_dir(myrundir)
        myoutfile = myrundir + '/stdout'
        myerrfile = myrundir + '/stderr'
        coordinator_log = myrundir + '/coordinator_log'

        fout = open(myoutfile, 'w') 
        ferr = open(myerrfile, 'w') 

        srun_cmd = get_ramcloud_coordinator_cmd(coordinator_node, coordinator_log)

        print "Launching coordinator.."
        print ' '.join(srun_cmd)
        p = subprocess.Popen(srun_cmd, stdout=fout, stderr=ferr, cwd=ramcloud_dir)
        ramcloud_instances[coordinator_node] = {'process': p, 'out': myoutfile, \
                    'err': myerrfile, 'type': 'coordinator', 'node_id' : coordinator_node}

	# When exiting, make sure all children are terminated cleanly
	atexit.register(shutdown_ramcloud_instances)

        wait_for_coordinator(coordinator_log)

	# Step II: Launch RAMCloud servers
	print '> Launching RAMCloud server nodes'
	print '>'

	for node in worker_nodes:
		print '> Launching RAMCloud server on ' + node

                srun_cmd = get_ramcloud_server_cmd(node, coordinator_node)

		myrundir = rundir + '/server-' + node
		make_dir(myrundir)
		myoutfile = myrundir + '/stdout'
		myerrfile = myrundir + '/stderr'

		fout = open(myoutfile, 'w')
		ferr = open(myerrfile, 'w')
		p = subprocess.Popen(srun_cmd, stdout=fout, stderr=ferr, cwd=ramcloud_dir)
		ramcloud_instances[node] = {'process': p, 'out': myoutfile, \
                    'err': myerrfile, 'type': 'worker', 'node_id' : node}


        wait_for_ramcloud_servers(worker_nodes)

	print '>'
	print '> ALL NODES ARE UP! TERMINATE THIS PROCESS TO SHUT DOWN RAMCLOUD CLUSTER.'
	while True:
		time.sleep(0.5)

# -------------------------------------------------------------------------------------------------

parser = argparse.ArgumentParser(description='Run script for RAMCloud on FireBox-0 cluster.')
parser.add_argument('action', nargs=1, help='the action to perform (setup|start|stop)')

args = parser.parse_args()

print '> ================================================================================'
print '> RAMCLOUD RUN SCRIPT FOR FIREBOX-0 CLUSTER (VERSION ' + str(version) + ')'
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
	shutdown_ramcloud_instances()
else:
	print '[ERROR] Unknown action \'' + args.action[0] + '\''
