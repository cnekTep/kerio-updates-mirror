from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncEngine,
    async_sessionmaker,
    AsyncSession,
)

from app.config import settings


class DatabaseHelper:
    def __init__(
        self,
        url: str,
        echo: bool,
        echo_pool: bool,
        pool_size: int,
        max_overflow: int,
    ) -> None:
        self.engine: AsyncEngine = create_async_engine(
            url=url,
            echo=echo,
            echo_pool=echo_pool,
            pool_size=pool_size,
            max_overflow=max_overflow,
        )
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get database session with automatic commit/rollback.

        Usage:
            async with get_session() as session:
                result = await session.execute(...)
        """
        async with self.session_factory() as session:
            try:
                yield session
            except:
                await session.rollback()
                raise

    async def close(self):
        """Close all database connections."""
        await self.engine.dispose()


db_helper = DatabaseHelper(
    url=settings.db.url,
    echo=settings.db.echo,
    echo_pool=settings.db.echo_pool,
    pool_size=settings.db.pool_size,
    max_overflow=settings.db.max_overflow,
)
