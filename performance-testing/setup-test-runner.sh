#!/usr/bin/env bash
# Installs everything needed to run the Bolt HAProxy-vs-Direct JMeter
# performance test on a fresh RHEL/Amazon Linux test-runner host (the
# Central VPC client, e.g. neo4j-nes-server-1 in ca-central-1).
#
# This test drives real Bolt protocol via a JSR223 (Groovy) Sampler backed
# by the official Neo4j Java driver, since JMeter has no native Bolt sampler.
# The driver ships as a single shaded jar, so setup is just dropping it into
# JMeter's lib/ folder.
#
# Usage:
#   ./setup-test-runner.sh
#
# Safe to re-run, every step is idempotent (skips what's already installed).

set -euo pipefail

JMETER_VERSION="5.6.3"
JMETER_URL="https://downloads.apache.org/jmeter/binaries/apache-jmeter-${JMETER_VERSION}.tgz"
JMETER_URL_FALLBACK="https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-${JMETER_VERSION}.tgz"
INSTALL_DIR="/opt/apache-jmeter-${JMETER_VERSION}"

NEO4J_DRIVER_VERSION="5.26.0"
NEO4J_DRIVER_JAR="neo4j-java-driver-${NEO4J_DRIVER_VERSION}.jar"
NEO4J_DRIVER_URL="https://repo1.maven.org/maven2/org/neo4j/driver/neo4j-java-driver/${NEO4J_DRIVER_VERSION}/${NEO4J_DRIVER_JAR}"

echo "=== 1/3: Java (required by JMeter) ==="
if command -v java >/dev/null 2>&1; then
  echo "Already installed: $(java -version 2>&1 | head -1)"
else
  sudo dnf install -y java-21-openjdk
fi

echo
echo "=== 2/3: Apache JMeter ${JMETER_VERSION} ==="
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
echo "=== 3/3: Neo4j Java Driver ${NEO4J_DRIVER_VERSION} (Bolt protocol support for JSR223 samplers) ==="
DEST="${INSTALL_DIR}/lib/${NEO4J_DRIVER_JAR}"
if [ -f "$DEST" ]; then
  echo "Already present: $DEST"
else
  curl -fsSL -o /tmp/"${NEO4J_DRIVER_JAR}" "$NEO4J_DRIVER_URL"
  sudo mv /tmp/"${NEO4J_DRIVER_JAR}" "$DEST"
  echo "Installed: $DEST"
fi

echo
echo "=== Versions ==="
java -version 2>&1 | head -1
jmeter --version 2>&1 | head -1
echo "neo4j-java-driver: ${NEO4J_DRIVER_VERSION}"

echo
echo "Setup complete. JMeter must be restarted to pick up the new lib/ jar if it was already running."
echo "Next steps:"
echo "  1. Seed the test data (run once against any node):"
echo "     cypher-shell -a bolt+ssc://<any-node-public-ip>:7687 -u neo4j -p '<password>' -f seed-data.cypher"
echo "  2. Run the test (override current public IPs, they change on restart):"
echo "     cd jmeter"
echo "     jmeter -n -t Bolt-HAProxy-vs-Direct.jmx \\"
echo "       -JDIRECT_HOST=<east-node-public-ip> -JDIRECT_PORT=7687 \\"
echo "       -JVIA_HAPROXY_HOST=privatelink.neo4jfield.org -JVIA_HAPROXY_PORT=443 \\"
echo "       -JNEO4J_PASSWORD='<password>' \\"
echo "       -l results.jtl -e -o report/"
