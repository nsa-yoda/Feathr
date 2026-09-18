# Storage Contract

`MongoEventStore` owns the events collection and exposes typed insert, fetch, filtered query, aggregate, and index-bootstrap operations. Routes and application services receive this interface rather than a PyMongo collection.

`EventAlreadyExists` represents duplicate event IDs. `MongoDependencyError` represents driver/server failures and includes only a safe operation label. No raw PyMongo exception, connection string, or collection handle is returned.
