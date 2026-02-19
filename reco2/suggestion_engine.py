"""
Suggestion engine: Generate rule-based and AI-powered suggestions for incidents.
"""

import logging
from typing import List, Dict, Any, Optional
from reco2.db import Suggestions, Observations, WebTargets
from reco2.orchestrator import get_orchestrator

logger = logging.getLogger(__name__)


class RuleBasedSuggestionGenerator:
    """Generate suggestions based on predefined rules."""

    @staticmethod
    def generate(incident: Dict[str, Any], org_id: str = "default") -> List[Dict[str, Any]]:
        """
        Generate rule-based suggestions for incident.

        Args:
            incident: Incident record
            org_id: Organization ID

        Returns:
            List of suggestion dictionaries (ready to save)
        """
        suggestions = []
        title = incident.get("title", "").lower()
        summary = incident.get("summary", "").lower()

        # Rule 1: HTTP 5xx errors
        if "http 5" in title or "500" in title or "503" in title:
            suggestions.append({
                "suggestion_type": "rule_based",
                "rationale": "HTTP 5xx indicates server error. Check service logs and consider restart.",
                "confidence": 0.95,
                "action": {"action_type": "NOTIFY_OPS"},
            })

        # Rule 2: Connection errors / timeouts
        if "timeout" in summary or "connection" in summary:
            suggestions.append({
                "suggestion_type": "rule_based",
                "rationale": "Connection timeout detected. Check network connectivity and firewall rules.",
                "confidence": 0.85,
                "action": {"action_type": "NOTIFY_OPS"},
            })

        # Rule 3: High latency
        if "latency" in title:
            suggestions.append({
                "suggestion_type": "rule_based",
                "rationale": "Slow response time detected. Consider scaling or optimizing endpoint.",
                "confidence": 0.75,
                "action": {"action_type": "RECOMMEND_SCALE"},
            })

        # Rule 4: 404 Not Found
        if "404" in title:
            suggestions.append({
                "suggestion_type": "rule_based",
                "rationale": "404 Not Found. Check if endpoint URL is correct or if deployment was incomplete.",
                "confidence": 0.80,
                "action": {"action_type": "CHECK_DEPLOYMENT"},
            })

        return suggestions


class AISuggestionGenerator:
    """Generate suggestions using LLM."""

    @staticmethod
    def generate(
        incident: Dict[str, Any],
        observations: List[Dict[str, Any]] = None,
        org_id: str = "default",
    ) -> Optional[Dict[str, Any]]:
        """
        Generate AI-powered suggestion for incident using LLM.

        Args:
            incident: Incident record
            observations: Related observations (context)
            org_id: Organization ID

        Returns:
            Suggestion dictionary or None if generation fails
        """
        try:
            orch = get_orchestrator()

            # Build context for LLM
            incident_desc = f"Title: {incident.get('title')}\nSummary: {incident.get('summary')}"

            obs_context = ""
            if observations:
                recent = observations[:5]  # Last 5 observations
                obs_context = "Recent observations:\n"
                for obs in recent:
                    payload = obs.get("payload_json", "{}")
                    obs_context += f"  - {obs.get('ts')}: {payload[:100]}\n"

            prompt = f"""
Given this incident:
{incident_desc}

{obs_context}

Provide a brief, actionable suggestion for resolving this issue.
Focus on practical diagnostic steps and remediation.
Keep response under 150 words.
"""

            response = orch.process(
                user_input=prompt,
                domain="incident_analysis",
                context={"incident_id": incident.get("id")},
                max_tokens=256,
            )

            ai_text = response.get("response", "").strip()
            if not ai_text:
                return None

            # Extract confidence from output analysis
            confidence = response.get("reco2_evaluation", {}).get("confidence_adjusted", 0.7)

            return {
                "suggestion_type": "ai_generated",
                "rationale": ai_text,
                "confidence": confidence,
                "action": None,  # AI suggestions are informational, not actionable
            }

        except Exception as e:
            logger.error(f"Error generating AI suggestion: {e}")
            return None


def generate_suggestions_for_incident(
    incident: Dict[str, Any],
    org_id: str = "default",
    include_ai: bool = True,
) -> int:
    """
    Generate and save suggestions for incident.

    Args:
        incident: Incident record
        org_id: Organization ID
        include_ai: Whether to include AI-generated suggestions

    Returns:
        Number of suggestions created
    """
    incident_id = incident.get("id")
    created_count = 0

    # Get context: recent observations for this source
    source_id = incident.get("source_id")
    if not source_id:
        # Try to extract from title
        pass

    # Rule-based suggestions
    rule_suggestions = RuleBasedSuggestionGenerator.generate(incident, org_id=org_id)
    for sug_dict in rule_suggestions:
        sug_id = Suggestions.create(
            incident_id=incident_id,
            suggestion_type=sug_dict.get("suggestion_type"),
            rationale=sug_dict.get("rationale"),
            confidence=float(sug_dict.get("confidence", 0.5)),
            action=sug_dict.get("action"),
            org_id=org_id,
        )
        created_count += 1
        logger.info(f"Created rule-based suggestion {sug_id}")

    # AI-generated suggestions
    if include_ai:
        recent_obs = Observations.list_recent(limit=20, org_id=org_id)
        ai_sug_dict = AISuggestionGenerator.generate(
            incident,
            observations=recent_obs,
            org_id=org_id,
        )

        if ai_sug_dict:
            sug_id = Suggestions.create(
                incident_id=incident_id,
                suggestion_type=ai_sug_dict.get("suggestion_type"),
                rationale=ai_sug_dict.get("rationale"),
                confidence=float(ai_sug_dict.get("confidence", 0.5)),
                action=ai_sug_dict.get("action"),
                org_id=org_id,
            )
            created_count += 1
            logger.info(f"Created AI suggestion {sug_id}")

    return created_count
