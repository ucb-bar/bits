#!/usr/bin/env python

# Usage of ycsb.py script:
# Need to run within a salloc allocation.
# Supported frameworks:
# - Cassandra (use cassandra run script)
# 
# setup: Download and compile YCSB.

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

modules = ['cassandra', 'core', 'distribution']

workdir = os.getcwd() + '/work'
srcdir = workdir + '/src'

rundir = workdir + '/ycsb-' +  datetime.datetime.fromtimestamp(run_timestamp). \
        strftime('%Y-%m-%d-%H-%M-%S')

git_url = 'git@github.com:brianfrankcooper/YCSB.git'

print_vars = ['git_url']

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

# -------------------------------------------------------------------------------------------------

def do_setup():
	print '> Setting up YCSB with source directory ' + srcdir
	print '>'

	if os.path.exists(srcdir):
		print '> Use existing YCSB source directory'
	else:
		print '> Cloning YCSB git repository (' + git_url + ')...'
		print '> Note: Enter SSH credentials as necessary'
		with open(workdir + '/git.log', 'w') as fout:
			p = subprocess.Popen(['git', 'clone', git_url], cwd=srcdir, \
				stdin=subprocess.PIPE, stdout=fout)
			p.wait()
			print '> GIT CLONE FINISHED'

	print '> Compiling YCSB (Log: ' + workdir + '/compile.log)...'
	print '> Modules: ' + ', '.join(modules)

	# Make a backup of the file
	subprocess.call(['cp', srcdir + '/YCSB/pom.xml', srcdir + '/YCSB/pom.xml.backup'])

        with open(srcdir + '/YCSB/pom.xml', 'r') as fpom:
                ycsb_pom = fpom.readlines()

	def module_filter(line):
		m = re.match('\s*<module>(.*)</module>', line)
		if not m:
			return True
		
		if m.group(1) in modules:
			return True

		return False
	

	new_pom = [l for l in ycsb_pom if module_filter(l)]

        with open(srcdir + '/YCSB/pom.xml', 'w') as fpom:
		fpom.write(''.join(new_pom))

	with open(workdir + '/compile.log', 'w') as fout:
		p = subprocess.Popen(['srun', '-N1', 'mvn', 'clean', 'package'], cwd=srcdir + '/YCSB', \
			stdin=subprocess.PIPE, stdout=fout)
		p.wait()

	print '> DONE'
	print '>'

# -------------------------------------------------------------------------------------------------

# Set up required tables for Cassandra
def prepare_ycsb_tables(cassandra_instance):
	print '> Deleting old tables'
	subprocess.call([cassandra_instance['cli-path'], \
		'-h', cassandra_instance['nodes'][0], \
		'-p', '9160', \
		'-f', os.getcwd() + '/cassandra-reset.cql' \
	])

	print '> Setting up required tables...'
	subprocess.call([cassandra_instance['cli-path'], \
		'-h', cassandra_instance['nodes'][0], \
		'-p', '9160', \
		'-f', os.getcwd() + '/cassandra-ycsb.cql' \
	])
	print '> Finished setting up tables'
	print '>'

# Run YCSB (action can be load or run)
def run_ycsb(action):
	if not action in ['load', 'run']:
		print '[ERROR] Invalid action ' + action
		exit(1)
	print '> Executing YCSB ' + action

        nodelist = get_slurm_nodelist()
        print '> Running YCSB on nodes: ' + ', '.join(nodelist)
	if len(nodelist) > 1:
		print '[WARNING] Only one node used for running YCSB (allocation contains > 1)'
	print '>'

	if args.cassandra:
		print '> Running against CASSANDRA (Instance: ' + args.cassandra[0] + ')'
		print '> Loading instance description...'
		with open(args.cassandra[0], 'r') as fjson:
			json_str = fjson.read()
		cassandra_instance = json.loads(json_str)

		if action == 'load':
			prepare_ycsb_tables(cassandra_instance)

		print '> Executing YCSB workload...'
		print '>'

		myrundir = rundir + '-' + action
		make_dir(myrundir)
		print '> Output redirected to ' + myrundir
		print '>'

		ycsb_workload = 'workloads/workloada'
		ycsb_properties = { \
			'recordcount':'100000', \
			'operationcount':'10000', \
			'hosts':','.join(cassandra_instance['nodes']), \
			'cassandra.connectionretries':'10', \
			'cassandra.operationretries':'10', \
		}

		print '> YCSB Properties:'
		for k,v in ycsb_properties.items():
			print '> ' + k + ' = ' + v
		print '>'

		subprocess.call(['ln', '-s', '-f', '-T', myrundir, workdir + '/latest-' + action])

                srun_cmd = ['srun', '-N1', 'bin/ycsb']
		srun_cmd += [action, 'cassandra-10']
                srun_cmd += ['-P', ycsb_workload]

		for k,v in ycsb_properties.items():
			srun_cmd += ['-p', k + '=' + v]

                myoutfile = myrundir + '/stdout'
                myerrfile = myrundir + '/stderr'

		print '> Running YCSB...'
		print '> Command line: ' + ' '.join(srun_cmd)
                fout = open(myoutfile, 'w')
                ferr = open(myerrfile, 'w')
                p = subprocess.Popen(srun_cmd, stdout=fout, stderr=ferr, cwd=srcdir + '/YCSB')

		def terminate_ycsb():
			if p.poll() == None:
				p.terminate()

		atexit.register(terminate_ycsb)
		p.communicate()
		if p.returncode != 0:
			print '[ERROR] There was an error executing YCSB.'
			exit(1)
		print '> DONE'
		print '>'	
	else:
		print '[ERROR] No supported database to run against given (e.g. --cassandra)'

# -------------------------------------------------------------------------------------------------

parser = argparse.ArgumentParser(description='Run script for YCSB on FireBox-0 cluster.')
parser.add_argument('action', nargs=1, help='the action to perform (setup)')
parser.add_argument('--cassandra', nargs=1, metavar='FILE', \
	help='run against cassandra, using instance described by FILE')

args = parser.parse_args()

print '> ================================================================================'
print '> YCSB RUN SCRIPT FOR FIREBOX-0 CLUSTER (VERSION ' + str(version) + ')'
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
elif args.action[0] == 'load':
	run_ycsb('load')
elif args.action[0] == 'run':
	run_ycsb('run')
else:
	print '[ERROR] Unknown action \'' + args.action[0] + '\''
