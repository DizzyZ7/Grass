"""Stage 3: privacy-aware social play, invited-by attribution and weekly rewards.

Revision ID: 0003_social
Revises: 0002_world
"""
from alembic import op
import sqlalchemy as sa

revision = '0003_social'
down_revision = '0002_world'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('players', sa.Column('show_public_profile', sa.Boolean(),
                                       nullable=False, server_default=sa.true()))
    op.add_column('players', sa.Column('referrer_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_players_referrer_id', 'players', 'players',
                          ['referrer_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_players_referrer_id', 'players', ['referrer_id'])
    op.create_table('weekly_claims',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('player_id', sa.BigInteger(), sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('week_start', sa.Date(), nullable=False),
        sa.Column('quest_code', sa.String(40), nullable=False),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('player_id', 'week_start', 'quest_code', name='uq_player_week_quest'))
    op.create_index('ix_weekly_claims_player_id', 'weekly_claims', ['player_id'])


def downgrade():
    op.drop_table('weekly_claims')
    op.drop_index('ix_players_referrer_id', table_name='players')
    op.drop_constraint('fk_players_referrer_id', 'players', type_='foreignkey')
    op.drop_column('players', 'referrer_id')
    op.drop_column('players', 'show_public_profile')
