"""First playable version: players, sessions, exact-once batch receipts, achievements.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('players',
        sa.Column('id', sa.BigInteger, primary_key=True),
        sa.Column('first_name', sa.String(120), nullable=False),
        sa.Column('username', sa.String(64)),
        sa.Column('total_touches', sa.Integer, nullable=False, server_default='0'),
        sa.Column('xp', sa.Integer, nullable=False, server_default='0'),
        sa.Column('sessions_completed', sa.Integer, nullable=False, server_default='0'),
        sa.Column('recent_jokes', sa.JSON, nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('game_sessions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('player_id', sa.BigInteger, sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_award_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True)),
        sa.Column('awarded', sa.Integer, nullable=False, server_default='0'),
        sa.Column('last_seq', sa.Integer, nullable=False, server_default='0'),
        sa.Column('flags', sa.Integer, nullable=False, server_default='0'))
    op.create_index('ix_game_sessions_player_id', 'game_sessions', ['player_id'])
    op.create_table('batch_receipts',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('player_id', sa.BigInteger, sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('game_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('batch_id', sa.String(36), nullable=False),
        sa.Column('seq', sa.Integer, nullable=False),
        sa.Column('requested', sa.Integer, nullable=False),
        sa.Column('awarded', sa.Integer, nullable=False),
        sa.Column('joke_id', sa.String(48)),
        sa.Column('new_achievements', sa.JSON, nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('session_id', 'batch_id', name='uq_batch_session'))
    op.create_index('ix_receipt_player_created', 'batch_receipts', ['player_id', 'created_at'])
    op.create_table('achievement_unlocks',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('player_id', sa.BigInteger, sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('unlocked_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('player_id', 'code', name='uq_player_achievement'))
    op.create_index('ix_achievement_unlocks_player_id', 'achievement_unlocks', ['player_id'])


def downgrade():
    op.drop_table('achievement_unlocks')
    op.drop_table('batch_receipts')
    op.drop_table('game_sessions')
    op.drop_table('players')
