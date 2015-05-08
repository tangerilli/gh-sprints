import random

from flask import Flask, request, Response, session
from flask import render_template, redirect, url_for

from flask.ext.login import LoginManager, login_user
from flask.ext.login import login_required, logout_user

import requests

from database import db_session
from models import Sprint, IssueSnapshot, SprintCommitment, User
from sprints import monitor_sprints
import settings

HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 403

app = Flask(__name__)
app.debug = settings.APP_DEBUG
app.secret_key = settings.APP_SECRET_KEY
random.seed()


def make_response(self, *args, **kwargs):
    status_code = None
    if 'status_code' in kwargs:
        status_code = kwargs.pop('status_code')
    r = Response(*args, **kwargs)
    if status_code:
        r.status_code = status_code
    return r


@app.template_filter('foreground_color')
def foreground_color(colorHEX):
    if (int(colorHEX[:2], 16)*0.299 +
        int(colorHEX[2:4], 16)*0.587 +
            int(colorHEX[4:6], 16)*0.114) > 186:
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
@login_required
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
@login_required
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
            setattr(sprint, name, value)
            db_session.commit()
        return _empty_response()


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

    return _empty_response()


@app.route('/snapshot', methods=['POST'])
def do_snapshot():
    monitor_sprints()
    return _empty_response()


@app.route('/issues/<repo>/<issue_id>', methods=['GET'])
@login_required
def issue(repo, issue_id):
    states = {state['id']: state for state in settings.ISSUE_STATES}

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


login_manager = LoginManager()


@login_manager.user_loader
def load_user(user_id):
    return User.query.filter(User.id == user_id).filter(User.active == True).first()


@app.route('/login', methods=['GET'])
def login():
    login_url_template = 'https://github.com/login/oauth/authorize?client_id={}&redirect_uri={}&scope={}&state={}'
    authorize_url = url_for('authorize', _external=True)
    scopes = 'read:org'
    state = random.randint(1, 999999999)
    session['oauth_state'] = state
    login_url = login_url_template.format(settings.GITHUB_APP_ID, authorize_url, scopes, state)
    return redirect(login_url)
login_manager.login_view = 'login'


def _get_github_headers(token):
    return {'authorization': 'token {}'.format(token)}


def _get_user_info(token):
    user_url = 'https://api.github.com/user'
    headers = _get_github_headers(token)
    r = requests.get(user_url, headers=headers)
    r.raise_for_status()
    return r.json()


def _get_orgs(token):
    org_url = 'https://api.github.com/user/orgs'
    headers = _get_github_headers(token)
    r = requests.get(org_url, headers=headers)
    r.raise_for_status()
    return r.json()


@app.route('/login/authorize', methods=['GET'])
def authorize():
    state = request.args['state']
    if state != str(session['oauth_state']):
        print state
        print session['oauth_state']
        return make_response('Bad state', status_code=HTTP_BAD_REQUEST)
    code = request.args['code']
    token_url = 'https://github.com/login/oauth/access_token'
    params = {
        'client_id': settings.GITHUB_APP_ID,
        'client_secret': settings.GITHUB_APP_SECRET,
        'code': code
    }
    headers = {'accept': 'application/json'}
    r = requests.post(token_url, params=params, headers=headers)
    r.raise_for_status()
    token = r.json()['access_token']
    orgs = _get_orgs(token)
    if settings.REQUIRED_ORG not in [org['login'] for org in orgs]:
        return make_response("Organization requirement not met", status_code=HTTP_UNAUTHORIZED)
    user_info = _get_user_info(token)
    username = user_info['login']

    user = User.query.filter(User.username == username).first()
    if user is None:
        user = User(username, token)
        db_session.add(user)
        db_session.commit()

    if not login_user(user, remember=True):
        return make_response('Login error', status_code=HTTP_UNAUTHORIZED)

    return redirect(url_for('sprints'))


@app.route('/logout', methods=['GET'])
def logout():
    logout_user()
    return render_template('logout.html')


login_manager.init_app(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
