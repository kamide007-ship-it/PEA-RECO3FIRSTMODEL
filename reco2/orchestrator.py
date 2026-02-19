from typing import Dict, Any, Optional
from reco2 import input_gate, output_gate
from reco2.system_prompt import RECO3_SYSTEM_PROMPT
from reco2.llm_adapter import create_adapter, BaseLLMAdapter
from reco2.engine import evaluate_payload
from reco2.config import load_config

class Orchestrator:
    PSI_REGEN_THRESHOLD = 0.50
    PSI_ANNOT_THRESHOLD = 0.80
    MAX_REGEN_ATTEMPTS = 2
    BASE_TEMPERATURE = 0.7

    def __init__(self, llm: Optional[BaseLLMAdapter] = None):
        self._llm = llm or create_adapter("dummy")
        self._active_adapter = self._llm.name
        self._active_model = getattr(self._llm, "model", "unknown")

    def set_llm(self, llm: BaseLLMAdapter) -> None:
        self._llm = llm
        self._active_adapter = self._llm.name
        self._active_model = getattr(self._llm, "model", "unknown")

    def get_active_adapter(self) -> str:
        """Currently active LLM adapter name"""
        return self._active_adapter

    def get_active_model(self) -> str:
        """Currently active LLM model name"""
        return self._active_model

    def _cool_down_result(self, in_analysis: Dict[str, Any]) -> Dict[str, Any]:
        warns = in_analysis.get("warnings") or []
        warn_lines = "\n".join([f"  * {w}" for w in warns]) if warns else "  * (none)"
        msg = (
            "-- 冷却モード --\n"
            "入力の分析結果、以下の点が検出されました：\n"
            f"{warn_lines}\n"
            "より具体的で冷静な質問に書き直していただけますか？\n"
            "正確で誠実な回答をするために、ご協力をお願いします。"
        )
        return {
            "session_id": None,
            "response": msg,
            "input_analysis": in_analysis,
            "output_analysis": None,
            "reco2_evaluation": None,
            "temperature_used": 0.0,
            "regenerated": False,
            "attempts": 0,
            "llm_model": None,
        }

    def process(self, user_input: str, domain: str = "general", context: Optional[Dict[str, Any]] = None, max_tokens: int = 1024) -> Dict[str, Any]:
        cfg = load_config()
        self.PSI_REGEN_THRESHOLD = float(cfg.get("psi_regen_threshold", self.PSI_REGEN_THRESHOLD))
        self.PSI_ANNOT_THRESHOLD = float(cfg.get("psi_annot_threshold", self.PSI_ANNOT_THRESHOLD))
        self.MAX_REGEN_ATTEMPTS = int(cfg.get("max_regen_attempts", self.MAX_REGEN_ATTEMPTS))
        self.BASE_TEMPERATURE = float(cfg.get("base_temperature", self.BASE_TEMPERATURE))

        in_analysis = input_gate.analyze(
            user_input,
            w_ambiguity=float(cfg.get("input_w_ambiguity", 0.20)),
            w_assertion=float(cfg.get("input_w_assertion", 0.25)),
            w_emotion=float(cfg.get("input_w_emotion", 0.30)),
            w_unrealistic=float(cfg.get("input_w_unrealistic", 0.25)),
        )
        t_mod = float(in_analysis.get("temperature_modifier", 1.0))
        adj_temp = max(0.1, min(1.0, self.BASE_TEMPERATURE * t_mod))

        if in_analysis.get("risk_level") == "critical":
            return self._cool_down_result(in_analysis)

        effective_prompt, _ = input_gate.rebuild_prompt(user_input, in_analysis)

        attempts = 0
        regenerated = False
        res = {"text": "", "model": "unknown", "usage": None}
        out_analysis = None

        for _ in range(max(1, self.MAX_REGEN_ATTEMPTS)):
            attempts += 1
            try:
                res = self._llm.generate(
                    prompt=effective_prompt,
                    temperature=adj_temp,
                    max_tokens=max_tokens,
                    system_prompt=RECO3_SYSTEM_PROMPT,
                )
            except RuntimeError as e:
                # LLM generation failed - return error to caller
                raise RuntimeError(f"LLM generation failed: {e}") from e
            out_analysis = output_gate.analyze(
                res.get("text", ""),
                w_assertion=float(cfg.get("output_w_assertion", 0.30)),
                w_evidence=float(cfg.get("output_w_evidence", 0.30)),
                w_contradiction=float(cfg.get("output_w_contradiction", 0.25)),
                w_provocative=float(cfg.get("output_w_provocative", 0.15)),
            )
            if float(out_analysis.get("psi_modifier", 1.0)) >= self.PSI_REGEN_THRESHOLD:
                break
            regenerated = True
            adj_temp = max(0.1, adj_temp * 0.6)

        text_out = str(res.get("text", ""))

        action = (out_analysis or {}).get("action") if out_analysis else "pass"
        annotated = False
        if action == "soften":
            text_out = output_gate.soften(text_out)
        elif action == "annotate":
            annotated = True
            text_out = "（注）不確実性が残るため、断定を避けています。\n\n" + text_out
        elif action == "regenerate":
            annotated = True
            text_out = "（警告）誠実度の観点で出力に問題がある可能性があります。\n\n" + text_out

        ctx = dict(context or {})
        ctx["domain"] = domain
        if "confidence" not in ctx:
            ctx["confidence"] = 0.7

        psi_mod = float((out_analysis or {}).get("psi_modifier", 1.0))
        payload = {
            "inference": {"integrity": psi_mod},
            "evidence": {"integrity": {"median": psi_mod}},
            "context": ctx,
        }
        try:
            reco2_eval = evaluate_payload(payload)
        except (OSError, IOError, ValueError) as e:
            # Fallback evaluation on state error
            import logging
            logging.getLogger(__name__).error(f"Failed to evaluate payload: {e}")
            reco2_eval = {
                "session_id": None,
                "deviation": 0.0,
                "temperature": 0.0,
                "integrity": 0.0,
                "confidence_adjusted": 0.5,
                "verdict": "unknown",
                "verdict_ja": "評価不可",
                "meta": {"error": str(e)},
            }

        return {
            "session_id": reco2_eval.get("session_id"),
            "response": text_out,
            "input_analysis": in_analysis,
            "output_analysis": out_analysis,
            "reco2_evaluation": reco2_eval,
            "temperature_used": round(adj_temp, 6),
            "regenerated": regenerated,
            "attempts": attempts,
            "annotated": annotated,
            "llm_model": res.get("model"),
        }

