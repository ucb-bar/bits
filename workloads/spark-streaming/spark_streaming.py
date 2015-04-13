#!/usr/bin/env python

# Usage of spark_streaming.py script:
# Need to run within a salloc allocation.
# 
# setup: Download and install Spark Streaming benchmark into a shared directory.
# start: Start a Spark Streaming benchmark run
# stop: Stop the Spark Streaming execution

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
outdir = user_dir + '/spark_streaming_bits'
spark_streaming_dir = outdir + '/spark-streaming-benchmark/'
workdir = os.getcwd() + '/work'
rundir = workdir + '/spark_streaming-' +  datetime.datetime.fromtimestamp(run_timestamp). \
	strftime('%Y-%m-%d-%H-%M-%S')

spark_streaming_url = 'git@github.com:jcarreira/spark-streaming-benchmark.git'

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
	print '> Setting up Spark Streaming in directory ' + outdir
	print '>'

	if not os.path.exists(spark_streaming_dir):
                make_dir(spark_streaming_dir)        
                print '> Entering directory: ' + outdir
                print '> Cloning Spark Streaming benchmark..'
                p = subprocess.Popen(['git', 'clone', spark_streaming_url], cwd = outdir)
                p.wait()

                print '> DONE'
	else:
                print '> Spark Streaming Benchmark was already setup. To perform setup' + \
                        'again please remove folder'
	print '>'
	print '> DONE'
	print '>'

# -------------------------------------------------------------------------------------------------

spark_streaming_instances = {}

def check_slurm_allocation():
        if (not 'SLURM_NODELIST' in os.environ) or (not os.environ['SLURM_NODELIST']):
            print '[ERROR] Need to run script within SLURM allocation'
            exit(1)


def shutdown_spark_streaming_instances():
	print '> Shutting down Spark Streaming instances'
	for c in spark_streaming_instances.values():
		c['process'].terminate()

	print '> Waiting for processes to terminate...'
	all_done = True
	while not all_done:
		all_done = True
		for c in spark_streaming_instances.values():
			if (c['process'].poll() == None):
				all_done = False
		time.sleep(0.01)
	print '> DONE'	

def do_start(data_generator_node, benchmark_node, benchmark_time):
	print '> Launching Spark Streaming cluster...'
	print '>'
	print '> Output redirected to ' + rundir
	print '>'

	# Create symlink for latest run
	subprocess.call(['ln', '-s', '-f', '-T', rundir, workdir + '/latest'])

	print '> Launching Data generator on node: ' + data_generator_node

        myrundir = rundir + '/data_generator-' + data_generator_node
        make_dir(myrundir)
        myoutfile = myrundir + '/stdout'
        myerrfile = myrundir + '/stderr'

        fout = open(myoutfile, 'w') 
        ferr = open(myerrfile, 'w') 


        print "Launching data generator in folder " + spark_streaming_dir
       
        srun_cmd = 'srun --nodelist=' + data_generator_node + ' -N1 ' 
        srun_cmd += "sbt/sbt \'run-main DataGenerator 9999 100-bytes-lines.txt 10000000\'";

        print "running " + srun_cmd

        p = subprocess.Popen(srun_cmd, 
                stdout=fout, stderr=ferr, 
                cwd=spark_streaming_dir, shell=True)
        spark_streaming_instances[data_generator_node] = {'process': p, 'out': myoutfile, 'err': myerrfile} 

        time.sleep(10)

	# When exiting, make sure all children are terminated cleanly
	atexit.register(shutdown_spark_streaming_instances)

	print '> Launching Spark Streaming benchmark'
	print '>'

        srun_cmd = "sbt/sbt \'run-main Benchmark 1 localhost 9999 1000\'"

	myrundir = rundir + '/benchmark-' + benchmark_node
	make_dir(myrundir)
	myoutfile = myrundir + '/stdout'
	myerrfile = myrundir + '/stderr'

	fout = open(myoutfile, 'w')
	ferr = open(myerrfile, 'w')
	p = subprocess.Popen(srun_cmd, 
                stdout=fout, stderr=ferr, 
                cwd=spark_streaming_dir, shell=True)
        spark_streaming_instances[benchmark_node] = {'process': p, 'out': myoutfile, 'err': myerrfile} 

	print '>'
	print '>BENCHMARK IS RUNNING! TERMINATE THIS PROCESS TO SHUT DOWN SPARK STREAMING'

        time.sleep(benchmark_time)

# -------------------------------------------------------------------------------------------------

parser = argparse.ArgumentParser(description='Run script for Spark Streaming on FireBox-0 cluster.')
parser.add_argument('action', nargs=1, help='the action to perform (setup|start|stop)')
parser.add_argument('data_generator_node', nargs=2, help='the node where data generator runs (make sure it is Slurm allocated)')
parser.add_argument('benchmark_node', nargs=2, help='the node where the receiver runs (make sure it is Slurm allocated)')
parser.add_argument('benchmark_time', nargs=2, help='the amount of time to run the benchmark')

args = parser.parse_args()

print '> ================================================================================'
print '> SPARK STREAMING RUN SCRIPT FOR FIREBOX-0 CLUSTER (VERSION ' + str(version) + ')'
print '> ================================================================================'
print '>'

git_rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'])
print '> GIT revision: ' + git_rev.replace('\n','')
print '>'

print '> COMMAND = ' + str(args.action)

check_slurm_allocation()
assert args.data_generator_node and args.data_generator_node[1] in get_slurm_nodelist()
assert args.benchmark_node and args.data_generator_node[1] in get_slurm_nodelist()
assert args.benchmark_time

if args.action[0] == 'setup':
	do_setup()
elif args.action[0] == 'start':
	do_start(args.data_generator_node[1], args.benchmark_node[1], int(args.benchmark_time[1]))
	shutdown_spark_streaming_instances()
elif args.action[0] == 'stop':
	shutdown_spark_streaming_instances()
else:
	print '[ERROR] Unknown action \'' + args.action[0] + '\''


