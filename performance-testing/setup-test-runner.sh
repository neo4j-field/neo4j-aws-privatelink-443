#!/usr/bin/env bash
# Installs everything needed to run the HAProxy-vs-Direct JMeter performance
# test on a fresh RHEL/Amazon Linux test-runner host.
#
# Usage:
#   ./setup-test-runner.sh
#
# Safe to re-run — every step is idempotent (skips what's already installed).

set -euo pipefail

JMETER_VERSION="5.6.3"
JMETER_URL="https://downloads.apache.org/jmeter/binaries/apache-jmeter-${JMETER_VERSION}.tgz"
JMETER_URL_FALLBACK="https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-${JMETER_VERSION}.tgz"
INSTALL_DIR="/opt/apache-jmeter-${JMETER_VERSION}"

echo "=== 1/2: Java (required by JMeter) ==="
if command -v java >/dev/null 2>&1; then
  echo "Already installed: $(java -version 2>&1 | head -1)"
else
  sudo dnf install -y java-21-openjdk
fi

echo
echo "=== 2/2: Apache JMeter ${JMETER_VERSION} ==="
if command -v jmeter >/dev/null 2>&1; then
  echo "Already installed: $(jmeter --version 2>&1 | head -1)"
else
  TMP_TGZ="/tmp/apache-jmeter-${JMETER_VERSION}.tgz"
  curl -fsSL -o "$TMP_TGZ" "$JMETER_URL" || curl -fsSL -o "$TMP_TGZ" "$JMETER_URL_FALLBACK"
  sudo tar -xzf "$TMP_TGZ" -C /opt
  sudo ln -sf "${INSTALL_DIR}/bin/jmeter" /usr/local/bin/jmeter
  rm -f "$TMP_TGZ"
fi

echo
echo "=== Versions ==="
java -version 2>&1 | head -1
jmeter --version 2>&1 | head -1

echo
echo "Setup complete. Seed the test data, then run the test:"
echo "  cypher-shell -a bolt+ssc://<host>:7687 -u neo4j -p '<password>' -f seed-data.cypher"
echo "  jmeter -n -t jmeter/HAProxy-vs-Direct-Neo4j.jmx -JNEO4J_PASSWORD='<password>' -l results.jtl -e -o report/"
