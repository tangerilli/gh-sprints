#!/usr/bin/env python

import os
import sys
import argparse
import datetime
import re

import requests
from requests.auth import HTTPBasicAuth

import settings
from database import init_db, db_session
from models import Sprint, Snapshot, IssueSnapshot

POINT_PATTERN = re.compile("\(SP(\d+)\)")


def _auth_get_request(url):
    return requests.get(url, auth=HTTPBasicAuth(settings.TOKEN, 'x-oauth-basic'))


def _get_next_page(response):
    if 'link' in response.headers and 'rel="next"' in response.headers['link']:
        return response.headers['link'].split(';')[0].replace('<', '').replace('>', '')
    else:
        return None


def get_or_create_sprint(milestone):
    sprint_name = milestone['title']
    sprint = Sprint.query.filter(Sprint.name == sprint_name).first()
    if not sprint:
        due_on = datetime.datetime.strptime(milestone['due_on'], settings.JSON_DATETIME_FORMAT)
        sprint = Sprint(sprint_name, due_on, milestone)
        db_session.add(sprint)
        db_session.commit()
    return sprint


def save_issue_snapshot(issue, snapshot):
    print "Snapshotting %s" % issue['number']
    match = POINT_PATTERN.search(issue['title'])
    if match:
        points = int(match.groups(0)[0])
    else:
        points = 0

    state = IssueSnapshot.ISSUE_STATE_CLOSED
    if issue['state'] == 'open':
        for label in issue['labels']:
            if label['name'][0] in ['1', '2']:
                state = IssueSnapshot.ISSUE_STATE_PICKUP
            if label['name'][0] in ['3']:
                state = IssueSnapshot.ISSUE_STATE_BUILDING
            if label['name'][0] in ['4']:
                state = IssueSnapshot.ISSUE_STATE_CR
            if label['name'][0] in ['']:
                state = IssueSnapshot.ISSUE_STATE_DEPLOY

    # TODO: Only snapshot if something has changed (maybe there's an updated_on field)
    updated_at = datetime.datetime.strptime(issue['updated_at'], settings.JSON_DATETIME_FORMAT)
    previous_issue = IssueSnapshot.query.filter(
        IssueSnapshot.issue_id == issue['number']).order_by(
        IssueSnapshot.updated_at.desc()).first()
    is_updated = True
    if previous_issue:
        previously_updated = datetime.datetime.strptime(previous_issue.data['updated_at'], settings.JSON_DATETIME_FORMAT)
        if previously_updated == updated_at:
            is_updated = False

    issue_snapshot = IssueSnapshot(issue['number'], points, state, snapshot, issue)
    db_session.add(issue_snapshot)
    return is_updated


def snapshot_issues(repo, milestone):
    """
    Fetches all of the issues for the given sprint and stores them in a database
    """
    sprint = get_or_create_sprint(milestone)
    if sprint.locked is True:
        print "Skipping '{}', it's locked".format(sprint.name)
    snapshot = Snapshot(sprint)
    db_session.add(snapshot)

    url = 'https://api.github.com/repos/{}/{}/issues?state=all&milestone={}'.format(settings.ORG, repo, milestone['number'])
    have_updates = False
    while True:
        issues = _auth_get_request(url)
        for issue in issues.json():
            is_updated = save_issue_snapshot(issue, snapshot)
            have_updates = have_updates or is_updated

        next_page = _get_next_page(issues)
        if next_page:
            url = next_page
        else:
            break

    if have_updates:
        print "Have updates, committing snapshot"
        db_session.commit()
    else:
        print "No updates, reverting snapshot"
        db_session.rollback()


def get_recent_milestones(repo):
    url = 'https://api.github.com/repos/{}/{}/milestones?state=all'.format(settings.ORG, repo)
    recent_milestones = []
    while True:
        milestones = _auth_get_request(url)
        for milestone in milestones.json():
            if milestone.get('due_on', None) is None:
                continue
            due_on = datetime.datetime.strptime(milestone['due_on'], settings.JSON_DATETIME_FORMAT)
            diff = due_on - datetime.datetime.now()
            if abs(diff.days) <= 8:
                recent_milestones.append(milestone)

        next_page = _get_next_page(milestones)
        if next_page:
            url = next_page
        else:
            break
    return recent_milestones


def monitor_sprints():
    for repo in settings.REPOS:
        milestones = get_recent_milestones(repo)
        for milestone in milestones:
            snapshot_issues(repo, milestone)


def _sum_points(issues, state):
    return sum([issue.points for issue in issues if issue.state == state])


def print_stats(sprint_name=None):
    if sprint_name:
        sprints = Sprint.query.filter(Sprint.name == sprint_name)
    else:
        sprints = Sprint.query.all()
    for sprint in sprints:
        print sprint.name
        snapshot = Snapshot.get_most_recent_for_sprint(sprint)
        if snapshot is None:
            print "  No stats exist"
        else:
            issues = snapshot.issues
            pickup = _sum_points(issues, IssueSnapshot.ISSUE_STATE_PICKUP)
            building = _sum_points(issues, IssueSnapshot.ISSUE_STATE_BUILDING)
            cr = _sum_points(issues, IssueSnapshot.ISSUE_STATE_CR)
            deploy = _sum_points(issues, IssueSnapshot.ISSUE_STATE_DEPLOY)
            closed = _sum_points(issues, IssueSnapshot.ISSUE_STATE_CLOSED)
            print "  Pickup: {}".format(pickup)
            print "  Building: {}".format(building)
            print "  CR: {}".format(cr)
            print "  Deploy: {}".format(deploy)
            print "  Completed: {}".format(closed)


def lock_sprint(sprint_name, lock):
    sprint = Sprint.query.filter(Sprint.name == sprint_name).first()
    if not sprint:
        print "Could not find sprint '{}'".format(sprint_name)
        return 1
    sprint.locked = lock
    db_session.commit()
    return 0


def print_sprints():
    for sprint in Sprint.query.order_by(Sprint.name).all():
        locked = "(locked)" if sprint.locked else ""
        print "{}\t\t{}".format(sprint.name, locked)


def main(args):
    parser = argparse.ArgumentParser(description='7Geese Sprint Management Tool')
    parser.add_argument('command', type=str, help="The command to run",
                        choices=['init', 'snapshot', 'stats', 'lock', 'unlock', 'sprints'])
    parser.add_argument('-s', '--sprint', type=str, help="The sprint to operate on")
    args = parser.parse_args()

    if args.command == 'init':
        init_db()
        return 0

    if args.command == 'snapshot':
        if settings.TOKEN is None:
            settings.TOKEN = os.environ.get('GITHUB_TOKEN', None)
        if settings.TOKEN is None:
            print "You need to have the GITHUB_TOKEN environment variable set."
            print "You can generate a new 'Personal access token' at https://github.com/settings/applications"
            return 2

        monitor_sprints()
        return 0

    if args.command == 'sprints':
        print_sprints()
        return 0

    if args.command == 'lock' or args.command == 'unlock':
        if not args.sprint:
            print "Sprint argument is required"
            return 1
        return lock_sprint(args.sprint, args.command == 'lock')

    if args.command == 'stats':
        print_stats(args.sprint)
        return 0

    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))