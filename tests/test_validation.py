import pandas as pd
import pytest

from project_alpha.validation import (
    apply_fold,
    chronological_split,
    expanding_walk_forward_folds,
)


def test_chronological_split_preserves_time_and_has_no_overlap():
    data = pd.Series(
        range(200),
        index=pd.date_range("2020-01-01", periods=200, freq="D"),
    )

    train, test = chronological_split(data, 0.7, min_train=100, min_test=30)

    assert len(train) == 140
    assert len(test) == 60
    assert train.index.max() < test.index.min()
    assert train.index.intersection(test.index).empty


def test_split_rejects_unsorted_or_duplicate_timestamps():
    unsorted = pd.Series([1, 2], index=pd.to_datetime(["2020-01-02", "2020-01-01"]))
    duplicate = pd.Series([1, 2], index=pd.to_datetime(["2020-01-01", "2020-01-01"]))

    with pytest.raises(ValueError):
        chronological_split(unsorted, min_train=1, min_test=1)
    with pytest.raises(ValueError):
        chronological_split(duplicate, min_train=1, min_test=1)


def test_expanding_folds_only_move_forward():
    folds = expanding_walk_forward_folds(
        260,
        min_train=100,
        test_size=40,
        step_size=40,
    )

    assert len(folds) == 4
    assert [fold.train_end for fold in folds] == [100, 140, 180, 220]
    assert [fold.test_start for fold in folds] == [100, 140, 180, 220]
    assert all(fold.train_end == fold.test_start for fold in folds)


def test_apply_fold_returns_disjoint_windows():
    data = pd.Series(range(150))
    fold = expanding_walk_forward_folds(
        len(data),
        min_train=100,
        test_size=25,
    )[0]

    train, test = apply_fold(data, fold)

    assert len(train) == 100
    assert len(test) == 25
    assert train.index.intersection(test.index).empty
