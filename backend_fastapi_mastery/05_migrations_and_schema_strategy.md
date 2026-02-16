# File: backend_fastapi_mastery/05_migrations_and_schema_strategy.md

# Migrations and Schema Strategy

## Why Migrations Matter

Your database schema will change. New features need new tables. Requirements change and columns get added. The question isn't if your schema will evolve, but how you'll manage that evolution safely.

**Without migrations:**
- "Just run this SQL on production" - pray it works
- No history of schema changes
- No way to roll back
- Different environments drift out of sync
- Deployments become terrifying

**With migrations:**
- Schema changes are version-controlled code
- Changes are repeatable and testable
- Roll back if something goes wrong
- All environments match
- Deploy with confidence

---

## Alembic Fundamentals

Alembic is SQLAlchemy's migration tool. It generates and runs migration scripts that evolve your database schema.

### Initial Setup

```bash
# Install
pip install alembic

# Initialize in your project
alembic init alembic
```

This creates:
```
alembic/
├── env.py              # Migration environment configuration
├── script.py.mako      # Template for new migrations
├── versions/           # Migration scripts live here
│   └── (empty)
└── alembic.ini         # Alembic configuration
```

### Configure for Async SQLAlchemy

```python
# alembic/env.py
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import your models' Base
from app.models.base import Base
from app.core.config import settings

config = context.config

# Set database URL from settings
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode - generates SQL without database."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### Creating Migrations

**Autogenerate from model changes:**
```bash
# Alembic compares models to database, generates migration
alembic revision --autogenerate -m "Add user table"
```

**Manual migration:**
```bash
alembic revision -m "Add custom index"
```

### Migration Script Anatomy

```python
# alembic/versions/001_add_user_table.py
"""Add user table

Revision ID: a1b2c3d4e5f6
Revises: 
Create Date: 2024-01-15 10:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# Revision identifiers
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = None  # Previous migration (None if first)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply migration."""
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)


def downgrade() -> None:
    """Revert migration."""
    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')
```

### Running Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Apply next migration only
alembic upgrade +1

# Upgrade to specific revision
alembic upgrade a1b2c3d4e5f6

# Rollback one migration
alembic downgrade -1

# Rollback to specific revision
alembic downgrade a1b2c3d4e5f6

# Rollback all
alembic downgrade base

# Show current revision
alembic current

# Show migration history
alembic history
```

---

## Common Migration Operations

### Adding Columns

```python
def upgrade() -> None:
    # Simple column
    op.add_column('users', sa.Column('phone', sa.String(20), nullable=True))
    
    # Column with default
    op.add_column('users', sa.Column(
        'is_verified', 
        sa.Boolean(), 
        nullable=False,
        server_default='false'  # SQL default for existing rows
    ))
    
    # After data is backfilled, optionally remove server_default
    # op.alter_column('users', 'is_verified', server_default=None)

def downgrade() -> None:
    op.drop_column('users', 'phone')
    op.drop_column('users', 'is_verified')
```

### Adding NOT NULL Column to Existing Table

This is tricky - you can't add a NOT NULL column without a default if rows exist.

```python
def upgrade() -> None:
    # Step 1: Add as nullable
    op.add_column('users', sa.Column('tenant_id', sa.Integer(), nullable=True))
    
    # Step 2: Backfill data (for existing rows)
    op.execute("UPDATE users SET tenant_id = 1 WHERE tenant_id IS NULL")
    
    # Step 3: Add NOT NULL constraint
    op.alter_column('users', 'tenant_id', nullable=False)
    
    # Step 4: Add foreign key (if needed)
    op.create_foreign_key(
        'fk_users_tenant_id',
        'users', 'tenants',
        ['tenant_id'], ['id']
    )

def downgrade() -> None:
    op.drop_constraint('fk_users_tenant_id', 'users', type_='foreignkey')
    op.drop_column('users', 'tenant_id')
```

### Renaming Columns

```python
def upgrade() -> None:
    op.alter_column('users', 'name', new_column_name='full_name')

def downgrade() -> None:
    op.alter_column('users', 'full_name', new_column_name='name')
```

