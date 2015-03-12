#! /usr/bin/env python

# Contributors:
# Zach Rowinski <zach@eecs.berkeley.edu> (2015)

from collections import defaultdict
from math import ceil
from time import sleep
import argparse
import getpass
import glob
import json
import os
import subprocess
import sys
import time
import urllib2
network_if = 'eth0'


DEFAULT_SOLR_PORT = 8983

HOME_DIR = '/nscratch/zach/'
WORK_DIR = HOME_DIR + 'solrcloud-firebox/'
SOLR_DOCS_DIR = HOME_DIR + 'fbox-data/'
REMOTE_DIR = '/data/solar/'
SOLR_CONF_DIR = 'example/solr/collection1/conf/'
SOLR_CONF = 'solrconfig.xml'
SCHEMA_CONF = 'schema.xml'
HOST_CONF = 'solrcloud-hosts.conf'
# REMOTE_DIR = '/pcie_data/solr/'
zk_version = '3.4.6'
solr_version = '4.10.1'

zk_download_url = 'http://apache.mirrors.pair.com/zookeeper/'
zk_download_url += 'zookeeper-{version}/'
zk_download_url += 'zookeeper-{version}.tar.gz'.format(version=zk_version)

zk_app_zip = 'zookeeper-{version}.tar.gz'.format(version=zk_version)
zk_app = 'zookeeper-{version}'.format(version=zk_version)
local_zk_zip = WORK_DIR + zk_app_zip

zk_dir = REMOTE_DIR + zk_app
zk_data_dir = os.path.join(zk_dir, 'data')
zk_conf_dir = os.path.join(zk_dir, 'conf')

solr_app_tgz = 'solr-{version}.tgz'.format(version=solr_version)
solr_app = 'solr-{version}'.format(version=solr_version)
local_solr_tgz = os.path.join(WORK_DIR, solr_app_tgz)

DNULL = open(os.devnull, 'w')

######## Helper functions ########

class HeadRequest(urllib2.Request):
    def get_method(self):
        return 'HEAD'

######## Zookeeper ########

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
#             zoo_cfg += 'server.%d=%s:2888:3888\n' % (z + 1, k)
            zoo_cfg += 'server.%d=%s:2888:3888\n' % (z + 1, k)

    return zoo_cfg

def setup_zk_ensemble(hosts):
    # Remove previous instance of app
    
    remote_zip = REMOTE_DIR + zk_app_zip
    print '> Removing previous copy of app...',
    p = subprocess.Popen(['srun', 'rm', '-rf', zk_dir, remote_zip])
    p.wait()
    print 'Done'
   
    # Copy zk over and unpack it
    print '> Copying Zookeeper'
    subprocess.call(['sbcast', local_zk_zip, remote_zip])
    subprocess.call(' '.join(['srun', 'tar', 'xfzv', remote_zip,
                              '-C', REMOTE_DIR,
                              '&>', '/dev/null']), shell=True)

    # Generate conf and broadcast to nodes
    print '> Generating Zookeeper conf files'
    subprocess.call(['srun', 'mkdir', zk_data_dir])

    conf = _gen_zoo_cfg(hosts)
    open('zoo.cfg', 'w').write(conf)
    
    subprocess.call(['sbcast', '-f', 'zoo.cfg', os.path.join(zk_conf_dir,
                                                            'zoo.cfg')])
    
    for n, h in enumerate(hosts):
        srun_cmd = ['srun', '--nodelist=' + h, '-N1']
        srun_cmd2 = ['bash', 'myid.sh', zk_data_dir + '/myid', str(n + 1)]
        subprocess.call(srun_cmd + srun_cmd2)
        subprocess.call(srun_cmd + ['rm', '-f', remote_zip])
        
