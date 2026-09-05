"""
Runs the full multi-layer pipeline for a single symbol and returns one
signal record (§17/§18 of quant_stock_signal_engine.md):

  Market Data -> Feature Engine -> Regime Detection -> Signal Models
      -> Signal Fusion -> Risk Engine -> (Pattern DB logging)

Every sub-engine failure is caught and neutralized rather than aborting the
whole symbol's scan — a bad print in one engine (e.g. no volume data) still
lets the rest of the composite score stand on its own.
"""
from datetime import datetime

import pandas as pd

import config
import data_fetcher
import indicators
import regime as regime_mod
import candle_features
import momentum_engine
import mean_reversion_engine
import volatility_engine
import volume_engine
import structure_engine
import relative_strength_engine
import multi_timeframe
import anomaly_engine
import ml_model
import signal_fusion
import strategies
import risk_engine
import pattern_db


def _empty_result(symbol: str, reason: str) -> dict:
    return {
        "symbol": symbol, "timestamp": datetime.now().isoformat(), "bar_time": None,
        "regime": "unknown", "market_regime": "UNKNOWN", "adx": None, "bb_width_pct": None,
        "strategy": "none", "side": "HOLD", "signal_label": "NEUTRAL", "confidence_pct": 0,
        "composite_score": 0.0, "reason": reason, "reasons": [], "entry": None,
        "stop": None, "target": None, "risk_status": "SKIPPED", "risk_reason": "",
        "suggested_qty": 0, "anomaly_flags": [], "pattern": None,
    }


