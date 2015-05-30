from datetime import datetime
import itertools

import pytz
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, distinct
from sqlalchemy.orm import relationship, joinedload
from sqlalchemy.dialects import postgresql
from sqlalchemy import func

from database import Base
import settings


def _find_sprint_snapshot(sprint_id, groups):
    for group in groups:
        for snapshot in group:
            if snapshot.sprint_id == sprint_id:
                return snapshot
    return None


def get_stats_for_snapshots(snapshots, committed=False):
    # First group the snapshots by date
    snapshots = sorted(snapshots, key=lambda snapshot: snapshot.timestamp)
    grouped_snapshots = [list(group) for k, group in itertools.groupby(
        snapshots, key=lambda snapshot: snapshot.local_timestamp.date())]

    # figure out which sprints should be in each group
    expected_sprints = set()
    for group in grouped_snapshots:
        expected_sprints.update([snapshot.sprint_id for snapshot in group])
    print "expected_sprints = {}".format(expected_sprints)

    # then fill in any blanks by copying snapshots forward or backward if a group doesn't have one
    # for a specific sprint
    for i, group in enumerate(grouped_snapshots):
        if len(group) < len(expected_sprints):
            missing_sprints = expected_sprints.difference([snapshot.sprint_id for snapshot in group])
            for sprint_id in missing_sprints:
                # first look backwards for a snapshot from this sprint
                snapshot = _find_sprint_snapshot(sprint_id, reversed(grouped_snapshots[:i]))
                if not snapshot:
                    # if we couldn't find one, then look forwards
                    snapshot = _find_sprint_snapshot(sprint_id, grouped_snapshots[i+1:])
                if not snapshot:
                    print "Couldn't find snapshot to fill in gap"
                else:
                    group.append(snapshot)

    completed = [sum([snapshot.completed_points(committed=committed) for snapshot in group]) for group in grouped_snapshots]
    remaining = [sum([snapshot.remaining_points(committed=committed) for snapshot in group]) for group in grouped_snapshots]
    totals = [sum([snapshot.total_points(committed=committed) for snapshot in group]) for group in grouped_snapshots]

    stats = {
        'completed': completed,
        'remaining': remaining,
        'total': totals,
        'dates': [group[0].local_timestamp.strftime('%d/%m') for group in grouped_snapshots],
    }
    if totals[-1]:
        stats['completion'] = int((float(completed[-1]) / (totals[-1])) * 100)
    return stats


class Sprint(Base):
    __tablename__ = 'sprints'
    id = Column(Integer, primary_key=True)
    name = Column(String(256))
    finished = Column(DateTime)
    data = Column(postgresql.JSON)
    snapshots = relationship('Snapshot', backref='sprint')
    commitments = relationship('SprintCommitment', backref='sprint')
    locked = Column(Boolean)

    def __init__(self, name, finished=None, data=None):
        self.name = name
        self.finished = finished
        self.data = data

    @property
    def end_date(self):
        return self.finished.date()

    @property
    def last_snapshot(self):
        return Snapshot.query.filter(Snapshot.sprint_id == self.id).order_by(
            Snapshot.timestamp.desc()).first()

    def get_snapshots(self):
        all_snapshots = Snapshot.query.filter(Snapshot.sprint_id == self.id).order_by(
            Snapshot.timestamp).all()
        filtered_snapshots = []
        for i, snapshot in enumerate(all_snapshots):
            if (i+1) < len(all_snapshots) and all_snapshots[i+1].local_timestamp.date() == snapshot.local_timestamp.date():
                continue
            filtered_snapshots.append(snapshot)
        return filtered_snapshots


class Snapshot(Base):
    __tablename__ = 'snapshots'
    id = Column(Integer, primary_key=True)
    sprint_id = Column(Integer, ForeignKey('sprints.id'), nullable=True)
    issues = relationship('IssueSnapshot', backref='snapshot')
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow)

    def __init__(self, sprint):
        self.sprint = sprint

    @classmethod
    def get_most_recent_for_sprint(cls, sprint):
        return Snapshot.query.filter(Snapshot.sprint_id == sprint.id).order_by(
            Snapshot.timestamp.desc()).first()

    @classmethod
    def get_points_for_states(cls, snapshots, sprints, states=[], committed_only=False):
        cursor = IssueSnapshot.query.with_entities(func.sum(IssueSnapshot.points)).filter(
            IssueSnapshot.snapshot_id.in_(snapshots))
        if states:
            cursor = cursor.filter(IssueSnapshot.state.in_(states))
        if committed_only:
            commitments = [c.issue_id for c in SprintCommitment.query.filter(SprintCommitment.sprint_id.in_(sprints))]
            cursor = cursor.filter(IssueSnapshot.issue_id.in_(commitments))
        return cursor.scalar() or 0

    def total_points(self, committed=False):
        return Snapshot.get_points_for_states([self.id], [self.sprint_id], committed_only=committed)

    def completed_points(self, committed=False):
        return Snapshot.get_points_for_states([self.id], [self.sprint_id], settings.COMPLETE_STATES, committed_only=committed)

    def remaining_points(self, committed=False):
        incomplete_states = [state['id'] for state in settings.ISSUE_STATES if state['id'] not in settings.COMPLETE_STATES]
        return Snapshot.get_points_for_states([self.id], [self.sprint_id], incomplete_states, committed_only=committed)

    @property
    def local_timestamp(self):
        timezone = pytz.timezone(settings.TIMEZONE)
        return self.timestamp.astimezone(timezone)


class IssueSnapshot(Base):
    __tablename__ = 'issue_snapshots'
    id = Column(Integer, primary_key=True)
    repo = Column(String(1024), nullable=True)
    issue_id = Column(Integer)
    points = Column(Integer)
    data = Column(postgresql.JSON)
    snapshot_id = Column(Integer, ForeignKey('snapshots.id'), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    state = Column(Integer)

    def __init__(self, issue_id, repo, points, state, snapshot, data):
        self.issue_id = issue_id
        self.repo = repo
        self.points = points
        self.snapshot = snapshot
        self.data = data
        self.state = state

    @property
    def sprint_count(self):
        """
        The number of sprints this issue appeared in
        """
        cursor = IssueSnapshot.query.with_entities(
            func.count(distinct(Snapshot.sprint_id))).filter(
            IssueSnapshot.issue_id == self.issue_id, IssueSnapshot.repo == self.repo, IssueSnapshot.snapshot_id == Snapshot.id)
        return cursor.scalar() or 0

    @classmethod
    def get_all_snapshots_for_issue(cls, repo, issue_id):
        return IssueSnapshot.query.filter(
            IssueSnapshot.issue_id == issue_id, IssueSnapshot.repo == repo).order_by(
            IssueSnapshot.updated_at).options(joinedload('snapshot'))


class SprintCommitment(Base):
    __tablename__ = 'sprint_commitments'
    id = Column(Integer, primary_key=True)
    sprint_id = Column(Integer, ForeignKey('sprints.id'))
    issue_id = Column(Integer)
    created = Column(DateTime(timezone=True), default=datetime.utcnow)

    def __init__(self, sprint_id, issue_id):
        self.sprint_id = sprint_id
        self.issue_id = issue_id


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(1024))
    access_token = Column(String(1024))
    active = Column(Boolean, default=True)

    def __init__(self, username, access_token=None):
        self.username = username
        self.access_token = access_token

    def is_active(self):
        return self.active

    def get_id(self):
        return self.id

    def is_authenticated(self):
        return True
