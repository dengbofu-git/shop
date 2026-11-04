"""Fail-closed PostgreSQL database and cluster admission for operator tools."""


def database_identity(connection):
    """Read the current database and cluster identifier from PostgreSQL itself."""
    if getattr(connection, 'vendor', None) != 'postgresql':
        raise RuntimeError('Database identity requires PostgreSQL')
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database(), system_identifier::text FROM pg_control_system()')
        identity = cursor.fetchone()
    if (not isinstance(identity, (tuple, list)) or len(identity) != 2
            or any(not isinstance(value, str) or not value for value in identity)):
        raise RuntimeError('PostgreSQL returned an incomplete database identity')
    return tuple(identity)


def require_database_identity(connection, expected_database, expected_system_identifier):
    """Reject missing expectations, another backend, or either target mismatch."""
    if any(not isinstance(value, str) or not value
           for value in (expected_database, expected_system_identifier)):
        raise RuntimeError('Expected PostgreSQL database and system identifier are required')
    identity = database_identity(connection)
    if identity != (expected_database, expected_system_identifier):
        raise RuntimeError('PostgreSQL database identity does not match the expected target')
    return identity