def _safe(fn, default, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        d = dict(default)
        d["error"] = str(e)
        return d


def run_for_symbol(symbol: str, benchmark_df: "pd.DataFrame | None" = None,
                    benchmark_df_ind: "pd.DataFrame | None" = None,
                    market_regime_info: dict = None,
                    raw_df: "pd.DataFrame | None" = None) -> dict:
    raw = raw_df if raw_df is not None else data_fetcher.get_bars(symbol)
    if raw.empty or len(raw) < 55:
        return _empty_result(symbol, "Insufficient bar data returned")

    # ---- Feature Engine -----------------------------------------------------
    df = indicators.compute_all(raw)
    last = df.iloc[-1]

    # ---- Regime Detection (per-symbol + market-wide) ------------------------
    current_regime = regime_mod.classify(df)
    market_regime_info = market_regime_info or {"regime": "UNKNOWN"}
    market_regime = market_regime_info.get("regime", "UNKNOWN")

    # ---- Signal Models (§2-§10, §16) -----------------------------------------
    mom = _safe(momentum_engine.compute, {"momentum_score": 0.0, "trend_score": 0.0}, df)
    vol = _safe(volatility_engine.compute, {"volatility_score": 0.0, "vol_confidence_multiplier": 1.0}, df)
    mr = _safe(mean_reversion_engine.compute, {"mean_reversion_score": 0.0}, df,
               trend_strength=mom.get("trend_score", 0.0))
    vlm = _safe(volume_engine.compute, {"volume_score": 0.0}, df)
    struct = _safe(structure_engine.compute, {"structure_score": 0.0}, df)
    rs = _safe(relative_strength_engine.compute, {"relative_strength_score": 0.0}, df, benchmark_df_ind)
    mtf = _safe(multi_timeframe.compute, {"trend_alignment_score": 0.0}, symbol, df)
    candles = _safe(candle_features.compute, {"pattern": None, "swing_structure": None}, df)
    anomaly = _safe(anomaly_engine.compute, {"is_anomaly": False, "anomaly_flags": []}, df,
                     relative_strength_pct=rs.get("blended_relative_strength_pct"))

    ml_features = {
        "trend_score": mom.get("trend_score", 0.0),
        "momentum_score": mom.get("momentum_score", 0.0),
        "mean_reversion_score": mr.get("mean_reversion_score", 0.0),
        "volume_score": vlm.get("volume_score", 0.0),
        "structure_score": struct.get("structure_score", 0.0),
        "relative_strength_score": rs.get("relative_strength_score", 0.0),
        "rvol": vlm.get("rvol") or 0.0,
    }
    ml = _safe(ml_model.predict, {"ml_score": 0.0, "ml_available": False}, ml_features)

    # ---- Signal Fusion (§14) -------------------------------------------------
    scores = {
        "trend": mom.get("trend_score", 0.0),
        "momentum": mom.get("momentum_score", 0.0),
        "mean_reversion": mr.get("mean_reversion_score", 0.0),
        "volume": vlm.get("volume_score", 0.0),
        "structure": struct.get("structure_score", 0.0),
        "relative_strength": rs.get("relative_strength_score", 0.0),
        "multi_timeframe": mtf.get("trend_alignment_score", 0.0),
        "ml": ml.get("ml_score", 0.0) if ml.get("ml_available") else None,
    }
    fusion = signal_fusion.fuse(scores, market_regime=market_regime,
                                 vol_confidence_multiplier=vol.get("vol_confidence_multiplier", 1.0))

    side = fusion["side"]
    levels = strategies.compute_levels(df, side)
    style = strategies.dominant_style(fusion["contributions"])

    # ---- Risk Engine (§15, unchanged — alpha and risk stay separate) --------
    risk_result = risk_engine.evaluate(symbol=symbol, side=side, entry=levels["entry"], stop=levels["stop"])

    result = {
        "symbol": symbol,
        "timestamp": datetime.now().isoformat(),
        "bar_time": df.index[-1].isoformat(),
        "regime": current_regime,
        "market_regime": market_regime,
        "adx": mom.get("adx"),
        "bb_width_pct": round(last["bb_width"] * 100, 2) if last.get("bb_width") == last.get("bb_width") else None,
        "strategy": style,
        "side": side,
        "signal_label": fusion["signal_label"],
        "composite_score": fusion["composite_score"],
        "confidence_pct": fusion["confidence_pct"],
        "reasons": fusion["reasons"],
        "reason": "; ".join(fusion["reasons"]) if fusion["reasons"] else "No engine crossed its threshold",
        "entry": levels["entry"],
        "stop": levels["stop"],
        "target": levels["target"],
        "risk_status": risk_result["status"],
        "risk_reason": risk_result["reason"],
        "suggested_qty": risk_result["suggested_qty"],
        "pattern": candles.get("pattern"),
        "swing_structure": candles.get("swing_structure"),
        "anomaly_flags": anomaly.get("anomaly_flags", []),
        "is_anomaly": anomaly.get("is_anomaly", False),
        "rvol": vlm.get("rvol"),
        "vol_state": vol.get("vol_state"),
        "relative_strength_pct": rs.get("blended_relative_strength_pct"),
        "ml_available": ml.get("ml_available", False),
        "engine_scores": scores,
    }

    _log_to_pattern_db(result, vol)
    return result


def _log_to_pattern_db(result: dict, vol: dict) -> None:
    try:
        pattern_db.log_observation({
            "symbol": result["symbol"], "bar_time": result["bar_time"],
            "logged_at": datetime.now().isoformat(), "entry_price": result["entry"],
            "pattern": result["pattern"], "swing_structure": result["swing_structure"],
            "regime": result["regime"], "market_regime": result["market_regime"],
            "vol_state": vol.get("vol_state"), "rvol": result["rvol"],
            "trend_score": result["engine_scores"].get("trend"),
            "momentum_score": result["engine_scores"].get("momentum"),
            "mean_reversion_score": result["engine_scores"].get("mean_reversion"),
            "volume_score": result["engine_scores"].get("volume"),
            "structure_score": result["engine_scores"].get("structure"),
            "relative_strength_score": result["engine_scores"].get("relative_strength"),
            "composite_score": result["composite_score"], "side": result["side"],
            "features_json": "{}",
        })
    except Exception:
        pass  # research logging must never break a live scan
