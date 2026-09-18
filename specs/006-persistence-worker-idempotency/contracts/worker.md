# Persistence Worker Contract

`PersistenceWorker.process_once()` returns whether a delivery was processed. Insert success and verified same-hash duplicates delete the current receipt. Conflicts call the optional disposition hook and do not overwrite canonical Mongo state.
