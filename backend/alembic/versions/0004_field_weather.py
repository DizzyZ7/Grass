"""Daily immutable field assignments and location snapshots for genuine session progress.

Revision ID: 0004_field_weather
Revises: 0003_social
"""
from alembic import op
import sqlalchemy as sa

revision = '0004_field_weather'
down_revision = '0003_social'
branch_labels = None
depends_on = None


def upgrade():
    # Old sessions cannot reliably reveal where the player played. Do not grant
    # retrospective location-based mission credit for pre-migration sessions.
    op.add_column('game_sessions', sa.Column('location_code', sa.String(40), nullable=False,
                                           server_default='windowsill'))
    op.create_table('field_missions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('player_id', sa.BigInteger(), sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('code', sa.String(40), nullable=False),
        sa.Column('location_code', sa.String(40), nullable=True),
        sa.Column('xp', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('player_id', 'day', name='uq_player_field_day'))
    op.create_index('ix_field_missions_player_id', 'field_missions', ['player_id'])
    op.create_index('ix_field_missions_day', 'field_missions', ['day'])


def downgrade():
    op.drop_index('ix_field_missions_day', table_name='field_missions')
    op.drop_index('ix_field_missions_player_id', table_name='field_missions')
    op.drop_table('field_missions')
    op.drop_column('game_sessions', 'location_code')
