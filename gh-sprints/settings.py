import re

# Your github API token for snapshotting sprint data
TOKEN = ''
# Your github organization name
ORG = ''
# The github repos owned by that organization which you want to monitor
REPOS = []

# Github App data to use for authorization
GITHUB_APP_ID = ''
GITHUB_APP_SECRET = ''
# The organization that a user must be a member of in order to login
REQUIRED_ORG = ''

JSON_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
TIMEZONE = 'Canada/Pacific'

# Database connection info (for storing issue snapshots)
DB_USER = ''
DB_PASS = ''
DB_HOST = ''
DB_NAME = ''
# An example for postgres
DATABASE_URI = 'postgresql+psycopg2://%s:%s@%s/%s' % (DB_USER, DB_PASS, DB_HOST, DB_NAME)

APP_DEBUG = True
# Bang on the keyboard for awhile to create a secret key
APP_SECRET_KEY = ''

# Describes the states a github issue can be in. If 'open' is True, must include the beginning of
# the github label that defines the state. 'label' is the string that will be used in the UI.
# There can only be one state where 'open' is False
#
# The setting below is an example
ISSUE_STATES = [
    {
        'label': 'Pickup',
        'github_label': ['1', '2'],
        'open': True,
        'id': 0,
        'color': '#EA6454'
    },
    {
        'label': 'Building',
        'github_label': ['3'],
        'open': True,
        'id': 1,
        'color': '#89ACEA'
    },
    {
        'label': 'Code Review',
        'github_label': ['4'],
        'open': True,
        'id': 2,
        'color': '#7CEAE8'
    },
    {
        'label': 'Ready to Deploy',
        'github_label': ['5'],
        'open': True,
        'id': 3,
        'color': '#92EAB4'
    },
    {
        'label': 'Closed',
        'open': False,
        'id': 4,
        'color': '#78EA76'
    }
]

# The id's of states that are considered "done"
COMPLETE_STATES = [3, 4]

# A regular expression to use for calculating the point count for an issue from its title
# In the example below, issue titles should look like "(SP3) Some issue" for a 3 point issue
POINT_PATTERN = re.compile("\(SP(\d+)\)")

# The port the flask dev server will listen on
LISTEN_PORT = 8080


try:
    from local_settings import *
except:
    pass
