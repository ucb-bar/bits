#/bin/bash
if [ -z "$CASSANDRA_CONF" ]; then
  echo "Need to set CASSANDRA_CONF"
  exit 1
fi

if [ -z "$CASSANDRA_HOME" ]; then
  echo "Need to set CASSANDRA_HOME"
  exit 1
fi

export JVM_OPTS="$JVM_OPTS -Xss256k"

echo "Running Cassandra with bin/cassandra -f"
echo "NODE" $(hostname)
echo "CASSANDRA_HOME="$CASSANDRA_HOME
echo "CASSANDRA_CONF="$CASSANDRA_CONF
echo "JVM_OPTS=$JVM_OPTS"
$CASSANDRA_HOME/bin/cassandra -f
