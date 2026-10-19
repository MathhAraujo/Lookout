from pathlib import Path

import yaml

from lookout.collectors.adzuna import AdzunaCollector
from lookout.collectors.arbeitnow import ArbeitnowCollector
from lookout.collectors.base import Collector
from lookout.collectors.greenhouse import GreenhouseCollector
from lookout.collectors.himalayas import HimalayasCollector
from lookout.collectors.hn_whoishiring import HnWhoIsHiringCollector
from lookout.collectors.jobicy import JobicyCollector
from lookout.collectors.lever import LeverCollector
from lookout.collectors.linkedin_email import LinkedInEmailCollector
from lookout.collectors.remoteok import RemoteOKCollector
from lookout.collectors.remotive import RemotiveCollector
from lookout.collectors.weworkremotely import WeWorkRemotelyCollector
from lookout.collectors.workable import WorkableCollector
from lookout.collectors.workingnomads import WorkingNomadsCollector
from lookout.config import Settings

COLLECTOR_NAMES = [
    "remoteok",
    "remotive",
    "arbeitnow",
    "jobicy",
    "adzuna",
    "weworkremotely",
    "workingnomads",
    "himalayas",
    "hn_whoishiring",
    "greenhouse",
    "lever",
    "workable",
    "linkedin_email",
]


def load_sources_config(path: Path) -> dict[str, dict]:
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Unable to load sources configuration from {path}: {exc}") from exc

    sources = config.get("sources") if isinstance(config, dict) else None
    if not isinstance(sources, dict):
        raise TypeError(f"Sources configuration at {path} must contain a 'sources' mapping")
    if any(not isinstance(source_config, dict) for source_config in sources.values()):
        raise TypeError(f"Each source entry in {path} must be a mapping")
    return sources


def get_collector(name: str, settings: Settings, config: dict) -> Collector:
    injected = config.get("collector")
    if injected is not None:
        return injected

    if name == "remoteok":
        return RemoteOKCollector(settings)
    if name == "remotive":
        return RemotiveCollector(settings)
    if name == "arbeitnow":
        return ArbeitnowCollector(settings)
    if name == "jobicy":
        return JobicyCollector(settings)
    if name == "adzuna":
        return AdzunaCollector(
            settings,
            countries=config.get("countries", []),
            queries=config.get("queries", []),
        )
    if name == "weworkremotely":
        return WeWorkRemotelyCollector(settings)
    if name == "workingnomads":
        return WorkingNomadsCollector(settings)
    if name == "himalayas":
        return HimalayasCollector(settings)
    if name == "hn_whoishiring":
        return HnWhoIsHiringCollector(settings)
    if name == "greenhouse":
        return GreenhouseCollector(settings, config.get("companies", {}))
    if name == "lever":
        return LeverCollector(settings, config.get("companies", {}))
    if name == "workable":
        return WorkableCollector(settings, config.get("companies", {}))
    if name == "linkedin_email":
        return LinkedInEmailCollector(settings)

    raise ValueError(f"Unknown collector source: {name}")


def build_collectors(settings: Settings, config: dict[str, dict]) -> list[Collector]:
    collectors = []
    for name, source_config in config.items():
        injected = source_config.get("collector")
        if name not in COLLECTOR_NAMES and injected is None:
            continue
        if not source_config.get("enabled", False) and injected is None:
            continue
        collectors.append(get_collector(name, settings, source_config))
    return collectors
