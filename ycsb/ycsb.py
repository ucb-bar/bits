# Usage of cassandra.py script:
# Need to run within a salloc allocation.
# 
# setup: Download and install Cassandra into a shared directory.
# start: Start a Cassandra cluster.
# stop: Stop the Cassandra cluster.

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

run_timestamp = time.time()

# -------------------------------------------------------------------------------------------------

version = '0.1'

workdir = os.getcwd() + '/work'
srcdir = workdir + '/src'

git_url = 'git@github.com:brianfrankcooper/YCSB.git'

# -------------------------------------------------------------------------------------------------

def make_dir(mydir):
	if not os.path.exists(mydir):
    		os.makedirs(mydir)

# -------------------------------------------------------------------------------------------------

def do_setup():
	print '> Setting up YCSB with source directory ' + srcdir
	print '>'

	if not os.path.exists(srcdir):
		print '> Use existing source directory'
	else:
		print '> Cloning YCSB git repository (' + git_url + ')...'
		print '> Note: Enter SSH credentials as necessary'
		with open(workdir + '/git.log', 'w') as fout:
			p = subprocess.Popen(['git', 'clone', git_url], cwd=srcdir, \
				stdin=subprocess.PIPE, stdout=fout)
			p.wait()
			print '> GIT CLONE FINISHED'
	print '> DONE'
	print '>'

# -------------------------------------------------------------------------------------------------

cassandra_instances = {}

def shutdown_cassandra_instances():
	print '> Shutting down Casssandra instances'
	for c in cassandra_instances.values():
		c['process'].terminate()

	print '> Waiting for processes to terminate...'
	all_done = True
	while not all_done:
		all_done = True
		for c in cassandra_instances.values():
			if (c['process'].poll() == None):
				all_done = False
		time.sleep(0.01)
	print '> DONE'	

