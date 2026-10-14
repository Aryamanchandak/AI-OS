"""Real official-gRPC A2A task joined into a waiting live graph."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import grpc
from a2a.types import a2a_pb2 as p
from a2a.types import a2a_pb2_grpc as pb_grpc

from s13code.core.a2a_adapter.official import A2AGraphBridge, GraphA2ARemote, OfficialA2AServer
from s13code.core.a2a_adapter.server import A2ADemoServer
from s13code.core.live_graph import GraphPatch, GraphStore, LiveGraphExecutor, TaskSpec


CARD = {
    "name": "Remote architecture specialist",
    "description": "Produces a bounded architecture review",
    "version": "1.0.0",
    "supportedInterfaces": [{"url": "grpc://127.0.0.1", "protocolBinding": "GRPC", "protocolVersion": "1.0"}],
    "capabilities": {"streaming": True, "pushNotifications": True},
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain"],
    "skills": [{"id": "architecture-review", "name": "Architecture review",
                "description": "Reviews one delegated architecture question", "tags": ["architecture"]}],
}


async def run(output: Path) -> None:
    prompt = "Slow remote report: explain in two lines why an agent card is not permission to access local memory."

    async def specialist(text: str) -> str:
        assert text == prompt
        return ("An Agent Card advertises capabilities and transports; it grants no local-memory authority.\n"
                "The coordinator must send only explicitly authorized task context and validate the returned artifact.")

    root = output.parent / ".a2a-proof-state"
    root.mkdir(parents=True, exist_ok=True)
    core = A2ADemoServer(CARD, task_handler=specialist, task_db=root / "tasks.sqlite")
    official = OfficialA2AServer(core, root / "push.sqlite")
    channel = grpc.aio.insecure_channel(await official.start())
    bridge = A2AGraphBridge(GraphA2ARemote(pb_grpc.A2AServiceStub(channel)))
    graph = GraphStore(root / "graph.sqlite")
    run_id = "official-a2a-live-proof"
    # Make the proof rerunnable without pretending an old completed run is new.
    if graph.db.execute("select 1 from runs where id=?", (run_id,)).fetchone():
        run_id += "-2"

    class Planner:
        async def plan(self, snapshot, event):
            if event.kind == "run_started":
                node = TaskSpec("remote_specialist", "a2a_result", {"run_id": snapshot.run_id},
                                {"agent": "remote-a2a-architecture-specialist"})
                return GraphPatch(add=(node,), wait=("remote_specialist",),
                                  reason="delegate only the bounded architecture question")
            if event.node_id == "remote_specialist":
                return GraphPatch(finish=True, reason="validated remote artifact joined the graph")
            return GraphPatch()

    executor = LiveGraphExecutor(graph, Planner(), {"a2a_result": bridge.result_skill})
    request = p.SendMessageRequest(message=p.Message(
        message_id="architecture-question-1", role=p.ROLE_USER, parts=[p.Part(text=prompt)]))
    try:
        parked = await executor.run(run_id)
        final = await bridge.dispatch_waiting(graph, run_id, "remote_specialist", request)
        report = await executor.run(run_id, resume=True)
        artifact_text = final.artifacts[0].parts[0].text
        payload = {
            "prompt": prompt,
            "agent_card": CARD,
            "initial_graph": {"finished": parked.finished, "waiting": parked.waiting},
            "remote_task": {"id": final.id, "state": p.TaskState.Name(final.status.state),
                            "artifact_id": final.artifacts[0].artifact_id, "artifact_text": artifact_text},
            "resumed_graph": {"finished": report.finished, "executed": report.executed,
                              "snapshot": graph.snapshot(run_id).__dict__},
            "events": [event.__dict__ for event in graph.events(run_id)],
        }
        output.write_text(json.dumps(payload, indent=2))
        print(json.dumps(payload, indent=2))
    finally:
        graph.close()
        await channel.close()
        await official.stop()
        await core.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("a2a-proof.json"))
    args = parser.parse_args()
    asyncio.run(run(args.output))
