#!/bin/bash
if [ ! -f /usr/share/elasticsearch/plugins/analysis-ik/.installed ]; then
    VERSION=${ES_VERSION:-8.17.4}
    /usr/share/elasticsearch/bin/elasticsearch-plugin install --batch https://release.infinilabs.com/analysis-ik/stable/elasticsearch-analysis-ik-${VERSION}.zip 2>/dev/null
    touch /usr/share/elasticsearch/plugins/analysis-ik/.installed
fi
exec /bin/tini -- /usr/local/bin/docker-entrypoint.sh
