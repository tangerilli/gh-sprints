import sys
from requests.packages import urllib3


from models import IssueSnapshot, Sprint
from sprints import _auth_get_request, _get_next_page
import settings

urllib3.disable_warnings()


def _print_user_stats(stats):
    for username, snapshots in stats.items():
        print "{}:".format(username)
        for snapshot in snapshots:
            print "\t#{} - {}".format(snapshot.issue_id, snapshot.data['title'])
        print ""


def _process_events_for_issue(events_url):
    reviewer = None
    build_starter = None
    build_finisher = None
    while True:
        response = _auth_get_request(events_url)
        events = response.json()
        for event in events:
            actor_login = event['actor']['login']
            if event['event'] == 'labeled':
                event_label = event['label']['name']
                if 'Deploy' in event_label:
                    reviewer = actor_login
                if 'Testing' in event_label:
                    build_finisher = actor_login
                if 'Building' in event_label:
                    build_starter = actor_login
        events_url = _get_next_page(response)
        if not events_url:
            break
    return build_starter, build_finisher, reviewer


def main(args):
    # states_dict = {state['id']: state for state in settings.ISSUE_STATES}
    reviewed = {}
    built = {}

    # Get all the issues for a given time period (i.e. sprint)
    sprint_number = args[1]
    sprint = Sprint.query.filter(Sprint.name == 'Sprint {}'.format(sprint_number)).first()
    issue_snapshots = IssueSnapshot.query.filter(IssueSnapshot.snapshot_id == sprint.last_snapshot.id)

    for snapshot in issue_snapshots:
        build_starter, build_finisher, reviewer = _process_events_for_issue(snapshot.data['events_url'])
        # print "#{} - {}: Started by {}, finished by {}, reviewed by {}".format(
        #     snapshot.issue_id, states_dict[snapshot.state]['label'], build_starter, build_finisher, reviewer)
        if snapshot.state in settings.COMPLETE_STATES:
            if reviewer:
                reviewed.setdefault(reviewer, set()).add(snapshot)
            if build_finisher:
                built.setdefault(build_finisher, set()).add(snapshot)
            if build_starter:
                built.setdefault(build_starter, set()).add(snapshot)

    print "Reviewed"
    print "-----"
    _print_user_stats(reviewed)

    print "Built"
    print "-----"
    _print_user_stats(built)

if __name__ == '__main__':
    sys.exit(main(sys.argv))
