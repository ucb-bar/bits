#!/usr/bin/env python

# Usage of ramcloud.py script:
# Need to run within a salloc allocation.
# 
# setup: Download and install RAMCloud into a shared directory.
# start: Start a RAMCloud cluster.
# stop: Stop the RAMCloud cluster.

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

version = '0.1'

outdir = '/nscratch/' + getpass.getuser() + '/ramcloud'
workdir = os.getcwd() + '/work'
rundir = workdir + '/ramcloud-' +  datetime.datetime.fromtimestamp(run_timestamp). \
	strftime('%Y-%m-%d-%H-%M-%S')

# what is this?
instance_json = rundir + '/ramcloud.json'

network_if = 'eth0'

ramcloud_version = '1'


# For now, use the Hadoop-2.4 version (as this is what the cluster is running).
ramcloud_url = 'XXX'

#spark_home = outdir + '/spark-1.1.0-bin-hd2.3'

#print_vars = ['spark_version', 'spark_home', 'spark_master_port', 'network_if']

# -------------------------------------------------------------------------------------------------

def make_dir(mydir):
	if not os.path.exists(mydir):
    		os.makedirs(mydir)

# Return the list of nodes in the current SLURM allocation
def get_slurm_nodelist():
	nodelist = subprocess.check_output( \
		['scontrol', 'show', 'hostname', os.environ['SLURM_NODELIST']], \
		universal_newlines=True)
	nodelist = nodelist.strip().split('\n')
	return nodelist

# Return list of the Ip addresses for the chosen network_if on all nodes in nodelist
def get_ip_addresses(nodelist):
	results = subprocess.check_output( \
		['srun', '--nodelist=' + ','.join(nodelist), 'bash', '../common/get_ip_address.sh', \
		network_if], universal_newlines=True)
	json_str = '[' + ','.join(results.splitlines()) + ']'
	raw_data = json.loads(json_str)
	ip_map = {}
	for entry in raw_data:
		ip_map[entry['host']] = entry['ip']
	return ip_map

# -------------------------------------------------------------------------------------------------

def do_setup():
	print '> Setting up RAMCloud in directory ' + outdir
	#print '> Working directory: ' + workdir
	print '>'

        ramcloud_dir = 'ramcloud'
	#download_path = workdir + '/downloads/'
	if not os.path.exists(outdir + '/ramcloud'):
                print '> Entering directory: ' + outdir
                os.chdir(outdir)
                print '> Cloning RAMCloud..'
                subprocess.call(['git', 'clone', 'git://fiz.stanford.edu/git/ramcloud.git'])
                os.chdir(ramcloud_dir)
                print '> Updating RAMCloud modules..'
                subprocess.call(['git', 'submodule', 'update', '--init', '--recursive'])
                os.chdir('..')
                print '> DONE'
	else:
                print '> Use previously downloaded RAMCloud package at ' + 'git://fiz.stanford.edu/git/ramcloud.git'
	print '>'
	print '> DONE'
	print '>'

# -------------------------------------------------------------------------------------------------

ramcloud_instances = {}

def shutdown_spark_instances():
	print '> Shutting down Spark instances'
	for c in spark_instances.values():
		c['process'].terminate()

	print '> Waiting for processes to terminate...'
	all_done = True
	while not all_done:
		all_done = True
		for c in spark_instances.values():
			if (c['process'].poll() == None):
				all_done = False
		time.sleep(0.01)
	print '> DONE'	

