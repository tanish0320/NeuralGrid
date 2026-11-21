from __future__ import annotations

import math
from datetime import timedelta
from uuid import uuid4

from apps.api.app.config import Settings
from apps.api.app.core.database import utc_now
from apps.api.app.schemas.networks import CellEdgeRecord, CellRecord
from apps.api.app.schemas.plans import (
    ConstraintCheckResult,
    ObjectiveBreakdown,
    ObjectiveTermBreakdown,
    PlanActionRecord,
    PlanGenerateRequest,
    PlanRecord,
)
from apps.api.app.schemas.simulations import SimulationStateResponse
from apps.api.app.schemas.twinnode import NodeRecord

try:
    from ortools.sat.python import cp_model as _ortools_cp_model  # noqa: F401
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False


class ConstrainedPlanner:
    """Deterministic constraint-aware intervention planner with explicit hard-constraint checks."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _compute_objective(
        self,
        *,
        demands: dict[str, float],
        capacities: dict[str, float],
        states: dict[str, str],
        action_count: int,
        max_actions: int,
        prefer_energy: bool,
    ) -> ObjectiveTermBreakdown:
        w1 = self.settings.w1_overload
        w2 = self.settings.w2_latency
        w3 = self.settings.w3_energy * (1.4 if prefer_energy else 1.0)
        w4 = self.settings.w4_churn

        active_cells = [cid for cid, st in states.items() if st == "ACTIVE" and capacities.get(cid, 0.0) > 0]
        if not active_cells:
            return ObjectiveTermBreakdown(
                overload_penalty=1.0,
                latency_penalty=1.0,
                energy_penalty=0.0,
                action_churn_penalty=0.0,
                total_score=round(w1 + w2, 4),
            )

        overload_ratios = [
            max(0.0, demands[cid] - capacities[cid]) / capacities[cid]
            for cid in active_cells
        ]
        overload_pen = min(1.0, (sum(overload_ratios) / max(1, len(active_cells))) * 15.0)

        utils = [min(1.8, demands[cid] / capacities[cid]) for cid in active_cells]
        latency_pen = min(1.0, sum((u ** 2) for u in utils) / max(1, len(active_cells)))

        energy_pen = min(1.0, len(active_cells) / max(1, len(states)))
        churn_pen = min(1.0, (action_count / max(1, max_actions)) * 0.25)

        total = round(w1 * overload_pen + w2 * latency_pen + w3 * energy_pen + w4 * churn_pen, 4)
        return ObjectiveTermBreakdown(
            overload_penalty=round(overload_pen, 4),
            latency_penalty=round(latency_pen, 4),
            energy_penalty=round(energy_pen, 4),
            action_churn_penalty=round(churn_pen, 4),
            total_score=total,
        )

    def generate_plan(
        self,
        *,
        sim_state: SimulationStateResponse,
        cells: list[CellRecord],
        edges: list[CellEdgeRecord],
        nodes: list[NodeRecord],
        request: PlanGenerateRequest,
        plan_version: int = 1,
    ) -> PlanRecord:
        now = utc_now()
        cell_map = {c.cell_id: c for c in cells}
        tel_map = {t.cell_id: t for t in sim_state.telemetry}
        max_actions = min(
            request.intent.max_actions,
            request.constraints.max_actions,
            self.settings.plan_max_actions,
        )

        # Working projections for deterministic simulation of candidate actions
        projected_states: dict[str, str] = {
            cid: tel_map[cid].cell_state if cid in tel_map else cell_map[cid].current_state
            for cid in cell_map
        }
        projected_demands: dict[str, float] = {
            cid: tel_map[cid].demand_mbps if cid in tel_map else cell_map[cid].base_load_mbps
            for cid in cell_map
        }
        projected_caps: dict[str, float] = {
            cid: (cell_map[cid].capacity_mbps if projected_states[cid] == "ACTIVE" else 0.0)
            for cid in cell_map
        }

        before_obj = self._compute_objective(
            demands=projected_demands,
            capacities=projected_caps,
            states=projected_states,
            action_count=0,
            max_actions=max_actions,
            prefer_energy=request.intent.prefer_energy_efficiency,
        )

        # Build handover adjacency list
        handover_adj: dict[str, list[tuple[str, CellEdgeRecord]]] = {cid: [] for cid in cell_map}
        for e in edges:
            if e.enabled and e.edge_type == "handover_support":
                handover_adj[e.source_cell_id].append((e.target_cell_id, e))
                handover_adj[e.target_cell_id].append((e.source_cell_id, e))

        # Identify stressed/overloaded source cells deterministically
        target_ratio = request.intent.target_utilisation_pct / 100.0
        stressed_sources = sorted(
            [
                cid
                for cid in cell_map
                if projected_states[cid] == "ACTIVE"
                and projected_caps[cid] > 0.0
                and (projected_demands[cid] > projected_caps[cid] * target_ratio)
            ],
            key=lambda cid: (
                -(projected_demands[cid] - projected_caps[cid] * target_ratio),
                cid,
            ),
        )

        actions: list[PlanActionRecord] = []
        explanations: list[str] = []
        action_order = 0

        # Step 1: Activate up to 2 eligible STANDBY cells adjacent to stressed cells to unlock clean spare capacity
        max_standby_activations = min(2, max(1, (max_actions - 1) // 3))
        standby_activated_count = 0
        if stressed_sources and len(actions) < max_actions:
            standby_candidates: dict[str, float] = {}
            for src_cid in stressed_sources:
                overload_amt = max(0.0, projected_demands[src_cid] - projected_caps[src_cid] * target_ratio)
                for nbr_cid, edge in handover_adj.get(src_cid, []):
                    if projected_states.get(nbr_cid) == "STANDBY":
                        standby_candidates[nbr_cid] = standby_candidates.get(nbr_cid, 0.0) + min(
                            overload_amt, edge.max_transfer_mbps
                        )

            for sb_cid, benefit in sorted(standby_candidates.items(), key=lambda x: (-x[1], x[0])):
                if standby_activated_count >= max_standby_activations:
                    break
                if len(actions) >= max_actions - (1 if request.intent.include_compute_offload else 0):
                    break
                if benefit <= 5.0:
                    continue
                action_order += 1
                standby_activated_count += 1
                projected_states[sb_cid] = "ACTIVE"
                projected_caps[sb_cid] = cell_map[sb_cid].capacity_mbps
                actions.append(
                    PlanActionRecord(
                        action_id=uuid4(),
                        action_order=action_order,
                        action_type="activate_standby_cell",
                        source_id=sb_cid,
                        target_id=sb_cid,
                        amount=cell_map[sb_cid].capacity_mbps,
                        params={
                            "region": cell_map[sb_cid].region,
                            "estimated_relief_mbps": round(benefit, 2),
                        },
                    )
                )
                explanations.append(
                    f"Activate standby cell {sb_cid} (+{cell_map[sb_cid].capacity_mbps:.1f} Mbps capacity) to absorb nearby surge"
                )

        # Step 2: Reallocate excess demand across enabled handover edges with safety headroom below 85% congestion
        dest_safe_fill = min(0.78, target_ratio)
        stressed_set = set(stressed_sources)
        for src_cid in stressed_sources:
            if len(actions) >= max_actions - (1 if request.intent.include_compute_offload else 0):
                break
            desired_shed = max(0.0, projected_demands[src_cid] - projected_caps[src_cid] * target_ratio)
            if desired_shed <= 1.0:
                continue

            # Candidate destinations sorted deterministically by safe spare capacity desc, edge weight desc, cell_id asc
            candidates: list[tuple[float, float, str, CellEdgeRecord]] = []
            for nbr_cid, edge in handover_adj.get(src_cid, []):
                if projected_states.get(nbr_cid) != "ACTIVE" or nbr_cid in stressed_set:
                    continue
                nbr_spare = max(0.0, projected_caps[nbr_cid] * dest_safe_fill - projected_demands[nbr_cid])
                if nbr_spare >= 5.0:
                    candidates.append((nbr_spare, edge.weight, nbr_cid, edge))

            candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
            for nbr_spare, _w, nbr_cid, edge in candidates:
                if desired_shed <= 1.0 or len(actions) >= max_actions - (1 if request.intent.include_compute_offload else 0):
                    break
                current_nbr_spare = max(
                    0.0, projected_caps[nbr_cid] * dest_safe_fill - projected_demands[nbr_cid]
                )
                raw_transfer = min(
                    desired_shed,
                    edge.max_transfer_mbps,
                    request.constraints.max_transfer_per_action_mbps,
                    current_nbr_spare,
                    projected_demands[src_cid],
                )
                transfer_amt = math.floor(raw_transfer * 100.0) / 100.0
                if transfer_amt < 1.0:
                    continue
                projected_demands[src_cid] = round(projected_demands[src_cid] - transfer_amt, 4)
                projected_demands[nbr_cid] = round(projected_demands[nbr_cid] + transfer_amt, 4)
                desired_shed = round(desired_shed - transfer_amt, 4)
                action_order += 1
                actions.append(
                    PlanActionRecord(
                        action_id=uuid4(),
                        action_order=action_order,
                        action_type="reallocate_load",
                        source_id=src_cid,
                        target_id=nbr_cid,
                        amount=transfer_amt,
                        params={
                            "edge_id": edge.edge_id,
                            "edge_max_mbps": edge.max_transfer_mbps,
                            "dest_spare_before_mbps": round(current_nbr_spare, 2),
                        },
                    )
                )
                explanations.append(
                    f"Reallocate {transfer_amt:.1f} Mbps from {src_cid} to {nbr_cid} via {edge.edge_id}"
                )

        # Step 3: Optionally assign simulation-compute verification batch to an eligible ACTIVE TwinNode worker
        eligible_nodes = [
            n
            for n in nodes
            if n.status == "ACTIVE"
            and n.worker_active
            and n.heartbeat_age_seconds <= self.settings.twinnode_heartbeat_timeout_seconds
            and "counterfactual_batch" in n.capabilities
        ]
        # Prefer remote worker NODE-JUNAID when ACTIVE so physical LAN offload is demonstrated
        eligible_nodes.sort(key=lambda n: (0 if n.node_id == "NODE-JUNAID" else 1, n.node_id))

        if request.intent.include_compute_offload and eligible_nodes and len(actions) < max_actions:
            chosen = eligible_nodes[0]
            action_order += 1
            actions.append(
                PlanActionRecord(
                    action_id=uuid4(),
                    action_order=action_order,
                    action_type="dispatch_compute_task",
                    source_id="NODE-TANISH",
                    target_id=chosen.node_id,
                    amount=1.0,
                    params={
                        "task_type": "counterfactual_batch",
                        "seed": sim_state.seed,
                        "simulation_id": str(sim_state.simulation_id),
                        "event_id": str(sim_state.active_event_id) if sim_state.active_event_id else None,
                    },
                )
            )
            explanations.append(
                f"Dispatch allowlisted counterfactual_batch simulation-compute task to active physical worker {chosen.node_id}"
            )

        if not explanations:
            explanations.append(
                "No load reallocation required or no eligible spare neighbour capacity available under current hard constraints."
            )

        after_obj = self._compute_objective(
            demands=projected_demands,
            capacities=projected_caps,
            states=projected_states,
            action_count=len(actions),
            max_actions=max_actions,
            prefer_energy=request.intent.prefer_energy_efficiency,
        )

        constraints_checked = self._verify_hard_constraints(
            actions=actions,
            cell_map=cell_map,
            edges=edges,
            projected_demands=projected_demands,
            projected_caps=projected_caps,
            projected_states=projected_states,
            nodes_by_id={n.node_id: n for n in nodes},
            max_actions=max_actions,
            protect_emergency=request.constraints.protect_emergency_cells,
            sim_state_version=sim_state.state_version,
            req_state_version=request.state_version,
        )

        # Deterministic greedy allocator is the guaranteed fallback (never labelled "optimal")
        solver_method = "deterministic_greedy_constrained"
        return PlanRecord(
            plan_id=uuid4(),
            simulation_id=sim_state.simulation_id,
            event_id=sim_state.active_event_id,
            seed=sim_state.seed,
            version=plan_version,
            state_version=sim_state.state_version,
            status="PENDING_APPROVAL",
            solver_method=solver_method,
            intent=request.intent,
            objective=ObjectiveBreakdown(
                weights={
                    "w1_overload": self.settings.w1_overload,
                    "w2_latency": self.settings.w2_latency,
                    "w3_energy": self.settings.w3_energy,
                    "w4_churn": self.settings.w4_churn,
                },
                before=before_obj,
                after_projected=after_obj,
                improvement=round(before_obj.total_score - after_obj.total_score, 4),
            ),
            constraints_checked=constraints_checked,
            actions=actions,
            explanation=explanations,
            expires_at=now + timedelta(seconds=self.settings.plan_expiry_seconds),
            created_at=now,
            updated_at=now,
        )

    def _verify_hard_constraints(
        self,
        *,
        actions: list[PlanActionRecord],
        cell_map: dict[str, CellRecord],
        edges: list[CellEdgeRecord],
        projected_demands: dict[str, float],
        projected_caps: dict[str, float],
        projected_states: dict[str, str],
        nodes_by_id: dict[str, NodeRecord],
        max_actions: int,
        protect_emergency: bool,
        sim_state_version: int,
        req_state_version: int,
    ) -> list[ConstraintCheckResult]:
        edge_by_id = {e.edge_id: e for e in edges}

        # 1. Destination capacity check after all transfers
        dest_ok = True
        for a in actions:
            if a.action_type == "reallocate_load":
                cap = projected_caps.get(a.target_id, 0.0)
                dem = projected_demands.get(a.target_id, 0.0)
                if projected_states.get(a.target_id) != "ACTIVE" or dem > cap + 1e-3:
                    dest_ok = False
                    break

        # 2. Edge transfer limit check
        edge_ok = True
        for a in actions:
            if a.action_type == "reallocate_load":
                eid = a.params.get("edge_id")
                edge = edge_by_id.get(str(eid))
                if edge is None or not edge.enabled or a.amount > edge.max_transfer_mbps + 1e-3:
                    edge_ok = False
                    break

        # 3. Critical/emergency cell protection (no emergency cell deactivated/failed)
        emergency_ok = True
        if protect_emergency:
            for cid, cell in cell_map.items():
                if cell.is_emergency and projected_states.get(cid) != "ACTIVE":
                    emergency_ok = False
                    break

        # 4. Physical worker eligibility
        worker_ok = True
        for a in actions:
            if a.action_type == "dispatch_compute_task":
                node = nodes_by_id.get(a.target_id)
                if node is None or node.status != "ACTIVE" or not node.worker_active:
                    worker_ok = False
                    break

        # 5. Action count cap
        cap_ok = len(actions) <= max_actions

        # 6. State version alignment
        sv_ok = sim_state_version == req_state_version

        return [
            ConstraintCheckResult(
                name="destination_capacity_bound",
                passed=dest_ok,
                detail="All transfer destinations remain within nominal cell capacity after reallocation.",
            ),
            ConstraintCheckResult(
                name="edge_transfer_limit",
                passed=edge_ok,
                detail="All load transfers respect enabled handover edge max_transfer_mbps bounds.",
            ),
            ConstraintCheckResult(
                name="emergency_coverage_protection",
                passed=emergency_ok,
                detail="No critical/emergency cell is shut down or left inactive.",
            ),
            ConstraintCheckResult(
                name="physical_worker_active_check",
                passed=worker_ok,
                detail="Compute tasks are assigned only to ACTIVE TwinNode workers with fresh heartbeats.",
            ),
            ConstraintCheckResult(
                name="max_action_churn_cap",
                passed=cap_ok,
                detail=f"Action count ({len(actions)}) within limit ({max_actions}).",
            ),
            ConstraintCheckResult(
                name="state_version_alignment",
                passed=sv_ok,
                detail=f"Plan bound to authoritative simulation state_version={req_state_version}.",
            ),
        ]
