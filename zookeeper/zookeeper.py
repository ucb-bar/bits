#!/usr/bin/env python

# Usage of zookeeper.py script:
# 
# setup: Download and install Zookeeper into a shared directory.
# start: Start a Zookeeper cluster.
# stop: Stop a Zookeeper cluster.

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
from shutil import copyfile

run_timestamp = time.time()

# -------------------------------------------------------------------------------------------------

zookeeper_version = '3.4.6'
zookeeper_url ='http://download.nextag.com/apache/zookeeper/' + \
               'zookeeper-${VERSION}/zookeeper-${VERSION}.tar.gz'
zookeeper_filename = 'zookeeper-' + zookeeper_version

outdir = '/nscratch/' + getpass.getuser() + '/zookeeper_bits'
download_path = outdir + '/' + zookeeper_filename + '.tar'
download_url = zookeeper_url.replace('${VERSION}', zookeeper_version)
zookeeper_path = outdir + '/' + zookeeper_filename
zookeeper_c_lib_path = zookeeper_path + '/src/c' 

workdir = os.getcwd() + '/work'

rundir = workdir + '/zookeeper-' +  datetime.datetime.fromtimestamp(run_timestamp). \
	strftime('%Y-%m-%d-%H-%M-%S')

network_if = 'eth0'

# XXX number of nodes and specific nodes should be
# in config file or input parameters
zookeeper_num_nodes = 3
zookeeper_nodes = ['16','15','14']
nodes_hash = {} # {'16' : '1', '15' : '2', '14' : '3'}

# -------------------------------------------------------------------------------------------------

def make_dir(mydir):
	if not os.path.exists(mydir):
                print "Creating " + mydir
    		os.makedirs(mydir)
        else:
                print "Directory " + mydir + " already exists"

# -------------------------------------------------------------------------------------------------

def do_install():
        print '> Installing Zookeeper libraries and includes'
        print '>'

        p = subprocess.Popen(['make','install'], cwd = zookeeper_c_lib_path)
        p.wait()

        print '> DONE'

# -------------------------------------------------------------------------------------------------

def do_setup():
	print '> Setting up Zookeeper in directory ' + outdir
	print '>'

        outdir_data = outdir + '/data'

        make_dir(outdir)
        make_dir(outdir_data)

	if not os.path.exists(download_path):
                print '> Entering directory: ' + outdir

                print '> Downloading Zookeeper..'
	        urllib.urlretrieve(download_url, download_path)
                
                print '> Untaring zookeeper..'
                p = subprocess.Popen(['tar','-xof',download_path], cwd = outdir)
                p.wait()

                zookeeper_path = outdir + '/' + zookeeper_filename
                
                print '> Compiling Zookeeper in dir: ' + zookeeper_path + '..'
                p = subprocess.Popen(['ant', 'bin-package'], cwd = zookeeper_path)
                p.wait()
               
                print '> Compiling Zookeeper libraries (used by RAMCloud) ' \
                      'in dir: ' + zookeeper_c_lib_path
                p = subprocess.Popen(['./configure'], cwd = zookeeper_c_lib_path)
                p.wait()
                p = subprocess.Popen(['make','-j','10'], cwd = zookeeper_c_lib_path)
                p.wait()

                # Zookeeper compiled
                # copy configuration to the deployed zookeeper
                if not os.path.exists('conf/zookeeper1.cfg'):
                        print 'Should run this script from the BITS-zookeeper folder'
                        exit(-1)

        conf_dir = outdir + '/conf'
        make_dir(conf_dir)

        print "Copying configuration files.."
        for node in zookeeper_nodes:
                filename = 'zookeeper' + nodes_hash[node] + '.cfg'
                destination_filename = conf_dir + '/' + filename

                copyfile('conf/zookeeper1.cfg', destination_filename)

                subs_pattern1 =  '\'s/${USER}/' + getpass.getuser() + '/\''
                subs_pattern2 =  '\'s/${NODE_ID}/' + nodes_hash[node] + '/\''
                os.system("sed -i " + subs_pattern1 + " " + destination_filename)
                os.system("sed -i " + subs_pattern2 + " " + destination_filename)

        print "Creating zookeeper conf instances in " + outdir_data
        for node in zookeeper_nodes:
                instance_data_dir = outdir_data + '/' + 'zookeeper' + nodes_hash[node]
                make_dir(instance_data_dir)
                fo = open(instance_data_dir + '/myid', "w")
                fo.write(node)
                fo.close()

        print '> DONE'
	print '>'

