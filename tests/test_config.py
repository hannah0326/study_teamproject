# 작성: 2026-10-25 23:12 KST
from teamapp import config


def test_roles_six():
    assert len(config.ROLES) == 6
    assert len(set(config.ROLES)) == 6
    assert config.PL in config.ROLES and config.WP in config.ROLES


def test_models_are_three_free_and_not_router():
    assert len(config.MODELS) == 3
    assert all(m.endswith(":free") for m in config.MODELS)
    assert "openrouter/free" not in config.MODELS


def test_get_secret_reads_env(monkeypatch):
    monkeypatch.setenv("TF_TEST_SECRET", "값있음")
    assert config.get_secret("TF_TEST_SECRET") == "값있음"


def test_get_secret_missing_is_none(monkeypatch):
    monkeypatch.delenv("TF_TEST_MISSING", raising=False)
    assert config.get_secret("TF_TEST_MISSING") is None
