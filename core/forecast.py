"""Daily sales forecasting: a few simple models, backtested, best one wins."""
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from .config import BACKTEST_DAYS, BACKTEST_FOLDS, MIN_HISTORY_DAYS, SEASON_DAYS


def wape(actual, predicted) -> float:
    """Total miss divided by total actual. 0.37 = about 37% off."""
    return float(np.abs(actual - predicted).sum() / max(np.abs(actual).sum(), 1e-9))


def _future_index(train: pd.Series, h: int) -> pd.DatetimeIndex:
    return pd.date_range(train.index[-1] + pd.Timedelta(days=1), periods=h)


def weekday_average(train: pd.Series, h: int) -> pd.Series:
    by_weekday = train.groupby(train.index.dayofweek).mean()
    idx = _future_index(train, h)
    return pd.Series([by_weekday[d] for d in idx.dayofweek], index=idx)


def ets(train: pd.Series, h: int) -> pd.Series:
    fit = ExponentialSmoothing(train, trend=None, seasonal="add", seasonal_periods=SEASON_DAYS).fit()
    return pd.Series(fit.forecast(h).values, index=_future_index(train, h)).clip(lower=0)


MODELS = {"weekday_average": weekday_average, "ets": ets}


def backtest(s: pd.Series, h: int = BACKTEST_DAYS, folds: int = BACKTEST_FOLDS) -> dict:
    """Average error of each model over several hidden windows at the end of the data."""
    scores = {}
    for name, model in MODELS.items():
        errors = []
        for k in range(folds, 0, -1):
            end = len(s) - k * h
            if end < 2 * SEASON_DAYS:
                continue
            train, test = s.iloc[:end], s.iloc[end:end + h]
            try:
                errors.append(wape(test.values, model(train, len(test)).values))
            except Exception:  # a model failing must not stop the others
                continue
        if errors:
            scores[name] = float(np.mean(errors))
    return scores


def forecast(s: pd.Series, horizon: int = 14) -> dict:
    if len(s) < MIN_HISTORY_DAYS:
        raise ValueError(f"Need at least {MIN_HISTORY_DAYS} days of sales history, have {len(s)}.")
    scores = backtest(s, h=min(BACKTEST_DAYS, horizon))
    if not scores:
        raise ValueError("Not enough history to backtest any model.")
    best = min(scores, key=scores.get)
    pred = MODELS[best](s, horizon)
    band = scores[best] * pred  # typical % miss from the backtest: a rough range, not a guarantee
    return {"best_model": best, "scores": scores, "forecast": pred,
            "lower": (pred - band).clip(lower=0), "upper": pred + band}
