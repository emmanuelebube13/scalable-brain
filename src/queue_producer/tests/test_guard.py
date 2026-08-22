import pytest
import os
from src.common.queue.local_durable import LocalDurableBackend


def test_production_queue_path_refused():
    prod_path = os.environ.get("QUEUE_LOCAL_ROOT", "results/state/queue")
    with pytest.raises(
        RuntimeError, match="Tests cannot write to the production queue path"
    ):
        LocalDurableBackend(root=prod_path)