### Changing Column Types

```python
def upgrade() -> None:
    # String to Text (usually safe)
    op.alter_column(
        'posts', 'content',
        type_=sa.Text(),
        existing_type=sa.String(1000)
    )
    
    # Be careful with type changes that might lose data!
    # Integer to String (safe)
    op.alter_column(
        'products', 'sku',
        type_=sa.String(50),
        existing_type=sa.Integer(),
        postgresql_using='sku::varchar'  # PostgreSQL needs cast
    )

def downgrade() -> None:
    op.alter_column(
        'posts', 'content',
        type_=sa.String(1000),
        existing_type=sa.Text()
    )
```

### Creating Indexes

```python
def upgrade() -> None:
    # Simple index
    op.create_index('ix_orders_user_id', 'orders', ['user_id'])
    
    # Unique index
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    
    # Composite index
    op.create_index(
        'ix_orders_user_status',
        'orders',
        ['user_id', 'status']
    )
    
    # Partial index (PostgreSQL)
    op.create_index(
        'ix_orders_pending',
        'orders',
        ['created_at'],
        postgresql_where=sa.text("status = 'pending'")
    )

def downgrade() -> None:
    op.drop_index('ix_orders_pending')
    op.drop_index('ix_orders_user_status')
    op.drop_index('ix_users_email')
    op.drop_index('ix_orders_user_id')
```

### Creating/Modifying Tables

```python
def upgrade() -> None:
    # Create table with all constraints
    op.create_table(
        'orders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('total', sa.Numeric(10, 2), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.CheckConstraint('total >= 0', name='check_total_positive')
    )
    
    # Add table comment
    op.execute("COMMENT ON TABLE orders IS 'Customer orders'")

def downgrade() -> None:
    op.drop_table('orders')
```

### Data Migrations

```python
def upgrade() -> None:
    # Get connection for raw SQL
    conn = op.get_bind()
    
    # Complex data transformation
    conn.execute(sa.text("""
        UPDATE users 
        SET full_name = first_name || ' ' || last_name
        WHERE full_name IS NULL
    """))
    
    # Or use SQLAlchemy models (be careful with model drift)
    # Better to use raw SQL for data migrations

def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE users 
        SET first_name = split_part(full_name, ' ', 1),
            last_name = split_part(full_name, ' ', 2)
    """))
```

---

## Schema Evolution Strategies

### The Expand-Contract Pattern

For breaking changes, use expand-contract:

1. **Expand**: Add new structure alongside old
2. **Migrate**: Move data/code to new structure
3. **Contract**: Remove old structure

**Example: Renaming a column safely**

```python
# Migration 1: Expand - add new column
def upgrade() -> None:
    op.add_column('users', sa.Column('full_name', sa.String(200), nullable=True))
    
    # Copy data
    op.execute("UPDATE users SET full_name = name")
    
    # Make NOT NULL after data copied
    op.alter_column('users', 'full_name', nullable=False)

# Deploy code that writes to BOTH columns
# Deploy code that reads from new column

# Migration 2: Contract - remove old column (after code fully deployed)
def upgrade() -> None:
    op.drop_column('users', 'name')
```

### Adding Enums

```python
def upgrade() -> None:
    # Create enum type (PostgreSQL)
    order_status = sa.Enum(
        'pending', 'processing', 'shipped', 'delivered', 'cancelled',
        name='order_status'
    )
    order_status.create(op.get_bind())
    
    # Add column using enum
    op.add_column('orders', sa.Column(
        'status',
        sa.Enum('pending', 'processing', 'shipped', 'delivered', 'cancelled', 
                name='order_status'),
        nullable=False,
        server_default='pending'
    ))

def downgrade() -> None:
    op.drop_column('orders', 'status')
    
    # Drop enum type
    sa.Enum(name='order_status').drop(op.get_bind())
```

### Modifying Enums

Adding values to PostgreSQL enums is tricky:

