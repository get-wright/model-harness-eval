import shutil
import subprocess

import pytest


def _docker_ready() -> bool:
    """True only if the docker CLI exists AND the daemon answers (not just installed)."""
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(
            ["docker", "info"], capture_output=True, timeout=10
        ).returncode == 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _docker_ready(), reason="docker daemon not available")


def test_sandbox_has_no_default_route():
    """network_mode: none -> /proc/net/route has no default route (dest 00000000)."""
    from inspect_ai import Task, eval
    from inspect_ai.dataset import Sample
    from inspect_ai.solver import Generate, TaskState, solver
    from inspect_ai.util import sandbox

    from sca_eval.tasks import COMPOSE_FILE

    @solver
    def check_route():
        async def solve(state: TaskState, generate: Generate) -> TaskState:
            res = await sandbox().exec(["cat", "/proc/net/route"])
            state.metadata["route"] = res.stdout
            return state
        return solve

    task = Task(
        dataset=[Sample(input="noop", target="noop")],
        solver=[check_route()],
        sandbox=("docker", COMPOSE_FILE),
    )
    logs = eval(task, model="mockllm/model", display="none")
    route = logs[0].samples[0].metadata["route"]

    data_lines = route.strip().splitlines()[1:]  # drop the header row
    default_routes = [ln for ln in data_lines if ln.split()[1] == "00000000"]
    assert not default_routes, f"expected no default route, found: {default_routes}"
