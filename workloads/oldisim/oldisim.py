#! /usr/bin/env python

# Contributors:
# Zach Rowinski <zach@eecs.berkeley.edu> (2015)

import argparse
import getpass
import os
import subprocess
from itertools import chain
from time import sleep
from signal import SIGINT

USER = getpass.getuser()
BUILD_DIR = '/nscratch/%s/fbox-oldisim' % USER 
RUN_DIR = '/data/%s/oldisim' % USER
CLONE_URL = 'https://github.com/GoogleCloudPlatform/oldisim.git'
RUN_TIME = 10 # in seconds

#TODO: specify these in a config file
root_nodes = ['f1']
leaf_nodes = ['f3', 'f4', 'f5']
driver_node = 'f2'

if not os.path.exists(BUILD_DIR):
    print '> Making directory: %s' % BUILD_DIR
    subprocess.call(['mkdir', '-p', BUILD_DIR])

def build_oldisim():
    if not os.getcwd() == BUILD_DIR:
        os.chdir(BUILD_DIR)
    print '> Downloading oldisim'
    subprocess.call(['git', 'clone', CLONE_URL])
    os.chdir(os.path.join(BUILD_DIR, 'oldisim'))
    subprocess.call(['git', 'submodule', 'update', '--init'])
    print '> Building'
    subprocess.call(['scons'])
    
    print '> Build finished'

def setup():
    for node in chain(root_nodes, leaf_nodes, [driver_node]):
        subprocess.call(['ssh', node, 'mkdir', '-p', RUN_DIR])
        
    RELEASE_DIR = os.path.join(BUILD_DIR, 'oldisim/release/workloads/search/')
    
    print '> Copying binary to root nodes'
    dest = '{node}:' + RUN_DIR
    for node in root_nodes:
        subprocess.call(['scp', RELEASE_DIR+'ParentNode', \
                         dest.format(node=node)])
    
    print '> Copying binary to leaf nodes'
    for node in leaf_nodes:
        subprocess.call(['scp', RELEASE_DIR+'LeafNode', \
                         dest.format(node=node)])

    print '> Copying binary to driver node'
    subprocess.call(['scp', RELEASE_DIR+'DriverNode', \
                     dest.format(node=driver_node)])
    
def start(clean_up = False):
    print '> Starting leaf nodes'
    for node in leaf_nodes:
        subprocess.Popen(['ssh', node, \
                           os.path.join(RUN_DIR, 'LeafNode')])
    
    sleep(3)
    
    print '> Starting root nodes'
    for node in root_nodes:
        cmd = ['ssh', node, os.path.join(RUN_DIR, 'ParentNode')]
        for leaf in leaf_nodes:
            cmd.append('--leaf=' + leaf)
        subprocess.Popen(cmd)

    sleep(3)

    print '> Starting driver node'
    driver_cmd = ['ssh', driver_node, os.path.join(RUN_DIR, 'DriverNode')]
    for root in root_nodes:
        driver_cmd.append('--server=' + root)
        
    print '> Running benchmark for %d seconds' % RUN_TIME
    subprocess.Popen(driver_cmd)
    
    sleep(RUN_TIME)
    print '> Finishing benchmark'
    stop(clean_up=clean_up)

def stop(clean_up=False):
    subprocess.call(['ssh', driver_node, 'pkill', '-u', USER, '-INT', '-f', \
                     'DriverNode'])
    sleep(2)
    print 'Terminating all nodes'
    for node in leaf_nodes:
        subprocess.call(['ssh', node, 'pkill', '-u', USER, '-SIGTERM', \
                         '-f', 'LeafNode'])
    for node in root_nodes:
        subprocess.call(['ssh', node, 'pkill', '-u', USER, '-SIGTERM', \
                         '-f', 'ParentNode'])    

    if clean_up == True:
        print '> --cleanup=True'
        print '> Cleaning up nodes'
        all_nodes = root_nodes[:]
        all_nodes.extend(leaf_nodes)
        all_nodes.append(driver_node)
        
        for node in all_nodes:
            print '> Removing node at ', node
            subprocess.call(['ssh', node, 'rm', '-rf', RUN_DIR])

#-----------------------------------------------------------------------------
## Argument list


parser = argparse.ArgumentParser()

parser.add_argument('action')

parser.add_argument('--time', type=int, default=10, \
                    help='Amount of time to run the benchmark')

parser.add_argument('--rundir', type=str, default=RUN_DIR, \
                    help='Install location for nodes')

parser.add_argument('--cleanup', type=bool, default=False, \
                    help='Optionally remove nodes when run is complete')


args = parser.parse_args()

RUN_DIR = args.rundir
clean_up = args.cleanup

if args.action == 'build':
    print '> Starting build process...'
    build_oldisim()
elif args.action == 'setup':
    print '> Setting up nodes'
    setup()
elif args.action == 'start':
    RUN_TIME = args.time
    start(clean_up=clean_up)
elif args.action == 'stop':
    stop(clean_up=clean_up)