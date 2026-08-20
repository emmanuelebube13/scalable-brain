import json
import inspect
from src.layer0.strategies.v2_harness import discover
from src.regime_aware.strategies import bollinger_aggressive, bollinger_h1, bollinger_h4, donchian_h1, donchian_h4, donchian_vcp, ema_adx_h1, ema_adx_h4, ema_adx_multitf

strategies = discover()
legacy_modules = [
    bollinger_aggressive, bollinger_h1, bollinger_h4, 
    donchian_h1, donchian_h4, donchian_vcp, 
    ema_adx_h1, ema_adx_h4, ema_adx_multitf
]

out = {}

for sid, strat in strategies.items():
    meta = strat.metadata
    doc = inspect.getdoc(strat.__class__) or ""
    out[sid] = {
        "universe": "v2",
        "hypothesis": meta.hypothesis,
        "doc": doc
    }

for mod in legacy_modules:
    for name in dir(mod):
        obj = getattr(mod, name)
        if inspect.isclass(obj) and hasattr(obj, "config") and obj.__module__ == mod.__name__:
            # instantiate to get config
            try:
                cfg = obj.config() if callable(obj.config) else obj.config
                sid = getattr(cfg, "name", name)
                doc = inspect.getdoc(obj) or ""
                out[sid] = {
                    "universe": "legacy",
                    "hypothesis": getattr(cfg, "description", ""),
                    "doc": doc
                }
            except Exception:
                pass

with open("scratch/strat_docs.json", "w") as f:
    json.dump(out, f, indent=2)
