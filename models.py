from datetime import datetime

import pytz
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
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

    def get_points_for_states(self, states=[]):
        cursor = IssueSnapshot.query.with_entities(func.sum(IssueSnapshot.points)).filter(IssueSnapshot.snapshot_id == self.id)
        if states:
            cursor = cursor.filter(IssueSnapshot.state.in_(states))
        return cursor.scalar() or 0

    @property
    def total_points(self):
        return self.get_points_for_states()

    @property
    def completed_points(self):
        return self.get_points_for_states(settings.COMPLETE_STATES)

    @property
    def remaining_points(self):
        incomplete_states = [state['id'] for state in settings.ISSUE_STATES if state['id'] not in settings.COMPLETE_STATES]
        return self.get_points_for_states(incomplete_states)

    @property
    def local_timestamp(self):
        timezone = pytz.timezone(settings.TIMEZONE)
        return self.timestamp.astimezone(timezone)


class IssueSnapshot(Base):
    __tablename__ = 'issue_snapshots'
    id = Column(Integer, primary_key=True)
    issue_id = Column(Integer)
    points = Column(Integer)
    data = Column(postgresql.JSON)
    snapshot_id = Column(Integer, ForeignKey('snapshots.id'), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    state = Column(Integer)

    def __init__(self, issue_id, points, state, snapshot, data):
        self.issue_id = issue_id
        self.points = points
        self.snapshot = snapshot
        self.data = data
        self.state = state


class SprintCommitment(Base):
    __tablename__ = 'sprint_commitments'
    id = Column(Integer, primary_key=True)
    sprint_id = Column(Integer, ForeignKey('sprints.id'))
    issue_id = Column(Integer)
    created = Column(DateTime(timezone=True), default=datetime.utcnow)

    def __init__(self, sprint_id, issue_id):
        self.sprint_id = sprint_id
        self.issue_id = issue_id