def start_zk_ensemble(zk_hosts):
    for h in zk_hosts:
        print '> Starting Zookeeper host on {}'.format(h)
        srun_cmd = ['srun', '--nodelist=' + h, '-N1']  # for each node...
        # Start each zk instance.
        srun_cmd2 = ['--chdir=' + os.path.join(zk_dir, 'bin'), 'nohup',
                         os.path.join(zk_dir, 'bin/zkServer.sh'),
                         'start-foreground', '>', '/dev/null', '2>&1', '&']
        subprocess.call(' '.join(srun_cmd + srun_cmd2), shell=True)
    sleep(3)
    check_instances_running(zk_hosts, 'zk')


def stop_zk_ensemble():
    print '> Stopping Zookeeper ensemble'

    # Kill all zookeeper processes started by current user
    subprocess.call(['srun', 'pkill', '-f', '-U', getpass.getuser(),
                     'zookeeper'], stderr=DNULL)

def _check_zk_instance(host):
    output = subprocess.check_output('echo srvr | nc {} 2181'.format(host), \
                             shell=True)
        
    if output is not None and output.lower().startswith('zookeeper version'):
        return True
    else:
        return False

def _zk_host_str():
    zk_hosts = get_hosts()['zk_hosts']
    return ','.join([h + ':2181' for h in zk_hosts])

######## Solr ########

def _check_solr_running(instance):
    running = False
    try:
        urllib2.urlopen(HeadRequest('http://%s/solr/#/' % instance))
        running = True
    except:
        running = False

    return running

def check_instances_running(instances, role):
    if role == 'solr':
        check_func = _check_solr_running
    elif role == 'zk':
        check_func = _check_zk_instance
    
    all_running = False
    max_time = 255  # seconds
    elapsed_time = 0
    i = 0
    while not all_running:
        if elapsed_time >= max_time:
            print '> Time expired for {} check.'.format(role)
            print '> Not all {} instances are running.'.format(role)
            return all_running
        
        all_running = all(map(check_func, instances))
        wait_time = 2 ** i # back off exponentially
        i += 1
        if not all_running:
            print '> Waiting for instances to start.',
            print 'Will check again in {} seconds'.format(wait_time)
            time.sleep(wait_time)
        elapsed_time += wait_time
        
    print '> All {} instances are running'.format(role)
    return all_running

def _install_new_solr_instance(host, cur_id, remote_zip):
    cur_dir = os.path.join(REMOTE_DIR, str(cur_id))
    cur_solr_dir = os.path.join(cur_dir, solr_app)
    srun_cmd = ['srun', '--nodelist=' + host, '-N1']
    srun_cmd1 = ['rm', '-rf', cur_dir]  # Remove existing dir
    srun_cmd2 = ['mkdir', cur_dir]  # Make new dir
    srun_cmd3 = ['tar', 'xzfv', remote_zip, '-C', cur_dir, '&>',
                 '/dev/null']
#     srun_cmd3 = ['tar', 'xzfv', remote_zip, '-C', cur_dir]
    srun_cmd4 = ['cp', WORK_DIR + SCHEMA_CONF, os.path.join(
            cur_solr_dir, os.path.join(SOLR_CONF_DIR, SCHEMA_CONF))]
    srun_cmd5 = ['cp', WORK_DIR + SOLR_CONF, os.path.join(
       cur_solr_dir, os.path.join(SOLR_CONF_DIR, SOLR_CONF))]
    

    # Remove previous solr dir
    subprocess.call(srun_cmd + srun_cmd1)
    
    # Create new dir, unzip new solr instance into it
    subprocess.call(srun_cmd + srun_cmd2)
    subprocess.call(' '.join(srun_cmd + srun_cmd3), shell=True)
    
    # Copy config file to new instance
    subprocess.call(srun_cmd + srun_cmd4)
    subprocess.call(srun_cmd + srun_cmd5)



