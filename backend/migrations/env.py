"""Alembic environment for SQL Server-only OpenLibraryOS migrations."""

from logging.config import fileConfig

from alembic import context
from alembic.ddl.impl import DefaultImpl
from sqlalchemy import (
    Column,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    engine_from_config,
    pool,
    text,
)


def _custom_version_table_impl(
    self,
    *,
    version_table: str,
    version_table_schema: str | None,
    version_table_pk: bool,
    **kw,
) -> Table:
    vt = Table(
        version_table,
        MetaData(),
        Column("version_num", String(128), nullable=False),
        schema=version_table_schema,
    )
    if version_table_pk:
        vt.append_constraint(
            PrimaryKeyConstraint("version_num", name=f"{version_table}_pkc")
        )
    return vt


DefaultImpl.version_table_impl = _custom_version_table_impl

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def run_migrations_offline() -> None:
    """Render SQL without opening a database connection."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_num_length=128,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply revisions through the migration-only connection URL."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        connection.execute(
            text(
                """
                IF OBJECT_ID('dbo.alembic_version', 'U') IS NULL
                BEGIN
                    CREATE TABLE dbo.alembic_version (
                        version_num VARCHAR(128) NOT NULL CONSTRAINT alembic_version_pkc PRIMARY KEY CLUSTERED (version_num)
                    );
                END
                ELSE IF COL_LENGTH('dbo.alembic_version', 'version_num') < 128
                BEGIN
                    DECLARE @pkName sysname;
                    SELECT @pkName = name FROM sys.key_constraints WHERE parent_object_id = OBJECT_ID('dbo.alembic_version') AND type = 'PK';
                    IF @pkName IS NOT NULL
                    BEGIN
                        EXEC('ALTER TABLE dbo.alembic_version DROP CONSTRAINT [' + @pkName + ']');
                        ALTER TABLE dbo.alembic_version ALTER COLUMN version_num VARCHAR(128) NOT NULL;
                        EXEC('ALTER TABLE dbo.alembic_version ADD CONSTRAINT [' + @pkName + '] PRIMARY KEY CLUSTERED (version_num)');
                    END
                END
                """
            )
        )
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_num_length=128,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
