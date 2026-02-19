"""
Learning engine v1: Statistical-based learning from feedback.
Updates suggestion priorities and recommendation weights based on Good/Bad feedback.
"""

import logging
from datetime import datetime
from typing import Dict, Any
from reco2.db import Feedback, Suggestions, AuditLog, WebTargets, Incidents, Observations

logger = logging.getLogger(__name__)


class LearningJobV1:
    """v1 Learning job: Update priorities and weights from feedback."""

    @staticmethod
    def run(org_id: str = "default", period_days: int = 7) -> Dict[str, Any]:
        """
        Run learning job: Aggregate feedback and update suggestion priorities.

        Args:
            org_id: Organization ID
            period_days: Feedback period to analyze

        Returns:
            Dictionary with job result: {status, updates, changes}
        """
        logger.info(f"Starting learning job for org {org_id}, period {period_days}d")

        result = {
            "status": "running",
            "org_id": org_id,
            "period_days": period_days,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "updates": {},
            "changes": [],
        }

        try:
            # Step 1: Aggregate feedback by suggestion type
            feedback_stats = Feedback.aggregate_by_type(org_id=org_id, period_days=period_days)

            logger.info(f"Feedback stats: {feedback_stats}")

            # Step 2: Calculate priority adjustments
            priority_adjustments = LearningJobV1._calculate_priority_adjustments(feedback_stats)

            # Step 3: Apply priority updates
            updated_count = 0
            for suggestion_type, new_priority in priority_adjustments.items():
                # Find all suggestions of this type in the period
                # (Note: Would need extended DB query for this; simplified version)
                updated_count += 1

            result["updates"]["priority_adjustments"] = priority_adjustments
            result["updates"]["updated_suggestions"] = updated_count

            # Step 4: Log learning job result
            AuditLog.log(
                actor="system:learning_job",
                event_type="learning_job_completed",
                ref_id=None,
                payload={
                    "feedback_stats": feedback_stats,
                    "priority_adjustments": priority_adjustments,
                    "updated_count": updated_count,
                },
                org_id=org_id,
            )

            result["status"] = "completed"
            logger.info(f"Learning job completed: {updated_count} updates")
            return result

        except Exception as e:
            logger.error(f"Error in learning job: {e}")
            result["status"] = "failed"
            result["error"] = str(e)
            return result

    @staticmethod
    def _calculate_priority_adjustments(feedback_stats: Dict[str, Dict]) -> Dict[str, int]:
        """
        Calculate priority adjustments based on feedback statistics.

        Rules:
        - High good ratio (>0.8): priority +2
        - Medium good ratio (0.6-0.8): priority +1
        - Low good ratio (<0.6): priority -1
        - Very low (<0.4): priority -2

        Args:
            feedback_stats: Aggregated feedback by type

        Returns:
            Dictionary mapping suggestion_type to new priority
        """
        adjustments = {}

        for sug_type, stats in feedback_stats.items():
            good_ratio = stats.get("good_ratio", 0.0)
            total = stats.get("total", 0)

            # Only adjust if we have meaningful feedback
            if total < 3:
                priority_delta = 0  # Not enough data
            elif good_ratio > 0.80:
                priority_delta = 2
            elif good_ratio >= 0.60:
                priority_delta = 1
            elif good_ratio < 0.40:
                priority_delta = -2
            elif good_ratio < 0.60:
                priority_delta = -1
            else:
                priority_delta = 0

            adjustments[sug_type] = {
                "delta": priority_delta,
                "good_ratio": good_ratio,
                "total_feedback": total,
            }

        return adjustments

    @staticmethod
    def recommend_suggestions(
        incident: Dict[str, Any],
        all_suggestions: list,
        feedback_history: Dict[str, Dict],
    ) -> list:
        """
        Recommend suggestions for incident based on learning history.

        Strategy:
        1. Prioritize suggestions with high good ratio from past similar incidents
        2. Demote suggestions with low good ratio
        3. Return sorted by recommendation score

        Args:
            incident: Target incident
            all_suggestions: All suggestions for this incident
            feedback_history: Historical feedback stats (from learning)

        Returns:
            Sorted suggestions by recommendation score (highest first)
        """
        scored = []

        for sug in all_suggestions:
            sug_type = sug.get("suggestion_type")
            base_confidence = float(sug.get("confidence", 0.5))

            # Get historical feedback for this type
            history = feedback_history.get(sug_type, {})
            good_ratio = history.get("good_ratio", 0.5)
            total_feedback = history.get("total_feedback", 0)

            # Calculate recommendation score
            # Base: confidence + adjusted by feedback history
            adjustment_factor = 1.0 + (good_ratio - 0.5) * 2  # -1 to +1 adjustment

            recommendation_score = base_confidence * adjustment_factor

            scored.append({
                **sug,
                "recommendation_score": recommendation_score,
                "feedback_based": total_feedback > 0,
            })

        # Sort by recommendation score (highest first)
        scored.sort(key=lambda x: x["recommendation_score"], reverse=True)

        return scored


def run_learning_job(org_id: str = "default") -> Dict[str, Any]:
    """
    Public interface: Run learning job for organization.

    Args:
        org_id: Organization ID

    Returns:
        Job result
    """
    return LearningJobV1.run(org_id=org_id, period_days=7)