```python
def upgrade() -> None:
    # PostgreSQL: Add new value to existing enum
    op.execute("ALTER TYPE order_status ADD VALUE 'refunded'")

def downgrade() -> None:
    # PostgreSQL: Can't remove enum values!
    # You'd need to recreate the type
    pass
```

For complex enum changes, recreate the column:

```python
def upgrade() -> None:
    # 1. Create new enum
    op.execute("""
        CREATE TYPE order_status_v2 AS ENUM (
            'draft', 'pending', 'processing', 'shipped', 'delivered', 'cancelled', 'refunded'
        )
    """)
    
    # 2. Add temp column with new type
    op.add_column('orders', sa.Column('status_new', 
        sa.Enum(name='order_status_v2'), nullable=True))
    
    # 3. Migrate data
    op.execute("UPDATE orders SET status_new = status::text::order_status_v2")
    
    # 4. Drop old column and rename
    op.drop_column('orders', 'status')
    op.alter_column('orders', 'status_new', new_column_name='status')
    
    # 5. Drop old enum
    op.execute("DROP TYPE order_status")
```

---

## Zero-Downtime Migrations

### The Problem

During deployment, old code and new code run simultaneously:

```
Time →
────────────────────────────────────────────────────
Old Code Running  │  Both Running  │  New Code Running
                  │                │
                  │  ← Dangerous!  │
────────────────────────────────────────────────────
                  ↑                ↑
           Deploy Start      Deploy Complete
```

Your migration must work with BOTH old and new code.

### Rules for Zero-Downtime

1. **Never remove a column that old code uses**
2. **Never rename a column that old code uses**
3. **Never add a NOT NULL column without default**
4. **Never change column type incompatibly**
5. **Migrations must be backward compatible**

### Safe Migration Sequence

**Adding a required column:**

```
Deploy 1: Add column as nullable
  ↓
Deploy 2: Code writes to new column
  ↓
Deploy 3: Backfill existing rows
  ↓
Deploy 4: Code requires new column
  ↓
Deploy 5: Add NOT NULL constraint
```

**Removing a column:**

```
Deploy 1: Code stops using column
  ↓
Deploy 2: Remove column from ORM model
  ↓
Deploy 3: Migration drops column
```

**Renaming a column:**

```
Deploy 1: Add new column
  ↓
Deploy 2: Code writes to both columns
  ↓
Deploy 3: Backfill new column from old
  ↓
Deploy 4: Code reads from new column only
  ↓
Deploy 5: Code writes to new column only
  ↓
Deploy 6: Drop old column
```

### Example: Safe Column Addition

```python
# models/user.py - Step 1
class User(Base):
    # ... existing columns ...
    tenant_id: Mapped[Optional[int]] = mapped_column(nullable=True)  # Optional first

# Migration 1: Add nullable column
def upgrade() -> None:
    op.add_column('users', sa.Column('tenant_id', sa.Integer(), nullable=True))

# Deploy, let all pods pick up new code

# models/user.py - Step 2
class User(Base):
    # Code now expects tenant_id (but handles None)
    tenant_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    
    @property
    def effective_tenant_id(self) -> int:
        return self.tenant_id or DEFAULT_TENANT_ID

# Migration 2: Backfill data
def upgrade() -> None:
    op.execute(f"UPDATE users SET tenant_id = {DEFAULT_TENANT_ID} WHERE tenant_id IS NULL")

# Migration 3: Add NOT NULL (after backfill deployed)
def upgrade() -> None:
    op.alter_column('users', 'tenant_id', nullable=False)

# models/user.py - Final
class User(Base):
    tenant_id: Mapped[int] = mapped_column(nullable=False)  # Now required
```

---

## Production Database Safety

### Locking Concerns

Some operations lock tables, blocking queries:

**High-risk operations:**
- `ALTER TABLE ... ADD COLUMN ... DEFAULT` (pre-PostgreSQL 11)
- Adding indexes on large tables
- Adding foreign key constraints

