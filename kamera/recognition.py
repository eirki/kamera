#! /usr/bin/env python3
# coding: utf-8
import typing as t
from copy import deepcopy
from dataclasses import dataclass, field
from io import BytesIO

import face_recognition

from kamera.config import Settings, facial_encoding


@dataclass(frozen=True, order=True)
class Match:
    distance: float = field(compare=True)
    name: str


def _get_matches_for_encodings(
    known_people: t.Dict[str, t.List[facial_encoding]],
    unknown_encodings: t.List[facial_encoding],
    tolerance: float,
) -> t.List[t.List[Match]]:
    """
    Return possible matches for all encodings in image

    Args:
        known_people: dictionary mapping names to lists of encodings
        unknown_encodings: list of encodings from an image

    Returns:
        matches: list of lists of matches, one list for each unknown_encoding
    """
    match_lists = []
    for unknown_encoding in unknown_encodings:
        match_list = _match_face_with_known_people(
            known_people, unknown_encoding, tolerance
        )
        if match_list:
            match_lists.append(match_list)
    return match_lists


def _match_face_with_known_people(
    known_people: t.Dict[str, t.List[facial_encoding]],
    unknown_encoding: facial_encoding,
    tolerance: float,
) -> t.List[Match]:
    """
    Returns possible matches for a single unknown face encoding

    Args:
        known_people: dictionary mapping names to lists of encodings
        unknown_encoding: single encoding from an image

    Returns:
        matches: list of matches, one match for each known person more
        similar than tolerance
    """

    match_list = []
    for name, encodings in known_people.items():
        # Get most similar match for each person's encodings
        distance = min(face_recognition.face_distance(encodings, unknown_encoding))
        if distance < tolerance:
            match_list.append(Match(distance, name))
    return match_list


def _get_best_match_for_each_face(
    all_match_lists: t.List[t.List[Match]]
) -> t.List[str]:
    """
    Returns list of best matches for multiple facial encodings, given a list of possible
    matches

    Args:
        all_match_lists: list of lists of matches

    Returns
        best_matches: list of names, one name for each list of match_lists
    """
    all_match_lists = [sorted(match_list) for match_list in all_match_lists]

    best_matches = []
    while any(all_match_lists):
        all_match_lists.sort()
        matches_for_pic_with_best_match = all_match_lists.pop(0)
        best_match = matches_for_pic_with_best_match[0]
        best_matches.append(best_match.name)

        # filter out recognized person from remaining matches
        all_match_lists = [
            [match for match in matchlist if match.name != best_match.name]
            for matchlist in all_match_lists
        ]
    return best_matches


def recognize_face(img_data: bytes, settings: Settings) -> t.List[str]:
    loaded_img = face_recognition.load_image_file(BytesIO(img_data))
    unknown_encodings = face_recognition.face_encodings(loaded_img)

    known_people = deepcopy(settings.recognition_data)

    match_lists = _get_matches_for_encodings(
        known_people=known_people,
        unknown_encodings=unknown_encodings,
        tolerance=settings.recognition_tolerance,
    )

    if any(len(match_list) > 1 for match_list in match_lists):
        recognized_people = _get_best_match_for_each_face(match_lists)
    else:
        recognized_people = [match_list[0].name for match_list in match_lists]

    return recognized_people
