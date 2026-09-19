# Feature 022 Quickstart

1. Start the Feature 021 Compose stack or another API instance.
2. Import `postman/Distributed Event Processing Platform.postman_collection.json`.
3. Import and select `postman/Local Docker.postman_environment.json`.
4. Run the collection in folder order, or use:

```bash
make postman
```

The CLI target requires Newman on `PATH`. It fails clearly when Newman or the API is unavailable. The collection leaves captured IDs and cursors in the selected environment for inspection.
