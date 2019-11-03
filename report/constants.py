# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

LOG_FORMAT = "%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s"
DATE_FMT = "%m/%d/%Y %H:%M:%S"

STATUS_PLACEHOLDER = "placeholder"
STATUS_REPORTED = "reported"
STATUS_CONFIRMED = "confirmed"
STATUS_CLOSED = "closed"
TYPE_TRAIL = "trail"
TYPE_DISTURBANCE = "disturbance"

TRAIL_VALUE_2_DESC = {
    "tll": "Lace Lichen",
    "tcm": "Carmelo Meadow",
    "tmc": "Moss Cove",
    "tgp": "Granite Point",
    "lwc": "Whaler's Cove",
    "tct": "Cabin Trail",
    "tns": "North Shore",
    "twk": "Whaler's Knoll",
    "tcg": "Cypress Grove",
    "tslp": "Sea Lion Pt",
    "tss": "South Shore",
    "lwb": "Weston Beach",
    "tbi": "Bird Island",
    "lgb": "Gibson Beach",
    "tsp": "South Plateau",
    "tpr": "Pine Ridge",
    "lpw": "Piney Woods",
    "tmm": "Mound Meadow",
    "lUnk": "Unknown",
}

# This is a comprehensive list for ALL report types
ISSUES_2_DESC = {
    "po": "Poison Oak",
    "sign": "Sign Missing/Broken",
    "cable": "Broken Cable",
    "tree": "Tree/obstruction",
    "step": "Broken Steps",
    "ot": "Other",
    "pin": "Pinnipeds",
    "ott": "Otters",
    "bird": "Birds",
    "off": "Off designated trails outside of the wire guides",
    "jump": "Jumping off rocks into or swimming in the ocean",
    "climb": "Climbing trees or off trail rocks or cliffs",
    "eat": "Picnicking in areas other than the designated areas",
    "pet": "Pets within the park (other than identified service animals)",
    "bike": "Biking off the paved road",
    "tide": "Collecting or disturbing tide pool marine life",
    "take": "Collecting and removing natural objects",
    "evil": "Vandalizing natural or manmade features (graffiti)",
    "drone": "Drones, any use regardless of disturbance",
    "air": "Airplane flying low",
    "fish": "Fishing boat with deployed lines, nets or poles within the Reserve",
    "Unk": "Unknown",
    "trash": "Trash",
}


def xlate_issues(issues):
    # translate comma separated issue names to descriptions
    return ", ".join([ISSUES_2_DESC[i] for i in issues.split(",")])
