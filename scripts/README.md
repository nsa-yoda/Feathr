# Scripts

`bootstrap-speckit.sh` is part of this handoff. `smoke` starts the Compose
stack, waits for bounded health, and verifies ingestion, canonical query,
search, and realtime statistics. Scripts use strict shell settings and clear
exit codes. Feature 022 owns any Postman runner helper.
