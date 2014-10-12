# Usage of cassandra.py script:
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

git_url = 'git@github.com:brianfrankcooper/YCSB.git'

# -------------------------------------------------------------------------------------------------

def make_dir(mydir):
	if not os.path.exists(mydir):
    		os.makedirs(mydir)

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
		p = subprocess.Popen(['srun', '-N', '1', 'mvn', 'clean', 'package'], cwd=srcdir + '/YCSB', \
			stdin=subprocess.PIPE, stdout=fout)
		p.wait()

	print '> DONE'
	print '>'

# -------------------------------------------------------------------------------------------------

def do_cassandra_load():
	print 'NIY'

# -------------------------------------------------------------------------------------------------

parser = argparse.ArgumentParser(description='Run script for YCSB on FireBox-0 cluster.')
parser.add_argument('action', nargs=1, help='the action to perform (setup)')

args = parser.parse_args()

print '> ================================================================================'
print '> YCSB RUN SCRIPT FOR FIREBOX-0 CLUSTER (VERSION ' + str(version) + ')'
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
