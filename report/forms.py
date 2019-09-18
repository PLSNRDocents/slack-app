# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

import json

TRAIL_REPORT = """
[
	{
		"type": "section",
		"text": {
			"type": "mrkdwn",
			"text": "Where did this happen?"
		},
		"accessory": {
			"type": "static_select",
			"placeholder": {
				"type": "plain_text",
				"text": "Select a location",
				"emoji": true
			},
			"options": [
				{
					"text": {
						"type": "plain_text",
						"text": "Granite Point",
						"emoji": true
					},
					"value": "gpoint"
				},
				{
					"text": {
						"type": "plain_text",
						"text": "Whaler's Cove",
						"emoji": true
					},
					"value": "wcove"
				},
				{
					"text": {
						"type": "plain_text",
						"text": "North Shore",
						"emoji": true
					},
					"value": "nshore"
				},
				{
					"text": {
						"type": "plain_text",
						"text": "Cypress Grove",
						"emoji": true
					},
					"value": "cgrove"
				},
				{
					"text": {
						"type": "plain_text",
						"text": "Sea Lion",
						"emoji": true
					},
					"value": "slion"
				},
				{
					"text": {
						"type": "plain_text",
						"text": "South Shore",
						"emoji": true
					},
					"value": "sshore"
				},
				{
					"text": {
						"type": "plain_text",
						"text": "Bird Island",
						"emoji": true
					},
					"value": "bisland"
				},
				{
					"text": {
						"type": "plain_text",
						"text": "South Plateau",
						"emoji": true
					},
					"value": "splateau"
				},
				{
					"text": {
						"type": "plain_text",
						"text": "Piney Woods",
						"emoji": true
					},
					"value": "pwoods"
				}
			]
		}
	},
	{
		"type": "section",
		"text": {
			"type": "mrkdwn",
			"text": "Ready?"
		},
		"accessory": {
			"type": "button",
			"text": {
				"type": "plain_text",
				"text": "Submit",
				"emoji": true
			},
			"value": "submit"
		}
	}
]"""


def get_trail_report():
    return json.loads(TRAIL_REPORT)