def setup_solr_instances(hosts, n_instances, install_new=True):
    '''Setup solr instances. Copy a version of solr to nodes in a round
    robin fashion. If install_new = False, just return the nodes assignments
    (host, port) of each instance.
    '''

    remote_zip = os.path.join(REMOTE_DIR, solr_app_tgz)
    cur_dir_id = DEFAULT_SOLR_PORT
    
    # Broadcast a copy of Solr to all the nodes
    if install_new:
        subprocess.call(['sbcast', '-f', local_solr_tgz, remote_zip])
    
    # Add hosts to nodes in a round-robin manner
    rounds = int(ceil(n_instances / float(len(hosts))))
    added = 0
    instance_ports = defaultdict(list)
    print '> Setting up Solr instances...'
    for r in range(rounds):

        for n, h in enumerate(hosts):
            if added + 1 > n_instances:
                break
            print '> Setting up Solr instance {} on host {}:{}'.format(
                                                    added + 1, h, cur_dir_id)
            
            if install_new:
                _install_new_solr_instance(h, cur_dir_id, remote_zip)
            #     print '>', zk_dir
            instance_ports[h].append(cur_dir_id)
            added += 1
            
        cur_dir_id += 1
        
    return instance_ports
    
def _start_instances(instance_hosts, n_shards, zk_hosts_str=None):
    if not zk_hosts_str:
        zk_hosts_str = _zk_host_str()
    all_instances = []
    for h in instance_hosts:
        srun_cmd = ' '.join(['srun', '--nodelist=' + h, '-N1'])
    
        for port in instance_hosts[h]:
            # Collection host:port string of all instances
            all_instances.append('{host}:{port}'.format(host=h, port=port))
            
            # increment jmx port with the initial solr port (8983)
            jmx_port = 9010 + int(port) - DEFAULT_SOLR_PORT
            
            # cd into the solr instance dir that will be run
            cur_dir = os.path.join(str(port), solr_app + '/example')
            solr_dir = os.path.join(REMOTE_DIR, cur_dir)
            srun_cmd1 = '--chdir=' + solr_dir
            
            srun_cmd2 = ' '.join(['nohup', 'java', 
            '-XX:+UseConcMarkSweepGC',
            '-DnumShards=' + str(n_shards),
            '-Dbootstrap_confdir=./solr/collection1/conf',
            '-Dcollection.configName=myconf',
            '-Djetty.port=' + str(port),
            '-DzkHost=' + zk_hosts_str,
            '-Dhttp.maxConnections=10',
            '-Dcom.sun.management.jmxremote',
            '-Dcom.sun.management.jmxremote.port=' + str(jmx_port),
            '-Dcom.sun.management.jmxremote.local.only=false',
            '-Dcom.sun.management.jmxremote.authenticate=false',
            '-Dcom.sun.management.jmxremote.ssl=false', '-jar', 'start.jar',
            '>', '/dev/null', '2>&1', '&'])
            

            print '> Starting solr instance at {}:{}'.format(h, port)
            subprocess.call(' ' .join([srun_cmd, srun_cmd1, srun_cmd2]),
                        shell=True)
    
    print '> Waiting for Solr instances to start...'
    time.sleep(2)
    check_instances_running(all_instances, 'solr')

def run_solr_instances(instance_hosts, zk_hosts, n_shards):
    zk_hosts_str = _zk_host_str()
    _start_instances(instance_hosts, n_shards, zk_hosts_str)

def stop_solr():
    hosts = get_hosts()['solr_hosts']
    
    for host in hosts:
        print '> Stopping Solr instances on', host
        cur_dir = os.path.join(str(DEFAULT_SOLR_PORT), solr_app + '/bin')
        solr_dir = os.path.join(REMOTE_DIR, cur_dir)
        
        # Run the stop command and check the exit status
        stopped = subprocess.call(['srun', '--nodelist=' + host, '-N1', '-D', \
                         solr_dir, 'solr', 'stop'], stderr=DNULL, stdout=DNULL)
        if stopped != 0:
            # Default method failed. Terminate using pgrep/pkill
            subprocess.call(['srun', '--nodelist=' + host, '-N1', 'pkill', '-f',
                             'start.jar', '-U', getpass.getuser()],
                            stderr=DNULL)

