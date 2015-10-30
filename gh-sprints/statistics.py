from __future__ import division
from __future__ import unicode_literals

from operator import attrgetter


class LabelStatistics(object):

    def __init__(self, name, collection):
        self.name = name
        self.issues = []
        self.total_story_points = 0
        self.collection = collection

    def add_issue(self, issue):
        self.issues.append(issue)
        self.total_story_points += issue.points

    @property
    def story_points_as_percentage(self):
        percentage = (self.total_story_points / self.collection.completed_story_points) * 100
        return int(round(percentage, 0))


class LabelStatisticsCollection(object):

    def __init__(self, completed_story_points=0):
        self.labels_by_name = {}
        self.completed_story_points = completed_story_points

    def add_issue(self, issue):
        for label in issue.labels:
            label_name = label['name']

            if label_name not in self.labels_by_name:
                self.labels_by_name[label_name] = LabelStatistics(label_name, self)

            self.labels_by_name[label_name].add_issue(issue)

    def sort_by_effort(self):
        labels = self.labels_by_name.values()
        sorted_labels = sorted(labels, key=attrgetter('total_story_points'))
        sorted_labels.reverse()
        return sorted_labels
