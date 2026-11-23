from __future__ import annotations

from fastapi import Request

from agents.twinnode.controller.node_manager import TwinNodeController
from apps.api.app.api.websocket import ConnectionManager
from apps.api.app.config import Settings
from apps.api.app.core.database import Database
from apps.api.app.core.events import AuditLogger
from apps.api.app.core.url_policy import DnsResolver
from apps.api.app.modules.digital_twin.engine import SimulationManager
from apps.api.app.modules.digital_twin.forecast_risk import PredictionService
from apps.api.app.modules.event_intelligence.orchestrator import (
    _AUTO_LOAD,
    EventIntelligenceOrchestrator,
    EventIntelligenceServiceProtocol,
)
from apps.api.app.modules.governance.lifecycle import GovernanceService
from apps.api.app.modules.verification.counterfactual import CounterfactualVerifier
from apps.api.app.repositories.event_sources import EventSourceRepository
from apps.api.app.repositories.events import EventRepository
from apps.api.app.repositories.networks import NetworkRepository
from apps.api.app.repositories.plans import PlanRepository
from apps.api.app.repositories.predictions import PredictionRepository
from apps.api.app.repositories.simulations import SimulationRepository
from apps.api.app.repositories.source_registry import SourceRegistryRepository
from apps.api.app.repositories.twinnode import TwinNodeRepository
from apps.api.app.repositories.verification import VerificationRepository
from apps.api.app.repositories.impact import ImpactRepository
from apps.api.app.modules.event_intelligence.connectors.registry import ConnectorRegistry
from apps.api.app.modules.event_intelligence.resolution.resolver import CanonicalEventResolver
from apps.api.app.modules.event_intelligence.geospatial.engine import GeospatialImpactEngine


class AppContainer:
    """Single-process controller dependency container owned by Junaid."""

    def __init__(
        self,
        *,
        settings: Settings,
        event_intelligence_service: EventIntelligenceServiceProtocol | None | object = _AUTO_LOAD,
        dns_resolver: DnsResolver | None = None,
    ) -> None:
        self.settings = settings
        self.db = Database(settings.neuralgrid_db_path)
        self.db.init_schema()

        self.ws_manager = ConnectionManager()
        self.audit = AuditLogger(self.db)

        self.network_repo = NetworkRepository(self.db)
        self.sim_repo = SimulationRepository(self.db)
        self.event_repo = EventRepository(self.db)
        self.source_repo = EventSourceRepository(self.db)
        self.pred_repo = PredictionRepository(self.db)
        self.plan_repo = PlanRepository(self.db)
        self.twinnode_repo = TwinNodeRepository(self.db)
        self.verification_repo = VerificationRepository(self.db)
        self.registry_repo = SourceRegistryRepository(self.db)
        self.impact_repo = ImpactRepository(self.db)
        self.connector_registry = ConnectorRegistry(settings)
        self.canonical_resolver = CanonicalEventResolver(self.event_repo, self.registry_repo)
        self.impact_engine = GeospatialImpactEngine(
            event_repo=self.event_repo,
            network_repo=self.network_repo,
            impact_repo=self.impact_repo,
            registry_repo=self.registry_repo,
        )

        self.event_orchestrator = EventIntelligenceOrchestrator(
            settings=settings,
            source_repo=self.source_repo,
            event_repo=self.event_repo,
            audit=self.audit,
            ws_manager=self.ws_manager,
            service=event_intelligence_service,
            dns_resolver=dns_resolver,
            canonical_resolver=self.canonical_resolver,
        )
        self.sim_manager = SimulationManager(
            network_repo=self.network_repo,
            sim_repo=self.sim_repo,
            event_repo=self.event_repo,
            plan_repo=self.plan_repo,
            audit=self.audit,
            ws_manager=self.ws_manager,
        )
        self.prediction_service = PredictionService(
            settings=settings,
            network_repo=self.network_repo,
            sim_repo=self.sim_repo,
            pred_repo=self.pred_repo,
            audit=self.audit,
            ws_manager=self.ws_manager,
        )
        self.twinnode_controller = TwinNodeController(
            settings=settings,
            repo=self.twinnode_repo,
            audit=self.audit,
            ws_manager=self.ws_manager,
        )
        self.governance_service = GovernanceService(
            settings=settings,
            sim_manager=self.sim_manager,
            network_repo=self.network_repo,
            plan_repo=self.plan_repo,
            twinnode_repo=self.twinnode_repo,
            twinnode_controller=self.twinnode_controller,
            audit=self.audit,
            ws_manager=self.ws_manager,
        )
        self.verifier = CounterfactualVerifier(
            network_repo=self.network_repo,
            sim_repo=self.sim_repo,
            event_repo=self.event_repo,
            plan_repo=self.plan_repo,
            twinnode_repo=self.twinnode_repo,
            verification_repo=self.verification_repo,
            audit=self.audit,
            ws_manager=self.ws_manager,
        )


def get_container(request: Request) -> AppContainer:
    return request.app.state.container
