from flask import Flask, request, Response
from flask import render_template

from database import db_session
from models import Sprint, IssueSnapshot, SprintCommitment
from sprints import monitor_sprints
import settings


app = Flask(__name__)
app.debug = settings.APP_DEBUG
app.secret_key = settings.APP_SECRET_KEY


@app.template_filter('foreground_color')
def foreground_color(colorHEX):
    if ( int(colorHEX[:2],16)*0.299 +
         int(colorHEX[2:4],16)*0.587 +
         int(colorHEX[4:6],16)*0.114 ) > 186:
        return '#000000'
    else:
        return '#FFFFFF'


def _empty_response():
    r = Response('')
    r.status_code = 204
    return r


# Clean up the database sessions after a request
@app.teardown_request
def shutdown_session(exception=None):
    db_session.remove()


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

        all_completed = [snapshot.completed_points for snapshot in snapshots]
        all_remaining = [snapshot.remaining_points for snapshot in snapshots]
        all_totals = [snapshot.total_points for snapshot in snapshots]
        all_stats = {
            'completed': all_completed,
            'remaining': all_remaining,
            'total': all_totals,
            'dates': [snapshot.timestamp.strftime('%d/%m') for snapshot in snapshots],
        }
        if all_totals[-1]:
            all_stats['completion'] = int((float(all_completed[-1]) / (all_totals[-1])) * 100)

        committed_completed = [snapshot.completed_points_committed for snapshot in snapshots]
        committed_remaining = [snapshot.remaining_points_committed for snapshot in snapshots]
        committed_totals = [snapshot.total_points_committed for snapshot in snapshots]
        committed_stats = {
            'completed': committed_completed,
            'remaining': committed_remaining,
            'total': committed_totals,
            'dates': [snapshot.timestamp.strftime('%d/%m') for snapshot in snapshots],
        }
        if committed_totals[-1]:
            committed_stats['completion'] = int((float(committed_completed[-1]) / (committed_totals[-1])) * 100)

        stats = {
            'all': all_stats,
            'committed': committed_stats
        }

        # Get all of the issues captured in the latest snapshot
        current_snapshot = snapshots[-1]
        issue_snapshots = IssueSnapshot.query.filter(IssueSnapshot.snapshot_id == current_snapshot.id)
        issues = sorted([(issue.data, issue.state) for issue in issue_snapshots], key=lambda x: x[1])
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
            setattr(sprint, name, value)
            db_session.commit()
        return _empty_response()


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

    return _empty_response()


@app.route('/snapshot', methods=['POST'])
def do_snapshot():
    monitor_sprints()
    return _empty_response()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
