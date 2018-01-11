#! /usr/bin/env python3.6
# coding: utf-8
import os
import json
from io import BytesIO
from collections import namedtuple

from typing import List

try:
    import face_recognition
    import numpy as np
except ImportError:
    face_recognition = None
    print("Unable to import face_recognition.")

import config

Match = namedtuple("Match", ["distance", "name"])


def load_encodings():
    """
    Opens pictures saved in /faces, encodes face in picture, adds encodings to person-tuple
    """
    if face_recognition is None:
        return

    for person in config.people:
        path = os.path.join(config.home, "faces", person.name)
        imgs = os.listdir(path)
        for img in imgs:
            img_path = os.path.join(path, img)
            root, ext = os.path.splitext(img_path)
            json_path = root + ".json"
            if os.path.exists(json_path):
                with open(json_path) as j:
                    encoding = np.array(json.load(j))
            else:
                data = face_recognition.load_image_file(img_path)
                encodings = face_recognition.face_encodings(data)
                if len(encodings) == 0:
                    print(f"Warning: No encodings found: {img}")
                    continue
                elif len(encodings) > 1:
                    raise Exception(f"Multiple encodings found: {img}")
                encoding = encodings[0]
                with open(json_path, "w") as j:
                    json.dump(encoding.tolist(), j)
            person.encodings.append(encoding)


def _match_face_with_known_people(
        known_people: List[config.Person],
        unknown_encoding: np.array
        ) -> List[Match]:
    """
    Returns possible matches for a single unknown face encoding

    Args:
        known_people: list of config.Person namedtuples, with fields `name` and `encodings`
        unknown_encoding: single encoding from a picture

    Returns:
        matches: list of matches, one match for each known person more similar than tolerance
    """

    match_list = []
    for person in known_people:
        # Get most similar match for each person's encodings
        distance = min(face_recognition.face_distance(person.encodings, unknown_encoding))
        if distance < config.recognition_tolerance:
            match_list.append(Match(distance, person.name))
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


def recognize_face(img_data: bytes) -> List[str]:
    loaded_img = face_recognition.load_image_file(BytesIO(img_data))
    unknown_encodings = face_recognition.face_encodings(loaded_img)

    known_people = config.people[:]

    all_facial_matches = []
    for unknown_encoding in unknown_encodings:
        match_list = _match_face_with_known_people(known_people, unknown_encoding)
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
