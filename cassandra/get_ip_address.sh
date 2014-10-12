#/usr/bash

# Invoke as ./get_ip_address <interface>
HOSTNAME=`hostname`
IP=`ifconfig eth0 | grep "inet addr" | sed 's/.*inet addr:\([0-9.]\+\).*/\1/'`

#echo $HOSTNAME $IP
echo '{"host":"'$HOSTNAME'","ip":"'$IP'"}'
