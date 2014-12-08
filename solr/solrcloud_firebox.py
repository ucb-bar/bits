#! /usr/bin/env python
import getpass
import os
import glob
import subprocess
import multiprocessing
import json
import urllib
import time
import argparse
import sys
from math import ceil
from collections import defaultdict
network_if = 'eth0'


HOME_DIR = '/nscratch/zach/'
WORK_DIR = HOME_DIR + 'solrcloud-firebox/'
SOLR_DOCS_DIR = HOME_DIR + 'fbox-data/'
REMOTE_DIR = '/data/solar/'
zk_version = '3.4.6'
solr_version = '4.10.1'

zk_download_url = 'http://apache.mirrors.pair.com/zookeeper/'
zk_download_url += 'zookeeper-{version}/'
zk_download_url += 'zookeeper-{version}.tar.gz'.format(version=zk_version)

zk_app_zip = 'zookeeper-{version}.tar.gz'.format(version=zk_version)
zk_app = 'zookeeper-{version}'.format(version=zk_version)
local_zk_zip = WORK_DIR + zk_app_zip

# Remove old data and create zk_dir anew
zk_dir = REMOTE_DIR + zk_app
zk_data_dir = os.path.join(zk_dir, 'data')
zk_conf_dir = os.path.join(zk_dir, 'conf')

solr_app_tgz = 'solr-{version}.tgz'.format(version=solr_version)
solr_app = 'solr-{version}'.format(version=solr_version)
local_solr_tgz = os.path.join(WORK_DIR, solr_app_tgz)


######## Zookeeper

def _gen_zoo_cfg(zkHosts):
    # zkhosts is a list with addresses to hosts
    
    zoo_cfg = ''
    zoo_cfg += 'tickTime=2000\n'
    zoo_cfg += 'initLimit=10\n'
    zoo_cfg += 'syncLimit=5\n'
    zoo_cfg += 'dataDir={}\n'.format(zk_data_dir)
    zoo_cfg += 'clientPort=2181\n'
    numHosts = len(zkHosts)
    if numHosts > 1:
        for z, k in enumerate(zkHosts): 
            zoo_cfg += 'server.%d=%s:2888:3888\n' % (z + 1, k)

    return zoo_cfg


def _zk_ensemble(hosts):
    # Remove previous instance of app
#     if os.path.exists(zk_dir):
    print local_zk_zip
    remote_zip = REMOTE_DIR + zk_app_zip
    print zk_dir
    print 'Removing previous copy of app...',
    p = subprocess.Popen(['srun', 'rm', '-rf', zk_dir, remote_zip])
    p.wait()
    print 'Done'
   

    # Copy zk over and unpack it
    print 'Copying Zookeeper'
    subprocess.call(['sbcast', local_zk_zip, remote_zip])
    subprocess.call(' '.join(['srun', 'tar', 'xfzv', remote_zip, 
                              '-C', REMOTE_DIR,
                              '&>', '/dev/null']), shell=True)
    subprocess.call(['srun', 'mkdir', zk_data_dir])

    conf = _gen_zoo_cfg(hosts)
    open('zoo.cfg', 'w').write(conf)
    
    subprocess.call(['sbcast', '-f','zoo.cfg', os.path.join(zk_conf_dir, 
                                                            'zoo.cfg')])
    
    for n, h in enumerate(hosts):
        srun_cmd = ['srun', '--nodelist=' + h, '-N1']
        srun_cmd2 = ['bash', 'myid.sh', zk_data_dir + '/myid', str(n+1)]
        subprocess.call(srun_cmd+srun_cmd2)

    
def start_zk_ensemble(zk_hosts):
    # Start zookeeper instances
    
    for h in zk_hosts:
        print 'Starting Zookeeper host on {}'.format(h)
        srun_cmd = ['srun', '--nodelist=' + h, '-N1'] # for each node...
        # Start each zk instance.
        srun_cmd2 = ['--chdir=' + os.path.join(zk_dir, 'bin'), 
                         os.path.join(zk_dir, 'bin/zkServer.sh'), 
                         'start-foreground', '>', '/dev/null', '2>&1', '&']
        subprocess.call(' '.join(srun_cmd + srun_cmd2), shell=True)
        


def setup_zk_ensemble(hosts):
    _zk_ensemble(hosts)
    
def stop_zk_ensemble(hosts=None):
#     subprocess.call(['srun', 'bash', os.path.join(zk_dir, 'bin/zkServer.sh'), \
#                     'stop'])

    # Kill all zookeeper processes started by current user
    subprocess.call(['srun', 'pkill', '-f','-U', getpass.getuser(), 
                     'zookeeper'])



def _zk_host_str():
    zk_hosts = get_hosts()['zk_hosts']
    return ','.join([h+':2181' for h in zk_hosts])


######## Solr