def restart_solr_instances(n_instances=3, n_shards=3):
    '''Restart Solr instances from a previous session. It is important that
    the n_instances and n_shards parameters are set to the exact same values
    as they were when Solr was last run. Zookeeper must be running'''
    
    stop_solr()
    time.sleep(5)

    all_hosts = get_hosts()
    solr_hosts = all_hosts['solr_hosts']
    zk_hosts = all_hosts['zk_hosts']
    
    if not check_instances_running(zk_hosts, 'zk'):
        print '[ERROR] Zookeeper must be running in order to restart Solr'
        print '[ERROR] Exiting...'
        return
    
    zk_host_str = _zk_host_str()
    print '> Restarting solr instances with zk servers: {}'.format(zk_host_str)
    instances = setup_solr_instances(solr_hosts, n_instances, \
                                     install_new=False)
    _start_instances(instances, n_shards, zk_host_str)

def add_solr_instances(n_instances, n_shards):
    '''Add instances to an existing, healthy* cluster.
    
    *No nodes with indexed data should be down.
    '''
    remote_zip = os.path.join(REMOTE_DIR, solr_app_tgz)
    hosts = get_hosts()['solr_hosts']
    # Get a list of all instances (hosts:ports) that are already running
    # or are being added
    all_instances = setup_solr_instances(hosts, n_instances, install_new=False)
    
    # Collect the names of the instances that need to be newly created
    instances_to_create = defaultdict(list)
    for host in all_instances:
        for port in all_instances[host]:
            instance = ':'.join([host, str(port)])
            if not _check_solr_running(instance):
                instances_to_create[host].append(port)
                _install_new_solr_instance(host, str(port), remote_zip)
    
    # Start just the new instances
    _start_instances(instances_to_create, 3)



######## Add / Query documents ########

def submit_doc(url):
    return subprocess.call(' '.join(['curl', url]), shell=True)
    
def index_sample_documents(dir=SOLR_DOCS_DIR):
    print '> Indexing sample documents. Warning: this may take a few hours'
    docs = []
    hosts = get_hosts()['solr_hosts'].keys()
    target = "http://{}:8983/solr/update".format(hosts[0])
    params = '?stream.file={}&stream.contentType=application/json;charset=utf-8'
    params += '&commit=true'
    
    jsn_docs = glob.glob(os.path.join(SOLR_DOCS_DIR, '*json'))
    jsn_docs.sort()
    
    for d in jsn_docs:
        print '> Submitting {} for indexing ... '.format(d),
        res = urllib2.urlopen(target+params.format(d))
        if res.getcode() != 200:
            print '> There was an error indexing file {}'.format(d)
            continue
        else:
            print 'Finished'

def test_query():
    
    host = get_hosts()['solr_hosts'].keys()[0]  # Pick first solr node off list
    url = '"http://{host}:8983'.format(host=host)
    print '> Submitting test query to {}:8983'.format(host)
    url += '/solr/select?df=text&fl=id&q=computer+science"'
    subprocess.call('curl ' + url, shell=True)
    
def run_demo(num_shards=3, n_instances=3):
    '''Run a demonstration of all the steps needed to setup a SolrCloud cluster
    and populate it with data.
    '''
    
    hosts = get_hosts()
    zk_hosts = hosts['zk_hosts']
    solr_hosts = hosts['solr_hosts']
    setup_zk_ensemble(zk_hosts)
    start_zk_ensemble(zk_hosts)

    
    solr_hosts = setup_solr_instances(solr_hosts, n_instances,
                                      install_new=True)
    run_solr_instances(solr_hosts, zk_hosts=zk_hosts, n_shards=num_shards)
    subprocess.call(['sleep', '10'])
    
    index_prompt = raw_input('''Would you like to start indexing the sample 
    collection (/nscratch/zach/fbox-data)? Warning: indexing may take a few
    hours [Y/n]''')
    
    if index_prompt.upper() == 'Y':
        index_sample_documents()
     