def do_start():
	nodelist = subprocess.check_output( \
		['scontrol', 'show', 'hostname', os.environ['SLURM_NODELIST']], \
		universal_newlines=True)
	nodelist = nodelist.strip().split('\n')
	print '> Running cassandra on nodes: ' + ', '.join(nodelist)

	confdir = outdir + '/config'
	print '> Configuration directory: ' + confdir
	print '> Deleting old configuration directory'

	if os.path.exists(confdir + '/marker'):
		shutil.rmtree(confdir)
	make_dir(confdir)

	cyaml_fn = cassandra_home + '/conf/cassandra.yaml'
	print '> Reading configuration file ' + cyaml_fn
	with open(cyaml_fn, 'r') as fyaml:
		cassandra_yaml = fyaml.read()

	log4j_fn = cassandra_home + '/conf/log4j-server.properties'
	print '> Reading configuration file ' + log4j_fn
	with open(log4j_fn, 'r') as flog4j:
		cassandra_log4j = flog4j.read()

	print '> Getting IP addresses for network interface ' + network_if + '...'
	ip_addresses = get_ip_addresses(nodelist)
	print '> IPs: ' + ', '.join(ip_addresses.values())

	for node in nodelist:
		myconfdir = confdir + '/' + node
		print '> Writing configuration for node ' + node + ' (' + myconfdir + ')...'
		make_dir(myconfdir)

		subprocess.call(['cp', '-r', cassandra_home + '/conf', myconfdir])

		myip = ip_addresses[node]
		
		# Change working directoreis

		my_cassandra_yaml = re.sub('(commitlog_directory:).*$', \
			'\g<1> ' + commitlog_dir, cassandra_yaml, \
			flags=re.MULTILINE)

		my_cassandra_yaml = re.sub('(saved_caches_directory:).*$', \
			'\g<1> ' + saved_caches_dir, my_cassandra_yaml, \
			flags=re.MULTILINE)

		my_cassandra_yaml = re.sub('(data_file_directories:.*?\- ).*?$', \
			'\g<1>' + data_dir, my_cassandra_yaml, \
			flags=re.MULTILINE|re.DOTALL)

		my_cassandra_yaml = re.sub('(listen_address:).*$', \
			'\g<1> ' + myip, my_cassandra_yaml, \
			flags=re.MULTILINE)

		my_cassandra_yaml = re.sub('(rpc_address:).*$', \
			'\g<1> ' + myip, my_cassandra_yaml, \
			flags=re.MULTILINE)

		my_cassandra_log4j = re.sub('(log4j.appender.R.File=).*$', \
			'\g<1>' + logfile, cassandra_log4j, \
			flags=re.MULTILINE)

		# Update seeds
		seeds_string = ','.join(ip_addresses.values())
		my_cassandra_yaml = re.sub('(- seeds:).*$', \
			'\g<1> "' + seeds_string + '"', my_cassandra_yaml, \
			flags=re.MULTILINE)

		with open(myconfdir + '/conf/cassandra.yaml', 'w') as fyaml:
			fyaml.write(my_cassandra_yaml)

		with open(myconfdir + '/conf/log4j-server.properties', 'w') as flog4j:
			flog4j.write(my_cassandra_log4j)

	print '> DONE'

	print '>'
	print '> Launching Cassandra nodes'
	print '>'
	print '> Output redirected to ' + rundir
	print '>'

	# Create symlink for latest run
	subprocess.call(['ln', '-s', '-f', '-T', rundir, workdir + '/latest'])

	for node in nodelist:
		print '> Launching Cassandra instance on ' + node
		myconfdir = confdir + '/' + node + '/conf'

		srun_cmd = ['srun', '--nodelist=' + node, '-N1']
		srun_cmd += ['bash', 'run_cassandra.sh']

		myenv = {'CASSANDRA_HOME': cassandra_home, 'CASSANDRA_CONF': myconfdir}
		myenv.update(os.environ)

		myrundir = rundir + '/' + node
		make_dir(myrundir)
		myoutfile = myrundir + '/stdout'
		myerrfile = myrundir + '/stderr'

		fout = open(myoutfile, 'w')
		ferr = open(myerrfile, 'w')
		p = subprocess.Popen(srun_cmd, stdout=fout, stderr=ferr, env=myenv)
		cassandra_instances[node] = {'process': p, 'out': myoutfile, 'err': myerrfile}

	# When exiting, make sure all children are terminated cleanly
	atexit.register(shutdown_cassandra_instances)

	print '>'
	print '> Waiting for all nodes to finish starting up...'
	unfinished_nodes = cassandra_instances.keys()

	while unfinished_nodes:
		done_nodes = []
		for node in unfinished_nodes:
			with open(myoutfile, 'r') as fout:
				outdata = fout.read()	
			if re.search("XXX", outdata) != None:
				done_nodes.append(node)
		for node in done_nodes:
			unfinished_nodes.remove(node)
		time.sleep(0.01)

	print '>'
	print '> ALL NODES ARE UP! TERMINATE THIS PROCESS TO SHUT DOWN CASSANDRA CLUSTER.'
	while True:
		sleep(0.5)

# -------------------------------------------------------------------------------------------------

parser = argparse.ArgumentParser(description='Run script for Cassandra on FireBox-0 cluster.')
parser.add_argument('action', nargs=1, help='the action to perform (setup|start|stop)')

args = parser.parse_args()

print '> ================================================================================'
print '> CASSANDRA RUN SCRIPT FOR FIREBOX-0 CLUSTER (VERSION ' + str(version) + ')'
print '> ================================================================================'
print '>'

if not os.environ['SLURM_NODELIST']:
	print '[ERROR] Need to run script within SLURM allocation'
	exit(1)

print '> COMMAND = ' + str(args.action)

if args.action[0] == 'setup':
	do_setup()
elif args.action[0] == 'start':
	do_start()
else:
	print '[ERROR] Unknown action \'' + args.action[0] + '\''
