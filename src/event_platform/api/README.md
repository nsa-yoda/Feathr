# Intended Module Boundary

HTTP route/middleware/dependency boundary. Routes validate/translate and call application services; they do not manipulate Mongo/Redis/ES clients directly.