**Safe in PostgreSQL 11+:**
```python
# Adding column with default is fast now (metadata-only change)
op.add_column('users', sa.Column('score', sa.Integer(), server_default='0'))
```

**Creating indexes concurrently:**
```python
def upgrade() -> None:
    # CONCURRENTLY doesn't lock the table
    op.execute("""
        CREATE INDEX CONCURRENTLY ix_orders_created 
        ON orders (created_at)
    """)
    # Note: Can't be in a transaction, use:
    # op.execute(..., execution_options={"isolation_level": "AUTOCOMMIT"})

def downgrade() -> None:
    op.execute("DROP INDEX CONCURRENTLY ix_orders_created")
```

### Testing Migrations

```python
# tests/test_migrations.py
import pytest
from alembic import command
from alembic.config import Config

@pytest.fixture
def alembic_config():
    return Config("alembic.ini")

def test_migrations_up_down(alembic_config, test_database):
    """Test that all migrations can be applied and rolled back."""
    # Upgrade to head
    command.upgrade(alembic_config, "head")
    
    # Downgrade to base
    command.downgrade(alembic_config, "base")
    
    # Upgrade again
    command.upgrade(alembic_config, "head")

def test_no_pending_migrations(alembic_config):
    """Test that model changes are captured in migrations."""
    # This would fail if models differ from migration history
    # Implement by comparing model metadata to database schema
```

### Pre-Deploy Checklist

Before running migrations in production:

1. **Backup the database**
2. **Test migration on staging with production-like data**
3. **Check for locking (large tables)**
4. **Verify rollback works**
5. **Plan for failure (what if migration fails midway?)**
6. **Schedule during low-traffic period**
7. **Monitor database metrics during migration**

### Migration in CI/CD

```yaml
# .github/workflows/deploy.yml
- name: Run migrations
  run: |
    # Set timeout for long migrations
    timeout 300 alembic upgrade head
  env:
    DATABASE_URL: ${{ secrets.DATABASE_URL }}

- name: Verify migration
  run: |
    # Check current revision matches expected
    alembic current | grep -q $(cat EXPECTED_REVISION)
```

---

## Multi-Environment Strategy

### Environment-Specific Settings

```python
# alembic/env.py
import os

def get_database_url():
    env = os.getenv("ENVIRONMENT", "development")
    
    if env == "production":
        return os.getenv("DATABASE_URL")
    elif env == "staging":
        return os.getenv("STAGING_DATABASE_URL")
    else:
        return "postgresql://localhost/myapp_dev"

config.set_main_option("sqlalchemy.url", get_database_url())
```

### Migration Ordering Across Teams

When multiple developers create migrations:

```bash
# Developer A creates migration
alembic revision --autogenerate -m "Add orders table"
# Creates: a1b2c3_add_orders_table.py, down_revision: xyz123

# Developer B creates migration (same base)
alembic revision --autogenerate -m "Add products table"
# Creates: d4e5f6_add_products_table.py, down_revision: xyz123

# Problem: Two migrations with same down_revision!
```

**Solution: Merge branches**
```bash
alembic merge heads -m "Merge orders and products"
# Creates merge migration that depends on both
```

### Generating Migration from Scratch

For new deployments without migration history:

```python
# Check if this is a fresh database
def run_migrations_online():
    connectable = create_engine(...)
    
    with connectable.connect() as connection:
        # Check if alembic_version table exists
        inspector = inspect(connection)
        if 'alembic_version' not in inspector.get_table_names():
            # Fresh database: create all tables directly
            Base.metadata.create_all(connection)
            # Stamp with current revision (don't run migrations)
            command.stamp(alembic_config, "head")
        else:
            # Existing database: run migrations
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
```

---

## Common Pitfalls

### 1. Not Testing Downgrade

```python
# WRONG: downgrade that doesn't actually revert
def upgrade() -> None:
    op.add_column('users', sa.Column('phone', sa.String(20)))
    op.add_column('users', sa.Column('address', sa.String(200)))

def downgrade() -> None:
    op.drop_column('users', 'phone')
    # Forgot address!
```

