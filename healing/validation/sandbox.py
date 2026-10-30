from contextlib import contextmanager
from copy import deepcopy
from tempfile import TemporaryDirectory


class RepairSandbox:

    @contextmanager
    def create(self, x, config):
        """
        Create an isolated workspace.

        Data and configuration are copied. Changes made in
        the sandbox must not affect the original objects.
        """

        with TemporaryDirectory(prefix="ml-healing-") as tmp:
            workspace = {
                "path": tmp,
                "data": x.copy(deep=True),
                "config": deepcopy(config)
            }

            yield workspace