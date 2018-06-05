#! /usr/bin/env python3.6
# coding: utf-8
from kamera.logger import log

from io import BytesIO
from collections import namedtuple
from copy import deepcopy

from numpy import array as np_array
try:
    import face_recognition
except ImportError:
    face_recognition = None
    log.info("Unable to import face_recognition.")

from typing import List, Dict


from kamera import config

Match = namedtuple("Match", ["distance", "name"])


def _match_face_with_known_people(
        known_people: Dict[str, List[np_array]],
        unknown_encoding: np_array,
        tolerance: float
        ) -> List[Match]:
    """
    Returns possible matches for a single unknown face encoding

    Args:
        known_people: dictionary of mapping names to list of encodings
        unknown_encoding: single encoding from a picture

    Returns:
        matches: list of matches, one match for each known person more similar than tolerance
    """

    match_list = []
    for name, encodings in known_people.items():
        # Get most similar match for each person's encodings
        distance = min(face_recognition.face_distance(encodings, unknown_encoding))
        if distance < tolerance:
            match_list.append(Match(distance, name))
    match_list.sort()
    return match_list


def _get_best_match_for_each_face(all_facial_matches: List[List[Match]]) -> List[str]:
    """
    Returns list of best matches for multiple facial encodings, given a list of possible matches

    Args:
        all_facial_matches: list of list of matches

    Returns
        recognized_people: list of names, one name for each list of match_lists
    """
    recognized_people = []
    while any(all_facial_matches):
        all_facial_matches.sort()
        matches_for_pic_with_best_match = all_facial_matches.pop(0)
        best_match = matches_for_pic_with_best_match[0]
        recognized_people.append(best_match.name)

        # filter out recognized person from remaining matches
        all_facial_matches = [
            [match for match in matchlist if match.name != best_match.name]
            for matchlist in all_facial_matches
        ]
    return recognized_people


def recognize_face(
    img_data: bytes,
    settings: config.Settings
) -> List[str]:
    loaded_img = face_recognition.load_image_file(BytesIO(img_data))
    unknown_encodings = face_recognition.face_encodings(loaded_img)

    known_people = deepcopy(settings.recognition_data)

    all_facial_matches = []
    for unknown_encoding in unknown_encodings:
        match_list = _match_face_with_known_people(
            known_people,
            unknown_encoding,
            settings.recognition_tolerance
        )
        if match_list:
            all_facial_matches.append(match_list)

    if any(len(n_matches) > 1 for n_matches in all_facial_matches):
        recognized_people = _get_best_match_for_each_face(all_facial_matches)
    else:
        recognized_people = [
            match_list[0].name
            for match_list in all_facial_matches
        ]

    return recognized_people