### 2. Data Loss in Downgrade

```python
# DANGEROUS: Downgrade loses data
def upgrade() -> None:
    op.add_column('users', sa.Column('preferences', sa.JSON()))

def downgrade() -> None:
    op.drop_column('users', 'preferences')  # Data gone forever
```

Consider if downgrade should preserve data or if that's acceptable.

### 3. Not Handling NULL in Data Migrations

```python
# WRONG: Assumes no NULL values
def upgrade() -> None:
    op.execute("UPDATE users SET name = UPPER(name)")  # NULL stays NULL, but...

# WRONG: Division by zero
def upgrade() -> None:
    op.execute("UPDATE products SET margin = profit / cost")  # cost might be 0!

# RIGHT: Handle edge cases
def upgrade() -> None:
    op.execute("""
        UPDATE products 
        SET margin = CASE 
            WHEN cost > 0 THEN profit / cost 
            ELSE 0 
        END
    """)
```

### 4. Implicit Dependencies

```python
# WRONG: Assumes another migration ran
def upgrade() -> None:
    # Assumes 'users' table exists from different migration
    op.add_column('users', sa.Column('score', sa.Integer()))

# If migrations run out of order or are skipped, this fails

# RIGHT: Explicit dependency
depends_on = 'a1b2c3_create_users'  # Requires users table migration
```

### 5. Using ORM Models in Migrations

```python
# DANGEROUS: Model might not match database state
from app.models import User

def upgrade() -> None:
    session = Session(bind=op.get_bind())
    for user in session.query(User).all():
        # User model might have columns that don't exist yet!
        user.score = calculate_score(user)
    session.commit()

# RIGHT: Use raw SQL
def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE users 
        SET score = (SELECT COUNT(*) FROM orders WHERE orders.user_id = users.id)
    """))
```

---

## Mastery Checkpoints

### Conceptual Questions

1. **Why can't you simply rename a column in production?**

   *Answer*: During deployment, old code (expecting old column name) and new code (expecting new column name) run simultaneously. Old code will fail when the column is renamed. Use expand-contract: add new column, copy data, deploy code that uses new column, then drop old column.

2. **What's the difference between `alembic upgrade head` and `alembic upgrade +1`?**

   *Answer*: `head` applies ALL pending migrations to reach the latest version. `+1` applies only the next single migration. Use `+1` for careful, step-by-step deployments where you want to verify each migration before proceeding.

3. **Why use `server_default` instead of `default` when adding columns?**

   *Answer*: `server_default` is a SQL DEFAULT that the database applies to existing rows. `default` is a Python/ORM default used when creating new objects. When adding a NOT NULL column to a table with data, you need `server_default` so existing rows get a value.

4. **How do you add an index without locking a production table?**

   *Answer*: Use `CREATE INDEX CONCURRENTLY` (PostgreSQL). This builds the index without holding a lock that blocks writes. It takes longer but allows concurrent operations. Note: Can't run in a transaction, so use `execution_options={"isolation_level": "AUTOCOMMIT"}`.

5. **What happens if a migration fails halfway through?**

   *Answer*: Depends on the database. PostgreSQL: DDL is transactional, so partial changes roll back. MySQL: DDL is auto-committed, so you have partial state. Always design migrations to be idempotent or have clear recovery paths. Test migrations thoroughly before production.

### Scenario Questions

6. **You need to split a `name` column into `first_name` and `last_name`. Design the migrations.**

   *Answer*:
   ```python
   # Migration 1: Add new columns
   def upgrade():
       op.add_column('users', sa.Column('first_name', sa.String(100), nullable=True))
       op.add_column('users', sa.Column('last_name', sa.String(100), nullable=True))
   
   # Deploy code that writes to both name and first_name/last_name
   
   # Migration 2: Backfill data
   def upgrade():
       op.execute("""
           UPDATE users SET 
               first_name = split_part(name, ' ', 1),
               last_name = CASE 
                   WHEN position(' ' in name) > 0 
                   THEN substring(name from position(' ' in name) + 1)
                   ELSE ''
               END
           WHERE first_name IS NULL
       """)
   
   # Deploy code that reads from first_name/last_name
   # Deploy code that stops writing to name
   
   # Migration 3: Add NOT NULL, drop old column
   def upgrade():
       op.alter_column('users', 'first_name', nullable=False)
       op.alter_column('users', 'last_name', nullable=False)
       op.drop_column('users', 'name')
   ```

