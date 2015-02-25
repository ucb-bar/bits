#!/usr/bin/env python

# Usage of HERD.py script:
# 
# Commands in order:
# setup: Download and install HERD into a shared directory
# start: Start the HERD test
# stop: Stop the HERD test
#

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
outdir = user_dir + '/HERD_bits'
herd_dir = outdir + '/HERD'
workdir = os.getcwd() + '/work'
rundir = workdir + '/HERD-' +  datetime.datetime.fromtimestamp(run_timestamp). \
	strftime('%Y-%m-%d-%H-%M-%S')

herd_url = 'git@github.com:jcarreira/HERD.git'

# -------------------------------------------------------------------------------------------------

def make_dir(mydir):
	if not os.path.exists(mydir):
                print "Creating " + mydir
    		os.makedirs(mydir)
        else:
                print "Directory " + mydir + " already exists"

# -------------------------------------------------------------------------------------------------

def do_setup():
	print '> Setting up HERD in directory ' + outdir
	print '>'

	if not os.path.exists(herd_dir):
                make_dir(herd_dir)        
                print '> Entering directory: ' + outdir
                print '> Cloning HERD..'
                p = subprocess.Popen(['git', 'clone', herd_url], cwd = outdir)
                p.wait()

                print '> Compiling HERD..'
                cmd_str = 'make -j 16'
                print cmd_str

                p =  subprocess.Popen(cmd_str, cwd = herd_dir, shell=True)
                p.wait()

                # We need to change some permissions
                # We will need to run as root later
                p = subprocess.call(['chmod', 'a+rwx', outdir])
                p = subprocess.call(['chmod', 'a+rwx', herd_dir])
                p = subprocess.call(['chmod', 'a+rwx', herd_dir + '/main'])
                p = subprocess.call(['chmod', 'a+rwx', herd_dir + '/run-servers.sh'])
                p = subprocess.call(['chmod', 'a+rwx', herd_dir + '/local-kill2.pl'])
                p = subprocess.call(['chmod', 'a+rwx', herd_dir + '/kill-remote.sh'])

	else:
                print '> HERD was already setup. To perform setup' + \
                        'again please remove folder'
	print '> DONE'
	print '>'

# -------------------------------------------------------------------------------------------------

herd_instances = {}


def shutdown_herd_instances():
        p = subprocess.Popen(['sudo','perl','local-kill2.pl'], cwd=herd_dir)
        p.wait()

        p = subprocess.Popen(['sudo','/bin/sh','kill-remote.sh'], cwd=herd_dir)
        p.wait()

	print '> DONE'	

def do_start():
	print '> Launching HERD test...'
	print '>'
	print '> Output redirected to ' + rundir
	print '>'

        make_dir(rundir)
	# Create symlink for latest run
	subprocess.call(['ln', '-s', '-f', '-T', rundir, workdir + '/latest'])

        print "Starting run-servers.."
        
        myoutfile = rundir + '/stdout'
        myerrfile = rundir + '/stderr'
        fout = open(myoutfile, 'w') 
        ferr = open(myerrfile, 'w') 

	atexit.register(shutdown_herd_instances)
        p = subprocess.Popen(['sudo', '/bin/sh', 'run-servers.sh'], stdout=fout, stderr=ferr, cwd=herd_dir, env = {'ROCE':'1'})
        p.wait()

	print '>'
	print '> TEST IS RUNNING! CHECK OUTPUT IN THE WORK FOLDER. TERMINATE THIS PROCESS TO SHUT DOWN THE TEST.'
	while True:
		time.sleep(0.5)

# -------------------------------------------------------------------------------------------------

parser = argparse.ArgumentParser(description='Run script for HERD on FireBox-0 cluster.')
parser.add_argument('action', nargs=1, help='the action to perform (setup|start|stop)')

args = parser.parse_args()

print '> ================================================================================'
print '> HERD RUN SCRIPT FOR FIREBOX-0 CLUSTER (VERSION ' + str(version) + ')'
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
	shutdown_herd_instances()
else:
	print '[ERROR] Unknown action \'' + args.action[0] + '\''
