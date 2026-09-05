"""
§14 — Signal Fusion.

Composite = sum(weight_i * signal_i), scaled by the volatility engine's
confidence multiplier and the market-regime multiplier, then mapped to the
doc's label bands and a 0-100% confidence figure. Every individual score
that contributed materially is surfaced as a plain-English reason, and
alpha (this module) never touches position size — that stays in
risk_engine.py, per the doc's explicit "keep alpha separate from risk".
"""
import config
import regime as regime_mod


def _label_for_score(score: float) -> str:
    t = config.COMPOSITE_THRESHOLDS
    if score >= t["strong"]:
        return "STRONG LONG"
    if score >= t["moderate"]:
        return "LONG"
    if score >= t["watch"]:
        return "WATCH"
    if score <= -t["strong"]:
        return "STRONG SHORT"
    if score <= -t["moderate"]:
        return "SHORT"
    if score <= -t["watch"]:
        return "WATCH"
    return "NEUTRAL"


def _side_for_label(label: str) -> str:
    if label in ("STRONG LONG", "LONG"):
        return "BUY"
    if label in ("STRONG SHORT", "SHORT"):
        return "SELL"
    return "HOLD"


def fuse(scores: dict, market_regime: str = "UNKNOWN", vol_confidence_multiplier: float = 1.0) -> dict:
    """`scores` maps engine name -> score in [-1, 1] (already computed by
    momentum_engine, mean_reversion_engine, volume_engine, structure_engine,
    relative_strength_engine, multi_timeframe, ml_model). Missing engines
    are simply skipped (their configured weight is excluded from the
    normalization, not treated as a zero vote)."""
    weights = config.ENGINE_WEIGHTS
    weighted_sum, weight_total = 0.0, 0.0
    contributions = {}

    for name, weight in weights.items():
        if name not in scores or scores[name] is None:
            continue
        contributions[name] = scores[name] * weight
        weighted_sum += contributions[name]
        weight_total += abs(weight)

    raw_composite = (weighted_sum / weight_total) if weight_total else 0.0

    regime_mult = regime_mod.REGIME_CONFIDENCE_MULTIPLIER.get(market_regime, 1.0)
    composite = max(-1.0, min(1.0, raw_composite * vol_confidence_multiplier * regime_mult))

    label = _label_for_score(composite)
    side = _side_for_label(label)
    confidence_pct = round(min(99.0, abs(composite) * 100), 0)

    # Reasons: the top contributing engines by absolute weighted contribution,
    # phrased in the direction that matches `side`.
    ranked = sorted(contributions.items(), key=lambda kv: -abs(kv[1]))
    reasons = []
    for name, contrib in ranked:
        if abs(contrib) < 0.03:
            continue
        direction = "positive" if contrib > 0 else "negative"
        reasons.append(f"{name.replace('_', ' ')} {direction} ({scores[name]:+.2f})")

    return {
        "composite_score": round(composite, 3),
        "raw_composite_score": round(raw_composite, 3),
        "signal_label": label,
        "side": side,
        "confidence_pct": confidence_pct,
        "vol_confidence_multiplier": vol_confidence_multiplier,
        "regime_confidence_multiplier": regime_mult,
        "contributions": {k: round(v, 3) for k, v in contributions.items()},
        "reasons": reasons[:6],
    }
