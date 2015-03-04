#!/usr/bin/env python

# Bits main script
# 1) setup and deployment of workloads in bulk in Firebox
# 2) running workloads
# 3) gathering the results

# the different workloads are integrated via:
# 1) xml configuration files that describe and specify paths to the workloads code
# 2) an interface shared by all the workloads to a) setup, 2) launch, 3) stop, 4) collect results

# USE CASES:
# ./bits.py --run <benchmark.xml> 
# ./bits.py --plan <benchmark.xml> 

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

#-------------------------------------------------------------------------------------------------

parser = argparse.ArgumentParser(description='Run benchmarks / workloads in firebox.')
parser.add_argument('--run', nargs=1, help='run a benchmark')
parser.add_argument('--plan', nargs=1, help='print a benchmark plan')

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
    print '[ERROR] Unknown action \'' + args.action[0] + '\''


