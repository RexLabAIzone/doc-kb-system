FROM elasticsearch:8.17.4

ARG ES_VERSION=8.17.4

RUN if command -v yum &>/dev/null; then         yum install -y -q wget unzip &&         wget -q https://release.infinilabs.com/analysis-ik/stable/elasticsearch-analysis-ik-${ES_VERSION}.zip -O /ik.zip &&         /usr/share/elasticsearch/bin/elasticsearch-plugin install --batch file:///ik.zip &&         rm -f /ik.zip &&         yum remove -y -q wget unzip &&         yum clean all;     elif command -v microdnf &>/dev/null; then         microdnf install -y wget unzip &&         wget -q https://release.infinilabs.com/analysis-ik/stable/elasticsearch-analysis-ik-${ES_VERSION}.zip -O /ik.zip &&         /usr/share/elasticsearch/bin/elasticsearch-plugin install --batch file:///ik.zip &&         rm -f /ik.zip &&         microdnf remove -y wget unzip &&         microdnf clean all;     fi

USER elasticsearch