def do_start():
	print '> Launching RAMCloud cluster...'
	print '>'
	print '> Output redirected to ' + rundir
	print '>'

	# Create symlink for latest run
	subprocess.call(['ln', '-s', '-f', '-T', rundir, workdir + '/latest'])

	nodelist = get_slurm_nodelist()
	master_node = nodelist[0]
	worker_nodes = nodelist[1:]

	print '> Master Node: ' + master_node
	print '> Worker Nodes: ' + ', '.join(worker_nodes)
	print '>'

	print '> Getting IP addresses for network interface ' + network_if + '...'
	ip_addresses = get_ip_addresses(nodelist)
	print '> IPs: ' + ', '.join(ip_addresses.values())
	print '>'

	# Step I: Launch Spark Master
	print '> Launching Spark master on node: ' + master_node

	srun_cmd = ['srun', '--nodelist=' + master_node, '-N1']
	srun_cmd += ['bin/spark-class']
	srun_cmd += ['org.apache.spark.deploy.master.Master']
	srun_cmd += ['--ip', ip_addresses[master_node]]
	srun_cmd += ['--port', spark_master_port]

	myenv = {} #{'CASSANDRA_HOME': cassandra_home, 'CASSANDRA_CONF': myconfdir}
	myenv.update(os.environ)

	myrundir = rundir + '/master-' + master_node
	make_dir(myrundir)
	myoutfile = myrundir + '/stdout'
	myerrfile = myrundir + '/stderr'

	fout = open(myoutfile, 'w')
	ferr = open(myerrfile, 'w')
	p = subprocess.Popen(srun_cmd, stdout=fout, stderr=ferr, env=myenv, cwd=spark_home)
	spark_instances[master_node] = {'process': p, 'out': myoutfile, 'err': myerrfile, 'type': 'master'}

	# When exiting, make sure all children are terminated cleanly
	atexit.register(shutdown_spark_instances)

	print '>'
	print '> Waiting for Master to finish starting up...'
	while True:
		with open(myerrfile, 'r') as fout:
			outdata = fout.read()	
		if re.search('Successfully started service \'sparkMaster\'', outdata) != None:
			break
		time.sleep(0.01)
	print '> MASTER IS UP!'
	print '>'

	# Step II: Launch Spark Workers
	print '> Launching Spark worker nodes'
	print '>'

	for node in worker_nodes:
		print '> Launching Spark worker on ' + node

		srun_cmd = ['srun', '--nodelist=' + node, '-N1']
		srun_cmd += ['bash', './bin/spark-class']
		srun_cmd += ['org.apache.spark.deploy.worker.Worker']
		srun_cmd += ['--ip', ip_addresses[node]]
		srun_cmd += ['spark://' + ip_addresses[master_node] + ':' + spark_master_port]

		#myenv = {'CASSANDRA_HOME': cassandra_home, 'CASSANDRA_CONF': myconfdir}
		myenv.update(os.environ)

		myrundir = rundir + '/worker-' + node
		make_dir(myrundir)
		myoutfile = myrundir + '/stdout'
		myerrfile = myrundir + '/stderr'

		fout = open(myoutfile, 'w')
		ferr = open(myerrfile, 'w')
		p = subprocess.Popen(srun_cmd, stdout=fout, stderr=ferr, env=myenv, cwd=spark_home)
		spark_instances[node] = {'process': p, 'out': myoutfile, 'err': myerrfile, 'type': 'worker'}

	# When exiting, make sure all children are terminated cleanly
	atexit.register(shutdown_spark_instances)

	print '>'
	print '> Waiting for all Workers to finish starting up...'
	unfinished_nodes = worker_nodes

	while unfinished_nodes:
		done_nodes = []
		for node in unfinished_nodes:
			with open(spark_instances[node]['err'], 'r') as fout:
				outdata = fout.read()	
			if re.search("Successfully registered with master", outdata) != None:
				done_nodes.append(node)
		for node in done_nodes:
			unfinished_nodes.remove(node)
		time.sleep(0.01)

	print '> ALL WORKERS ARE UP!'

	# Write a JSON description of the Cassandra instance that can be used by others.
	print '> Writing instance description to ' + instance_json
	#cassandra_instance = { \
	#	'nodes' : ip_addresses.values(), \
	#	'cli-path' : cassandra_home + '/bin/cassandra-cli', \
	#}

	#json_str = json.dumps(cassandra_instance)
	#with open(instance_json, 'w') as fjson:
	#	fjson.write(json_str)	

	print '>'
	print '> ALL NODES ARE UP! TERMINATE THIS PROCESS TO SHUT DOWN SPARK CLUSTER.'
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

print '> Constants:'
for v in print_vars:
	print '> ' + v + '=' + globals()[v]

print '>'

if (not 'SLURM_NODELIST' in os.environ) or (not os.environ['SLURM_NODELIST']):
	print '[ERROR] Need to run script within SLURM allocation'
	exit(1)

print '> COMMAND = ' + str(args.action)

if args.action[0] == 'setup':
	do_setup()
elif args.action[0] == 'start':
	do_start()
else:
	print '[ERROR] Unknown action \'' + args.action[0] + '\''