_instance: Optional[Orchestrator] = None

def get_orchestrator() -> Orchestrator:
    global _instance
    if _instance is None:
        import os
        cfg = load_config()

        # Priority: ENV > config.json > default
        adapter_name = os.getenv("LLM_ADAPTER") or cfg.get("llm_adapter", "auto")

        # Resolve "auto" to actual adapter
        from reco2.llm_adapter import _resolve_auto
        if adapter_name == "auto":
            adapter_name = _resolve_auto()

        # Select model based on adapter type
        model = None
        adapter_lower = (adapter_name or "dummy").strip().lower()

        if adapter_lower in ("openai", "gpt"):
            # OpenAI: ENV(OPENAI_MODEL) > config.json > "gpt-4o"
            model = os.getenv("OPENAI_MODEL") or cfg.get("llm_model") or "gpt-4o"
        elif adapter_lower in ("claude", "anthropic"):
            # Claude: ENV(ANTHROPIC_MODEL) > config.json > "claude-sonnet-4-5-20250929"
            model = os.getenv("ANTHROPIC_MODEL") or cfg.get("llm_model") or "claude-sonnet-4-5-20250929"
        else:
            # Dummy or others: use config.json or None
            model = cfg.get("llm_model") or None

        kw = {"model": model} if model else {}
        llm = create_adapter(adapter_name, **kw)
        _instance = Orchestrator(llm=llm)
    return _instance

def set_orchestrator(orch: Orchestrator) -> None:
    global _instance
    _instance = orch
