from common.decision.turn import EngineBackendDescriptor, register_engine_backend


ENGINE_BACKEND = EngineBackendDescriptor(
    "cgpy", "cgpy.compat.api", "cgpy-compat-api-v1", "cgpy")


def register_backend() -> None:
    register_engine_backend(ENGINE_BACKEND)


__all__ = ("ENGINE_BACKEND", "register_backend")
