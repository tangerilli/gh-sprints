from flask import Flask, request, Response
from flask import render_template

from database import db_session
from models import Sprint, IssueSnapshot, SprintCommitment
import settings


app = Flask(__name__)
app.debug = settings.APP_DEBUG
app.secret_key = settings.APP_SECRET_KEY


@app.route('/', methods=['GET'])
def sprints():
    sprints = []
    for sprint in Sprint.query.order_by(Sprint.finished):
        snapshot = sprint.last_snapshot
        if snapshot is None:
            continue
        total = snapshot.total_points
        completed = snapshot.completed_points
        sprints.append({
            'model': sprint,
            'total': total,
            'completed': completed,
            'completion': int((completed / float(total)) * 100)
        })
    return render_template('sprints.html', sprints=sprints)


@app.route('/sprints/<sprint_id>', methods=['GET', 'PATCH'])
def sprint(sprint_id):
    sprint = Sprint.query.filter(Sprint.id == sprint_id).first()
    if request.method == 'GET':
        snapshots = sprint.get_snapshots()
        states = {state['id']: state for state in settings.ISSUE_STATES}
        completed = [snapshot.completed_points for snapshot in snapshots]
        remaining = [snapshot.remaining_points for snapshot in snapshots]
        dates = [snapshot.timestamp.strftime('%d/%m') for snapshot in snapshots]

        # Get all of the issues captured in the latest snapshot
        current_snapshot = snapshots[-1]
        issue_snapshots = IssueSnapshot.query.filter(IssueSnapshot.snapshot_id == current_snapshot.id)
        issues = sorted([(issue.data, issue.state) for issue in issue_snapshots], key=lambda x: x[1])

        committed_issues = [commitment.issue_id for commitment in sprint.commitments]

        context = {
            'sprint': sprint,
            'snapshots': snapshots,
            'states': states,
            'dates': dates,
            'completed': completed,
            'remaining': remaining,
            'completion': int((float(completed[-1]) / (completed[-1]+remaining[-1])) * 100),
            'issues': issues,
            'committed_issues': committed_issues
        }
        return render_template('sprint.html', **context)
    elif request.method == 'PATCH':
        for name, value in request.json.items():
            setattr(sprint, name, value)
            db_session.commit()
        r = Response('')
        r.status_code = 204
        return r


@app.route('/sprints/<sprint_id>/commitments', methods=['POST'])
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

    r = Response('')
    r.status_code = 204
    return r

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
