Yahoo! Cloud Serving Benchmark (YCSB)
================================================================================

Run scripts for YCSB on the FireBox-0 Cluster at Berkeley (note: these
scripts are currently of limited use in other deployments).

Simple Setup
--------------------------------------------------------------------------------

1. Launch a Cassandra cluster (see README.md in `cassandra` directory).

1. While the cluster is running, change to the `ycsb` directory and get
   another SLURM allocation to run YCSB:

        $ salloc -N1

   This allocation should have exactly one node (multi-node YCSB is not
   supported at this point).

1. Clone and compile the latest version of YCSB:

        $ ./ycsb.py setup

1. Initialize the Cassandra instance with the data for the benchmark.

        $ ./ycsb.py --cassandra <CASSANDRA_DIR>/work/latest/cassandra.json load

   where `CASSANDRA_DIR` is the path in the bits repository from which
   Cassandra was run (`cassandra.json` is a file that describes the
   Cassandra instance, so YCSB knows which nodes to connect to).

1. Run the actual benchmark:

        $ ./ycsb.py --cassandra <CASSANDRA_DIR>/work/latest/cassandra.json run

1. The benchmark results can be found in `work/latest-run/stdout`
