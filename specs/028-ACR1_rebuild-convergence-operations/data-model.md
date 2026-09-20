# Data Model

`RebuildRecord` now carries bounded source high-water and projector checkpoint markers plus a non-negative fencing token. `MongoRebuildStore.get` retrieves one historical record by UUID while `latest` remains the default status path.
