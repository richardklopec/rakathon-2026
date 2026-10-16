"""SQL access to InterSystems IRIS (namespace FHIRSERVER). FHIR REST goes through app/fhir/client.py."""

from contextlib import contextmanager

import iris

from app.config import get_settings


@contextmanager
def cursor():
    """Yield a cursor and always close cursor + connection (Community Edition has few connection slots)."""
    s = get_settings()
    conn = iris.connect(s.iris_host, s.iris_port, s.iris_namespace, s.iris_user, s.iris_password)
    cur = conn.cursor()
    try:
        yield cur
    finally:
        cur.close()
        conn.close()


def to_vector(v: list[float]) -> str:
    """IRIS TO_VECTOR(?, DOUBLE) takes a comma-separated string."""
    return ",".join(f"{x:.6f}" for x in v)
