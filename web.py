from flask import Flask
from flask import render_template

from database import db_session
from models import Sprint, IssueSnapshot
import settings


app = Flask(__name__)
app.debug = settings.APP_DEBUG
app.secret_key = settings.APP_SECRET_KEY


@app.route('/', methods=['GET'])
def sprints():
    sprints = []
    for sprint in Sprint.query.order_by(Sprint.finished):
        snapshot = sprint.last_snapshot
        total = snapshot.total_points
        completed = snapshot.completed_points
        sprints.append({
            'model': sprint,
            'total': total,
            'completed': completed,
            'completion': int((completed / float(total)) * 100)
        })
    return render_template('sprints.html', sprints=sprints)


@app.route('/sprints/<sprint_id>', methods=['GET'])
def sprint(sprint_id):
    sprint = Sprint.query.filter(Sprint.id == sprint_id).first()
    snapshots = sprint.get_snapshots()
    states = {state['id']: state for state in settings.ISSUE_STATES}
    completed = [snapshot.completed_points for snapshot in snapshots]
    remaining = [snapshot.remaining_points for snapshot in snapshots]
    dates = [snapshot.timestamp.strftime('%d/%m') for snapshot in snapshots]
    context = {
        'sprint': sprint,
        'snapshots': snapshots,
        'states': states,
        'dates': dates,
        'completed': completed,
        'remaining': remaining,
        'completion': int((float(completed[-1]) / (completed[-1]+remaining[-1])) * 100)
    }
    return render_template('sprint.html', **context)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
