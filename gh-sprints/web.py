import httplib

from flask import Flask, request, Response
from flask import render_template
from flask.ext.login import login_required

from database import db_session
from models import Sprint, IssueSnapshot, SprintCommitment
from sprints import monitor_sprints
from authorization import setup_authorization

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


@app.route('/sprints/<sprint_id>', methods=['GET', 'PATCH'])
@login_required
def sprint(sprint_id):
    sprint = Sprint.query.filter(Sprint.id == sprint_id).first()
    if request.method == 'GET':
        snapshots = sprint.get_snapshots()
        states = _get_states_dict()

        stats = {
            'all': sprint.get_stats(),
            'committed': sprint.get_stats(committed=True)
        }

        # Get all of the issues captured in the latest snapshot
        issue_snapshots = IssueSnapshot.query.filter(IssueSnapshot.snapshot_id == sprint.last_snapshot.id)
        issues = sorted([(issue.data, issue.state, issue, issue.sprint_count) for issue in issue_snapshots], key=lambda x: x[1])
        committed_issues = [commitment.issue_id for commitment in sprint.commitments]

        context = {
            'sprint': sprint,
            'snapshots': snapshots,
            'states': states,
            'stats': stats,
            'issues': issues,
            'committed_issues': committed_issues
        }
        return render_template('sprint.html', **context)
    elif request.method == 'PATCH':
        for name, value in request.json.items():
            if hasattr(sprint, name):
                setattr(sprint, name, value)
            db_session.commit()
        return Response(''), httplib.NO_CONTENT


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


@app.route('/welcome', methods=['GET'])
def welcome():
    return render_template('welcome.html')


if __name__ == '__main__':
    setup_authorization(app)
    app.run(host='0.0.0.0', port=settings.LISTEN_PORT)
