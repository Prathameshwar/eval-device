from alembic import context
from sqlalchemy import create_engine

from pms_api.core.config import get_settings

settings = get_settings()
url = (settings.migration_database_url or settings.database_url).get_secret_value()
if context.is_offline_mode():
    raise RuntimeError("Use online PostgreSQL migrations so complete SQL function bodies are preserved")
engine = create_engine(url, isolation_level="READ COMMITTED")
with engine.connect() as connection:
    context.configure(connection=connection, transaction_per_migration=True, version_table_schema="public")
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