7. **You need to add a foreign key to a table with millions of rows. How do you do it safely?**

   *Answer*:
   ```python
   def upgrade():
       # 1. Add column (fast, nullable)
       op.add_column('orders', sa.Column('customer_id', sa.Integer(), nullable=True))
       
       # 2. Create index concurrently (background)
       op.execute("""
           CREATE INDEX CONCURRENTLY ix_orders_customer_id 
           ON orders (customer_id)
       """)
       
       # 3. Backfill in batches (separate job/migration)
       # Don't do this in one transaction for millions of rows
       
       # 4. Add FK constraint with NOT VALID (doesn't check existing rows)
       op.execute("""
           ALTER TABLE orders 
           ADD CONSTRAINT fk_orders_customer 
           FOREIGN KEY (customer_id) REFERENCES customers(id)
           NOT VALID
       """)
       
       # 5. Validate constraint in background
       op.execute("""
           ALTER TABLE orders 
           VALIDATE CONSTRAINT fk_orders_customer
       """)
       
       # 6. Add NOT NULL after validation
       op.alter_column('orders', 'customer_id', nullable=False)
   ```

8. **Your migration creates an index, but it takes 30 minutes on production data. How do you handle deployment?**

   *Answer*: 
   - Use `CREATE INDEX CONCURRENTLY` so reads/writes aren't blocked
   - Don't include in normal deploy pipeline (would timeout)
   - Run as separate maintenance task during low-traffic period
   - Or: Add index in earlier deploy cycle, before the code that needs it
   - Consider: Is the index necessary for initial deploy? Can code work (slowly) without it?

9. **Team member merged their branch with a migration that conflicts with yours. What do you do?**

   *Answer*:
   ```bash
   # Check for multiple heads
   alembic heads
   # Shows two revisions with same parent
   
   # Create merge migration
   alembic merge heads -m "Merge feature_a and feature_b migrations"
   
   # This creates a migration that depends on both
   # Now there's a single head again
   
   # Verify
   alembic heads  # Should show single head
   alembic upgrade head  # Apply all
   ```

10. **You need to change a column from VARCHAR(100) to TEXT, but there's no downtime window. How?**

    *Answer*: In PostgreSQL, this is actually safe:
    ```python
    def upgrade():
        # VARCHAR to TEXT is metadata-only change in PostgreSQL
        # No table rewrite, no locks (for relaxing constraints)
        op.alter_column('posts', 'content',
            type_=sa.Text(),
            existing_type=sa.String(100)
        )
    ```
    
    Going the other direction (TEXT to VARCHAR) or changing between incompatible types requires more care: add new column, copy data, swap.

---

## Interview Framing

When discussing migrations in interviews:

1. **Emphasize safety**: "I design migrations for zero-downtime deployment. Every change must work with both old and new code running simultaneously. I use the expand-contract pattern for breaking changes."

2. **Show production awareness**: "Before running migrations, I test on staging with production-like data volume. Large table operations need special handling - concurrent index creation, batched updates, off-peak scheduling."

3. **Discuss rollback strategy**: "I always write and test downgrade functions. But I also recognize that sometimes you can't roll back (data migrations). In those cases, I have a forward-fix strategy ready."

4. **Connect to deployment pipeline**: "Migrations are part of CI/CD. They run automatically on deploy, with timeouts and health checks. If a migration fails, deployment stops before new code reaches traffic."

5. **Mention real scenarios**: "I've dealt with adding columns to billion-row tables. The key is breaking it into multiple deployments: add nullable column, backfill in batches over days, then add constraint. No single operation that locks the table."
