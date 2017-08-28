#! /usr/bin/env python3.6
# coding: utf-8
import os
import json
from io import BytesIO

try:
    import face_recognition
    import numpy as np
except ImportError:
    face_recognition = None
    print("Unable to import face_recognition.")

import config


def load_encodings():
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


def _match_face_with_known_people(known_people, unknown_encoding):
    matches = []
    for person in known_people:
        # Get most similar match for each person's encodings
        distance = min(face_recognition.face_distance(person.encodings, unknown_encoding))
        if distance < config.recognition_tolerance:
            matches.append((distance, person.name))
    matches.sort()
    return matches


def _get_best_facial_matches(all_facial_matches):
    recognized_people = []
    while any(all_facial_matches):
        all_facial_matches.sort()
        matches_for_pic_with_best_match = all_facial_matches.pop(0)
        lowest_distance, most_similar_person = matches_for_pic_with_best_match[0]
        recognized_people.append(most_similar_person)

        # filter out person from remaining matches
        all_facial_matches = [
            [(distance, person) for distance, person in array if person != most_similar_person]
            for array in all_facial_matches
        ]
    return recognized_people


def recognize_face(img_data):
    loaded_img = face_recognition.load_image_file(BytesIO(img_data))
    unknown_encodings = face_recognition.face_encodings(loaded_img)

    known_people = config.people[:]

    all_facial_matches = []
    for unknown_encoding in unknown_encodings:
        matches = _match_face_with_known_people(known_people, unknown_encoding)
        all_facial_matches.append(matches)

    if any(len(n_matches) > 1 for n_matches in all_facial_matches):
        recognized_people = _get_best_facial_matches(all_facial_matches)
    else:
        recognized_people = [
            person
            for match in all_facial_matches
            for distance, person in match
        ]

    return recognized_people
