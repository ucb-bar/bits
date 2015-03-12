## Getting started

Allocate nodes with slurm. A minimum of 3 are required

```
$ salloc -N3
```

cd into the bits/solr repository

The fastest way to get started is to run the demo:

```
$ python solrcloud_firebox.py run-demo
```

This will start 3 Zookeeper and 3 Solr instances, 1 instance of each on each machine. By default, the first 3 machines in the allocation will be given to Zookeeper. The rest will be given to Solr or shared with the Zookeper machines. 

You can also specify the how many instances and shards you would like to use:

```
$ python solrcloud_firebox.py run-demo --shards 3 --instances 6
```

This splits the index into 3 shards that will be serviced by 6 instances (3 leaders and 3 replicas). Generally speaking, if the number of instances is more than the number of shards, Solrcloud will automatically create replicas of the existing shards.

### Stopping Solr and Zookeeper

Be sure to stop all the Solr and Zookeeper instances when finished with testing:

```
$ python solrcloud_firebox.py stop-solr

$ python solrcloud_firebox.py stop-zk
```

Alternatively, if you are done testing and want to stop all services and remove all Solr data from disk, you can terminate the session completely:

```
$ python solrcloud_firebox.py terminate-session
```

### Indexing the sample collection
The "run-demo" command will ask if you want to use start indexing a set of sample documents located on /nscratch. This sample set contains 50 million synthetically generated documents that take up 200 GB of storage on disk. It usually takes a few hours to index this sample set completely. If you would like to index a set of documents with a different schema, you will need to modify the solrcloud_firebox.py code to point to a different schema.xml file. 

### Manually specifying layout of nodes
You can specify the layout of nodes by including solrcloud-hosts.conf file in the  directory where solrcloud_firebox.py script is located. The solrcloud-hosts.conf is a tab-delimited file listing a mapping of Firebox nodes to instance types ("solr" or "zk"). The example below puts Solr on the f1, f2, and f3 nodes and collocates Solr and Zookeeper on nodes f4, f5, and f6:

```
f1  solr
f2  solr
f3  solr
f4  solr
f5  solr
f6  solr
f4  zk
f5  zk
f6  zk
```

If you have more than 3 nodes and don't include a solrcloud-hosts.conf file, solrcloud_firebox.py will place Zookeeper ONLY on the first 3 nodes and no Solr instances. If you want ZK and Solr to share nodes, use the solrcloud_hosts.conf file (or only allocate 3 nodes).


