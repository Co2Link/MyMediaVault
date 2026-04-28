"""initial video vault schema

Revision ID: 001_initial_video_vault
Revises:
Create Date: 2026-04-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlmodel.sql.sqltypes import AutoString

revision: str = "001_initial_video_vault"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("external_subject", AutoString(), nullable=False),
        sa.Column("display_name", AutoString()),
        sa.Column("email", AutoString()),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_external_subject", "users", ["external_subject"], unique=True)
    op.create_table(
        "torrents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("info_hash", AutoString(), nullable=False),
        sa.Column("name", AutoString()),
        sa.Column("size_bytes", sa.Integer()),
        sa.Column("raw_blob_key", AutoString()),
        sa.Column("metadata_status", AutoString(), nullable=False),
        sa.Column("metadata_error", AutoString()),
        sa.Column("metadata_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_torrents_info_hash", "torrents", ["info_hash"], unique=True)
    op.create_index("ix_torrents_name", "torrents", ["name"])
    op.create_index("ix_torrents_metadata_status", "torrents", ["metadata_status"])
    op.create_table(
        "tags",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tags_name", "tags", ["name"], unique=True)
    op.create_table(
        "videos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("torrent_id", sa.Uuid(), sa.ForeignKey("torrents.id"), nullable=False),
        sa.Column("title", AutoString()),
        sa.Column("description", AutoString()),
        sa.Column("rating", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "torrent_id", name="uq_videos_user_torrent"),
    )
    op.create_index("ix_videos_user_id", "videos", ["user_id"])
    op.create_index("ix_videos_torrent_id", "videos", ["torrent_id"])
    op.create_index("ix_videos_title", "videos", ["title"])
    op.create_index("ix_videos_rating", "videos", ["rating"])
    op.create_table(
        "torrent_files",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("torrent_id", sa.Uuid(), sa.ForeignKey("torrents.id"), nullable=False),
        sa.Column("path", AutoString(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("torrent_id", "position", name="uq_torrent_files_torrent_position"),
    )
    op.create_table(
        "video_tags",
        sa.Column("video_id", sa.Uuid(), sa.ForeignKey("videos.id"), primary_key=True),
        sa.Column("tag_id", sa.Uuid(), sa.ForeignKey("tags.id"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("video_id", "tag_id", name="uq_video_tags_video_tag"),
    )
    op.create_table(
        "torrent_processing_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("torrent_id", sa.Uuid(), sa.ForeignKey("torrents.id"), nullable=False),
        sa.Column("status", AutoString(), nullable=False),
        sa.Column("error", AutoString()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table in [
        "torrent_processing_jobs",
        "video_tags",
        "torrent_files",
        "videos",
        "tags",
        "torrents",
        "users",
    ]:
        op.drop_table(table)
