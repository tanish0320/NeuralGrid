from __future__ import annotations

import uvicorn

from agents.twinnode.node_agent.agent_app import create_agent_app
from agents.twinnode.node_agent.host_metrics import get_local_ipv4
from apps.api.app.config import Settings


def main() -> None:
    settings = Settings()
    public_ip = get_local_ipv4()
    agent_url = f"http://{public_ip}:{settings.twinnode_agent_port}"
    print(
        f"[TwinNode Agent] Starting {settings.twinnode_node_id} on {settings.twinnode_agent_host}:{settings.twinnode_agent_port} "
        f"(advertised URL={agent_url}, controller={settings.twinnode_controller_url})"
    )
    app = create_agent_app(
        node_id=settings.twinnode_node_id,
        node_token=settings.twinnode_node_token,
        controller_url=settings.twinnode_controller_url,
        agent_port=settings.twinnode_agent_port,
        agent_url=agent_url,
        heartbeat_interval_seconds=settings.twinnode_heartbeat_interval_seconds,
    )
    uvicorn.run(
        app,
        host=settings.twinnode_agent_host,
        port=settings.twinnode_agent_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