# Get hosts for current setup

def _read_host_conf(conf):
    '''The solrcloud-hosts.conf is a tab-delimited list of hosts and their 
roles. Below is an example of a 5-node allocation with 3 solr nodes and
2 Zookeeper nodes:
    
    f1\tsolr
    f2\tsolr
    f3\tzk
    f4\tzk
    f5\tzk
    '''
    conf = open(conf)
    roles = defaultdict(list)
    for line in conf:
        host, role = line.strip().split('\t')
        roles[role].append(host)
        
    return roles

def get_hosts():
    '''Must run within a SLURM allocation. Unless otherwise specified in the 
    solrcloud-hosts.conf file, assume first 3 nodes are dedicated
    to the Zookeeper servers and that the Solr instances are assigned to the
    remaining available nodes. If only 3 nodes are allocated, Zookeeper 
    and Solr share the nodes.
    '''
    ips = get_ip_addresses(get_slurm_nodelist())
    nhosts = len(ips)
    if nhosts < 3:
        raise ValueError, 'Insufficient number of nodes. Minimum 3 required'
    
    if os.path.exists(HOST_CONF):
        roles = _read_host_conf(HOST_CONF)
        zk_hosts = {}
        solr_hosts = {}
        for h in roles['zk']:
            zk_hosts[h] = ips[h]
        for h in roles['solr']:
            solr_hosts[h] = ips[h]
    else:
        ips = ips.items()
        ips.sort()
        zk_hosts = dict(ips[:3])
        if nhosts == 3:
            solr_hosts = zk_hosts
        else:
            
            solr_hosts = dict(ips[3:])
    
    return {'solr_hosts': solr_hosts, 'zk_hosts': zk_hosts}


def get_live_nodes():
    '''Returns a list ({host}:{port}) of all the running Solr nodes'''
    
    solr_hosts = get_hosts()['solr_hosts'].keys()
    solr_hosts.sort()
    host = solr_hosts[0]  # Pick first solr node off list
    url = 'http://{host}:8983'.format(host=host)
    url += '/solr/zookeeper?path=/live_nodes'
    
    err_msg = '[ERROR] Solr and Zookeeper must be running in order to \
perform this operation'
    
    nodes = []
    try:
        res = urllib2.urlopen(url)
    except:
        print err_msg
        return
    
    if res.getcode() == 200:
        jsn = json.loads(res.read())
        children = [n['data']['title'] for n in jsn['tree'][0]['children']]
        nodes = [c.replace('_solr', '') for c in children]
        nodes.sort()
        internal_hosts = [n.split(':')[0] for n in nodes]
        host_map = {}
        
        # Map solr fbox node names to internal (high-bandwidth) ip addresses
        i = 0
        slr_inx = 0
        while (len(host_map) < len(solr_hosts)) and i < len(nodes):
            h = internal_hosts[i]
            if h not in host_map:
                host_map[h] = solr_hosts[slr_inx]
                slr_inx += 1
            i+=1
        
        # Rename hosts by replacing internal IP addresses with f1,f2, etc names
        for i, h in enumerate(internal_hosts):
            nodes[i] = nodes[i].replace(h, host_map[h])
    else:
        print error_msg
        return
    return nodes


def terminate_session():
    '''Stop all services and remove all Solr data'''
    
    nodes = get_live_nodes()
    stop_solr()
    stop_zk_ensemble()
    print '> Removing Solr data from nodes'
    for n in nodes:
        host, port = n.split(':')
         
        subprocess.call(['srun', '-N1', '--nodelist='+host, 'rm', '-rf', \
                         os.path.join(REMOTE_DIR, port)])
    
    # Finally, remove any remaining Solr archive files
    solr_archive = os.path.join(REMOTE_DIR, solr_app_tgz)
    for h in get_hosts()['solr_hosts']:
        subprocess.call(['srun', '-N1', '--nodelist='+h, 'rm', '-rf', \
                         solr_archive, zk_dir])
        
    
    print '> Finished'
    
