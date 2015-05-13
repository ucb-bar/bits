#!/bin/bash

# Latency/Bandwidth benchmarks for the firebox cluster
# Run this script on a f[2-16] node

export SERVER_NODE=f1
# sleep time in seconds
export TIME=1
export BREAK_LINE="-----------------------------------------------"
export NEWLINES='printf \n\n'
export F1_IP=10.10.49.83


function print_header {
    $NEWLINES
    echo $BREAK_LINE
    echo $1
    echo $BREAK_LINE
}

####################
# BENCHMARKS BELOW #
####################


#
# RDMA read latency between two nodes (RTT)
#
print_header "RDMA read latency between $(hostname) and $SERVER_NODE"

ssh -f $SERVER_NODE ib_read_lat
sleep $TIME
ib_read_lat $SERVER_NODE


#
# RDMA write latency between two nodes (half RTT)
#
print_header "RDMA write latency between $(hostname) and $SERVER_NODE"

ssh -f $SERVER_NODE ib_write_lat
sleep $TIME
ib_write_lat $SERVER_NODE


#
# IPoIB latency ping pong tests.
#

# InfiniBand Reliable Connection transport test
print_header "IB Reliable connect between $(hostname) and $SERVER_NODE"

ssh -f $SERVER_NODE ibv_rc_pingpong
sleep $TIME
ibv_rc_pingpong $SERVER_NODE


#  InfiniBand Unreliable Connection transport test
print_header "IB Unreliable connect between $(hostname) and $SERVER_NODE"

ssh -f $SERVER_NODE ibv_uc_pingpong 
sleep $TIME
ibv_uc_pingpong $SERVER_NODE

# Infiniband Unreliable Datagram transport test
print_header "IB Unreliable datagram connect between $(hostname) and $SERVER_NODE"

ssh -f $SERVER_NODE ibv_ud_pingpong
sleep $TIME
ibv_ud_pingpong $SERVER_NODE

#
# RDMA read bandwidth between two nodes
#

print_header "RDMA read bandwidth between $(hostname) and $SERVER_NODE"

ssh -f $SERVER_NODE ib_read_bw
sleep $TIME
ib_read_bw $SERVER_NODE

#
# RDMA write bandwidth between two nodes
#

print_header "RDMA write bandwidth between $(hostname) and $SERVER_NODE"

ssh -f $SERVER_NODE ib_write_bw
sleep $TIME
ib_write_bw $SERVER_NODE

#
# Iperf bandwidth benchmark between two nodes
#

print_header "(iperf) bandwidth between $(hostname) and $SERVER_NODE"

ssh -f $SERVER_NODE "iperf -s"
sleep $TIME
iperf -c $SERVER_NODE -P 8 # 8 threads
ssh $SERVER_NODE "killall iperf"

#
# Intel MPI ping pong Benchmark
#

print_header "Intel MPI ping pong benchmark between two nodes"

export MPI_EXEC=/opt/openmpi/bin/mpirun
export MACHINE_FILE=/nscratch/joao/firebox_2_hosts_mpi
export IMB_EXEC=/home/eecs/joao/mpi_benchmark/imb/src/IMB-MPI1

$MPI_EXEC --mca btl_openib_verbose,btl_tcp_if_include "ib0" --mca btl ^tcp -n 2 -machinefile $MACHINE_FILE $IMB_EXEC pingpong

#
# Sockperf benchmark without kernel bypass
#

print_header "Sockperf ping pong benchmark (w/o kernel bypass) between $(hostname) and $SERVER_NODE"

export SOCKP_EXEC=/home/eecs/joao/sock_perf/sockperf-2.5.241/src/sockperf

ssh -f $SERVER_NODE "VMA_MTU=2044 $SOCKP_EXEC sr --nonblocked --tcp-skip-blocking-send --tcp-avoid-nodelay"
sleep $TIME
VMA_MTU=2044 $SOCKP_EXEC pp -i $F1_IP --nonblocked --tcp-skip-blocking-send --sender-affinity 8 --receiver-affinity 2

ssh $SERVER_NODE "killall sockperf" # kill the sockperf server

#
# Sockperf benchmark with kernel bypass
#

print_header "Sockperf ping pong benchmark (with kernel bypass) between $(hostname) and $SERVER_NODE"

ssh -f $SERVER_NODE "VMA_MTU=1500 $SOCKP_EXEC sr --nonblocked --tcp-skip-blocking-send --tcp-avoid-nodelay --vmazcopyread --load-vma"
sleep $TIME
VMA_MTU=1500 $SOCKP_EXEC pp -i $F1_IP --nonblocked --tcp-skip-blocking-send --sender-affinity 8 --receiver-affinity 2 --load-vma

ssh $SERVER_NODE "killall sockperf" # kill the sockperf server
