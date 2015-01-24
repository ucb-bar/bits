#!/usr/bin/env python

# Usage of spark.py script:
# Need to run within a salloc allocation.
# 
# setup: Download and install Spark into a shared directory.
# start: Start a Spark cluster.
# stop: Stop the Spark cluster.

# Contributors:
# Martin Maas <maas@eecs.berkeley.edu> (2014)

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
import sys

run_timestamp = time.time()

# -------------------------------------------------------------------------------------------------

version = '0.1'

srcdir = os.path.abspath(os.path.dirname(__file__))

outdir = '/nscratch/' + getpass.getuser() + '/spark'
workdir = os.getcwd() + '/work'
rundir = workdir + '/spark-' +  datetime.datetime.fromtimestamp(run_timestamp). \
	strftime('%Y-%m-%d-%H-%M-%S')

instance_json = rundir + '/spark.json'

network_if = 'eth2'

spark_version = '1.1.0'

spark_master_port = '7077'

spark_executor_memory = '32G'

# For now, use the Hadoop-2.4 version (as this is what the cluster is running).
spark_url = 'http://d3kbcqa49mib13.cloudfront.net/spark-${VERSION}-bin-hadoop2.4.tgz'

spark_home = outdir + '/spark-1.1.0-bin-hd2.3'
spark_work = spark_home + '/work'

# Workload specific
workload_config = {}
workload_config['WikipediaPageRank'] = { \
	'args' : ['hdfs://10.10.49.98/user/maas/freebase-wex-2010-07-05-articles.tsv', '100', '256', 'true'], \
	'class' : 'org.apache.spark.examples.bagel.WikipediaPageRank', \
	'file' : spark_home + '/lib/spark-examples-1.1.0-hadoop2.3.0.jar' \
	}
workload_config['SparkPi'] = { \
	'args' : ['10'], \
	'class' : 'org.apache.spark.examples.SparkPi', \
	'file' : spark_home + '/lib/spark-examples-1.1.0-hadoop2.3.0.jar' \
	}

java_opts = '-XX:+PrintGC -XX:+PrintGCDetails -XX:+PrintGCTimeStamps'

print_vars = ['spark_version', 'spark_home', 'spark_master_port', 'network_if', 'java_opts']

cluster_info = {}

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
		['srun', '--nodelist=' + ','.join(nodelist), 'bash', srcdir + '/../common/get_ip_address.sh', \
		network_if], universal_newlines=True)
	json_str = '[' + ','.join(results.splitlines()) + ']'
	raw_data = json.loads(json_str)
	ip_map = {}
	for entry in raw_data:
		ip_map[entry['host']] = entry['ip']
	return ip_map

# -------------------------------------------------------------------------------------------------

def do_setup():
	# For now, manually download and extract spark-1.1.0-bin-hadoop2.4
	print '[ERROR] Spark setup not implemented yet'
	sys.exit(1)

# -------------------------------------------------------------------------------------------------

spark_instances = {}

def shutdown_spark_instances():
	print '> Shutting down Spark instances'
	for c in spark_instances.values():
		if c['process'].poll() == None:
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
	print '> Launching Spark cluster...'
	print '>'
	print '> Output redirected to ' + rundir
	print '>'

	# Create symlink for latest run
	make_dir(workdir)
	subprocess.call(['ln', '-s', '-f', '-T', rundir, workdir + '/latest'])

	nodelist = get_slurm_nodelist()
	master_node = nodelist[0]
	worker_start_index = 1
	if args.workload != 'none':
		# Set one node aside to execute the workload, if requested.
		job_node = nodelist[1]
		worker_start_index = 2
	worker_nodes = nodelist[worker_start_index:]

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

	myenv = {'SPARK_JAVA_OPTS': java_opts, 'SPARK_DAEMON_JAVA_OPTS': java_opts}
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

	cluster_info['master_ip'] = ip_addresses[master_node]
	cluster_info['master_port'] = spark_master_port

	# Step II: Launch Spark Workers
	print '> Launching Spark worker nodes'
	print '>'

	cluster_info['workers'] = []

	for node in worker_nodes:
		print '> Launching Spark worker on ' + node

		srun_cmd = ['srun', '--nodelist=' + node, '-N1']
		srun_cmd += ['bash', './bin/spark-class']
		srun_cmd += ['org.apache.spark.deploy.worker.Worker']
		srun_cmd += ['--ip', ip_addresses[node]]
		srun_cmd += ['spark://' + ip_addresses[master_node] + ':' + spark_master_port]

		myenv = {'SPARK_JAVA_OPTS': java_opts, 'SPARK_DAEMON_JAVA_OPTS': java_opts}
		myenv.update(os.environ)

		myrundir = rundir + '/worker-' + node
		make_dir(myrundir)
		myoutfile = myrundir + '/stdout'
		myerrfile = myrundir + '/stderr'

		fout = open(myoutfile, 'w')
		ferr = open(myerrfile, 'w')
		p = subprocess.Popen(srun_cmd, stdout=fout, stderr=ferr, env=myenv, cwd=spark_home)
		spark_instances[node] = {'process': p, 'out': myoutfile, 'err': myerrfile, 'type': 'worker'}

		cluster_info['workers'].append({'ip': ip_addresses[node], 'node': node})

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

	spark_instance = { \
		'master_ip' : ip_addresses[master_node], \
		'master_port' : spark_master_port \
	}

	if args.workload != 'none':
		# If a workload is given, run the workload and shut down cluster afterwards.
		job = run_workload(args.workload, spark_instance, job_node)
		print '>'
		print '> WAITING FOR WORKLOAD TO TERMINATE'
		while True:
			if (job.poll() != None):
				if args.logs:
					extract_spark_logs(rundir + '/master-' + master_node + '/stderr')
				sys.exit(0)
			time.sleep(0.5)
	else:
		# Write a JSON description of the Cassandra instance that can be used by others.
		print '> Writing instance description to ' + instance_json

		json_str = json.dumps(spark_instance)
		with open(instance_json, 'w') as fjson:
			fjson.write(json_str)	

		print '>'
		print '> ALL NODES ARE UP! TERMINATE THIS PROCESS TO SHUT DOWN SPARK CLUSTER.'
		while True:
			time.sleep(0.5)

