"""Persistent locations, collection, daily claims and forgiving activity streaks.

Revision ID: 0002_world
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = '0002_world'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_session_player_finished', 'game_sessions', ['player_id', 'finished_at'])
    op.create_index('ix_receipts_created_at', 'batch_receipts', ['created_at'])
    op.add_column('game_sessions', sa.Column('species_awarded', sa.String(40), nullable=True))
    op.add_column('players', sa.Column('selected_location', sa.String(40), nullable=False, server_default='windowsill'))
    op.add_column('players', sa.Column('selected_grass', sa.String(40), nullable=False, server_default='meadow'))
    op.add_column('players', sa.Column('activity_streak', sa.Integer, nullable=False, server_default='0'))
    op.add_column('players', sa.Column('best_streak', sa.Integer, nullable=False, server_default='0'))
    op.add_column('players', sa.Column('last_active_date', sa.Date(), nullable=True))
    op.create_table('grass_unlocks',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('player_id', sa.BigInteger, sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('species_code', sa.String(40), nullable=False),
        sa.Column('copies', sa.Integer, nullable=False, server_default='1'),
        sa.Column('first_found_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('player_id', 'species_code', name='uq_player_grass'))
    op.create_index('ix_grass_unlocks_player_id', 'grass_unlocks', ['player_id'])
    op.create_table('daily_claims',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('player_id', sa.BigInteger, sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('day', sa.Date, nullable=False),
        sa.Column('quest_code', sa.String(40), nullable=False),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('player_id', 'day', 'quest_code', name='uq_player_day_quest'))
    op.create_index('ix_daily_claims_player_id', 'daily_claims', ['player_id'])


def downgrade():
    op.drop_table('daily_claims')
    op.drop_table('grass_unlocks')
    op.drop_column('players', 'last_active_date')
    op.drop_column('players', 'best_streak')
    op.drop_column('players', 'activity_streak')
    op.drop_column('players', 'selected_grass')
    op.drop_column('players', 'selected_location')
    op.drop_column('game_sessions', 'species_awarded')
    op.drop_index('ix_receipts_created_at', table_name='batch_receipts')
    op.drop_index('ix_session_player_finished', table_name='game_sessions')
