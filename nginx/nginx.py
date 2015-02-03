#!/usr/bin/env python

# Usage of nginx.py script:
# 
# Commands in order:
# setup: Download and install nginx into a shared directory
# start: Start nginx
# stop: Stop nginx
# run-test: Start ab test of nginx
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

version = '1.7.9'

user_dir = '/nscratch/' + getpass.getuser()
outdir = user_dir + '/nginx_bits'
nginx_dir = outdir + '/nginx-' + version
nginx_work_dir = nginx_dir + '/wdir'
workdir = os.getcwd() + '/work'
rundir_nginx = workdir + '/nginx-' +  datetime.datetime.fromtimestamp(run_timestamp). \
	strftime('%Y-%m-%d-%H-%M-%S')
rundir_ab = workdir + '/ab-' +  datetime.datetime.fromtimestamp(run_timestamp). \
	strftime('%Y-%m-%d-%H-%M-%S')

nginx_url_file = 'nginx-' + version
nginx_url = 'http://nginx.org/download/' + nginx_url_file + '.tar.gz'

ab_port = 2000

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

def check_slurm_allocation():
        if (not 'SLURM_NODELIST' in os.environ) or (not os.environ['SLURM_NODELIST']):
            print '[ERROR] Need to run script within SLURM allocation'
            exit(1)
# -------------------------------------------------------------------------------------------------

def do_setup():
	print '> Setting up nginx in directory ' + outdir
	print '>'

	if not os.path.exists(nginx_dir):
                make_dir(nginx_dir)        
                print '> Entering directory: ' + outdir
                print '> Downloading nginx..'
                p = subprocess.Popen(['wget', nginx_url], cwd = outdir)
                p.wait()

                # XXX get rid of hardcoded values
                p = subprocess.Popen(['tar', '-xof', nginx_url_file + '.tar.gz'], 
                        cwd = outdir)
                p.wait()
                
                # create working dir for nginx
                make_dir(nginx_work_dir)
                make_dir(nginx_work_dir + '/logs')
                # copy tree
                try:
                    print "Copying " + nginx_dir + "/conf/ "  + "to " + \
                            nginx_work_dir + "/conf"
                    shutil.copytree(nginx_dir + '/conf/', nginx_work_dir + '/conf')
                except:
                    print 'Error copying confdir'
                    exit(-1)

                print '> Configure\'ing nginx..'
                srun_cmd = ['./configure','--prefix=' + nginx_work_dir]
                p =  subprocess.Popen(srun_cmd, cwd = nginx_dir+'/')
                p.wait()

                print '> Compiling nginx..'
                p =  subprocess.Popen(['make', '-j', '16'], cwd = nginx_dir)
                p.wait()

                # Change port used by nginx (80 requires root)
                subs_pattern = 's/listen.*80;/listen ' + str(ab_port) + ';/'
                p =  subprocess.Popen(['sed', '-si', subs_pattern, nginx_work_dir +
                        '/conf/nginx.conf'], cwd = nginx_dir)
                p.wait()

	else:
                print '> nginx was already setup. To perform setup' + \
                        'again please remove folder'
	print '> DONE'
	print '>'

# -------------------------------------------------------------------------------------------------

def shutdown_nginx():
        p = subprocess.Popen(['./objs/nginx','-s','stop'], cwd=nginx_dir)
        p.wait()

	print '> DONE'	

def do_start():
	print '> Launching nginx...'
	print '>'
	print '> Output redirected to ' + rundir_nginx
	print '>'

        make_dir(rundir_nginx)
	# Create symlink for latest run
	subprocess.call(['ln', '-s', '-f', '-T', rundir_nginx, workdir + '/latest-nginx'])

        nginx_node = get_slurm_nodelist()[0] # we use the first node for nginx

        print "Starting nginx in node " + nginx_node
        
        myoutfile = rundir_nginx + '/stdout'
        myerrfile = rundir_nginx + '/stderr'
        fout = open(myoutfile, 'w') 
        ferr = open(myerrfile, 'w') 

        srun_cmd = ['srun', '--nodelist=' + nginx_node, '-N1']
        srun_cmd += ['./objs/nginx']

        p = subprocess.Popen(srun_cmd, stdout=fout, stderr=ferr, cwd=nginx_dir)
        p.wait()

	print '>'
	print '> TEST IS RUNNING! CHECK OUTPUT IN THE WORK FOLDER'

def run_ab_test():
	print '> Launching the ab test against nginx...'
	print '>'
	print '> Output redirected to ' + rundir_ab
	print '>'

        make_dir(rundir_ab)
	# Create symlink for latest run
	subprocess.call(['ln', '-s', '-f', '-T', rundir_ab, workdir + '/latest-ab'])

        # use second node for ab
        nginx_node = get_slurm_nodelist()[0] 
        ab_node = get_slurm_nodelist()[1] 

        myoutfile = rundir_ab + '/stdout'
        myerrfile = rundir_ab + '/stderr'
        fout = open(myoutfile, 'w') 
        ferr = open(myerrfile, 'w') 
        
        srun_cmd = ['srun', '--nodelist=' + ab_node, '-N1'] 
        srun_cmd = ['ab', '-kc', '1000', '-n', '10000']
        srun_cmd += [nginx_node + ':' + str(ab_port) + '/index.html']

        print "Starting ab in node " + ab_node
        print ' '.join(srun_cmd)
	print '>'

        p = subprocess.Popen(srun_cmd, stdout=fout, stderr=ferr, cwd=nginx_dir)
        print "AB running.."
        p.wait()
        print "AB terminated.."

        if p.returncode != 0:
            print 'Error running the ab test. Make sure it is installed' \
                  'in the node where it is running'

# -------------------------------------------------------------------------------------------------

parser = argparse.ArgumentParser(description='Run nginx on FireBox-0 cluster.')
parser.add_argument('action', nargs=1, help='the action to perform (setup|start|stop)')

args = parser.parse_args()

print '> ================================================================================'
print '> NGINX RUN SCRIPT FOR FIREBOX-0 CLUSTER (VERSION ' + str(version) + ')'
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
	shutdown_nginx()
elif args.action[0] == 'run-test':
        check_slurm_allocation()
	run_ab_test()
else:
	print '[ERROR] Unknown action \'' + args.action[0] + '\''
