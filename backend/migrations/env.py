from alembic import context

from app.config import load_settings
from app.database import make_engine
from app.models import Base

settings = load_settings()
if settings.database_url is None:
    raise RuntimeError("Explicit synthetic database configuration is required")
engine = make_engine(settings.database_url.get_secret_value())
try:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
finally:
    engine.dispose()
