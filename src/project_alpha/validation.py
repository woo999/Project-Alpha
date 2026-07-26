"""Chronological validation tools that prevent train/test leakage."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class WalkForwardFold:
    """Integer boundaries for one expanding-window validation fold."""

    train_start: int
    train_end: int
    test_start: int
    test_end: int

    def validate(self) -> None:
        if not (0 <= self.train_start < self.train_end <= self.test_start < self.test_end):
            raise ValueError("fold boundaries must be ordered and non-overlapping")


def chronological_split(
    data: pd.Series,
    train_fraction: float = 0.7,
    *,
    min_train: int = 100,
    min_test: int = 30,
) -> tuple[pd.Series, pd.Series]:
    """Split observations in time order, never randomly."""
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be between zero and one")
    if min_train < 1 or min_test < 1:
        raise ValueError("minimum lengths must be positive")
    if not data.index.is_monotonic_increasing:
        raise ValueError("data must be sorted from oldest to newest")
    if data.index.has_duplicates:
        raise ValueError("data index cannot contain duplicate timestamps")

    split_at = int(len(data) * train_fraction)
    train = data.iloc[:split_at].copy()
    test = data.iloc[split_at:].copy()
    if len(train) < min_train or len(test) < min_test:
        raise ValueError("not enough observations for requested split")
    return train, test


def expanding_walk_forward_folds(
    n_observations: int,
    *,
    min_train: int,
    test_size: int,
    step_size: int | None = None,
) -> list[WalkForwardFold]:
    """Build expanding train windows followed by untouched test windows."""
    if n_observations < 1 or min_train < 1 or test_size < 1:
        raise ValueError("lengths must be positive")
    step = test_size if step_size is None else step_size
    if step < 1:
        raise ValueError("step_size must be positive")
    if min_train + test_size > n_observations:
        raise ValueError("not enough observations for one complete fold")

    folds: list[WalkForwardFold] = []
    test_start = min_train
    while test_start + test_size <= n_observations:
        fold = WalkForwardFold(
            train_start=0,
            train_end=test_start,
            test_start=test_start,
            test_end=test_start + test_size,
        )
        fold.validate()
        folds.append(fold)
        test_start += step
    return folds


def apply_fold(
    data: pd.Series, fold: WalkForwardFold
) -> tuple[pd.Series, pd.Series]:
    """Materialize one fold and assert that its labels do not overlap."""
    fold.validate()
    if fold.test_end > len(data):
        raise ValueError("fold extends beyond available data")
    train = data.iloc[fold.train_start : fold.train_end].copy()
    test = data.iloc[fold.test_start : fold.test_end].copy()
    if not train.index.intersection(test.index).empty:
        raise ValueError("training and test labels overlap")
    return train, test
