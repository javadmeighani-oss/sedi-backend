"""088: additive country column on the I5 directory tables (default IR)."""
from backend.app.models import IranDoctor, IranHospital, IranLaboratory
from backend.tests.helpers.alembic_head import current_script_head


def test_088_is_in_chain_and_follows_087():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config("backend/alembic.ini")
    cfg.set_main_option("script_location", "backend/alembic")
    rev = ScriptDirectory.from_config(cfg).get_revision("088_i5_directory_country")
    assert rev.down_revision == "087_a4_notification_inbox_visibility"
    assert current_script_head()


def test_directory_models_default_country_ir():
    for model in (IranDoctor, IranLaboratory, IranHospital):
        col = model.__table__.c.country
        assert col.nullable is False
        assert str(col.server_default.arg) == "IR"
        assert col.default.arg == "IR"
