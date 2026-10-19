from pathlib import Path

from lookout.collectors.registry import COLLECTOR_NAMES, build_collectors, load_sources_config


def test_load_sources_config_lists_all_phase_one_sources():
    config = load_sources_config(Path("config/sources.yml"))

    assert set(config) == set(COLLECTOR_NAMES)


def test_build_collectors_includes_only_enabled_sources(settings):
    config = {
        "remoteok": {"enabled": True},
        "remotive": {"enabled": False},
    }

    collectors = build_collectors(settings, config)

    assert [collector.name for collector in collectors] == ["remoteok"]


def test_build_collectors_accepts_injected_test_collectors(settings):
    class FakeCollector:
        name = "fake"

        def fetch(self):
            return []

    fake = FakeCollector()
    collectors = build_collectors(
        settings,
        {"fake": {"enabled": True, "collector": fake}},
    )

    assert collectors == [fake]
