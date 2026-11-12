class CoordinatorError(RuntimeError):
    """Base class for repository coordinator failures."""


class IllegalStageTransition(CoordinatorError):
    pass


class IllegalDecisionError(CoordinatorError):
    pass


class RunBusyError(CoordinatorError):
    pass


class PreflightFailed(CoordinatorError):
    pass


class GateUnavailable(CoordinatorError):
    pass


class NoActiveRunError(CoordinatorError):
    pass
