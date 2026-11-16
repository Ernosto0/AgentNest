"""Runtime database roles for tests that switch role (``SET LOCAL ROLE``)."""

from sqlalchemy.orm import Session

from app.operations.backup_restore import provision_database_roles


def ensure_runtime_roles(session: Session) -> None:
    """Create the runtime roles and their grants inside the test's transaction.

    Roles are cluster-wide, so a developer database that has ever provisioned them hides the
    problem; on a fresh cluster (CI) they do not exist until something provisions them. The
    statements are transactional: they roll back with the test.
    """
    provision_database_roles(session)
