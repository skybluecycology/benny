import pytest
import sys
from unittest.mock import patch, MagicMock

# PREVENT PyO3/Tokenizers error by mocking swarm before it loads
mock_swarm = MagicMock()
sys.modules["benny.graph.swarm"] = mock_swarm

from benny.graph.manifest_runner import plan_from_requirement, execute_manifest, _apply_delta
from benny.core.manifest import SwarmManifest, RunStatus

@pytest.fixture
def mock_planner():
    return mock_swarm.planner_node

@pytest.fixture
def mock_scheduler():
    return mock_swarm.wave_scheduler_node

@pytest.fixture
def mock_graph():
    graph = MagicMock()
    mock_swarm.build_swarm_graph.return_value = graph
    return graph

@pytest.mark.asyncio
async def test_plan_from_requirement_success(mock_planner, mock_scheduler):
    mock_planner.side_effect = [
        {"plan": [{"task_id": "p1", "is_pillar": True, "is_expanded": False}]},
        {"plan": [{"task_id": "p1", "is_pillar": True, "is_expanded": True}, {"task_id": "t1"}]}
    ]
    mock_scheduler.return_value = {"waves": [["p1"]]}

    manifest = await plan_from_requirement(
        requirement="test req",
        model="m",
        output_spec=None
    )
    assert manifest.id.startswith("manifest-")
    assert mock_planner.call_count >= 2

@pytest.mark.asyncio
async def test_execute_manifest_success(mock_graph):
    manifest = SwarmManifest(id="m1", name="M", requirement="req")
    mock_graph.ainvoke.return_value = {
        "status": "completed",
        "plan": [{"task_id": "t1", "status": "completed"}]
    }
    
    with patch("benny.persistence.run_store.save_run"):
        with patch("benny.persistence.run_store.update_run_status") as mock_update:
            mock_update.return_value = MagicMock()
            await execute_manifest(manifest, run_id="run1")
            assert mock_update.called

def test_apply_delta_reducers():
    state = {"errors": ["e1"]}
    delta = {"errors": ["e2"], "status": "ok"}
    new_state = _apply_delta(state, delta)
    assert new_state["errors"] == ["e1", "e2"]
