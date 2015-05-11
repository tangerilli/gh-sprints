import random

import requests

from flask import redirect, url_for, session, request, render_template
from flask.ext.login import LoginManager, login_user
from flask.ext.login import logout_user

from models import User
from database import db_session
import settings


login_manager = LoginManager()


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


@login_manager.user_loader
def load_user(user_id):
    return User.query.filter(User.id == user_id).filter(User.active == True).first()


def login():
    login_url_template = 'https://github.com/login/oauth/authorize?client_id={}&redirect_uri={}&scope={}&state={}'
    authorize_url = url_for('authorize', _external=True)
    scopes = 'read:org'
    state = random.randint(1, 999999999)
    session['oauth_state'] = state
    login_url = login_url_template.format(settings.GITHUB_APP_ID, authorize_url, scopes, state)
    return redirect(login_url)
login_manager.login_view = 'login'


def authorize():
    state = request.args['state']
    if state != str(session['oauth_state']):
        return render_template('login.html', error='Invalid state')
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
        return render_template('login.html', error='Organization requirement not met')
    user_info = _get_user_info(token)
    username = user_info['login']

    user = User.query.filter(User.username == username).first()
    if user is None:
        user = User(username, token)
        db_session.add(user)
        db_session.commit()

    if not login_user(user, remember=True):
        return render_template('login.html', error='Unknown login error')

    return redirect(url_for('sprints'))


def logout():
    logout_user()
    return redirect(url_for('welcome'))


def setup_authorization_routes(app):
    app.add_url_rule('/login', 'login', login, methods=['GET'])
    app.add_url_rule('/login/authorize', 'authorize', authorize, methods=['GET'])
    app.add_url_rule('/logout', 'logout', logout, methods=['GET'])


def setup_authorization(app):
    random.seed()
    login_manager.init_app(app)
    setup_authorization_routes(app)
