"""
Default indicator weights within each tier.
Keys must match Indicator.name values exactly.
Weights within a tier are normalized at scoring time, so they don't need to sum to 1.0.
"""

INDICATOR_WEIGHTS: dict[str, float] = {
    # Economic
    "unemployment_rate": 1.2,
    "cpi_inflation": 1.0,
    "yield_curve_spread": 1.5,
    "vix_volatility": 1.3,
    # Political
    "global_media_tone": 1.0,
    "global_conflict_events": 1.4,
    "protest_intensity_index": 0.9,
    # Military
    "active_conflict_zones": 1.3,
    "battle_deaths_30d": 1.5,
    "nuclear_launch_readiness": 2.0,
    "arms_transfer_volume": 1.0,
    # Existential
    "doomsday_clock_seconds": 2.0,
    "global_temp_anomaly": 1.5,
    "who_outbreak_alerts": 1.3,
    "co2_ppm": 0.8,
}

DEFAULT_WEIGHT = 1.0
