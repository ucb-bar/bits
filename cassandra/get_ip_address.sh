#/usr/bash

# Invoke as ./get_ip_address <interface>
hostname
ifconfig eth3 | grep "inet addr" | sed 's/.*inet addr:\([0-9.]\+\).*/\1/'
