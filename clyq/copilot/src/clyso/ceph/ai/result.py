import json

from clyso.ceph.ai.helpers import *

class AIResult:
    def __init__(self):
        self.data = {
            "summary": {
                "score": float(),
                "grade": "",
            },
            "sections": [],
        }
        self.force_fail = False
        self.update_scores()

    def add_section(self, id):
        for s in self.data['sections']:
            assert id != s['id'], f"Attempt to create section {id} twice!"
        s = {
            "id": id,
            "score": 0.0,
            "max_score": 0,
            "summary": "",
            "info": [],
            "checks": [],
        }
        self.data['sections'].append(s)
        self.update_scores()

    def add_info_result(self, section: str, id: str, summary: str, detail: list):
        # find this section
        index = 0
        for s in self.data['sections']:
            if s['id'] == section: break
            index += 1

        assert index < len(self.data['sections']), f'Could not find section {section}'
        assert self.data['sections'][index]['id'] == section, f"Error finding section {section} at index {index}"

        i = {
            "id": id,
            "summary": summary,
            "detail": detail,
        }
        self.data['sections'][index]['info'].append(i)

    def add_check_result(self, section: str, id: str, result: str, summary: str, detail: list, recommend: list):
        assert result in ['UNKNOWN', 'PASS', 'WARN', 'FAIL'], "Check result must be 'UNKNOWN', 'PASS', 'WARN', or 'FAIL'"

        # find this section
        index = 0
        for s in self.data['sections']:
            if s['id'] == section: break
            index += 1

        assert index < len(self.data['sections']), f'Could not find section {section}'
        assert self.data['sections'][index]['id'] == section, f"Error finding section {section} at index {index}"

        c = {
            "id": id,
            "result": result,
            "summary": summary,
            "detail": detail,
            "recommend": recommend
        }
        self.data['sections'][index]['checks'].append(c)
        self.update_scores()

    def dump(self):
        return json.dumps(self.data)

    # TODO: this is a simple scoring method that gives at most 1 point per check.
    #       In future we may want to give higher or lower scores per check depending on importance.
    def update_scores(self):
        score_map = {'PASS': 1.0, 'WARN': 0.5, 'FAIL': 0.0}

        # update score for each section
        for s in range(len(self.data['sections'])):
            checks = self.data['sections'][s]['checks']
            max_score = len(checks)
            self.data['sections'][s]['max_score'] = max_score
            score = sum(score_map[c['result']] for c in checks)
            self.data['sections'][s]['score'] = score
            try:
                self.data['sections'][s]['grade'] = map_score_to_grade(score/max_score)
            except ZeroDivisionError:
                self.data['sections'][s]['grade'] = '-'

        # update overall summary
        sections = self.data['sections']
        max_score = sum(s['max_score'] for s in sections)
        score = sum(s['score'] for s in sections)
        self.data['summary']['score'] = score
        self.data['summary']['max_score'] = max_score
        if self.force_fail:
            self.data['summary']['grade'] = 'F'
        else:
            try:
                self.data['summary']['grade'] = map_score_to_grade(score/max_score)
            except ZeroDivisionError:
                self.data['summary']['grade'] = '-'