# -------------------------------------------------------------------------------------------------

zookeeper_instances = {}

def check_slurm_allocation():
        if (not 'SLURM_NODELIST' in os.environ) or (not os.environ['SLURM_NODELIST']):
            print '[ERROR] Need to run script within SLURM allocation'
            exit(1)

def shutdown_zookeeper_launch_processes():
	print '> Shutting down Zookeeper launch processes'
	for c in zookeeper_instances.values():
		c['process'].terminate()

	print '> Waiting for processes to terminate...'
	all_done = True
	while not all_done:
		all_done = True
		for c in zookeeper_instances.values():
			if (c['process'].poll() == None):
				all_done = False
		time.sleep(0.01)


def shutdown_zookeeper_instances():
	print '> Shutting down Zookeeper instances'
	for node in zookeeper_nodes:
		print '> Terminating Zookeeper on ' + node

		srun_cmd = ['ssh', 'f' + node]
		srun_cmd += [zookeeper_path + '/bin/zkServer.sh', 'stop']
		srun_cmd += [zookeeper_path + '/../conf/zookeeper' + \
                            nodes_hash[node] + '.cfg']

		p = subprocess.Popen(srun_cmd)
                p.wait()

	print '> DONE'	

def initialize():
        counter = 0
        for node in zookeeper_nodes:
                counter += 1
                nodes_hash[node] = str(counter)

def do_start():
	print '> Launching Zookeeper cluster...'
	print '>'
	print '> Output redirected to ' + rundir
	print '>'

	print '> Master/Worker Nodes: ' + ', '.join(zookeeper_nodes)
	print '>'

	# Launch Zookeeper Workers
	print '> Launching Zookeeper nodes'
	print '>'

        # Create symlink for latest run
        subprocess.call(['ln', '-s', '-f', '-T', rundir, workdir + '/latest'])

	for node in zookeeper_nodes:
		print '> Launching Zookeeper on ' + node

		srun_cmd = ['ssh', 'f' + node]
		srun_cmd += [zookeeper_path + '/bin/zkServer.sh', 'start']
		srun_cmd += [zookeeper_path + '/../conf/zookeeper' + \
                            str(nodes_hash[node]) + '.cfg']

		myrundir = rundir + '/worker-' + node
		make_dir(myrundir)


		myoutfile = myrundir + '/stdout'
		myerrfile = myrundir + '/stderr'

		fout = open(myoutfile, 'w')
		ferr = open(myerrfile, 'w')
		p = subprocess.Popen(srun_cmd, stdout=fout, stderr=ferr)
		zookeeper_instances[node] = {'process': p, 'out': myoutfile, \
                    'err': myerrfile, 'node': node}
	
        # When exiting, make sure all children are terminated cleanly
	atexit.register(shutdown_zookeeper_instances)

	print '>'
	print '> ALL NODES ARE UP! TERMINATE THIS PROCESS TO SHUT DOWN ZOOKEEPER CLUSTER.'
	while True:
		time.sleep(0.5)

# -------------------------------------------------------------------------------------------------

parser = argparse.ArgumentParser(description='Run script for Zookeeper on FireBox-0 cluster.')
parser.add_argument('action', nargs=1, help='the action to perform (setup|start|stop)')

args = parser.parse_args()

print '> ================================================================================'
print '> ZOOKEEPER RUN SCRIPT FOR FIREBOX-0 CLUSTER (VERSION ' + str(zookeeper_version) + ')'
print '> ================================================================================'
print '>'

git_rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'])
print '> GIT revision: ' + git_rev.replace('\n','')
print '>'

print '> COMMAND = ' + str(args.action)

initialize()

if args.action[0] == 'setup':
	do_setup()
elif args.action[0] == 'start':
	do_start()
elif args.action[0] == 'install':
	do_install()
elif args.action[0] == 'stop':
        shutdown_zookeeper_instances()
else:
	print '[ERROR] Unknown action \'' + args.action[0] + '\''

