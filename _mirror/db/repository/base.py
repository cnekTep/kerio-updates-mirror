from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """Base repository class for database operations."""

    def __init__(self, session: AsyncSession):
        """Initialize the repository with a database session."""
        self.session = session
