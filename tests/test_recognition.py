#! /usr/bin/env python3
# coding: utf-8
import typing as t

import numpy as np

from kamera import recognition
from kamera.config import facial_encoding
from kamera.recognition import Match


def encoding(i: int) -> facial_encoding:
    return np.array([np.float64(i)])


def test_multiple_matches() -> None:
    match_lists = [
        [Match(1, "p1"), Match(2, "p2")],
        [Match(3, "p3"), Match(2, "p2")],
        [Match(3, "p3")],
    ]
    best_matches_names = recognition._get_best_match_for_each_face(match_lists)
    assert best_matches_names == ["p1", "p2", "p3"]


def test_get_closest_match(monkeypatch) -> None:
    known_people: t.Dict[str, t.List[facial_encoding]] = {
        "p1": [encoding(1), encoding(4), encoding(7)],
        "p2": [encoding(2), encoding(5), encoding(8)],
        "p3": [encoding(3), encoding(6), encoding(9)],
    }
    unknown_encoding: facial_encoding = encoding(9)
    tolerance = 3
    matches = recognition._match_face_with_known_people(
        known_people=known_people,
        unknown_encoding=unknown_encoding,
        tolerance=tolerance,
    )
    assert sorted(matches) == [
        Match(distance=0.0, name="p3"),
        Match(distance=1.0, name="p2"),
        Match(distance=2.0, name="p1"),
    ]
