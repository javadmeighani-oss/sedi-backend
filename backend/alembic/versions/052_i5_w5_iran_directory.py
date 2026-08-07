"""I5-IMPL-W5-P01 — Iran directory tables (AUTHOR ONLY; do not run in this Gate).

Revision ID: 052_i5_w5_iran_directory
Revises: 051_i5b2_governed_source_profile

Creates iran_doctors / iran_laboratories / iran_hospitals.
No seed, no network, no KU linkage, no production write.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "052_i5_w5_iran_directory"
down_revision: Union[str, None] = "051_i5b2_governed_source_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "iran_doctors",
        sa.Column("id", sa.Integer(), sa.Identity(start=1), nullable=False),
        sa.Column("canonical_directory_key", sa.String(length=128), nullable=False),
        sa.Column("full_name", sa.String(length=256), nullable=False),
        sa.Column("specialty", sa.String(length=128), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("province", sa.String(length=128), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("address", sa.String(length=512), nullable=True),
        sa.Column("record_state", sa.String(length=32), server_default="ACTIVE", nullable=False),
        sa.Column("source_system_label", sa.String(length=128), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(), nullable=True),
        sa.Column("last_observed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("char_length(canonical_directory_key) >= 1", name="ck_iran_doctor_key_nonempty"),
        sa.CheckConstraint("char_length(full_name) >= 1", name="ck_iran_doctor_name_nonempty"),
        sa.CheckConstraint("record_state IN ('ACTIVE', 'INACTIVE')", name="ck_iran_doctor_record_state"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_directory_key", name="uq_iran_doctor_canonical_key"),
    )
    op.create_index("ix_iran_doctor_city", "iran_doctors", ["city"])
    op.create_index("ix_iran_doctor_province", "iran_doctors", ["province"])
    op.create_index("ix_iran_doctor_specialty", "iran_doctors", ["specialty"])
    op.create_index("ix_iran_doctor_record_state", "iran_doctors", ["record_state"])

    op.create_table(
        "iran_laboratories",
        sa.Column("id", sa.Integer(), sa.Identity(start=1), nullable=False),
        sa.Column("canonical_directory_key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("province", sa.String(length=128), nullable=True),
        sa.Column("services_text", sa.String(length=512), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("address", sa.String(length=512), nullable=True),
        sa.Column("record_state", sa.String(length=32), server_default="ACTIVE", nullable=False),
        sa.Column("source_system_label", sa.String(length=128), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(), nullable=True),
        sa.Column("last_observed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("char_length(canonical_directory_key) >= 1", name="ck_iran_lab_key_nonempty"),
        sa.CheckConstraint("char_length(name) >= 1", name="ck_iran_lab_name_nonempty"),
        sa.CheckConstraint("record_state IN ('ACTIVE', 'INACTIVE')", name="ck_iran_lab_record_state"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_directory_key", name="uq_iran_lab_canonical_key"),
    )
    op.create_index("ix_iran_lab_city", "iran_laboratories", ["city"])
    op.create_index("ix_iran_lab_province", "iran_laboratories", ["province"])
    op.create_index("ix_iran_lab_record_state", "iran_laboratories", ["record_state"])

    op.create_table(
        "iran_hospitals",
        sa.Column("id", sa.Integer(), sa.Identity(start=1), nullable=False),
        sa.Column("canonical_directory_key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("facility_type", sa.String(length=32), server_default="HOSPITAL", nullable=False),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("province", sa.String(length=128), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("address", sa.String(length=512), nullable=True),
        sa.Column("record_state", sa.String(length=32), server_default="ACTIVE", nullable=False),
        sa.Column("source_system_label", sa.String(length=128), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(), nullable=True),
        sa.Column("last_observed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("char_length(canonical_directory_key) >= 1", name="ck_iran_hosp_key_nonempty"),
        sa.CheckConstraint("char_length(name) >= 1", name="ck_iran_hosp_name_nonempty"),
        sa.CheckConstraint(
            "facility_type IN ('HOSPITAL', 'MEDICAL_CENTER')",
            name="ck_iran_hosp_facility_type",
        ),
        sa.CheckConstraint("record_state IN ('ACTIVE', 'INACTIVE')", name="ck_iran_hosp_record_state"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_directory_key", name="uq_iran_hosp_canonical_key"),
    )
    op.create_index("ix_iran_hosp_city", "iran_hospitals", ["city"])
    op.create_index("ix_iran_hosp_province", "iran_hospitals", ["province"])
    op.create_index("ix_iran_hosp_facility_type", "iran_hospitals", ["facility_type"])
    op.create_index("ix_iran_hosp_record_state", "iran_hospitals", ["record_state"])


def downgrade() -> None:
    op.drop_index("ix_iran_hosp_record_state", table_name="iran_hospitals")
    op.drop_index("ix_iran_hosp_facility_type", table_name="iran_hospitals")
    op.drop_index("ix_iran_hosp_province", table_name="iran_hospitals")
    op.drop_index("ix_iran_hosp_city", table_name="iran_hospitals")
    op.drop_table("iran_hospitals")
    op.drop_index("ix_iran_lab_record_state", table_name="iran_laboratories")
    op.drop_index("ix_iran_lab_province", table_name="iran_laboratories")
    op.drop_index("ix_iran_lab_city", table_name="iran_laboratories")
    op.drop_table("iran_laboratories")
    op.drop_index("ix_iran_doctor_record_state", table_name="iran_doctors")
    op.drop_index("ix_iran_doctor_specialty", table_name="iran_doctors")
    op.drop_index("ix_iran_doctor_province", table_name="iran_doctors")
    op.drop_index("ix_iran_doctor_city", table_name="iran_doctors")
    op.drop_table("iran_doctors")
