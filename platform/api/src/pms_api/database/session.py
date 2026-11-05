from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pms_api.core.config import Settings

REVISION = "0048_refined_starters"


def engine_for(settings: Settings, purpose: str = "api"):
    configured = getattr(settings, f"{purpose}_database_url", None) if purpose != "api" else None
    url = make_url((configured or settings.database_url).get_secret_value())
    options = url.query.get("options", "")
    if not isinstance(options, str):
        raise ValueError("Configure a single PostgreSQL options value")
    options = (options + " -c timezone=UTC -c statement_timeout=15000 -c lock_timeout=5000").strip()
    return create_async_engine(
        url,
        isolation_level="READ COMMITTED",
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        connect_args={"options": options},
    )


def sessions_for(engine):
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def session_dependency(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as session:
        # Services explicitly commit before responding; this is rollback/close only.
        try:
            yield session
        finally:
            if session.in_transaction():
                await session.rollback()


async def check_schema(session: AsyncSession) -> bool:
    values = await session.scalars(text("SELECT version_num FROM public.alembic_version"))
    return values.all() == [REVISION]


async def lock_administration(session: AsyncSession) -> None:
    await session.execute(text("SELECT id FROM device_platform.platform_settings WHERE id=1 FOR UPDATE"))