def setup_solr_instances(hosts, n_instances, install_new=True):
    '''Setup solr instances. Copy a version of solr to nodes in a round
    robin fashion. If install_new = False, just return the nodes assignments
    (host, port) of each instance.
    '''

    remote_zip = os.path.join(REMOTE_DIR, solr_app_tgz)
    cur_dir_id = 8983
    
    # Broadcast a copy of Solr to all the nodes
    if install_new:
        subprocess.call(['sbcast', '-f', local_solr_tgz, remote_zip])
    
    
    # Add hosts to nodes in a round-robin manner
    rounds = int(ceil(n_instances/float(len(hosts))))
    added = 0
    instance_ports = defaultdict(list)
    print 'Setting up instances...'
    for r in range(rounds):
        cur_dir = os.path.join(REMOTE_DIR, str(cur_dir_id))
        cur_solr_dir = os.path.join(cur_dir, solr_app)
        for n, h in enumerate(hosts):
            if added + 1 > n_instances:
                break
            print 'Setting up solr instance {} on host {}:{}'.format(
                                                    added + 1, h, cur_dir_id)
            
            srun_cmd = ['srun', '--nodelist=' + h, '-N1']
            srun_cmd1 = ['rm', '-rf', cur_dir] # Remove existing dir
            srun_cmd2 = ['mkdir', cur_dir] # Make new dir
            srun_cmd3 = ['tar', 'xzfv', remote_zip, '-C', cur_dir, '&>', 
                         '/dev/null']
            srun_cmd4 = ['cp', WORK_DIR+'schema.xml', os.path.join(
                    cur_solr_dir,'example/solr/collection1/conf/schema.xml')]
            srun_cmd5 = ['cp', WORK_DIR+'solrconfig.xml', os.path.join(
               cur_solr_dir, 'example/solr/collection1/conf/solrconfig.xml')]
            
            if install_new:
                # Remove previous solr dir
                subprocess.call(srun_cmd+srun_cmd1)
                
                # Create new dir, unzip new solr instance into it
                subprocess.call(srun_cmd+srun_cmd2)
                subprocess.call(' '.join(srun_cmd+srun_cmd3), shell=True)
                
                # Copy config file to new instance
                subprocess.call(srun_cmd+srun_cmd4)
                subprocess.call(srun_cmd+srun_cmd5)
            
            
            instance_ports[h].append(cur_dir_id)
            added += 1
            

        cur_dir_id += 1
        
    return instance_ports
    
def _start_instances(instance_hosts, n_shards, zk_hosts_str):
    for h in instance_hosts:
        srun_cmd = ' '.join(['srun', '--nodelist=' + h, '-N1'])
    
        jmx_port = 9010
        for port in instance_hosts[h]:
            
            # cd into the solr instance dir that will be run
            cur_dir = os.path.join(str(port), solr_app+'/example')
            solr_dir = os.path.join(REMOTE_DIR, cur_dir)
            srun_cmd1 = '--chdir='+solr_dir
            
            
            srun_cmd2 = ' '.join(['java', '-DnumShards=' + str(n_shards), 
            '-Dbootstrap_confdir=./solr/collection1/conf', 
            '-Dcollection.configName=myconf',
            '-Djetty.port=' + str(port),
            '-DzkHost='+zk_hosts_str, 
            '-Dcom.sun.management.jmxremote', 
            '-Dcom.sun.management.jmxremote.port=' + str(jmx_port), 
            '-Dcom.sun.management.jmxremote.local.only=false', 
            '-Dcom.sun.management.jmxremote.authenticate=false', 
            '-Dcom.sun.management.jmxremote.ssl=false', '-jar', 'start.jar', 
            '>', '/dev/null', '2>&1', '&'])
            
            jmx_port += 1
            print 'Starting solr instance at {}:{}'.format(h, port)
        subprocess.call(' ' .join([srun_cmd, srun_cmd1, srun_cmd2]), 
                        shell=True)



def run_solr_instances(instance_hosts, zk_hosts, n_shards, n_instances=None):
    zk_hosts_str = _zk_host_str(zk_hosts)
    if not n_instances:
        n_instances = sum(len(instance_hosts[h]) for h in instance_hosts)
    
    _start_instances(instance_hosts, n_shards, zk_hosts_str)

def stop_solr():
    print 'Pid of running instances:'
    subprocess.call(['srun', 'pgrep', '-f','-U', getpass.getuser(), 
                     'start.jar'])
    print 'Killing all solr instances'
    subprocess.call(['srun', 'pkill', '-f','-U', getpass.getuser(), 
                     'start.jar'])

def restart_solr_instances(n_instances=3, n_shards=3):
    
    hosts = get_hosts()['solr_hosts']
    zk_host_str = _zk_host_str()
    print 'Restarting solr instances with zk servers: {}'.format(zk_host_str)
    instances = setup_solr_instances(hosts, n_instances, install_new=False)
    _start_instances(instances, n_shards, zk_host_str)

def submit_doc(url):
    subprocess.call(' '.join(['curl', url]), shell=True)


######## Add / Query documents

