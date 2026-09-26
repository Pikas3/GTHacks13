"""Repositories: the only layer that talks SQL. They return Pydantic schemas, never ORM rows,
so services above can be tested with in-memory fakes that implement `interfaces.py`."""
