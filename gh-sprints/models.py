from datetime import datetime

import pytz
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, distinct
from sqlalchemy.orm import relationship, joinedload
from sqlalchemy.dialects import postgresql
from sqlalchemy import func

from database import Base
import settings


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

    def get_stats(self, committed=False):
        snapshots = self.get_snapshots()
        completed = [snapshot.completed_points(committed=committed) for snapshot in snapshots]
        remaining = [snapshot.remaining_points(committed=committed) for snapshot in snapshots]
        totals = [snapshot.total_points(committed=committed) for snapshot in snapshots]
        stats = {
            'completed': completed,
            'remaining': remaining,
            'total': totals,
            'dates': [snapshot.local_timestamp.strftime('%d/%m') for snapshot in snapshots],
        }
        if totals[-1]:
            stats['completion'] = int((float(completed[-1]) / (totals[-1])) * 100)
        return stats


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

    def get_points_for_states(self, states=[], committed_only=False):
        cursor = IssueSnapshot.query.with_entities(func.sum(IssueSnapshot.points)).filter(
            IssueSnapshot.snapshot_id == self.id)
        if states:
            cursor = cursor.filter(IssueSnapshot.state.in_(states))
        if committed_only:
            commitments = [c.issue_id for c in SprintCommitment.query.filter(SprintCommitment.sprint_id == self.sprint_id)]
            cursor = cursor.filter(IssueSnapshot.issue_id.in_(commitments))
        return cursor.scalar() or 0

    def total_points(self, committed=False):
        return self.get_points_for_states(committed_only=committed)

    def completed_points(self, committed=False):
        return self.get_points_for_states(settings.COMPLETE_STATES, committed_only=committed)

    def remaining_points(self, committed=False):
        incomplete_states = [state['id'] for state in settings.ISSUE_STATES if state['id'] not in settings.COMPLETE_STATES]
        return self.get_points_for_states(incomplete_states, committed_only=committed)

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