# -------------------------------------------------------------------------------------------------

def run_workload(workload, spark_instance, node):
	print '> Launching Spark workload ' + workload + '...'
	if not (workload in workload_config.keys()):
		print '[ERROR] No workload ' + workload
		sys.exit(1)

	print '>'
	print '> Output redirected to ' + rundir
	print '>'

	print '> Launching Spark workload on ' + node

	srun_cmd = ['srun', '--nodelist=' + node, '-N1']
	srun_cmd += ['bash', './bin/spark-submit']
	srun_cmd += ['--class', workload_config[workload]['class']]
	srun_cmd += ['--master', 'spark://' + spark_instance['master_ip'] + ':' + spark_instance['master_port']]
	srun_cmd += ['--executor-memory', '32G']
	srun_cmd += ['--total-executor-cores', '16']
	srun_cmd += [workload_config[workload]['file']]
	srun_cmd += workload_config[workload]['args']

	myenv = {}
	myenv = {'SPARK_JAVA_OPTS': java_opts, 'SPARK_DAEMON_JAVA_OPTS': java_opts}
	myenv.update(os.environ)

	myrundir = rundir + '/job-' + node
	make_dir(myrundir)
	myoutfile = myrundir + '/stdout'
	myerrfile = myrundir + '/stderr'

	fout = open(myoutfile, 'w')
	ferr = open(myerrfile, 'w')
	p = subprocess.Popen(srun_cmd, stdout=fout, stderr=ferr, env=myenv, cwd=spark_home)
	spark_instances[node] = {'process': p, 'out': myoutfile, 'err': myerrfile, 'type': 'job'}
	print '> Workload ' + workload + ' is running...'

	if (hooks.start_workload):
		hooks.start_workload()

	return p

def extract_spark_logs(master_err):
	with open(master_err, 'r') as fmaster:
		log = fmaster.read()

	m = re.search('Registered app .+ with ID ([a-zA-Z0-9\-]+)', log)
	app = m.group(1)

	source_dir = spark_work + '/' + app
	dest_dir = rundir + '/spark_logs'

	print '> Copying spark logs from ' + source_dir + ' to ' + dest_dir + '...'
	shutil.copytree(source_dir, dest_dir, ignore=shutil.ignore_patterns('*.jar'))
	print '> Finished copying!'
	print '>'

# -------------------------------------------------------------------------------------------------

parser = argparse.ArgumentParser(description='Run script for Spark on FireBox-0 cluster.')
parser.add_argument('action', nargs=1, help='the action to perform (setup|start|stop)')
parser.add_argument('--workload', nargs='?', metavar='NAME', default='none', \
	help='if set, run the Spark workload described by NAME')
parser.add_argument('--logs', action='store_true', default=False, \
	help='copy the Spark executor logs into work directory')
parser.add_argument('--hooks', nargs='?', metavar='FILE', default='none', \
	help='if set, defines a Python file with custom hooks to call')

args = parser.parse_args()

print '> ================================================================================'
print '> SPARK RUN SCRIPT FOR FIREBOX-0 CLUSTER (VERSION ' + str(version) + ')'
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
print '> COPY SPARK LOGS = ' + str(args.logs)

if args.hooks:
	print '> CUSTOM HOOKS FILE = ' + args.hooks
	execfile(args.hooks)
	hooks = Hooks(cluster_info)

	if hooks.start_workload:
		print '> - FOUND HOOK: start_workload'
	
print '>'

if args.action[0] == 'setup':
	do_setup()
elif args.action[0] == 'start':
	do_start()
else:
	print '[ERROR] Unknown action \'' + args.action[0] + '\''
