"""REST surface (FastAPI). Owned by T06 — see ``tasks/T06.md``.

Routes are country-scoped:
    GET /v1/countries
    GET /v1/{country}/company/{id}
    GET /v1/{country}/search?name=&limit=
    GET /v1/{country}/company/{id}/deadlines?today=
    GET /v1/{country}/validate/{id}

Every response body is a model from ``core.models``; every error body is
``RegistryError.to_dict()`` (``DECISIONS.md`` D-004, D-007).
"""
