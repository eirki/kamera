#! /usr/bin/env python3.6
# coding: utf-8

import typing as t
from copy import deepcopy
from io import BytesIO

import face_recognition
import numpy

from kamera import config


class Match(t.NamedTuple):
    distance: numpy.float64
    name: str


def _match_face_with_known_people(
    known_people: t.Dict[str, t.List[numpy.array]],
    unknown_encoding: numpy.array,
    tolerance: float,
) -> t.List[Match]:
    """
    Returns possible matches for a single unknown face encoding

    Args:
        known_people: dictionary of mapping names to list of encodings
        unknown_encoding: single encoding from a picture

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
    match_list.sort()
    return match_list


def _get_best_match_for_each_face(
    all_facial_matches: t.List[t.List[Match]]
) -> t.List[str]:
    """
    Returns list of best matches for multiple facial encodings, given a list of possible
    matches

    Args:
        all_facial_matches: list of list of matches

    Returns
        best_matches: list of names, one name for each list of match_lists
    """
    best_matches = []
    while any(all_facial_matches):
        all_facial_matches.sort()
        matches_for_pic_with_best_match = all_facial_matches.pop(0)
        best_match = matches_for_pic_with_best_match[0]
        best_matches.append(best_match.name)

        # filter out recognized person from remaining matches
        all_facial_matches = [
            [match for match in matchlist if match.name != best_match.name]
            for matchlist in all_facial_matches
        ]
    return best_matches


def recognize_face(img_data: bytes, settings: config.Settings) -> t.List[str]:
    loaded_img = face_recognition.load_image_file(BytesIO(img_data))
    unknown_encodings = face_recognition.face_encodings(loaded_img)

    known_people = deepcopy(settings.recognition_data)

    all_facial_matches = []
    for unknown_encoding in unknown_encodings:
        match_list = _match_face_with_known_people(
            known_people, unknown_encoding, settings.recognition_tolerance
        )
        if match_list:
            all_facial_matches.append(match_list)

    if any(len(n_matches) > 1 for n_matches in all_facial_matches):
        recognized_people = _get_best_match_for_each_face(all_facial_matches)
    else:
        recognized_people = [match_list[0].name for match_list in all_facial_matches]

    return recognized_people
