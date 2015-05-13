#! /bin/bash

SOLRFILE="/data/solar/$1/solr-4.10.1/example/solr/solr.xml"
URL="$2.millennium.berkeley.edu"
EXPR="s/\${host:}/$URL/g"
sed -i $EXPR $SOLRFILE