def index_sample_documents(hosts, dir=SOLR_DOCS_DIR, processes=2):
    print 'Indexing sample documents. Warning: this may take a few hours'
    pool = multiprocessing.Pool(processes=processes)
    docs = []
    hosts = hosts.keys()
    target = '"http://{}:8983/solr/update'.format(hosts[0])
    params = '?stream.file={}&stream.contentType=application/json;charset=utf-8"'
    
    for d in glob.glob(os.path.join(SOLR_DOCS_DIR, '*json')):
#         h = hosts[i % len(hosts)] # distribute hosts evenly
        docs.append(target.format(h) + params.format(d))
    
    pool.map(submit_doc, docs)

def test_query():
    
    host = get_hosts()['solr_hosts'].keys()[0] #Pick first solr node off list
    url = '"http://{host}:8983'.format(host=host)
    print 'Submitting test query to {}:8983'.format(host)
    url += '/solr/select?df=text&fl=title&q=computer+science"'
    subprocess.call('curl ' + url, shell=True)
    

# Get hosts for current setup

def get_hosts():
    '''Must run within a SLURM allocation. Assume first 3 nodes are dedicated
    to the Zookeeper servers. Solr instances are assigned to the remaining
    nodes. If only 3 nodes are allocated, Zookeeper and Solr share the nodes.
    '''
    ips = get_ip_addresses(get_slurm_nodelist()).items()
    ips.sort()
    nhosts = len(ips)
    if nhosts < 3:
        raise ValueError, 'Insufficient number of nodes. Minimum 3 required'
    
    zk_hosts = dict(ips[:3])
    if nhosts == 3:
        solr_hosts = zk_hosts
    else:
        solr_hosts = dict(ips[3:])
    
    return {'solr_hosts': solr_hosts, 'zk_hosts': zk_hosts}

#######################################
# Return the list of nodes in the current SLURM allocation
# below is from Martin Maas' cassandra.py code on github ucb-bits

def get_slurm_nodelist():
    nodelist = subprocess.check_output( \
        ['scontrol', 'show', 'hostname', os.environ['SLURM_NODELIST']], \
        universal_newlines=True)
    nodelist = nodelist.strip().split('\n')
    return nodelist

# Return list of the Ip addresses for the chosen network_if on all nodes in nodelist
def get_ip_addresses(nodelist):
    results = subprocess.check_output( \
       ['srun', '--nodelist=' + ','.join(nodelist), 'bash', \
        '../common/get_ip_address.sh', network_if], universal_newlines=True)
    json_str = '[' + ','.join(results.splitlines()) + ']'
    raw_data = json.loads(json_str)
    ip_map = {}
    for entry in raw_data:
        ip_map[entry['host']] = entry['ip']
    return ip_map


#### Commands

parser = argparse.ArgumentParser(
                         description='Setup SolrCloud to run on Firebox-0.')
parser.add_argument('action', nargs=1,
    help='''the action to perform: setup-zk, start-zk, stop-zk, setup-solr,
    start-solr, stop-solr, restart-solr, run-demo, index-samples, test-query.
    
    "run-demo" starts 3 zookeeper instances and 3 solr instances/shards
    '''

args = parser.parse_args()


if not os.environ['SLURM_NODELIST']:
    print '[ERROR] Need to run script within SLURM allocation'
    exit(1)

print '> COMMAND = ' + str(args.action)

if args.action[0] == 'setup-zk':
    setup_zk_ensemble()
elif args.action[0] == 'start-zk':
    start_zk_ensemble()
elif args.action[0] == 'stop-zk':
    stop_zk_ensemble()
elif args.action[0] == 'setup-solr':
    hosts = setup_solr_instances(n_instances=3, install_new=True)
elif args.action[0] == 'start-solr':
    hosts = setup_solr_instances(n_instances=3, install_new=False)
    run_solr_instances(hosts, zk_hosts='blah', n_shards=4)
elif args.action[0] == 'run-demo':
    num_shards = 3
    n_instances = 3
    hosts = get_hosts()
    zk_hosts = hosts['zk_hosts']
    solr_hosts = hosts['solr_hosts']
    setup_zk_ensemble(zk_hosts)
    start_zk_ensemble(zk_hosts)
    # check_zk_running(zk_hosts)
    solr_hosts = setup_solr_instances(solr_hosts, n_instances, 
                                      install_new=True)
    run_solr_instances(solr_hosts, zk_hosts=zk_hosts, n_shards=num_shards)
    subprocess.call(['sleep', '10'])
elif args.action[0] == 'stop-solr':
    stop_solr()
elif args.action[0] == 'restart-solr':
    restart_solr_instances()
elif args.action[0] == 'index-samples':
    hosts = get_hosts()
    solr_hosts = hosts['solr_hosts']
    index_sample_documents(hosts=solr_hosts)
elif args.action[0] == 'test-query':
    test_query()
else:
    print '[ERROR] Unknown action \'' + args.action[0] + '\''





