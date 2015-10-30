import httplib

from flask import Flask, request, Response
from flask import render_template
from flask.ext.login import login_required

from database import db_session
from models import Sprint, IssueSnapshot, SprintCommitment, Snapshot, get_stats_for_snapshots
from sprints import monitor_sprints
from authorization import setup_authorization
from statistics import LabelStatisticsCollection
import settings


app = Flask(__name__)
app.debug = settings.APP_DEBUG
app.secret_key = settings.APP_SECRET_KEY


def _get_states_dict():
    return {state['id']: state for state in settings.ISSUE_STATES}


@app.template_filter('foreground_color')
def foreground_color(colorHEX):
    if (int(colorHEX[:2], 16)*0.299 +
        int(colorHEX[2:4], 16)*0.587 +
            int(colorHEX[4:6], 16)*0.114) > 186:
        return '#000000'
    else:
        return '#FFFFFF'


# Clean up the database sessions after a request
@app.teardown_request
def shutdown_session(exception=None):
    db_session.remove()


@app.route('/', methods=['GET'])
@login_required
def sprints():
    sprints = []
    for sprint in Sprint.query.order_by(Sprint.finished.desc()):
        snapshot = sprint.last_snapshot
        if snapshot is None:
            continue
        total = snapshot.total_points()
        completed = snapshot.completed_points()
        sprints.append({
            'model': sprint,
            'total': total,
            'completed': completed,
            'completion': int((completed / float(total)) * 100)
        })
    return render_template('sprints.html', sprints=sprints)


@app.route('/sprints/<sprint_ids>', methods=['GET', 'PATCH'])
@login_required
def sprint(sprint_ids):
    ids = sprint_ids.split(',')
    if request.method == 'GET':
        sprints = []
        snapshots = []
        last_snapshots = []
        issues = []
        committed_issues = []
        states = _get_states_dict()
        for sprint_id in ids:
            sprint = Sprint.query.filter(Sprint.id == sprint_id).first()
            sprints.append(sprint)
            sprint_snapshots = sprint.get_snapshots()
            snapshots.extend(sprint_snapshots)
            last_snapshots.append(sprint_snapshots[-1])

            # Get all of the issues captured in the latest snapshot
            issue_snapshots = IssueSnapshot.query.filter(IssueSnapshot.snapshot_id == sprint.last_snapshot.id)
            issues.extend([(issue.data, issue.state, issue, issue.sprint_count) for issue in issue_snapshots])
            committed_issues.extend([commitment.issue_id for commitment in sprint.commitments])

        stats_for_all_issues = get_stats_for_snapshots(snapshots)
        completed_story_points = stats_for_all_issues['completed'][-1]
        stats = {
            'all': stats_for_all_issues,
            'committed': get_stats_for_snapshots(snapshots, committed=True),
            'label_stats': _get_label_statistics(sprints, completed_story_points),
        }

        snapshot_ids = [snapshot.id for snapshot in last_snapshots]
        issue_state_stats = {
            'all': {state: Snapshot.get_points_for_states(snapshot_ids, ids, [state]) for state in states.keys()},
            'committed': {state: Snapshot.get_points_for_states(snapshot_ids, ids, [state], True) for state in states.keys()}
        }

        context = {
            'sprints': sprints,
            'snapshots': snapshots,
            'states': states,
            'stats': stats,
            'issue_state_stats': issue_state_stats,
            'issues': sorted(issues, key=lambda x: x[1]),
            'committed_issues': committed_issues
        }
        return render_template('sprint.html', **context)
    elif request.method == 'PATCH':
        if len(ids) > 1:
            return Response('Can only update one sprint at a time'), httplib.BAD_REQUEST
        sprint = Sprint.query.filter(Sprint.id == ids[0]).first()
        for name, value in request.json.items():
            if hasattr(sprint, name):
                setattr(sprint, name, value)
            db_session.commit()
        return Response(''), httplib.NO_CONTENT


def _get_label_statistics(sprints, completed_story_points):
    """
    :type sprints list
    :rtype {string: LabelStatistics}
    """
    label_statistics = LabelStatisticsCollection(completed_story_points)

    for curr_sprint in sprints:
        issues = curr_sprint.last_snapshot.get_completed_issues()
        for curr_issue in issues:
            label_statistics.add_issue(curr_issue)

    return label_statistics


@app.route('/sprints/<sprint_id>/commitments', methods=['POST'])
@login_required
def edit_committments(sprint_id):
    for commitment in request.json:
        issue_id = commitment['issue_id']
        if commitment['committed']:
            commitment_model = SprintCommitment(sprint_id, issue_id)
            db_session.add(commitment_model)
        else:
            SprintCommitment.query.filter(
                SprintCommitment.sprint_id == sprint_id, SprintCommitment.issue_id == issue_id).delete()
    db_session.commit()

    return Response(''), httplib.NO_CONTENT


@app.route('/snapshot', methods=['POST'])
def do_snapshot():
    monitor_sprints()
    return Response(''), httplib.NO_CONTENT


@app.route('/issues/<repo>/<issue_id>', methods=['GET'])
@login_required
def issue(repo, issue_id):
    states = _get_states_dict()

    snapshots = IssueSnapshot.get_all_snapshots_for_issue(repo, issue_id)
    sprints = {}
    for issue_snapshot in snapshots:
        sprint = sprints.setdefault(issue_snapshot.snapshot.sprint_id, {
            'min': issue_snapshot.points,
            'max': issue_snapshot.points,
            'sprint_data': issue_snapshot.snapshot.sprint,
            'states': [],
        })
        sprint['min'] = min(sprint['min'], issue_snapshot.points)
        sprint['max'] = max(sprint['max'], issue_snapshot.points)
        state_label = states[issue_snapshot.state]['label']
        if state_label not in sprint['states']:
            sprint['states'].append(state_label)

    context = {
        'sprints': sorted(sprints.values(), key=lambda sprint: sprint['sprint_data'].finished),
        'issue': snapshots[-1]
    }
    return render_template('issue.html', **context)


@app.route('/stats/<sprint_ids>', methods=['GET'])
@app.route('/stats/', methods=['GET'])
@login_required
def stats(sprint_ids=''):
    ids = sprint_ids.split(',')
    issue_ids = set()
    if sprint_ids:
        for sprint_id in ids:
            # todo: this is pretty brute force right now, should be able to
            # write a smarter query to get all the issues associated with a sprint
            sprint = Sprint.query.filter(Sprint.id == sprint_id).first()
            for snapshot in sprint.snapshots:
                for issue in snapshot.issues:
                    issue_ids.add((issue.issue_id, issue.repo))
    else:
        issue_ids = IssueSnapshot.query.distinct(IssueSnapshot.issue_id).values(IssueSnapshot.issue_id, IssueSnapshot.repo)

    times = {}
    for issue_id, repo in issue_ids:
        elapsed = IssueSnapshot.get_time_in_states(repo, issue_id, settings.BUILD_STATES, settings.COMPLETE_STATES)
        max_points = IssueSnapshot.get_max_points(repo, issue_id)
        if elapsed:
            times.setdefault(max_points, []).append(elapsed.total_seconds() / 60.0)

    context = {
        'times': times,
        'included_issues': sum([len(t) for t in times.values()])
    }
    return render_template('stats.html', **context)


@app.route('/welcome', methods=['GET'])
def welcome():
    return render_template('welcome.html')


if __name__ == '__main__':
    setup_authorization(app)
    app.run(host='0.0.0.0', port=settings.LISTEN_PORT)
