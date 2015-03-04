# Code to manage the setup and launch of workloads

# Contributors:
# Joao Carreira <joao@eecs.berkeley.edu> (2015)

import subprocess
import os
from utils import make_dir

def build_cl_options(workload):
    # each option has 2 parts
    first = workload['cl-options'][0]
    second = workload['cl-options'][1]
    return [first, "\"" + second + "\""]

def run_benchmarks(benchmarks, workloads):

    process_handles = [] # for concurrent execution

    myrundir = os.getcwd() + '/work'
    make_dir(myrundir)

    myoutfile = myrundir + '/stdout'
    myerrfile = myrundir + '/stderr'

    fout = open(myoutfile, 'w')
    ferr = open(myerrfile, 'w')
    
    for benchmark in benchmarks:
        print "Benchmark name: " + benchmark['name']
        print "Benchmark description: " + benchmark['description']
        print "Benchmark mode: " + benchmark['mode']

        is_sequential = (benchmark['mode'] == 'sequential')

        # setup all workloads
        for workload in benchmark['workloads']:

            print "Setting up workload"
            path = workloads[workload]['path']
            run_cmd = ["/usr/bin/python", path, "setup"]

            subprocess.call(run_cmd, stdout = fout, stderr = ferr)

        # run workloads
        for workload in benchmark['workloads']:
            print "Running workload: " + workload

            # build command line options
            cl_options = build_cl_options(workloads[workload])
            
            print "Starting workload " + workload
            run_cmd = ["/usr/bin/python", path, "start"]
            run_cmd += cl_options
            print "Running " + ' '.join(run_cmd)

            if (is_sequential):
                subprocess.call(run_cmd, stdout = fout, stderr = ferr)
            else:
                p = subprocess.Popen(run_cmd, stdout = fout, stderr = ferr)
                process_handles += [p]

        # if is concurrent we need to wait for all workloads to finish
        for p in process_handles:
            p.wait()
