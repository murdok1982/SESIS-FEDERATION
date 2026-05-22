"""Alembic migration: Estructura inicial SESIS v3.0."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from geoalchemy2.types import Geography


# revision identifiers
revision = '001_sesis_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ─── Tablas base (legacy) ───────────────────────────────

    op.create_table('assets',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('current_status', sa.String()),
        sa.Column('last_heartbeat', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('location', Geography(geometry_type='POINT', srid=4326)),
        sa.Column('classification_level', sa.String(), nullable=False),
        sa.Column('metadata', sa.JSON(), server_default='{}')
    )

    op.create_table('events',
        sa.Column('event_id', sa.String(), primary_key=True),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('asset_id', sa.String(), sa.ForeignKey('assets.id'), nullable=False),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('geo_point', Geography(geometry_type='POINT', srid=4326), nullable=False),
        sa.Column('classification_level', sa.String(), nullable=False),
        sa.Column('confidence_score', sa.Float(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('signature', sa.JSON(), nullable=False)
    )

    op.create_table('telemetry',
        sa.Column('ts', sa.DateTime(timezone=True), primary_key=True),
        sa.Column('asset_id', sa.String(), primary_key=True),
        sa.Column('parameter', sa.String(), primary_key=True),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('unit', sa.String()),
        sa.Column('metadata', sa.JSON(), server_default='{}')
    )

    op.create_table('alerts',
        sa.Column('id', sa.String(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column('event_id', sa.String(), sa.ForeignKey('events.event_id')),
        sa.Column('rule_id', sa.String(), nullable=False),
        sa.Column('severity', sa.String(), nullable=False),
        sa.Column('description', sa.String()),
        sa.Column('is_anomaly', sa.Boolean(), server_default='false'),
        sa.Column('human_validated', sa.Boolean(), server_default='false'),
        sa.Column('validated_by', sa.String()),
        sa.Column('metadata', sa.JSON(), server_default='{}'),
        sa.Column('sensitive', sa.Text())
    )

    op.create_table('audit_log',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('ts', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('actor', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('resource_type', sa.String(), nullable=False),
        sa.Column('resource_id', sa.String(), nullable=False),
        sa.Column('context', sa.JSON(), server_default='{}')
    )

    op.create_table('intelligence_products',
        sa.Column('id', sa.String(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column('product_type', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('classification_level', sa.String(), nullable=False, server_default='CONFIDENTIAL'),
        sa.Column('source_data', sa.JSON(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('created_by', sa.String(), nullable=False, server_default='SYSTEM')
    )

    op.create_table('priority_intelligence_requirements',
        sa.Column('id', sa.String(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('collection_methods', sa.JSON(), server_default='[]'),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('classification_level', sa.String(), nullable=False, server_default='CONFIDENTIAL'),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    )

    op.create_table('sensor_sources',
        sa.Column('id', sa.String(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column('sensor_id', sa.String(), nullable=False, unique=True),
        sa.Column('sensor_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='ACTIVE'),
        sa.Column('classification_level', sa.String(), nullable=False, server_default='CONFIDENTIAL'),
        sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('metadata', sa.JSON(), server_default='{}')
    )

    op.create_table('intel_fusion_records',
        sa.Column('id', sa.String(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column('entity_id', sa.String(), nullable=True),
        sa.Column('fusion_score', sa.Float(), nullable=False),
        sa.Column('source_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('correlated_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('assessment', sa.JSON(), server_default='{}'),
        sa.Column('classification_level', sa.String(), nullable=False, server_default='CONFIDENTIAL'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    )

    # ─── NUEVAS TABLAS v3.0 ──────────────────────────────

    op.create_table('orbat_units',
        sa.Column('id', sa.String(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column('parent_id', sa.String(), sa.ForeignKey('orbat_units.id'), nullable=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('unit_type', sa.String(), nullable=False),
        sa.Column('classification_level', sa.String(), nullable=False, server_default='CONFIDENTIAL'),
        sa.Column('location', Geography(geometry_type='POINT', srid=4326), nullable=True),
        sa.Column('commander_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(), server_default='ACTIVE'),
        sa.Column('metadata', sa.JSON(), server_default='{}')
    )

    op.create_table('missions',
        sa.Column('id', sa.String(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('mission_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), server_default='PLANNED'),
        sa.Column('classification_level', sa.String(), nullable=False, server_default='SECRET'),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('commander_id', sa.String(), nullable=True),
        sa.Column('orbat_unit_id', sa.String(), sa.ForeignKey('orbat_units.id'), nullable=True),
        sa.Column('sensitive', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('created_by', sa.String(), nullable=False)
    )

    op.create_table('blue_force_tracking',
        sa.Column('id', sa.String(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column('unit_id', sa.String(), sa.ForeignKey('orbat_units.id'), nullable=False),
        sa.Column('asset_id', sa.String(), sa.ForeignKey('assets.id'), nullable=True),
        sa.Column('position', Geography(geometry_type='POINT', srid=4326), nullable=False),
        sa.Column('altitude', sa.Float(), nullable=True),
        sa.Column('heading', sa.Float(), nullable=True),
        sa.Column('speed', sa.Float(), nullable=True),
        sa.Column('status', sa.String(), server_default='ACTIVE'),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    )

    op.create_table('ew_events',
        sa.Column('id', sa.String(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('frequency_mhz', sa.Float(), nullable=True),
        sa.Column('bandwidth_mhz', sa.Float(), nullable=True),
        sa.Column('signal_strength', sa.Float(), nullable=True),
        sa.Column('position', Geography(geometry_type='POINT', srid=4326), nullable=True),
        sa.Column('classification_level', sa.String(), nullable=False, server_default='SECRET'),
        sa.Column('analysis', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    )

    op.create_table('cyber_incidents',
        sa.Column('id', sa.String(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column('incident_type', sa.String(), nullable=False),
        sa.Column('severity', sa.String(), nullable=False),
        sa.Column('source_ip', sa.String(), nullable=True),
        sa.Column('target_system', sa.String(), nullable=False),
        sa.Column('kill_chain_stage', sa.String(), nullable=True),
        sa.Column('classification_level', sa.String(), nullable=False, server_default='SECRET'),
        sa.Column('forensics', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), server_default='OPEN'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('created_by', sa.String(), nullable=False)
    )

    op.create_table('logistics_supplies',
        sa.Column('id', sa.String(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column('item_type', sa.String(), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('unit', sa.String(), nullable=False),
        sa.Column('location_id', sa.String(), sa.ForeignKey('orbat_units.id'), nullable=True),
        sa.Column('min_threshold', sa.Float(), nullable=True),
        sa.Column('classification_level', sa.String(), nullable=False, server_default='CONFIDENTIAL'),
        sa.Column('last_updated', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    )

    op.create_table('event_store',
        sa.Column('event_id', sa.String(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column('aggregate_id', sa.String(), nullable=False, index=True),
        sa.Column('aggregate_type', sa.String(), nullable=False, index=True),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('metadata', sa.JSON(), server_default='{}'),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('actor', sa.String(), nullable=True)
    )

    # ─── Índices espaciales ─────────────────────────────────
    op.create_index('idx_assets_location', 'assets', ['location'], postgresql_using='gist')
    op.create_index('idx_events_geo', 'events', ['geo_point'], postgresql_using='gist')
    op.create_index('idx_bft_position', 'blue_force_tracking', ['position'], postgresql_using='gist')
    op.create_index('idx_ew_position', 'ew_events', ['position'], postgresql_using='gist')

    # Índices para Event Store
    op.create_index('idx_event_store_agg', 'event_store', ['aggregate_id', 'aggregate_type'])
    op.create_index('idx_event_store_type', 'event_store', ['event_type'])


def downgrade():
    op.drop_table('event_store')
    op.drop_table('logistics_supplies')
    op.drop_table('cyber_incidents')
    op.drop_table('ew_events')
    op.drop_table('blue_force_tracking')
    op.drop_table('missions')
    op.drop_table('orbat_units')
    op.drop_table('intel_fusion_records')
    op.drop_table('sensor_sources')
    op.drop_table('priority_intelligence_requirements')
    op.drop_table('intelligence_products')
    op.drop_table('audit_log')
    op.drop_table('alerts')
    op.drop_table('telemetry')
    op.drop_table('events')
    op.drop_table('assets')
