from collections.abc import Callable, Sequence
from math import isfinite

import numpy as np
from scipy.optimize import linear_sum_assignment

from DBDofusUnity.proto_mapper_assembly.interfaces.counter_profile import CounterProfile


def ratio_similarity(left: int | None, right: int | None, max_value: int) -> float:
    if left is None and right is None:
        return 1.0
    if left is None or right is None:
        return 0.0

    if left == right:
        return 1.0
    assert max_value > 0
    delta_ratio = abs(left - right) / max_value
    assert 0 <= delta_ratio <= 1, f"{delta_ratio} invalid, left {left}, right {right}, max_value {max_value}"
    return 1 - delta_ratio


def counter_profile_overlap_similarity(*, left: CounterProfile, right: CounterProfile) -> float:
    if not left.counts and not right.counts:
        return 1.0
    if not left.counts or not right.counts:
        return 0.0

    intersection = left.counts.keys() & right.counts.keys()

    dot = sum(left.counts[key] * right.counts[key] for key in intersection)

    norm_left = left.norm
    norm_right = right.norm

    return dot / (norm_left * norm_right) if norm_left and norm_right else 0.0


def get_average_best_similarity_sequences[T](
    left: Sequence[T],
    right: Sequence[T],
    scorer: Callable[[T, T], float],
) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    n = len(left)
    m = len(right)
    if n == m == 1:
        score = float(scorer(left[0], right[0]))
        if isfinite(score):
            return score or 0.0
        cost = np.array([[score]], dtype=float)
    else:
        cost = np.empty((n, m), dtype=float)
        for index_left, part_left in enumerate(left):
            for index_right, part_right in enumerate(right):
                cost[index_left, index_right] = scorer(part_left, part_right)

    return average_assignment_similarity(cost)


def average_assignment_similarity(cost: np.ndarray) -> float:
    row_ind, col_ind = linear_sum_assignment(cost, maximize=True)

    total_similarity = sum(cost[i, j] for i, j in zip(row_ind, col_ind, strict=True))

    return total_similarity / max(cost.shape)
