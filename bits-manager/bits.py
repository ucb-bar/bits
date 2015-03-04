#!/usr/bin/env python

# Bits main script
# Allows:
# 1) setup and deployment of workloads in bulk in Firebox
# 2) running workloads
# 3) gathering the results

# the different workloads are integrated via:
# 1) xml configuration files that describe and specify paths to the workloads code
# 2) an interface shared by all the workloads to a) setup, 2) launch, 3) stop, 4) collect results

# USE CASES:
# ./bits.py --run <workload.xml> 
# ./bits.py --list <workload.xml> 

# Contributors:
# Joao Carreira <joao@eecs.berkeley.edu> (2015)

import argparse

import os
from xml_parsing import parse_xml
from benchmarks import run_benchmarks
from utils import make_dir
from data_aggregation import gather_data

# -----------------------------------------------------------------------------------------------

version = '1.0'

# -----------------------------------------------------------------------------------------------

def make_dir(mydir):
	if not os.path.exists(mydir):
                print "Creating " + mydir
    		os.makedirs(mydir)
        else:
                print "Directory " + mydir + " already exists"

def getTagData(node, tagName):
    return node.getElementsByTagName(tagName)[0].childNodes[0].data

def print_parse_xml(file_path):

    workloads_db = {} # workload_name -> workload
    benchmarks_db = []

    try:
        print "Parsing " + file_path
        xmldoc = minidom.parse(file_path)
        print "Getting workloads.."
        workloads = xmldoc.getElementsByTagName("workload")
        for workload in workloads:

            workload_dict = {}

            workload_name = getTagData(workload, "name")
            workload_dict['name'] = workload_name

            workload_description = getTagData(workload, "description")
            workload_dict['description'] = workload_description

            workload_path = getTagData(workload, "path")
            workload_dict['path'] = workload_path

            cl_options = []

            xml_cl_options = workload.getElementsByTagName("cl-options")[0]
            for child in xml_cl_options.childNodes:
                if child.nodeName == "#text": # ??
                    continue
                #print "nodeName: " + child.nodeName
                #print "data: " + child.childNodes[0].data
                data = child.childNodes[0].data

                cl_options += [child.nodeName + " " + data]

            workload_dict['cl-options'] = cl_options
            workloads_db[workload_dict['name']] = workload_dict
        
        print "Getting benchmarks.."
        benchmarks = xmldoc.getElementsByTagName("benchmark")
        for benchmark in benchmarks:
            benchmark_name = getTagData(benchmark, "name")
            #print "Benchmark name: " + benchmark_name
            benchmark_description = getTagData(benchmark, "description")
            #print benchmark_description
   
            # check if benchmark is sequential or concurrent
            seq = benchmark.getElementsByTagName("sequential")
            conc = benchmark.getElementsByTagName("concurrent")

            assert len(seq) == 0 or len(conc) == 0 # either sequential or concurrent

            workload_instances_list = []
            benchmark_mode = ""

            if len(seq) > 0:
                benchmark_mode = "sequential"
                for seq_workload in seq[0].childNodes:
                    if seq_workload.nodeName == "#text": # ??
                        continue
                    workload_instances_list += [seq_workload.getAttribute("name")]
            elif len(conc) > 0:
                benchmark_mode = "concurrent"
                for conc_workload in conc[0].childNodes:
                    if conc_workload.nodeName == "#text": # ??
                        continue
                    workload_instances_list += [conc_workload.getAttribute("name")]

            benchmarks_db += [{'name': benchmark_name,
                    'description': benchmark_description,
                    'mode': benchmark_mode,
                    'workloads': workload_instances_list}]
    except:
        print "Error parsing the configuration file " + file_path
        exit(-1)
    
    return benchmarks_db

def run_benchmarks(benchmarks):

    myrundir = os.getcwd() + '/work'
    make_dir(myrundir)

    myoutfile = myrundir + '/stdout'
    myerrfile = myrundir + '/stderr'

    fout = open(myoutfile, 'w')
    ferr = open(myerrfile, 'w')
    
    workloads = benchmark['workloads']

    for benchmark in benchmarks:
        print "Benchmark name: " + benchmark['name']
        print "Benchmark description: " + benchmark['description']
        print "Benchmark mode: " + benchmark['mode']

        if benchmark['mode'] == 'sequential':
            for workload in benchmark['workloads']:
                print "Running workload: " + workload
                path = workloads['workload']['path']
                print "Workload path: " + path

                # setup workload
                run_cmd = "python " + path + " setup"
                print "Running command " + run_cmd
                subprocess.Popen(run_cmd, stdout=fout, stderr=ferr)
#-------------------------------------------------------------------------------------------------

parser = argparse.ArgumentParser(description='Run script for AeroSpike on FireBox-0 cluster.')
parser.add_argument('--run', nargs=1, help='run a workload configuration')
parser.add_argument('--list', nargs=1, help='print a workload plan')

args = parser.parse_args()

print '> ================================================================================'
print '> BITS MAIN SCRIPT (VERSION ' + str(version) + ')'
print '> ================================================================================'
print '>'

if args.run:
    print "Running workload " + args.run[0]

    parse_res = parse_xml(args.run[0])

    benchmarks = parse_res[0]
    workloads = parse_res[1]

    print "Running benchmarks"
    run_benchmarks(benchmarks, workloads)

    print "Gathering data from workloads"
    gather_data(benchmarks, workloads)

elif args.plan:
    print "Listing workload " + args.plan[0] + "."

    parse_res = parse_xml(args.plan[0])

    benchmarks = parse_res[0]
    workloads = parse_res[1]

    for benchmark in benchmarks:
        print "Benchmark name: " + benchmark['name']
        print "Benchmark description: " + benchmark['description']
        print "Benchmark mode: " + benchmark['mode']
        for workload in benchmark['workloads']:
            print "Workload name: " + workload

else:
        print '[ERROR] Unknown action'

