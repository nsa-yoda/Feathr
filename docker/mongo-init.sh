#!/usr/bin/env bash
set -euo pipefail

deadline_seconds=${MONGO_INIT_DEADLINE_SECONDS:-90}
[[ "$deadline_seconds" =~ ^[1-9][0-9]*$ ]] || {
  echo 'MONGO_INIT_DEADLINE_SECONDS must be a positive integer' >&2
  exit 2
}
deadline=$((SECONDS + deadline_seconds))
init_uri=${MONGO_INIT_URI:?MONGO_INIT_URI is required}
replica_uri=${MONGO_REPLICA_URI:?MONGO_REPLICA_URI is required}

mongo_shell() {
  local uri=$1
  shift
  local separator='?'
  [[ "$uri" == *\?* ]] && separator='&'
  # These are supported MongoDB URI options; mongosh itself does not expose
  # them as standalone CLI flags. They bound each network operation.
  mongosh --quiet "${uri}${separator}serverSelectionTimeoutMS=1000&connectTimeoutMS=1000&socketTimeoutMS=1000" "$@"
}

while (( SECONDS < deadline )); do
  if mongo_shell "$init_uri" --eval 'db.adminCommand({ping: 1}).ok' 2>/dev/null | grep -q 1; then
    break
  fi
  sleep 1
done
(( SECONDS < deadline )) || { echo 'mongo ping deadline exceeded' >&2; exit 1; }

if ! mongo_shell "$replica_uri" --eval 'rs.status().ok' 2>/dev/null | grep -q 1; then
  mongo_shell "$init_uri" --eval 'try { rs.initiate({_id: "rs0", members: [{_id: 0, host: "mongo:27017"}]}) } catch (error) { if (!String(error).includes("already initialized")) throw error }' >/dev/null
fi

while (( SECONDS < deadline )); do
  state=$(mongo_shell "$replica_uri" --eval 'rs.status().myState' 2>/dev/null || true)
  if [[ "$state" == "1" ]]; then
    echo 'mongo replica set ready'
    exit 0
  fi
  sleep 1
done

echo 'mongo replica set readiness deadline exceeded' >&2
exit 1
