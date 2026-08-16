"""slowking — Kaggle agent hook. The shared runtime is the whole shell (ADR-0055):
deployment profile, knowledge seams, telemetry, the agent(obs) contract."""
from common.runtime import make_agent
from strategy import STRATEGY

agent = make_agent(STRATEGY)
