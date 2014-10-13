Apache Cassandra
================================================================================

Run scripts for Cassandra on the FireBox-0 Cluster at Berkeley (note: these
scripts are currently of limited use in other deployments).

Simple Setup
--------------------------------------------------------------------------------

1. Clone the bits repository and change into the `cassandra` directory.

1. Get a SLURM allocation for the required number of nodes, e.g.

        $ salloc -N4

1. Download and setup the selected Cassandra version:

        $ ./cassandra.py setup

1. Launch the Cassandra cluster:

        $ ./cassandra.py start

1. To shut down the Cluster, terminate the process with CTRL+C.

Advanced Settings
--------------------------------------------------------------------------------

Modify variables at the start of the cassandra.py script to change settings, 
such as the network interface (`network_if`) or the Cassandra version.
