"""Alembic migration: Audit log append-only + hash chain (CRITICAL-4)."""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '002_audit_chain'
down_revision = '001_sesis_initial'
branch_labels = None
depends_on = None


def upgrade():
    # Añadir columnas de hash chain.
    op.add_column(
        'audit_log',
        sa.Column('prev_hash', sa.String(length=64), nullable=False, server_default=sa.text("repeat('0', 64)"))
    )
    op.add_column(
        'audit_log',
        sa.Column('row_hash', sa.String(length=64), nullable=False, server_default='')
    )

    # Trigger BEFORE UPDATE/DELETE: rechaza cualquier modificación (append-only).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_immutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log es append-only';
        END
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_no_update
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_immutable();
        """
    )

    # Revocar UPDATE/DELETE públicos sobre audit_log.
    op.execute("REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;")


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS audit_no_update ON audit_log;")
    op.execute("DROP FUNCTION IF EXISTS audit_immutable();")
    op.drop_column('audit_log', 'row_hash')
    op.drop_column('audit_log', 'prev_hash')
