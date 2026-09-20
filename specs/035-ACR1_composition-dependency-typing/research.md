# Research

`main.py` owns network-client creation and close order but routes read untyped `app.state` values. A small dataclass container makes ownership and optionality explicit without hiding lifespan behavior or adding framework machinery.
