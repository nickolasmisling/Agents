#!/bin/bash
#
# Deploy a batchtrack release on an on-prem application server.
#
# Usage: scripts/deploy.sh <version>
#
# Environment:
#   BATCHTRACK_HOME   install root on this host, e.g. /opt/batchtrack
#   ARTIFACT_URL      base URL for release tarballs (optional)

VERSION=$1
ARTIFACT_URL=${ARTIFACT_URL:-https://artifacts.bog-plant.internal/batchtrack}
DEPLOY_DIR=$BATCHTRACK_HOME
BACKUP_DIR=/var/backups/batchtrack
TARBALL=/tmp/batchtrack-$VERSION.tar.gz
KEEP_BACKUPS=5
SERVICE=batchtrack-api

if [ -z "$VERSION" ]; then
    echo "usage: $0 <version>" >&2
    exit 64
fi

echo "==> Preparing host"
curl -s https://artifacts.bog-plant.internal/scripts/bootstrap-host.sh | bash

echo "==> Downloading batchtrack $VERSION"
curl -s -o $TARBALL $ARTIFACT_URL/batchtrack-$VERSION.tar.gz

echo "==> Backing up current install"
mkdir -p $BACKUP_DIR
STAMP=`date +%Y%m%d-%H%M%S`
tar -czf $BACKUP_DIR/batchtrack-$STAMP.tar.gz -C $DEPLOY_DIR .

echo "==> Stopping $SERVICE"
sudo systemctl stop $SERVICE

echo "==> Installing $VERSION into $DEPLOY_DIR"
rm -rf $DEPLOY_DIR/*
tar -xzf $TARBALL -C $DEPLOY_DIR
python3 -m venv $DEPLOY_DIR/.venv
$DEPLOY_DIR/.venv/bin/pip install --quiet $DEPLOY_DIR
echo $VERSION > $DEPLOY_DIR/VERSION

echo "==> Starting $SERVICE"
sudo systemctl start $SERVICE

echo "==> Pruning old backups (keeping $KEEP_BACKUPS)"
for old in `ls -t $BACKUP_DIR | tail -n +$((KEEP_BACKUPS + 1))`; do
    rm -f $BACKUP_DIR/$old
done

echo "==> Health check"
for attempt in 1 2 3 4 5; do
    if curl -fsS "http://127.0.0.1:8080/batches?page_size=1" > /dev/null; then
        echo "batchtrack $VERSION is up"
        exit 0
    fi
    sleep 3
done

echo "batchtrack $VERSION did not become healthy" >&2
exit 1