#######################################
# Return the list of nodes in the current SLURM allocation
# below is from Martin Maas' cassandra.py code on github ucb-bits

def get_slurm_nodelist():
    nodelist = subprocess.check_output(\
        ['scontrol', 'show', 'hostname', os.environ['SLURM_NODELIST']], \
        universal_newlines=True)
    nodelist = nodelist.strip().split('\n')
    return nodelist

# Return list of the Ip addresses for the chosen network_if on all nodes in nodelist
def get_ip_addresses(nodelist):
    results = subprocess.check_output(\
       ['srun', '--nodelist=' + ','.join(nodelist), 'bash', \
        '../common/get_ip_address.sh', network_if], universal_newlines=True)
    json_str = '[' + ','.join(results.splitlines()) + ']'
    raw_data = json.loads(json_str)
    ip_map = {}
    for entry in raw_data:
        ip_map[entry['host']] = entry['ip']
    return ip_map

#######################################

#### Commands

parser = argparse.ArgumentParser(
                         description='Setup SolrCloud to run on Firebox-0.')
parser.add_argument('action',
    help='''Available actions: 
    setup-zk 
    start-zk 
    stop-zk 
    check-zk-health
    setup-solr 
    start-solr
    stop-solr
    restart-solr
    get-live-nodes
    run-demo
    index-samples
    test-query
    terminate-session
    ''')

parser.add_argument('--instances', type=int, default=3, \
                    help='The number of solr instances to setup/run. default=3')
parser.add_argument('--shards', type=int, default=3, \
                    help='The number of shards in the collection. default=3')

args = parser.parse_args()

if (not 'SLURM_NODELIST' in os.environ) or (not os.environ['SLURM_NODELIST']):
    print '[ERROR] Need to run script within SLURM allocation'
    exit(1)

print '> COMMAND = ' + str(args.action)

num_shards = args.shards
n_instances = args.instances

# ## ZK and Solr hosts
all_hosts = get_hosts()
solr_hosts = all_hosts['solr_hosts']
zk_hosts = all_hosts['zk_hosts']

if args.action == 'setup-zk':

    setup_zk_ensemble(zk_hosts)
elif args.action == 'start-zk':
    start_zk_ensemble(zk_hosts)
elif args.action == 'stop-zk':
    stop_zk_ensemble()
elif args.action == 'check-zk-health':
    check_zk_running()
elif args.action == 'setup-solr':
    solr_instances = setup_solr_instances(solr_hosts, n_instances=n_instances,
                                          install_new=True)
elif args.action == 'start-solr':
    solr_hosts = setup_solr_instances(solr_hosts, n_instances,
                                      install_new=False)
    run_solr_instances(solr_hosts, zk_hosts=zk_hosts, n_shards=num_shards)
elif args.action == 'run-demo':
    run_demo(num_shards=num_shards, n_instances=n_instances)
elif args.action == 'stop-solr':
    stop_solr()
elif args.action == 'restart-solr':
    restart_solr_instances(n_instances=n_instances, n_shards=num_shards)
elif args.action == 'add-solr-instances':
    # n_instance is the resultant, total number you want in the cluster
    # including any instances already instantiated and started
    add_solr_instances(n_instances, num_shards)
elif args.action == 'index-samples':
    index_sample_documents()
elif args.action == 'test-query':
    test_query()
elif args.action == 'get-live-nodes':
    print 'Live Solr instances:', get_live_nodes()
elif args.action == 'terminate-session':
    terminate_session()
else:
    print '[ERROR] Unknown action \'' + args.action[0] + '\''

