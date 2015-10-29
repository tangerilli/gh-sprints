class LabelStatistics(object):
    """
    Statistics for a given label
    """

    def __init__(self):
        self.issues = []

    @property
    def total_story_points(self):
        points = 0
        for issue in self.issues:
            points += issue.points

        return points

    def add_issue(self, issue):
        self.issues.append(issue)


